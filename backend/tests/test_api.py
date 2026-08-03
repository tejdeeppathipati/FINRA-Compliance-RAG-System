from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "service": "finra-compliance-rag",
    }


def test_query_is_explicitly_not_implemented() -> None:
    response = client.post(
        "/api/query",
        json={"question": "What does Rule 2090 require?", "retrieval_mode": "hybrid", "top_k": 5},
    )
    assert response.status_code == 501

