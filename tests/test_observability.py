import pytest
from fastapi.testclient import TestClient

from app.core.auth import Principal, require_bearer
from app.main import app


class StubPrometheusClient:
    async def query(self, query: str, *, at: float | None = None):
        return {
            "resultType": "vector",
            "result": [{"metric": {"job": "ouros-ai"}, "value": [at or 1, "1"]}],
        }

    async def query_range(
        self,
        query: str,
        *,
        start: float,
        end: float,
        step: float,
    ):
        return {
            "resultType": "matrix",
            "result": [
                {
                    "metric": {"job": "ouros-ai"},
                    "values": [[start, "1"], [end, "1"]],
                }
            ],
        }

    async def targets(self):
        return {
            "activeTargets": [
                {
                    "labels": {"job": "ouros-ai"},
                    "health": "up",
                    "lastError": "",
                }
            ]
        }


@pytest.fixture(autouse=True)
def authenticated_admin() -> None:
    async def principal() -> Principal:
        return Principal(
            subject="keycloak-admin",
            database_id=1,
            account_type="admin",
            roles=frozenset({"admin"}),
        )

    app.dependency_overrides[require_bearer] = principal
    yield
    app.dependency_overrides.pop(require_bearer, None)


def test_observability_query_uses_prometheus_client(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TestClient(app) as client:
        monkeypatch.setattr(app.state, "prometheus_client", StubPrometheusClient())
        response = client.get(
            "/v1/observability/query",
            params={"query": "up"},
            headers={"Authorization": "Bearer token"},
        )

    assert response.status_code == 200
    assert response.json()["result"][0]["metric"]["job"] == "ouros-ai"


def test_observability_targets_returns_target_health(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TestClient(app) as client:
        monkeypatch.setattr(app.state, "prometheus_client", StubPrometheusClient())
        response = client.get(
            "/v1/observability/targets",
            headers={"Authorization": "Bearer token"},
        )

    assert response.status_code == 200
    assert response.json()["activeTargets"][0]["health"] == "up"


def test_observability_range_rejects_oversized_window(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TestClient(app) as client:
        monkeypatch.setattr(app.state, "prometheus_client", StubPrometheusClient())
        response = client.get(
            "/v1/observability/query-range",
            params={
                "query": "up",
                "start": 0,
                "end": app.state.settings.prometheus_max_range_seconds + 1,
                "step": 15,
            },
            headers={"Authorization": "Bearer token"},
        )

    assert response.status_code == 400


def test_observability_is_unavailable_without_prometheus(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    with TestClient(app) as client:
        monkeypatch.setattr(app.state, "prometheus_client", None)
        response = client.get(
            "/v1/observability/query",
            params={"query": "up"},
            headers={"Authorization": "Bearer token"},
        )

    assert response.status_code == 503
