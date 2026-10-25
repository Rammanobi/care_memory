"""Lane G: Core API app. Run: uvicorn cm.api.main:app --port 8080 (CORS for the Vite dev server)."""

from __future__ import annotations

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import psycopg
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from cm.api import firebase_auth
from cm.api.body_limit import BodyLimitMiddleware
from cm.api.deps import ApiError, problem_response
from cm.api.routers import (
    admin,
    auth,
    consent,
    dashboard,
    ops,
    patient_requests,
    patients,
    portal,
    portal_answers,
    query,
    review,
    stream,
    tasks,
    templates,
    webhooks,
)
from cm.api.web import AllowedHostsMiddleware, mount_spa, parse_hosts
from cm.contracts.api import HealthOut
from cm.core import budget_pg, clock, db
from cm.core import tasks as core_tasks
from cm.core.config import load_settings
from cm.core.logging import get_logger
from cm.uploads.validate import max_bytes

log = get_logger()


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    try:
        with db.transaction() as conn:
            at = clock.load_pin(conn)
        log.info("clock pinned", pinned=bool(at))
    except Exception as exc:  # the API still boots without a database (healthz)
        log.warning("db not ready at startup", error=type(exc).__name__)
    try:
        budget_pg.install_governor()  # DB-backed AI budget governor (spend in cm.task_runs)
    except Exception as exc:
        log.warning("budget governor not installed", error=type(exc).__name__)
    if core_tasks.start_local_worker():  # dev only: TASKS_MODE=local
        log.info("local task worker started")
    yield
    core_tasks.stop_local_worker()
    db.close_pool()


def create_app() -> FastAPI:
    settings = load_settings()
    firebase_auth.check_config()  # AUTH_MODE=firebase without FIREBASE_PROJECT_ID refuses to start
    app = FastAPI(title="CareMemory", lifespan=lifespan)
    hosts = parse_hosts(os.environ.get("CM_ALLOWED_HOSTS"))
    if hosts:
        app.add_middleware(AllowedHostsMiddleware, allowed=hosts)
    # upload size is enforced before FastAPI parses (and spools) the multipart body
    app.add_middleware(BodyLimitMiddleware, paths=("/portal/documents",), limit=max_bytes)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=firebase_auth.mode() != "firebase",  # firebase: bearer only, no cookies
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-CM-Client"],
    )

    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return problem_response(exc.status, exc.title, exc.code, exc.detail)

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        return problem_response(exc.status_code, str(exc.detail), "http_error")

    @app.exception_handler(RequestValidationError)
    async def _invalid(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = ", ".join(".".join(str(x) for x in e["loc"][1:]) for e in exc.errors())
        return problem_response(422, "Invalid request", "validation_error", fields)

    @app.exception_handler(psycopg.DataError)
    async def _bad_data(_: Request, exc: psycopg.DataError) -> JSONResponse:
        # e.g. a NUL byte in text, or a number outside the database range: the client's fault, not a 500.
        log.warning("rejected value the database cannot store", error=type(exc).__name__)
        return problem_response(
            422, "Invalid request", "invalid_value", "a value is not acceptable"
        )

    @app.get("/healthz", response_model=HealthOut, response_model_exclude_none=True)
    def healthz() -> HealthOut:
        return HealthOut(status="ok")

    @app.get("/readyz", response_model=HealthOut, response_model_exclude_none=True)
    def readyz() -> JSONResponse | HealthOut:
        ok = db.ping()
        if not ok:
            return JSONResponse(status_code=503, content={"status": "down", "db": False})
        return HealthOut(status="ok", db=True)

    for r in (
        auth,
        review,
        patient_requests,
        patients,
        dashboard,
        query,
        admin,
        consent,
        templates,
        portal,
    portal_answers,
        ops,
        stream,
        webhooks,
        tasks,
    ):
        app.include_router(r.router)
    mount_spa(app)  # last: the SPA catch-all must not shadow API routes
    return app


app = create_app()
