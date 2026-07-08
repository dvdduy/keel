from keel.domain.run import Run, RunStep
from keel.adapters.db.models import RunRecord, RunStepRecord


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
