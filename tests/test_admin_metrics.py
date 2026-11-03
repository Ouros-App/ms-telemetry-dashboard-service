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


def test_empty_admin_ai_metrics_do_not_return_sample_data() -> None:
    app.dependency_overrides[require_admin_bearer] = lambda: make_principal("admin")
    client = TestClient(app)

    kpis = client.get("/v1/admin/ai-metrics/kpis")
    assert kpis.status_code == 200
    for item in kpis.json().values():
        assert item["value"] is None
        assert item["formatted"] == "Sem dados"

    for endpoint in (
        "/v1/admin/ai-metrics/charts/token-spend",
        "/v1/admin/ai-metrics/charts/request-spend",
        "/v1/admin/ai-metrics/charts/cost-by-region",
        "/v1/admin/ai-metrics/charts/monthly-cost",
        "/v1/admin/ai-metrics/charts/latency-distribution",
    ):
        response = client.get(endpoint)
        assert response.status_code == 200
        assert response.json()["items"] == []

    sessions = client.get("/v1/admin/ai-metrics/sessions?page=1&limit=2")
    assert sessions.status_code == 200
    assert sessions.json() == {
        "total": 0,
        "page": 1,
        "limit": 2,
        "items": [],
    }


@pytest.mark.parametrize("month", ["0000-01", "9999-12"])
def test_admin_ai_kpis_reject_unrepresentable_month(month: str) -> None:
    app.dependency_overrides[require_admin_bearer] = lambda: make_principal("admin")
    client = TestClient(app)

    response = client.get(f"/v1/admin/ai-metrics/kpis?month={month}")

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_ai_kpis_use_selected_calendar_month() -> None:
    expected_timestamp = datetime(2024, 3, 1, tzinfo=UTC).timestamp()

    class Prometheus:
        async def query(self, query: str, *, timestamp: float | None = None):
            values = {
                "increase(midas_jev_cost_usd_total[2505600s])": "0.000546417",
                "increase(midas_jev_input_tokens_total[2505600s])": "13010",
                "increase(midas_jev_output_tokens_total[2505600s])": "1752",
            }
            assert timestamp == expected_timestamp
            return [{"value": [timestamp, values[query]]}]

    service = AdminMetricsService(
        repository=build_repository(with_ai_sessions=True),
        prometheus=Prometheus(),
    )

    response = await service.get_kpis(month="2024-02")

    assert response.token_spend.value == pytest.approx(0.000546417)
    assert response.token_spend.unit == "US$"
    assert response.token_spend.period == "2024-02"
    assert response.unit_cost.value == pytest.approx(
        0.000546417 / (13010 + 1752) * 1000
    )
    assert response.unit_cost.unit == "US$/1k tokens"
    assert response.active_users.value == 2.0
    assert response.total_tokens.value == pytest.approx(14762)
    assert response.total_tokens.formatted == "14.762"
    assert response.total_tokens.unit == "tokens"
    assert response.total_tokens.period == "2024-02"


@pytest.mark.parametrize(
    ("enterprise_id", "expected_tokens", "expected_formatted"),
    [(None, 3000, "3.000"), (88, 1000, "1.000")],
)
@pytest.mark.asyncio
async def test_admin_ai_kpis_use_analytics_tokens_without_prometheus(
    enterprise_id: int | None,
    expected_tokens: int,
    expected_formatted: str,
) -> None:
    service = AdminMetricsService(
        repository=build_repository(with_ai_sessions=True),
        prometheus=None,
    )

    response = await service.get_kpis(enterprise_id=enterprise_id)

    assert response.total_tokens.value == expected_tokens
    assert response.total_tokens.formatted == expected_formatted
    assert response.total_tokens.period is None


@pytest.mark.asyncio
async def test_admin_ai_kpis_keep_prometheus_source_when_month_has_no_samples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 15, 12, tzinfo=UTC)

    class Prometheus:
        async def query(self, query: str, *, timestamp: float | None = None):
            return []

    monkeypatch.setattr("app.services.admin_metrics.datetime", FrozenDateTime)
    service = AdminMetricsService(
        repository=build_repository(with_ai_sessions=True),
        prometheus=Prometheus(),
    )

    response = await service.get_kpis()

    assert response.token_spend.value is None
    assert response.token_spend.unit == "US$"
    assert response.token_spend.period == "2026-10"
    assert response.unit_cost.value is None
    assert response.unit_cost.unit == "US$/1k tokens"
    assert response.active_users.value == 2.0
    assert response.total_tokens.value is None
    assert response.total_tokens.formatted == "Sem dados"
    assert response.total_tokens.unit == "tokens"


@pytest.mark.asyncio
async def test_admin_ai_kpis_limit_current_month_to_now(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FrozenDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 10, 15, 12, tzinfo=UTC)

    calls: list[tuple[str, float | None]] = []

    class Prometheus:
        async def query(self, query: str, *, timestamp: float | None = None):
            calls.append((query, timestamp))
            value = "0.01" if "cost_usd" in query else "100"
            return [{"value": [timestamp, value]}]

    monkeypatch.setattr("app.services.admin_metrics.datetime", FrozenDateTime)

    await AdminMetricsService(prometheus=Prometheus()).get_kpis()

    assert len(calls) == 3
    assert {timestamp for _, timestamp in calls} == {
        FrozenDateTime(2026, 10, 15, 12, tzinfo=UTC).timestamp()
    }
    assert {query for query, _ in calls} == {
        "increase(midas_jev_cost_usd_total[1252800s])",
        "increase(midas_jev_input_tokens_total[1252800s])",
        "increase(midas_jev_output_tokens_total[1252800s])",
    }


