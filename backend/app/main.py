from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import automation_router, candidates_router, claims_router, discover_router, evidence_router, projects_router, queue_router
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

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5000",
        "http://127.0.0.1:5000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:5001",
        "http://127.0.0.1:5001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(projects_router)
app.include_router(automation_router)
app.include_router(candidates_router)
app.include_router(discover_router)
app.include_router(evidence_router)
app.include_router(claims_router)
app.include_router(queue_router)


@app.get("/health")
def healthcheck() -> dict[str, str]:
    return {"status": "ok", "database_url": DATABASE_URL}
