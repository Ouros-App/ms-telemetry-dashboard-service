"""Unit and integration tests for Admin AI Metrics & Corporate Farms governance."""

from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from bson import Decimal128
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials
from fastapi.testclient import TestClient

from app.core.auth import (
    Principal,
    require_admin_bearer,
    require_corporate_or_admin_bearer,
)
from app.core.config import settings
from app.main import app
from app.providers.analytics import AnalyticsDashboardProvider
from app.repositories.analytics import (
    AnalyticsQueryError,
    AnalyticsRepository,
    AnalyticsUnavailable,
)
from app.services.admin_metrics import AdminMetricsService
from app.services.user_dashboard import UserDashboardService


class MockCollection:
    def __init__(self, documents):
        self.documents = documents

    def find_one(self, selector):
        return next(
            (d for d in self.documents if d.get("_id") == selector["_id"]), None
        )

    def find(self, selector):
        def matches(item):
            for key, expected in selector.items():
                if isinstance(expected, dict) and "$in" in expected:
                    if item.get(key) not in expected["$in"]:
                        return False
                elif item.get(key) != expected:
                    return False
            return True

        return (d for d in self.documents if matches(d))


class MockMongoClient:
    def __init__(self):
        self.admin = self
        self.closed = False

    def command(self, _name):
        return {"ok": 1}

    def close(self):
        self.closed = True


def make_principal(
    account_type: str,
    *,
    farm_id: int | None = None,
    enterprise_id: int | None = None,
    roles: set[str] | None = None,
) -> Principal:
    effective_roles = roles if roles is not None else {account_type}
    return Principal(
        subject=f"sub-{account_type}",
        database_id=1,
        account_type=account_type,
        roles=frozenset(effective_roles),
        farm_id=farm_id,
        enterprise_id=enterprise_id,
    )


def build_repository(*, with_ai_sessions: bool = False) -> AnalyticsRepository:
    now = datetime.now(UTC)
    run = "admin-metrics-run"
    rows = [
        {
            "dataset": "dim_farm",
            "_sync_run": run,
            "farm_id": 101,
            "enterprise_id": 99,
            "farm_name": "Granja Primavera",
            "manager_name": "Carlos Silva",
            "state": "GO",
            "city": "Rio Verde",
            "regional_management": "Centro-Oeste 1",
            "chickens_now": 50000,
            "poultry_capacity": 60000,
        },
        {
            "dataset": "dim_farm",
            "_sync_run": run,
            "farm_id": 201,
            "enterprise_id": 88,
            "farm_name": "Granja Sulista",
            "manager_name": "Roberto Sul",
            "state": "PR",
            "city": "Cascavel",
            "regional_management": "Sul 1",
            "chickens_now": 40000,
            "poultry_capacity": 50000,
        },
        {
            "dataset": "fact_lot",
            "_sync_run": run,
            "farm_id": 101,
            "enterprise_id": 99,
            "delivery_date": datetime(now.year, 4, 15, tzinfo=UTC),
            "received_chickens": 50000,
            "cost": Decimal128("1200000.00"),
        },
        {
            "dataset": "fact_lot",
            "_sync_run": run,
            "farm_id": 201,
            "enterprise_id": 88,
            "delivery_date": datetime(now.year, 4, 15, tzinfo=UTC),
            "received_chickens": 40000,
            "cost": Decimal128("900000.00"),
        },
    ]

    if with_ai_sessions:
        rows.extend(
            [
                {
                    "dataset": "fact_ai_session",
                    "_sync_run": run,
                    "session_id": "db-sess-1",
                    "user_id": 10,
                    "user_name": "Vera Admin",
                    "account_type": "admin",
                    "enterprise_id": 99,
                    "farm_id": None,
                    "model": "openai/gpt-oss-120b",
                    "prompt_tokens": 1000,
                    "completion_tokens": 1000,
                    "total_tokens": 2000,
                    "cost_brl": Decimal128("2.00"),
                    "latency_ms": 60,
                    "accuracy_rate": 99.0,
                    "status": "success",
                    "created_at": "2026-10-28T10:00:00Z",
                    "period": "0-50k",
                },
                {
                    "dataset": "fact_ai_session",
                    "_sync_run": run,
                    "session_id": "db-sess-2",
                    "user_id": 20,
                    "user_name": "Gestor Sul",
                    "account_type": "company_employee",
                    "enterprise_id": 88,
                    "farm_id": 201,
                    "model": "openai/gpt-oss-20b",
                    "prompt_tokens": 500,
                    "completion_tokens": 500,
                    "total_tokens": 1000,
                    "cost_brl": Decimal128("1.00"),
                    "latency_ms": 130,
                    "accuracy_rate": 97.5,
                    "status": "success",
                    "created_at": "2026-10-28T11:00:00Z",
                    "period": "50k-75k",
                },
            ]
        )

    state = [
        {
            "_id": "production_to_mongodb_poc",
            "status": "success",
            "run_id": run,
            "last_success_at": now - timedelta(minutes=2),
        }
    ]

    repo = object.__new__(AnalyticsRepository)
    repo._retry_after = 0.0
    repo.retry_backoff_seconds = 0.0
    repo._client = MockMongoClient()
    repo._database = {
        "poc_sync_state": MockCollection(state),
        "poc_analytics_rows": MockCollection(rows),
        "poc_farm_monthly": MockCollection([]),
        "poc_metric_buckets": MockCollection([]),
    }
    return repo


