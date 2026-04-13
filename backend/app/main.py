from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.routes import projects_router
from app.core.db import DATABASE_URL, create_db_and_tables


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_db_and_tables()
    yield


app = FastAPI(
    title="Data Center Power Risk Backend",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(projects_router)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok", "database_url": DATABASE_URL}
