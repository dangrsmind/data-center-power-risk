from app.api.routes.automation import router as automation_router
from app.api.routes.candidates import router as candidates_router
from app.api.routes.discover import router as discover_router
from app.api.routes.discovered_sources import router as discovered_sources_router
from app.api.routes.ingestion import claims_router, evidence_router, queue_router
from app.api.routes.projects import router as projects_router

__all__ = [
    "automation_router",
    "candidates_router",
    "claims_router",
    "discover_router",
    "discovered_sources_router",
    "evidence_router",
    "projects_router",
    "queue_router",
]
