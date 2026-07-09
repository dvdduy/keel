from keel.domain.run import Run, RunStep
from keel.adapters.db.models import RunRecord, RunStepRecord
from keel.adapters.db.models import QualityResultRecord
from keel.application.quality.results import QualityResult
from keel.adapters.db.models import DatasetRecord
from keel.application.catalog.entry import CatalogEntry
from keel.application.specs.models import ContractColumn


def run_to_record(run: Run) -> RunRecord:
    return RunRecord(
        id=run.id,
        pipeline_id=run.pipeline_id,
        status=run.status,
        created_at=run.created_at,
        started_at=run.started_at,
        finished_at=run.finished_at,
        steps=[
            RunStepRecord(
                id=s.id,
                run_id=s.run_id,
                name=s.name,
                status=s.status,
                sequence=s.sequence,
                created_at=s.created_at,
            )
            for s in run.steps
        ],
        watermark=run.watermark,
    )


def record_to_run(record: RunRecord) -> Run:
    return Run(
        id=record.id,
        pipeline_id=record.pipeline_id,
        status=record.status,
        created_at=record.created_at,
        started_at=record.started_at,
        finished_at=record.finished_at,
        steps=[
            RunStep(
                id=s.id,
                run_id=s.run_id,
                name=s.name,
                status=s.status,
                sequence=s.sequence,
                created_at=s.created_at,
            )
            for s in record.steps
        ],
        watermark=record.watermark,
    )


def quality_result_to_record(result: QualityResult) -> QualityResultRecord:
    return QualityResultRecord(
        id=result.id,
        run_id=result.run_id,
        check_type=result.check_type,
        column=result.column,
        status=result.status,
        violations=result.violations,
        detail=result.detail,
        created_at=result.created_at,
    )


def record_to_quality_result(record: QualityResultRecord) -> QualityResult:
    return QualityResult(
        id=record.id,
        run_id=record.run_id,
        check_type=record.check_type,
        column=record.column,
        status=record.status,
        violations=record.violations,
        detail=record.detail,
        created_at=record.created_at,
    )


def catalog_entry_to_record(entry: CatalogEntry) -> DatasetRecord:
    return DatasetRecord(
        dataset=entry.dataset,
        pipeline_id=entry.pipeline_id,
        pipeline_name=entry.pipeline_name,
        team=entry.team,
        owner=entry.owner,
        columns=[column.model_dump(mode="json") for column in entry.columns],
        source_spec_id=entry.source_spec_id,
        updated_at=entry.updated_at,
    )


def record_to_catalog_entry(record: DatasetRecord) -> CatalogEntry:
    return CatalogEntry(
        dataset=record.dataset,
        pipeline_id=record.pipeline_id,
        pipeline_name=record.pipeline_name,
        team=record.team,
        owner=record.owner,
        columns=tuple(ContractColumn.model_validate(column) for column in record.columns),
        source_spec_id=record.source_spec_id,
        updated_at=record.updated_at,
    )