@pytest.mark.asyncio
async def test_admin_ai_kpis_leave_unit_cost_unavailable_without_prometheus_cost() -> None:
    class Prometheus:
        async def query(self, query: str, *, timestamp: float | None = None):
            if "cost_usd" in query:
                return []
            return [{"value": [timestamp, "100"]}]

    response = await AdminMetricsService(prometheus=Prometheus()).get_kpis(
        month="2026-10"
    )

    assert response.token_spend.value is None
    assert response.token_spend.formatted == "Sem dados"
    assert response.unit_cost.value is None
    assert response.unit_cost.formatted == "Sem dados"


@pytest.mark.asyncio
async def test_admin_ai_kpis_ignore_non_finite_prometheus_samples() -> None:
    class Prometheus:
        async def query(self, query: str, *, timestamp: float | None = None):
            if "cost_usd" in query:
                values = ["NaN", "0.0004", "Inf"]
            elif "input_tokens" in query:
                values = ["-Inf", "100"]
            else:
                values = ["50"]
            return [{"value": [timestamp, value]} for value in values]

    response = await AdminMetricsService(prometheus=Prometheus()).get_kpis(
        month="2026-10"
    )

    assert response.token_spend.value == pytest.approx(0.0004)
    assert response.unit_cost.value == pytest.approx(0.0004 / 150 * 1000)


@pytest.mark.asyncio
async def test_admin_ai_kpis_do_not_query_future_overflow_month() -> None:
    class Prometheus:
        async def query(self, query: str, *, timestamp: float | None = None):
            raise AssertionError("future month must not be queried")

    response = await AdminMetricsService(prometheus=Prometheus()).get_kpis(
        month="9999-12"
    )

    assert response.token_spend.value is None
    assert response.token_spend.period == "9999-12"


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
        "/v1/admin/ai-metrics/charts/request-spend",
        "/v1/admin/ai-metrics/charts/cost-by-region",
        "/v1/admin/ai-metrics/charts/monthly-cost",
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

        async def get_request_spend_chart(self, **_kwargs):
            raise AnalyticsQueryError("bad query")

        async def get_cost_by_region_chart(self, **_kwargs):
            raise AnalyticsUnavailable("offline")

        async def get_monthly_cost_chart(self, **_kwargs):
            raise AnalyticsQueryError("bad query")

        async def get_sessions(self, **_kwargs):
            raise AnalyticsQueryError("bad query")

    monkeypatch.setattr(app.state, "admin_metrics_service", FailingAdminService())
    app.dependency_overrides[require_admin_bearer] = lambda: make_principal("admin")
    client = TestClient(app)

    res = client.get(endpoint)
    assert res.status_code == 503



def test_admin_metrics_service_new_methods_with_custom_repo_data() -> None:
    import asyncio
    service = AdminMetricsService(None)

    async def _run():
        # 1. request spend with data and filters
        fake_spend = [
            {
                "cohort": "0-50k",
                "cost_brl": 1500.0,
                "previous_year_cost_brl": 2000.0,
                "current_year_requests": 300,
                "previous_year_requests": 250,
                "created_at": "2026-10-01T12:00:00Z",
                "model": "openai/gpt-oss-120b",
            },
            {
                "cohort": "50k-75k",
                "cost_brl": 2500.0,
                "created_at": "2026-09-01T12:00:00Z",
                "model": "other-model",
            },
        ]
        with patch.object(service, "_fetch_from_repo", return_value=fake_spend):
            res_spend = await service.get_request_spend_chart(month="2026-10", model="openai/gpt-oss-120b", enterprise_id=99)
            assert len(res_spend.items) == 1
            assert res_spend.items[0].cohort == "0-50k"

        # 2. cost by region with data and filters
        fake_regions = [
            {
                "region": "Sudeste",
                "previous_year_cost_brl": 50000.0,
                "current_year_cost_brl": 60000.0,
                "created_at": "2026-10-01T12:00:00Z",
            },
            {
                "region": "Sul",
                "previous_year_cost_brl": 40000.0,
                "current_year_cost_brl": 45000.0,
                "created_at": "2026-09-01T12:00:00Z",
            },
        ]
        with patch.object(service, "_fetch_from_repo", return_value=fake_regions):
            res_reg = await service.get_cost_by_region_chart(month="2026-10", enterprise_id=88)
            assert len(res_reg.items) == 1
            assert res_reg.items[0].region == "Sudeste"

        # 3. monthly cost with data
        fake_monthly = [
            {
                "month": "Jan",
                "previous_year_cost_brl": 100000.0,
                "current_year_cost_brl": 120000.0,
            }
        ]
        with patch.object(service, "_fetch_from_repo", return_value=fake_monthly):
            res_mon = await service.get_monthly_cost_chart(enterprise_id=99)
            assert len(res_mon.items) == 1
            assert res_mon.items[0].month == "Jan"

    asyncio.run(_run())


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
