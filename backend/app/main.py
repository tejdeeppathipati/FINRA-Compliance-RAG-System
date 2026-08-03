from fastapi import FastAPI

from app.api.health import router as health_router
from app.api.query import router as query_router

app = FastAPI(
    title="FINRA Compliance RAG & Evaluation System",
    description="Source-grounded FINRA retrieval with evidence traceability and abstention.",
    version="0.1.0",
)
app.include_router(health_router, prefix="/api")
app.include_router(query_router, prefix="/api")

