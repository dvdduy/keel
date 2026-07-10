import os
import shutil
from pathlib import Path
from typing import Final

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from keel.config import Settings
from uuid import UUID, uuid4
from datetime import datetime, timezone
from keel.adapters.db.models import TeamRecord, PipelineRecord

NOW = datetime(2026, 7, 6, 12, 0, 0, tzinfo=timezone.utc)

POSTGRES_INTEGRATION_TESTS: Final = {
    "tests/test_dataset_catalog_repository.py::test_submit_projects_dataset_and_updates_same_row",
    "tests/test_run_pipeline.py::test_run_pipeline_persists_run_and_materializes_table",
    "tests/test_run_repository.py::test_get_unknown_returns_none",
    "tests/test_run_repository.py::test_run_round_trips",
    "tests/test_run_repository.py::test_triggering_same_key_twice_persists_one_successful_execution",
    "tests/test_spec_version_repository.py::test_breaking_override_persists_across_round_trip",
    "tests/test_spec_version_repository.py::test_heads_returns_latest_version_for_each_pipeline",
    "tests/test_spec_version_repository.py::test_platform_lineage_graph_builds_from_persisted_heads",
    "tests/test_spec_version_repository.py::test_same_parent_fork_is_rejected",
    "tests/test_spec_version_repository.py::test_submit_changed_spec_persists_child",
    "tests/test_spec_version_repository.py::test_submit_identical_twice_persists_one_row",
}

DBT_INTEGRATION_TESTS: Final = {
    "tests/test_dbt_transform.py::test_capture_manifest_includes_depends_on_edges",
    "tests/test_dbt_transform.py::test_capture_manifest_returns_model_and_source_nodes",
    "tests/test_dbt_transform.py::test_failing_dbt_test_reports_not_ok_with_failure_count",
    "tests/test_dbt_transform.py::test_model_sql_error_is_a_failed_result_not_an_exception",
    "tests/test_dbt_transform.py::test_passing_dbt_tests_report_ok",
    "tests/test_dbt_transform.py::test_run_materializes_marts_through_staging_chain",
    "tests/test_dbt_transform.py::test_run_materializes_staging_model_from_raw",
    "tests/test_dbt_transform.py::test_warn_severity_does_not_block_by_default",
    "tests/test_local_executor_dbt_transform.py::test_local_executor_runs_ingest_then_dbt_transform_end_to_end",
    "tests/test_local_executor_dbt_transform.py::test_marts_model_failure_is_a_failed_step_with_model_detail",
    "tests/test_local_executor_dbt_transform.py::test_transform_rollback_drops_all_materialized_models",
    "tests/test_local_executor_dbt_transform.py::test_transform_step_builds_target_and_upstream_models",
    "tests/test_local_executor_dbt_transform.py::test_transform_step_drops_materialization_on_test_failure",
}


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    missing_database_url = not os.environ.get("DATABASE_URL")
    missing_dbt = shutil.which("dbt") is None

    for item in items:
        nodeid = Path(item.nodeid).as_posix()
        requires_postgres = nodeid in POSTGRES_INTEGRATION_TESTS
        requires_dbt = nodeid in DBT_INTEGRATION_TESTS

        if not requires_postgres and not requires_dbt:
            continue

        item.add_marker(pytest.mark.integration)

        skip_reasons = []
        if requires_postgres and missing_database_url:
            skip_reasons.append("DATABASE_URL is unset")
        if requires_dbt and missing_dbt:
            skip_reasons.append("dbt is not on PATH")
        if skip_reasons:
            item.add_marker(
                pytest.mark.skip(
                    reason="integration prerequisites missing: " + ", ".join(skip_reasons)
                )
            )


@pytest.fixture
def session():
    settings = Settings()
    engine = create_engine(settings.database_url, future=True)
    connection = engine.connect()
    trans = connection.begin()
    s = Session(connection)
    try:
        yield s
    finally:
        s.close()
        trans.rollback()
        connection.close()


@pytest.fixture
def seeded_pipeline(session) -> UUID:
    team = TeamRecord(id=uuid4(), name="analytics", created_at=NOW)
    session.add(team)
    session.flush()
    pipeline = PipelineRecord(id=uuid4(), team_id=team.id, name="orders", created_at=NOW)
    session.add(pipeline)
    session.flush()
    return pipeline.id
