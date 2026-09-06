"""Create the FastAPI application and register the public API routers."""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.health import router as health_router
from app.api.query import router as query_router
from app.api.sources import router as sources_router
from app.config import get_settings

app = FastAPI(
    title="FINRA Compliance RAG & Evaluation System",
    description="Source-grounded FINRA retrieval with evidence traceability and abstention.",
    version="0.1.0",
)
settings = get_settings()
if settings.cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            origin.strip()
            for origin in settings.cors_origins.split(",")
            if origin.strip()
        ],
        allow_credentials=False,
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
app.include_router(health_router, prefix="/api")
app.include_router(query_router, prefix="/api")
app.include_router(sources_router, prefix="/api")
