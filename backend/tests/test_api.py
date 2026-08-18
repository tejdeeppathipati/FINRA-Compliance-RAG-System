"""Exercise health, query failure modes, and source endpoints."""

import json
import shutil
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy.exc import SQLAlchemyError

from app.api import query as query_api
from app.api import sources as sources_api
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


def test_query_reports_database_unavailable(monkeypatch) -> None:
    class BrokenSession:
        def execute(self, *_args, **_kwargs):
            raise SQLAlchemyError("database offline")

    def broken_session():
        yield BrokenSession()

    # Keep this failure-mode test independent of whichever provider a developer
    # has configured in their local .env file.
    monkeypatch.setattr(query_api, "has_embedding_credentials", lambda: False)
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


def test_vector_query_requires_embedding_provider(monkeypatch) -> None:
    monkeypatch.setattr(query_api, "has_embedding_credentials", lambda: False)
    response = client.post(
        "/api/query",
        json={"question": "What does Rule 2090 require?", "retrieval_mode": "vector"},
    )
    assert response.status_code == 503
    assert response.json()["detail"] == (
        "Vector retrieval requires a configured embedding provider key."
    )


def test_sources_expose_manifest_and_local_snapshot_state(monkeypatch, tmp_path: Path) -> None:
    # Raw and normalized snapshots are intentionally ignored by Git, so CI cannot
    # rely on a developer's local data directory. Build the smallest fixture needed
    # to verify the endpoint's provenance-state behavior.
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    shutil.copy(
        Path(__file__).resolve().parents[2] / "data" / "source_manifest.yaml",
        data_dir / "source_manifest.yaml",
    )
    normalized_dir = data_dir / "normalized" / "finra-rule-2090"
    normalized_dir.mkdir(parents=True)
    (normalized_dir / "snapshot.json").write_text(
        json.dumps(
            {
                "latest_effective_date": "2012-07-09",
                "normalized_content_hash": "fixture-hash",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(sources_api, "_repo_root", lambda: tmp_path)

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
