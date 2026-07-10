from __future__ import annotations

import asyncio
import tempfile
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import UUID

from keel.adapters.executor.duckdb_step_handler import DuckDbStepHandler
from keel.adapters.executor.local import LocalExecutor
from keel.adapters.transform.dbt_runner import DbtTransformRunner
from keel.adapters.warehouse.duckdb_warehouse import DuckDbWarehouse
from keel.application.agent.diagnose import Diagnosis, diagnose
from keel.application.agent.dossier import DatasetOwner, IncidentDossier, RunView, assemble_dossier
from keel.application.execution.plan import ExecutionPlan, IngestStep, QualityGateStep
from keel.application.incident.detect import detect_incident
from keel.application.incident.group import IncidentGroup, group_incidents
from keel.application.incident.model import Incident, IncidentContext
from keel.application.lineage.edges import LineageEdge
from keel.application.lineage.graph import LineageGraph
from keel.application.quality.results import QualityResult
from keel.application.slo.evaluate import evaluate_slo
from keel.application.slo.model import Slo, SloObservation, SloOutcome, SloStatus
from keel.application.specs.compatibility import BreakingChange, IncompatibleSpecError
from keel.application.specs.models import PipelineSpec, QualityCheckSpec, QualityCheckType
from keel.application.specs.parser import parse_pipeline_spec_file
from keel.application.specs.versioning import SpecVersion
from keel.application.use_cases.submit_spec import SubmitSpec
from keel.domain.run import Run, RunStatus

ROOT = Path(__file__).resolve().parents[1]
SEED_SPEC = ROOT / "tests" / "fixtures" / "orders_raw.yaml"
TRANSFORM_PROJECT = ROOT / "transform"
NOW = datetime(2026, 7, 10, 12, 0, tzinfo=UTC)
PIPELINE_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
DOWNSTREAM_DATASETS = (
    "main.orders_stg",
    "main.revenue_daily",
    "main.customer_ltv",
    "main.fulfillment_health",
    "main.executive_revenue",
)


@dataclass(frozen=True)
class SubmittedGraph:
    pipeline_id: UUID
    original: PipelineSpec
    proposed: PipelineSpec
    graph: LineageGraph
    downstream: tuple[str, ...]


@dataclass(frozen=True)
class RejectedChange:
    changes: tuple[BreakingChange, ...]
    head_unchanged: bool


@dataclass(frozen=True)
class OverrideResult:
    version: SpecVersion
    audited: bool


@dataclass(frozen=True)
class ContainmentResult:
    run: Run
    quality_results: tuple[QualityResult, ...]
    evaluation_status: SloStatus
    incidents: tuple[Incident, ...]
    groups: tuple[IncidentGroup, ...]
    dossier: IncidentDossier
    diagnosis: Diagnosis

    @property
    def upstream_incident(self) -> Incident:
        return next(incident for incident in self.incidents if incident.subject == "raw.orders")

    @property
    def top_hypothesis_kind(self) -> str:
        return self.diagnosis.hypotheses[0].kind


@dataclass(frozen=True)
class DemoResult:
    graph: SubmittedGraph
    rejection: RejectedChange
    override: OverrideResult
    containment: ContainmentResult


@dataclass
class InMemorySpecVersionRepository:
    history: dict[UUID, list[SpecVersion]] = field(default_factory=lambda: defaultdict(list))

    def head_for(self, pipeline_id: UUID) -> SpecVersion | None:
        versions = self.history[pipeline_id]
        return versions[-1] if versions else None

    def heads(self) -> tuple[SpecVersion, ...]:
        return tuple(versions[-1] for versions in self.history.values() if versions)

    def add(self, version: SpecVersion) -> None:
        self.history[version.pipeline_id].append(version)


@dataclass
class InMemoryRunRepository:
    added: list[Run] = field(default_factory=list)

    def add(self, run: Run) -> None:
        self.added.append(run)


@dataclass
class InMemoryQualityResultRepository:
    added: list[QualityResult] = field(default_factory=list)

    def add(self, result: QualityResult) -> None:
        self.added.append(result)

    def for_run(self, run_id: UUID) -> tuple[QualityResult, ...]:
        return tuple(result for result in self.added if result.run_id == run_id)


