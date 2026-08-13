from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.db.session import get_db_session
from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "finra-compliance-rag",
    }


def test_query_reports_database_unavailable() -> None:
    class BrokenSession:
        def execute(self, *_args, **_kwargs):
            raise SQLAlchemyError("database offline")

    def broken_session():
        yield BrokenSession()

    app.dependency_overrides[get_db_session] = broken_session
    try:
        response = client.post(
            "/api/query",
            json={
                "question": "What does Rule 2090 require?",
                "retrieval_mode": "hybrid",
                "top_k": 5,
            },
        )
    finally:
        app.dependency_overrides.clear()
    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Database is unavailable. Start PostgreSQL and apply migrations."
    )


def test_vector_query_requires_embedding_provider() -> None:
    response = client.post(
        "/api/query",
        json={"question": "What does Rule 2090 require?", "retrieval_mode": "vector"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Vector retrieval requires a configured OPENAI_API_KEY."
    )


def test_sources_expose_manifest_and_local_snapshot_state() -> None:
    response = client.get("/api/sources")
    assert response.status_code == 200
    sources = response.json()
    assert len(sources) == 13
    rule_2090 = next(item for item in sources if item["source_id"] == "finra-rule-2090")
    assert rule_2090["normalized"] is True
    assert rule_2090["latest_effective_date"] == "2012-07-09"


def test_unknown_source_returns_404() -> None:
    response = client.get("/api/sources/not-a-source")
    assert response.status_code == 404
