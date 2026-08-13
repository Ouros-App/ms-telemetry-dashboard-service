from fastapi.testclient import TestClient

from app.main import app


def test_health_has_request_id_and_does_not_require_databricks() -> None:
    with TestClient(app) as client:
        response = client.get("/health", headers={"X-Request-ID": "test-request"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["X-Request-ID"] == "test-request"


def test_catalog_excludes_disabled_dashboard() -> None:
    with TestClient(app) as client:
        response = client.get("/v1/dashboards")

    assert response.status_code == 200
    body = response.json()
    assert body == {"items": []}


def test_missing_dashboard_is_not_found() -> None:
    with TestClient(app) as client:
        response = client.get("/v1/dashboards/missing")

    assert response.status_code == 404
