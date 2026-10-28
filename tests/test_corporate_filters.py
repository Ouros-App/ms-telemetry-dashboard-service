"""Integration tests for corporate dashboard global filters (state, management, month)."""

from datetime import UTC, datetime, timedelta

import pytest
from bson import Decimal128
from fastapi.testclient import TestClient

from app.core.auth import Principal, require_user_bearer
from app.main import app
from app.providers.analytics import AnalyticsDashboardProvider
from app.repositories.analytics import AnalyticsRepository
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


def make_principal(enterprise_id: int = 99) -> Principal:
    return Principal(
        subject="sub-company-emp",
        database_id=1,
        account_type="company_employee",
        roles=frozenset({"company_employee"}),
        enterprise_id=enterprise_id,
    )


@pytest.fixture
def client_with_data():
    now = datetime.now(UTC)
    run = "filters-test-run"
    rows = [
        # Farms
        {
            "dataset": "dim_farm",
            "_sync_run": run,
            "farm_id": 101,
            "enterprise_id": 99,
            "farm_name": "Granja Goiás",
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
            "farm_id": 102,
            "enterprise_id": 99,
            "farm_name": "Granja São Paulo",
            "manager_name": "Mariana Santos",
            "state": "SP",
            "city": "Campinas",
            "regional_management": "Sudeste 1",
            "chickens_now": 30000,
            "poultry_capacity": 40000,
        },
        # Lots for 101 (GO, April)
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
            "farm_id": 101,
            "enterprise_id": 99,
            "delivery_date": datetime(now.year - 1, 4, 10, tzinfo=UTC),
            "received_chickens": 45000,
            "cost": Decimal128("1000000.00"),
        },
        # Lots for 102 (SP, May)
        {
            "dataset": "fact_lot",
            "_sync_run": run,
            "farm_id": 102,
            "enterprise_id": 99,
            "delivery_date": datetime(now.year, 5, 20, tzinfo=UTC),
            "received_chickens": 30000,
            "cost": Decimal128("800000.00"),
        },
        {
            "dataset": "fact_lot",
            "_sync_run": run,
            "farm_id": 102,
            "enterprise_id": 99,
            "delivery_date": datetime(now.year - 1, 5, 18, tzinfo=UTC),
            "received_chickens": 28000,
            "cost": Decimal128("750000.00"),
        },
    ]

    monthly = [
        {
            "_sync_run": run,
            "farm_id": 101,
            "enterprise_id": 99,
            "month_start": datetime(now.year, 4, 1, tzinfo=UTC),
            "water_metrics": {"monthly_total_m3": Decimal128("1500")},
            "energy_metrics": {"monthly_total_kwh": Decimal128("45000")},
            "chickens_reference": 50000,
        },
        {
            "_sync_run": run,
            "farm_id": 102,
            "enterprise_id": 99,
            "month_start": datetime(now.year, 5, 1, tzinfo=UTC),
            "water_metrics": {"monthly_total_m3": Decimal128("1000")},
            "energy_metrics": {"monthly_total_kwh": Decimal128("30000")},
            "chickens_reference": 30000,
        },
    ]

    state = [
        {
            "_id": "production_to_mongodb_poc",
            "status": "success",
            "run_id": run,
            "last_success_at": now - timedelta(minutes=5),
        }
    ]

    repo = object.__new__(AnalyticsRepository)
    repo._retry_after = 0.0
    repo.retry_backoff_seconds = 0.0
    repo._client = MockMongoClient()
    repo._database = {
        "poc_sync_state": MockCollection(state),
        "poc_analytics_rows": MockCollection(rows),
        "poc_farm_monthly": MockCollection(monthly),
        "poc_metric_buckets": MockCollection([]),
    }

    provider = AnalyticsDashboardProvider(repo)
    service = UserDashboardService(provider)
    app.state.user_dashboard_service = service
    app.dependency_overrides[require_user_bearer] = lambda: make_principal(99)

    yield TestClient(app)
    app.dependency_overrides.clear()