@pytest.fixture(autouse=True)
def setup_services():
    repo = build_repository(with_ai_sessions=False)
    app.state.analytics_repository = repo
    app.state.admin_metrics_service = AdminMetricsService(repo)
    app.state.user_dashboard_service = UserDashboardService(
        AnalyticsDashboardProvider(repo)
    )
    yield
    app.dependency_overrides.clear()


@pytest.mark.parametrize(
    "endpoint",
    [
        "/v1/admin/ai-metrics/kpis",
        "/v1/admin/ai-metrics/charts/token-spend",
        "/v1/admin/ai-metrics/charts/latency-distribution",
        "/v1/admin/ai-metrics/sessions",
    ],
)
@pytest.mark.parametrize(
    "non_admin_principal",
    [
        make_principal("company_employee", enterprise_id=99),
        make_principal("farm_owner", farm_id=101),
    ],
)
def test_non_admin_profiles_receive_403_on_admin_ai_metrics(
    endpoint: str, non_admin_principal: Principal
) -> None:
    app.dependency_overrides[require_admin_bearer] = lambda: non_admin_principal
    client = TestClient(app)

    response = client.get(endpoint)
    assert response.status_code == 403
    assert "administradores" in response.json()["detail"].lower()


@pytest.mark.asyncio
async def test_require_admin_bearer_token_validation() -> None:
    cred = HTTPAuthorizationCredentials(scheme="Bearer", credentials="tok")
    emp_claims = {
        "sub": "emp-1",
        "database_id": 10,
        "account_type": "company_employee",
        "enterprise_id": 99,
        "realm_access": {"roles": ["company_employee"]},
    }
    admin_claims = {
        "sub": "adm-1",
        "database_id": 1,
        "account_type": "admin",
        "realm_access": {"roles": ["admin"]},
    }
    with (
        patch.object(settings, "keycloak_issuer_url", "https://issuer.example"),
        patch.object(settings, "keycloak_audience", "ms-telemetry-dashboard-service"),
        patch("app.core.auth._decode_keycloak_token", return_value=emp_claims),
        pytest.raises(HTTPException) as exc_info,
    ):
        await require_admin_bearer(cred)
    assert exc_info.value.status_code == 403

    with (
        patch.object(settings, "keycloak_issuer_url", "https://issuer.example"),
        patch.object(settings, "keycloak_audience", "ms-telemetry-dashboard-service"),
        patch("app.core.auth._decode_keycloak_token", return_value=admin_claims),
    ):
        principal = await require_admin_bearer(cred)
        assert principal.account_type == "admin"

        corp_principal = await require_corporate_or_admin_bearer(cred)
        assert corp_principal.account_type == "admin"


def test_admin_can_fetch_ai_metrics_kpis_figma_contract() -> None:
    app.dependency_overrides[require_admin_bearer] = lambda: make_principal("admin")
    client = TestClient(app)

    response = client.get("/v1/admin/ai-metrics/kpis")
    assert response.status_code == 200
    data = response.json()

    assert data["token_spend"]["formatted"] == "R$ 15.11M"
    assert data["token_spend"]["value"] == 15_110_000.0
    assert data["unit_cost"]["formatted"] == "R$ 0.94"
    assert data["unit_cost"]["value"] == 0.94
    assert data["active_users"]["formatted"] == "104.728"
    assert data["active_users"]["value"] == 104_728.0


def test_admin_can_fetch_token_spend_and_latency_charts() -> None:
    app.dependency_overrides[require_admin_bearer] = lambda: make_principal("admin")
    client = TestClient(app)

    spend_res = client.get("/v1/admin/ai-metrics/charts/token-spend")
    assert spend_res.status_code == 200
    spend_items = spend_res.json()["items"]
    assert len(spend_items) == 7
    assert spend_items[0]["period"] == "0-50k"
    assert spend_items[3]["period"] == "100k-125k"
    assert spend_items[3]["current_year_cost_brl"] == 24000.0

    latency_res = client.get("/v1/admin/ai-metrics/charts/latency-distribution")
    assert latency_res.status_code == 200
    latency_items = latency_res.json()["items"]
    assert len(latency_items) == 7
    assert latency_items[0]["bucket"] == "0-50k"
    assert latency_items[3]["avg_cost_brl"] == 0.94


