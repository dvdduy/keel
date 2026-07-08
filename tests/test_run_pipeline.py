from pathlib import Path

from keel.adapters.db.run_repository import SqlAlchemyRunRepository
from keel.adapters.warehouse.duckdb_warehouse import DuckDbWarehouse
from keel.application.use_cases.run_pipeline import RunPipeline
from keel.domain.run import RunStatus

FIXTURE = Path(__file__).parent / "fixtures" / "orders.csv"


def test_run_pipeline_persists_run_and_materializes_table(session, seeded_pipeline, tmp_path):
    repo = SqlAlchemyRunRepository(session)
    wh = DuckDbWarehouse(str(tmp_path / "w.duckdb"))
    uc = RunPipeline(runs=repo, warehouse=wh)

    run = uc.execute(seeded_pipeline, FIXTURE, "raw.orders")
    session.commit()

    assert repo.get(run.id).status == RunStatus.SUCCESS

    steps = repo.get(run.id).steps
    assert len(steps) == 1
    assert steps[0].status == RunStatus.SUCCESS
    assert steps[0].name == "ingest"

    assert wh.row_count("raw.orders") == 3