@dataclass
class DemoClock:
    current: datetime = NOW

    def __call__(self) -> datetime:
        value = self.current
        self.current = self.current + timedelta(seconds=1)
        return value


@dataclass
class DemoPlatformReader:
    graph: LineageGraph
    run: Run
    head: SpecVersion

    async def lineage_impact(self, dataset: str) -> frozenset[str]:
        return self.graph.impacted_by(dataset)

    async def catalog_show(self, dataset: str) -> DatasetOwner | None:
        return DatasetOwner(
            dataset=dataset,
            team="analytics" if dataset.startswith("main.") else "growth",
            owner="analytics-oncall@keel.dev",
        )

    async def run_show(self, run_id: UUID) -> RunView | None:
        if run_id != self.run.id:
            return None

        failed_steps = tuple(
            f"quality:{step.name.removeprefix('quality_')}"
            for step in self.run.steps
            if step.status == RunStatus.FAILED and step.name.startswith("quality")
        )
        return RunView(run_id=run_id, status=self.run.status.value, failed_steps=failed_steps)

    async def spec_head(self, pipeline_id: UUID) -> UUID | None:
        if pipeline_id != self.head.pipeline_id:
            return None

        return self.head.version_id


def submit_spec_graph(repository: InMemorySpecVersionRepository) -> SubmittedGraph:
    original = parse_pipeline_spec_file(SEED_SPEC)
    proposed = original.model_copy(
        update={
            "contract": tuple(column for column in original.contract if column.name != "amount")
        }
    )

    SubmitSpec(repository).submit(PIPELINE_ID, original)
    graph = LineageGraph.from_edges(
        LineageEdge("raw.orders", downstream) for downstream in DOWNSTREAM_DATASETS
    )

    return SubmittedGraph(
        pipeline_id=PIPELINE_ID,
        original=original,
        proposed=proposed,
        graph=graph,
        downstream=DOWNSTREAM_DATASETS,
    )


def submit_breaking_change(
    graph: SubmittedGraph,
    repository: InMemorySpecVersionRepository,
) -> RejectedChange:
    head_before = repository.head_for(graph.pipeline_id)

    try:
        SubmitSpec(repository).submit(graph.pipeline_id, graph.proposed)
    except IncompatibleSpecError as exc:
        head_after = repository.head_for(graph.pipeline_id)
        return RejectedChange(
            changes=exc.report.breaking_changes,
            head_unchanged=head_before == head_after,
        )

    raise AssertionError("breaking change was accepted without --allow-breaking")


def submit_override(
    graph: SubmittedGraph,
    repository: InMemorySpecVersionRepository,
) -> OverrideResult:
    result = SubmitSpec(repository).submit(
        graph.pipeline_id,
        graph.proposed,
        allow_breaking=True,
    )
    return OverrideResult(version=result.version, audited=result.version.breaking_override)