def test_kpis_state_filter(client_with_data):
    # Total without filters: 1.2M + 0.8M = 2.0M curr year
    res = client_with_data.get("/v1/user/dashboards/corporate/kpis")
    assert res.status_code == 200
    assert res.json()["spend_current_year"]["value"] == 2000000.0

    # Filter state=SP: only farm 102 (0.8M)
    res_sp = client_with_data.get("/v1/user/dashboards/corporate/kpis?state=SP")
    assert res_sp.status_code == 200
    assert res_sp.json()["spend_current_year"]["value"] == 800000.0
    assert res_sp.json()["spend_previous_year"]["value"] == 750000.0
    assert res_sp.json()["total_lots"]["value"] == 1.0

    # Filter state=todos: should NOT filter out everything
    res_todos = client_with_data.get("/v1/user/dashboards/corporate/kpis?state=todos")
    assert res_todos.status_code == 200
    assert res_todos.json()["spend_current_year"]["value"] == 2000000.0


def test_kpis_management_filter(client_with_data):
    # Filter management = "Centro-Oeste 1": only farm 101 (1.2M curr)
    res = client_with_data.get(
        "/v1/user/dashboards/corporate/kpis?management=Centro-Oeste 1"
    )
    assert res.status_code == 200
    assert res.json()["spend_current_year"]["value"] == 1200000.0
    assert res.json()["total_lots"]["value"] == 1.0

    # Filter management = "todas"
    res_todas = client_with_data.get(
        "/v1/user/dashboards/corporate/kpis?management=todas"
    )
    assert res_todas.status_code == 200
    assert res_todas.json()["spend_current_year"]["value"] == 2000000.0


def test_kpis_month_filter(client_with_data):
    # May only has farm 102 (800k curr, 750k prev)
    res_may = client_with_data.get("/v1/user/dashboards/corporate/kpis?month=2026-05")
    assert res_may.status_code == 200
    assert res_may.json()["spend_current_year"]["value"] == 800000.0
    assert res_may.json()["spend_previous_year"]["value"] == 750000.0
    assert res_may.json()["total_lots"]["value"] == 1.0

    # April only has farm 101 (1.2M curr, 1.0M prev)
    res_apr = client_with_data.get("/v1/user/dashboards/corporate/kpis?month=2026-04")
    assert res_apr.status_code == 200
    assert res_apr.json()["spend_current_year"]["value"] == 1200000.0
    assert res_apr.json()["spend_previous_year"]["value"] == 1000000.0
    assert res_apr.json()["total_lots"]["value"] == 1.0

    # month="atual": should return full safra/year
    res_atual = client_with_data.get("/v1/user/dashboards/corporate/kpis?month=atual")
    assert res_atual.status_code == 200
    assert res_atual.json()["spend_current_year"]["value"] == 2000000.0


def test_cohort_chart_with_filters(client_with_data):
    # Filter state=SP: only 30k lot from farm 102
    res_sp = client_with_data.get(
        "/v1/user/dashboards/corporate/charts/cost-by-lot-size-cohort/data?state=SP"
    )
    assert res_sp.status_code == 200
    rows = res_sp.json()
    assert len(rows) >= 1
    # Check that GO farm lots are not included
    total_curr_cost = sum(r["current_year_cost"] for r in rows)
    assert total_curr_cost == 800000.0

    # Filter month=2026-04: only 101 lots (50k curr, 45k prev)
    res_apr = client_with_data.get(
        "/v1/user/dashboards/corporate/charts/cost-by-lot-size-cohort/data?month=2026-04"
    )
    assert res_apr.status_code == 200
    apr_rows = res_apr.json()
    total_apr_cost = sum(r["current_year_cost"] for r in apr_rows)
    assert total_apr_cost == 1200000.0


def test_farms_table_with_filters(client_with_data):
    # Filter state=SP
    res_sp = client_with_data.get("/v1/user/dashboards/corporate/farms?state=SP")
    assert res_sp.status_code == 200
    data = res_sp.json()
    assert data["total"] == 1
    assert data["items"][0]["farm_name"] == "Granja São Paulo"

    # Filter management="Centro-Oeste 1"
    res_mgmt = client_with_data.get(
        "/v1/user/dashboards/corporate/farms?management=Centro-Oeste 1"
    )
    assert res_mgmt.status_code == 200
    assert res_mgmt.json()["total"] == 1
    assert res_mgmt.json()["items"][0]["farm_name"] == "Granja Goiás"

    # Filter month=2026-05: only farm 102 had lots in May
    res_may = client_with_data.get("/v1/user/dashboards/corporate/farms?month=2026-05")
    assert res_may.status_code == 200
    items = res_may.json()["items"]
    sp_farm = next((f for f in items if f["farm_name"] == "Granja São Paulo"), None)
    go_farm = next((f for f in items if f["farm_name"] == "Granja Goiás"), None)
    assert sp_farm["lots_count"] == 1
    assert go_farm["lots_count"] == 0
