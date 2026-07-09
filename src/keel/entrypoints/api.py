from __future__ import annotations

from typing import Annotated
from uuid import UUID

from fastapi import Body, FastAPI, HTTPException, Response
from fastapi.requests import Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session, sessionmaker

from keel.application.lineage.edges import build_lineage_graph
from keel.application.specs.compatibility import IncompatibleSpecError
from keel.application.specs.diagnostics import SpecError, SpecValidationError
from keel.application.specs.parser import SpecParseError, parse_pipeline_spec_yaml
from keel.entrypoints.dependencies import CatalogDep, RunsDep, SpecVersionsDep, SubmitSpecDep
from keel.entrypoints.schemas import (
    BreakingChangeOut,
    CatalogEntryOut,
    DiagnosticOut,
    LineageImpactOut,
    RunOut,
    SpecVersionOut,
)


def create_app(session_factory: sessionmaker[Session]) -> FastAPI:
    app = FastAPI(title="Keel Control Plane API")
    app.state.session_factory = session_factory

    @app.exception_handler(IncompatibleSpecError)
    async def incompatible_spec_handler(
        _request: Request,
        exc: IncompatibleSpecError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={
                "detail": {
                    "message": str(exc),
                    "breaking_changes": [
                        BreakingChangeOut.from_change(change).model_dump(mode="json")
                        for change in exc.report.breaking_changes
                    ],
                }
            },
        )

    @app.exception_handler(SpecValidationError)
    async def spec_validation_handler(
        _request: Request,
        exc: SpecValidationError,
    ) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={
                "detail": {
                    "diagnostics": [
                        DiagnosticOut.from_diagnostic(diagnostic).model_dump(mode="json")
                        for diagnostic in exc.diagnostics
                    ]
                }
            },
        )

    @app.exception_handler(SpecParseError)
    async def spec_parse_handler(_request: Request, exc: SpecParseError) -> JSONResponse:
        return JSONResponse(
            status_code=422,
            content={"detail": {"diagnostics": [{"loc": "(root)", "message": str(exc)}]}},
        )

    @app.exception_handler(SpecError)
    async def spec_error_handler(_request: Request, exc: SpecError) -> JSONResponse:
        return JSONResponse(status_code=422, content={"detail": {"message": str(exc)}})

    @app.post(
        "/pipelines/{pipeline_id}/specs",
        response_model=SpecVersionOut,
        status_code=201,
    )
    def submit_spec(
        pipeline_id: UUID,
        spec_yaml: Annotated[str, Body(media_type="application/x-yaml")],
        submit: SubmitSpecDep,
        response: Response,
        allow_breaking: bool = False,
    ) -> SpecVersionOut:
        spec = parse_pipeline_spec_yaml(spec_yaml)
        result = submit.submit(pipeline_id, spec, allow_breaking=allow_breaking)
        response.status_code = 201 if result.created else 200
        return SpecVersionOut.from_version(result.version)

    @app.get("/pipelines/{pipeline_id}/specs/head", response_model=SpecVersionOut)
    def get_head(pipeline_id: UUID, versions: SpecVersionsDep) -> SpecVersionOut:
        version = versions.head_for(pipeline_id)
        if version is None:
            raise HTTPException(status_code=404, detail="pipeline spec head not found")
        return SpecVersionOut.from_version(version)

    @app.get("/catalog", response_model=tuple[CatalogEntryOut, ...])
    def list_catalog(catalog: CatalogDep) -> tuple[CatalogEntryOut, ...]:
        return tuple(CatalogEntryOut.from_entry(entry) for entry in catalog.list())

    @app.get("/catalog/{dataset}", response_model=CatalogEntryOut)
    def get_catalog_entry(dataset: str, catalog: CatalogDep) -> CatalogEntryOut:
        entry = catalog.get(dataset)
        if entry is None:
            raise HTTPException(status_code=404, detail="catalog entry not found")
        return CatalogEntryOut.from_entry(entry)

    @app.get("/runs/{run_id}", response_model=RunOut)
    def get_run(run_id: UUID, runs: RunsDep) -> RunOut:
        run = runs.get(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found")
        return RunOut.from_run(run)

    @app.get("/lineage/{dataset}/impact", response_model=LineageImpactOut)
    def get_lineage_impact(dataset: str, versions: SpecVersionsDep) -> LineageImpactOut:
        graph = build_lineage_graph(versions.heads())
        if not graph.contains(dataset):
            raise HTTPException(status_code=404, detail="lineage dataset not found")
        return LineageImpactOut(dataset=dataset, impacted=tuple(sorted(graph.impacted_by(dataset))))

    return app