def run_downstream_containment(
    *,
    graph: SubmittedGraph,
    override: OverrideResult,
    workspace: Path,
) -> ContainmentResult:
    source = workspace / "orders_without_amount.csv"
    source.write_text(
        "order_id,created_at\n" "1,2026-07-10T11:00:00Z\n" "2,2026-07-10T11:01:00Z\n",
        encoding="utf-8",
    )

    warehouse_path = workspace / "warehouse.duckdb"
    quality_results = InMemoryQualityResultRepository()
    clock = DemoClock()
    handler = DuckDbStepHandler(
        warehouse_factory=lambda: DuckDbWarehouse(str(warehouse_path)),
        transform_runner=DbtTransformRunner(
            project_dir=TRANSFORM_PROJECT,
            warehouse_path=str(warehouse_path),
        ),
        results=quality_results,
        clock=clock,
    )
    executor = LocalExecutor(
        runs=InMemoryRunRepository(),
        handler=handler,
        clock=clock,
    )

    run = executor.execute(
        graph.pipeline_id,
        ExecutionPlan(
            steps=(
                IngestStep(
                    key="ingest_orders_raw",
                    depends_on=frozenset(),
                    source_path=str(source),
                    destination="raw.orders",
                ),
                QualityGateStep(
                    key="quality_amount",
                    depends_on=frozenset({"ingest_orders_raw"}),
                    table="raw.orders",
                    checks=(
                        QualityCheckSpec(
                            type=QualityCheckType.NOT_NULL,
                            column="amount",
                        ),
                    ),
                ),
            )
        ),
    )

    evaluation = evaluate_slo(
        slo=Slo(objective=0.95, window=timedelta(hours=1)),
        observations=(
            SloObservation(at=NOW - timedelta(minutes=20), outcome=SloOutcome.GOOD),
            SloObservation(at=NOW - timedelta(minutes=5), outcome=SloOutcome.BAD),
        ),
        now=NOW,
    )
    incidents = tuple(
        incident
        for incident in (
            detect_incident(
                slo_name="quality",
                evaluation=evaluation,
                context=IncidentContext(
                    subject=subject,
                    pipeline_id=graph.pipeline_id,
                    team="growth",
                    owner="duy@keel.dev",
                    run=run,
                    graph=graph.graph,
                ),
                now=NOW,
                new_id=UUID(int=index),
            )
            for index, subject in enumerate(("raw.orders", *graph.downstream), start=1)
        )
        if incident is not None
    )
    groups = group_incidents(incidents, graph.graph)
    assert len(groups) == 1

    upstream = next(incident for incident in incidents if incident.subject == "raw.orders")
    reader = DemoPlatformReader(graph=graph.graph, run=run, head=override.version)
    dossier = asyncio.run(assemble_dossier(upstream, reader))
    diagnosis = diagnose(dossier)

    return ContainmentResult(
        run=run,
        quality_results=quality_results.for_run(run.id),
        evaluation_status=evaluation.status,
        incidents=incidents,
        groups=groups,
        dossier=dossier,
        diagnosis=diagnosis,
    )


def run_demo(
    *, workspace_factory: Callable[[], tempfile.TemporaryDirectory[str]] | None = None
) -> DemoResult:
    repository = InMemorySpecVersionRepository()
    graph = submit_spec_graph(repository)
    rejection = submit_breaking_change(graph, repository)
    override = submit_override(graph, repository)

    factory = workspace_factory or tempfile.TemporaryDirectory
    with factory() as workspace_name:
        containment = run_downstream_containment(
            graph=graph,
            override=override,
            workspace=Path(workspace_name),
        )

    return DemoResult(
        graph=graph,
        rejection=rejection,
        override=override,
        containment=containment,
    )


def main() -> None:
    result = run_demo()

    print("1. Submit a spec graph")
    print(
        "   raw.orders feeds "
        + ", ".join(result.graph.downstream)
        + f" ({len(result.graph.downstream)} downstream datasets)"
    )
    print()

    print("2. Submit a breaking upstream contract change")
    for change in result.rejection.changes:
        print(f"   rejected: {change.kind.value} on {change.column} - {change.detail}")
    print(f"   nothing shipped: {result.rejection.head_unchanged}")
    print()

    print("3. Resubmit with --allow-breaking")
    print(f"   audited override: {result.override.audited}")
    print(f"   version: {result.override.version.version_id}")
    print()

    print("4. Run downstream and contain the blast radius")
    quality = result.containment.quality_results[0]
    print(f"   quality gate: {quality.status.value} ({quality.detail})")
    print(f"   quarantined: run ended {result.containment.run.status.value}")
    print(f"   SLO: {result.containment.evaluation_status.value}")
    print(f"   incidents grouped: {len(result.containment.groups)}")
    print("   assert len(incidents) == 1 group")
    print()

    print("5. Diagnose the incident")
    top = result.containment.diagnosis.hypotheses[0]
    print(f"   RCA subject: {result.containment.diagnosis.subject}")
    print(f"   top hypothesis: {top.kind} ({top.status.value})")
    print(f"   evidence: {'; '.join(top.evidence)}")


if __name__ == "__main__":
    main()