def test_admin_can_fetch_and_filter_midas_sessions() -> None:
    app.dependency_overrides[require_admin_bearer] = lambda: make_principal("admin")
    client = TestClient(app)

    res = client.get("/v1/admin/ai-metrics/sessions?page=1&limit=2")
    assert res.status_code == 200
    payload = res.json()
    assert payload["total"] == 4
    assert payload["page"] == 1
    assert payload["limit"] == 2
    assert len(payload["items"]) == 2
    assert payload["items"][0]["session_id"] == "midas-sess-001"

    # Search filter
    res_search = client.get("/v1/admin/ai-metrics/sessions?search=Vera")
    assert res_search.status_code == 200
    assert res_search.json()["total"] == 1
    assert res_search.json()["items"][0]["user_name"] == "Vera Marcelinha"

    # Model filter
    res_model = client.get("/v1/admin/ai-metrics/sessions?model=openai/gpt-oss-20b")
    assert res_model.status_code == 200
    assert res_model.json()["total"] == 1

    # Enterprise filter
    res_ent = client.get("/v1/admin/ai-metrics/sessions?enterprise_id=2")
    assert res_ent.status_code == 200
    assert res_ent.json()["total"] == 1
    assert res_ent.json()["items"][0]["user_name"] == "Roberto Almeida"


def test_admin_ai_metrics_populated_from_mongodb_snapshot(monkeypatch: pytest.MonkeyPatch) -> None:
    repo = build_repository(with_ai_sessions=True)
    monkeypatch.setattr(app.state, "analytics_repository", repo)
    monkeypatch.setattr(app.state, "admin_metrics_service", AdminMetricsService(repo))
    app.dependency_overrides[require_admin_bearer] = lambda: make_principal("admin")
    client = TestClient(app)

    kpis = client.get("/v1/admin/ai-metrics/kpis").json()
    assert kpis["token_spend"]["value"] == 3.0
    assert kpis["unit_cost"]["value"] == 1.0  # R$ 3.00 / 3k tokens = R$ 1.00/1k
    assert kpis["active_users"]["value"] == 2.0

    spend = client.get("/v1/admin/ai-metrics/charts/token-spend").json()
    assert len(spend["items"]) == 2

    latency = client.get("/v1/admin/ai-metrics/charts/latency-distribution").json()
    assert len(latency["items"]) == 7
    total_counted = sum(b["count"] for b in latency["items"])
    assert total_counted == 2

    sessions = client.get("/v1/admin/ai-metrics/sessions?enterprise_id=99").json()
    assert sessions["total"] == 1
    assert sessions["items"][0]["session_id"] == "db-sess-1"


@pytest.mark.parametrize(
    "endpoint",
    [
        "/v1/admin/ai-metrics/kpis",
        "/v1/admin/ai-metrics/charts/token-spend",
        "/v1/admin/ai-metrics/charts/latency-distribution",
        "/v1/admin/ai-metrics/sessions",
    ],
)
def test_admin_ai_metrics_routes_map_service_errors_to_503(endpoint: str, monkeypatch: pytest.MonkeyPatch) -> None:
    class FailingAdminService:
        async def get_kpis(self, **_kwargs):
            raise AnalyticsUnavailable("offline")

        async def get_token_spend_chart(self, **_kwargs):
            raise AnalyticsQueryError("bad query")

        async def get_latency_distribution_chart(self, **_kwargs):
            raise AnalyticsUnavailable("offline")

        async def get_sessions(self, **_kwargs):
            raise AnalyticsQueryError("bad query")

    monkeypatch.setattr(app.state, "admin_metrics_service", FailingAdminService())
    app.dependency_overrides[require_admin_bearer] = lambda: make_principal("admin")
    client = TestClient(app)

    res = client.get(endpoint)
    assert res.status_code == 503


def test_admin_can_access_corporate_farms_globally_and_by_enterprise() -> None:
    app.dependency_overrides[require_corporate_or_admin_bearer] = (
        lambda: make_principal("admin")
    )
    client = TestClient(app)

    # Global vision (all enterprises: 99 and 88)
    res_global = client.get("/v1/user/dashboards/corporate/farms")
    assert res_global.status_code == 200
    global_data = res_global.json()
    assert global_data["total"] == 2
    farm_names = {f["farm_name"] for f in global_data["items"]}
    assert farm_names == {"Granja Primavera", "Granja Sulista"}

    # Filtered by enterprise_id=88
    res_ent = client.get("/v1/user/dashboards/corporate/farms?enterprise_id=88")
    assert res_ent.status_code == 200
    ent_data = res_ent.json()
    assert ent_data["total"] == 1
    assert ent_data["items"][0]["farm_name"] == "Granja Sulista"

    # Admin can also query corporate KPIs, filters, and chart data globally
    res_kpis = client.get("/v1/user/dashboards/corporate/kpis")
    assert res_kpis.status_code == 200
    assert res_kpis.json()["spend_current_year"]["value"] == 2_100_000.0

    res_filters = client.get("/v1/user/dashboards/corporate/filters")
    assert res_filters.status_code == 200
    assert set(res_filters.json()["states"]) == {"GO", "PR"}

    res_chart = client.get(
        "/v1/user/dashboards/corporate/charts/monthly-cost/data?enterprise_id=99"
    )
    assert res_chart.status_code == 200
    assert len(res_chart.json()) == 12
