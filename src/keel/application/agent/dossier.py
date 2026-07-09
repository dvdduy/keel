from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID

from keel.application.incident.model import Incident
from keel.application.ports.platform_reader import PlatformReader


@dataclass(frozen=True)
class DatasetOwner:
    dataset: str
    team: str
    owner: str


@dataclass(frozen=True)
class RunView:
    run_id: UUID
    status: str
    failed_steps: tuple[str, ...]


@dataclass(frozen=True)
class IncidentDossier:
    subject: str
    pipeline_id: UUID
    team: str
    owner: str
    live_impacted: frozenset[str]
    impacted_owners: tuple[DatasetOwner, ...]
    failing_run: RunView | None
    spec_version_id: UUID | None
    impact_drifted: bool
    gaps: tuple[str, ...]


async def assemble_dossier(incident: Incident, reader: PlatformReader) -> IncidentDossier:
    gaps: list[str] = [
        "schema diffs unavailable: no schema diff read endpoint",
        "correlated changes unavailable: no spec history/diff read endpoint",
        "recent runs unavailable: no run listing read endpoint",
    ]

    try:
        live_impacted = await reader.lineage_impact(incident.subject)
    except Exception as exc:
        live_impacted = frozenset()
        gaps.append(f"could not gather live lineage impact for {incident.subject}: {exc}")

    impacted_owners: list[DatasetOwner] = []
    for dataset in sorted(live_impacted):
        try:
            owner = await reader.catalog_show(dataset)
        except Exception as exc:
            owner = None
            gaps.append(f"could not gather catalog owner for {dataset}: {exc}")

        if owner is None:
            gaps.append(f"catalog owner missing for impacted dataset {dataset}")
        else:
            impacted_owners.append(owner)

    failing_run: RunView | None = None
    if incident.run_id is not None:
        try:
            failing_run = await reader.run_show(incident.run_id)
        except Exception as exc:
            gaps.append(f"could not gather failing run {incident.run_id}: {exc}")
        if failing_run is None:
            gaps.append(f"failing run {incident.run_id} not found")

    try:
        spec_version_id = await reader.spec_head(incident.pipeline_id)
    except Exception as exc:
        spec_version_id = None
        gaps.append(f"could not gather spec head for pipeline {incident.pipeline_id}: {exc}")
    if spec_version_id is None:
        gaps.append(f"spec head missing for pipeline {incident.pipeline_id}")

    return IncidentDossier(
        subject=incident.subject,
        pipeline_id=incident.pipeline_id,
        team=incident.team,
        owner=incident.owner,
        live_impacted=live_impacted,
        impacted_owners=tuple(impacted_owners),
        failing_run=failing_run,
        spec_version_id=spec_version_id,
        impact_drifted=live_impacted != incident.impacted,
        gaps=tuple(gaps),
    )
