from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session, sessionmaker

from keel.adapters.db.dataset_catalog import SqlAlchemyDatasetCatalog
from keel.adapters.db.run_repository import SqlAlchemyRunRepository
from keel.adapters.db.spec_version_repository import SqlAlchemySpecVersionRepository
from keel.application.ports.catalog import DatasetCatalog
from keel.application.ports.run_repo import RunRepository
from keel.application.ports.spec_version_repo import SpecVersionRepository
from keel.application.use_cases.submit_spec import SubmitSpec


def session_provider(factory: sessionmaker[Session]) -> Iterator[Session]:
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def get_session(request: Request) -> Iterator[Session]:
    factory: sessionmaker[Session] = request.app.state.session_factory
    yield from session_provider(factory)


SessionDep = Annotated[Session, Depends(get_session)]


def get_spec_versions(session: SessionDep) -> SpecVersionRepository:
    return SqlAlchemySpecVersionRepository(session)


SpecVersionsDep = Annotated[SpecVersionRepository, Depends(get_spec_versions)]


def get_catalog(session: SessionDep) -> DatasetCatalog:
    return SqlAlchemyDatasetCatalog(session)


CatalogDep = Annotated[DatasetCatalog, Depends(get_catalog)]


def get_runs(session: SessionDep) -> RunRepository:
    return SqlAlchemyRunRepository(session)


RunsDep = Annotated[RunRepository, Depends(get_runs)]


def get_submit_spec(
    versions: SpecVersionsDep,
    catalog: CatalogDep,
) -> SubmitSpec:
    return SubmitSpec(versions=versions, catalog=catalog)


SubmitSpecDep = Annotated[SubmitSpec, Depends(get_submit_spec)]
