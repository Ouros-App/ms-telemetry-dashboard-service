"""Integration and authorization tests for corporate dashboards (company_employee)."""

from datetime import UTC, datetime, timedelta

import pytest
from bson import Decimal128
from fastapi.testclient import TestClient

from app.core.auth import (
    Principal,
    require_corporate_or_admin_bearer,
    require_user_bearer,
)
from app.main import app
from app.providers.analytics import AnalyticsDashboardProvider
from app.repositories.analytics import AnalyticsRepository
from app.schemas.user_dashboards import (
    CorporateCostBucketItem,
    CorporateCostByLotSizeCohortItem,
    CorporateCostByRegionItem,
    CorporateMonthlyCostItem,
)
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


def corporate_repository():
    now = datetime.now(UTC)
    run = "corporate-test-run"
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
            "farm_id": 102,
            "enterprise_id": 99,
            "farm_name": "Granja Alvorada",
            "manager_name": "Mariana Santos",
            "state": "SP",
            "city": "Campinas",
            "regional_management": "Sudeste 1",
            "chickens_now": 30000,
            "poultry_capacity": 40000,
        },
        {
            "dataset": "dim_farm",
            "_sync_run": run,
            "farm_id": 201,
            "enterprise_id": 88,
            "farm_name": "Granja Outra Empresa",
            "manager_name": "Outro Gestor",
            "state": "PR",
            "city": "Cascavel",
            "regional_management": "Sul 1",
            "chickens_now": 10000,
            "poultry_capacity": 15000,
        },
        # Lots for enterprise 99 (current year)
        {
            "dataset": "fact_lot",
            "_sync_run": run,
            "farm_id": 101,
            "enterprise_id": 99,
            "delivery_date": datetime(now.year, 4, 15, tzinfo=UTC),
            "received_chickens": 50000,
            "delivered_chickens": 48000,
            "lost_chickens": 2000,
            "cost": Decimal128("1200000.00"),
        },
        {
            "dataset": "fact_lot",
            "_sync_run": run,
            "farm_id": 102,
            "enterprise_id": 99,
            "delivery_date": datetime(now.year, 5, 20, tzinfo=UTC),
            "received_chickens": 30000,
            "delivered_chickens": 29000,
            "lost_chickens": 1000,
            "cost": Decimal128("800000.00"),
        },
        # Lots for enterprise 99 (previous year)
        {
            "dataset": "fact_lot",
            "_sync_run": run,
            "farm_id": 101,
            "enterprise_id": 99,
            "delivery_date": datetime(now.year - 1, 4, 10, tzinfo=UTC),
            "received_chickens": 45000,
            "delivered_chickens": 43000,
            "lost_chickens": 2000,
            "cost": Decimal128("1000000.00"),
        },
        # Lots for competitor enterprise 88
        {
            "dataset": "fact_lot",
            "_sync_run": run,
            "farm_id": 201,
            "enterprise_id": 88,
            "delivery_date": datetime(now.year, 4, 1, tzinfo=UTC),
            "received_chickens": 10000,
            "delivered_chickens": 9500,
            "lost_chickens": 500,
            "cost": Decimal128("5000000.00"),
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
        {
            "_sync_run": run,
            "farm_id": 201,
            "enterprise_id": 88,
            "month_start": datetime(now.year, 4, 1, tzinfo=UTC),
            "water_metrics": {"monthly_total_m3": Decimal128("9999")},
            "energy_metrics": {"monthly_total_kwh": Decimal128("99999")},
            "chickens_reference": 10000,
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
    return repo


@pytest.fixture(autouse=True)
def setup_app_state():
    repo = corporate_repository()
    provider = AnalyticsDashboardProvider(repo)
    service = UserDashboardService(provider)
    app.state.user_dashboard_service = service
    yield
    app.dependency_overrides.clear()


def make_principal(
    account_type: str, farm_id: int | None = None, enterprise_id: int | None = None
) -> Principal:
    roles = {account_type}
    return Principal(
        subject=f"sub-{account_type}",
        database_id=1,
        account_type=account_type,
        roles=frozenset(roles),
        farm_id=farm_id,
        enterprise_id=enterprise_id,
    )


def override_user_auth(principal: Principal) -> None:
    app.dependency_overrides[require_user_bearer] = lambda: principal
    app.dependency_overrides[require_corporate_or_admin_bearer] = lambda: principal


def test_farm_owner_cannot_access_corporate_endpoints():
    override_user_auth(make_principal("farm_owner", farm_id=101))
    client = TestClient(app)

    # 1. KPIs
    res = client.get("/v1/user/dashboards/corporate/kpis")
    assert res.status_code == 403
    assert "restrito" in res.json()["detail"].lower()

    # 2. Filters
    res = client.get("/v1/user/dashboards/corporate/filters")
    assert res.status_code == 403

    # 3. Chart data
    res = client.get("/v1/user/dashboards/corporate/charts/trend-kwh-aves/data")
    assert res.status_code == 403

    # 4. Farms table
    res = client.get("/v1/user/dashboards/corporate/farms")
    assert res.status_code == 403

    # 5. Corporate dashboard info
    res = client.get("/v1/user/dashboards/corporate")
    assert res.status_code == 403

    # 6. Corporate charts list
    res = client.get("/v1/user/dashboards/corporate/charts")
    assert res.status_code == 403

    # 7. Plotly route
    res = client.get("/v1/user/dashboards/corporate/charts/trend-kwh-aves/plotly")
    assert res.status_code == 403


def test_farm_owner_dashboard_list_does_not_contain_corporate():
    app.dependency_overrides[require_user_bearer] = lambda: make_principal(
        "farm_owner", farm_id=101
    )
    client = TestClient(app)

    res = client.get("/v1/user/dashboards")
    assert res.status_code == 200
    ids = [item["id"] for item in res.json()["items"]]
    assert "corporate" not in ids
    assert "overview" in ids


def test_company_employee_dashboard_list_contains_corporate():
    app.dependency_overrides[require_user_bearer] = lambda: make_principal(
        "company_employee", enterprise_id=99
    )
    client = TestClient(app)

    res = client.get("/v1/user/dashboards")
    assert res.status_code == 200
    ids = [item["id"] for item in res.json()["items"]]
    assert "corporate" in ids


def test_company_employee_get_corporate_kpis():
    override_user_auth(make_principal("company_employee", enterprise_id=99))
    client = TestClient(app)

    res = client.get("/v1/user/dashboards/corporate/kpis")
    assert res.status_code == 200
    data = res.json()
    assert "spend_current_year" in data
    assert "spend_previous_year" in data
    assert "avg_cost_per_bird" in data
    assert "total_lots" in data

    # 1.2M + 0.8M = 2.0M in current year
    assert data["spend_current_year"]["value"] == 2000000.0
    assert "R$" in data["spend_current_year"]["formatted"]
    # 1.0M in previous year
    assert data["spend_previous_year"]["value"] == 1000000.0
    # 2 lots in current year
    assert data["total_lots"]["value"] == 2.0
    # avg cost per bird: 2.0M / 80k birds = 25.0
    assert data["avg_cost_per_bird"]["value"] == 25.0

    # Filter by state SP (only farm 102: cost 800,000, 30,000 birds)
    res_sp = client.get("/v1/user/dashboards/corporate/kpis?state=SP")
    assert res_sp.status_code == 200
    sp_data = res_sp.json()
    assert sp_data["spend_current_year"]["value"] == 800000.0


def test_company_employee_get_corporate_filters():
    override_user_auth(make_principal("company_employee", enterprise_id=99))
    client = TestClient(app)

    res = client.get("/v1/user/dashboards/corporate/filters")
    assert res.status_code == 200
    data = res.json()
    assert "states" in data
    assert "SP" in data["states"]
    assert "GO" in data["states"]
    assert "PR" not in data["states"]  # PR belongs to enterprise 88!
    assert "Centro-Oeste 1" in data["regional_managements"]
    assert "Sudeste 1" in data["regional_managements"]


def test_company_employee_get_corporate_chart_data():
    override_user_auth(make_principal("company_employee", enterprise_id=99))
    client = TestClient(app)

    # 1. trend-kwh-aves
    res = client.get("/v1/user/dashboards/corporate/charts/trend-kwh-aves/data")
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 2
    assert "energy_kwh" in rows[0]
    assert "chickens" in rows[0]

    # 2. trend-liters-aves
    res = client.get("/v1/user/dashboards/corporate/charts/trend-liters-aves/data")
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 2
    assert "water_liters" in rows[0]
    assert rows[0]["water_liters"] == 1500000.0  # 1500 m3 * 1000

    # 3. cost-distribution-buckets (Adaptive bucketing with million-scale lots)
    res = client.get(
        "/v1/user/dashboards/corporate/charts/cost-distribution-buckets/data"
    )
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 4
    assert rows[0]["bucket"] == "R$ 800k - 900k"
    assert rows[0]["count"] == 1
    assert rows[0]["value"] == 1
    assert rows[0]["total_cost"] == 800000.0
    assert rows[0]["percentage"] == 33.3
    assert rows[0]["color"] == "#5A53FF"
    assert "low" in rows[0]
    assert "high" in rows[0]
    for r in rows:
        CorporateCostBucketItem.model_validate(r)

    # 4. cost-by-lot-size-cohort (Adaptive dynamic binning with continuous axis)
    res = client.get(
        "/v1/user/dashboards/corporate/charts/cost-by-lot-size-cohort/data"
    )
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 4
    cohort_map = {r["cohort"]: r for r in rows}
    assert "30k-35k" in cohort_map
    assert "35k-40k" in cohort_map
    assert "40k-45k" in cohort_map
    assert "45k-50k" in cohort_map
    assert cohort_map["30k-35k"]["current_year_cost"] == 800000.0
    assert cohort_map["30k-35k"]["current_year_lots"] == 1
    assert cohort_map["35k-40k"]["current_year_lots"] == 0
    assert cohort_map["40k-45k"]["current_year_lots"] == 0
    assert cohort_map["45k-50k"]["previous_year_cost"] == 1000000.0
    assert cohort_map["45k-50k"]["previous_year_lots"] == 1
    assert cohort_map["45k-50k"]["current_year_cost"] == 1200000.0
    assert cohort_map["45k-50k"]["current_year_lots"] == 1
    for r in rows:
        CorporateCostByLotSizeCohortItem.model_validate(r)

    # 5. cost-by-region (Macroregions with normalized resolution and BoxPlotStats)
    res = client.get("/v1/user/dashboards/corporate/charts/cost-by-region/data")
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 5
    region_map = {r["region"]: r for r in rows}
    assert region_map["Centro-Oeste"]["current_year_cost"] == 1200000.0
    assert region_map["Centro-Oeste"]["previous_year_cost"] == 1000000.0
    assert region_map["Sudeste"]["current_year_cost"] == 800000.0
    assert region_map["Centro-Oeste"]["current_year"]["median"] == 1200000.0
    assert region_map["Centro-Oeste"]["previous_year"]["median"] == 1000000.0
    for r in rows:
        CorporateCostByRegionItem.model_validate(r)

    # 6. monthly-cost (12 calendar months Jan-Dez comparative curve)
    res = client.get("/v1/user/dashboards/corporate/charts/monthly-cost/data")
    assert res.status_code == 200
    rows = res.json()
    assert len(rows) == 12
    assert rows[0]["month"] == 1
    assert rows[0]["month_label"] == "Jan"
    assert rows[3]["month"] == 4
    assert rows[3]["month_label"] == "Abr"
    assert rows[3]["previous_year_cost"] == 1000000.0
    assert rows[3]["current_year_cost"] == 1200000.0
    assert rows[3]["cost"] == 1200000.0
    assert rows[4]["month"] == 5
    assert rows[4]["month_label"] == "Mai"
    assert rows[4]["current_year_cost"] == 800000.0
    for r in rows:
        CorporateMonthlyCostItem.model_validate(r)

    # 7. Nonexistent chart returns 404
    res = client.get("/v1/user/dashboards/corporate/charts/nonexistent/data")
    assert res.status_code == 404


def test_company_employee_get_corporate_farms_table():
    override_user_auth(make_principal("company_employee", enterprise_id=99))
    client = TestClient(app)

    res = client.get("/v1/user/dashboards/corporate/farms?page=1&limit=10")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2
    farm_names = [f["farm_name"] for f in data["items"]]
    assert "Granja Primavera" in farm_names
    assert "Granja Alvorada" in farm_names
    assert "Granja Outra Empresa" not in farm_names

    # Search filter
    res_search = client.get("/v1/user/dashboards/corporate/farms?search=Primavera")
    assert res_search.status_code == 200
    assert res_search.json()["total"] == 1
    assert res_search.json()["items"][0]["farm_name"] == "Granja Primavera"

    # State filter
    res_state = client.get("/v1/user/dashboards/corporate/farms?state=GO")
    assert res_state.status_code == 200
    assert res_state.json()["total"] == 1
    assert res_state.json()["items"][0]["location"] == "Rio Verde - GO"


def test_company_employee_corporate_plotly_rendering():
    app.dependency_overrides[require_user_bearer] = lambda: make_principal(
        "company_employee", enterprise_id=99
    )
    client = TestClient(app)

    # 1. Combo chart with dual Y-axis
    res = client.get("/v1/user/dashboards/corporate/charts/trend-kwh-aves/plotly")
    assert res.status_code == 200
    html = res.text
    assert "Plotly.newPlot" in html
    assert "yaxis2" in html
    assert "overlaying" in html

    # 2. Cohort chart
    res_cohort = client.get(
        "/v1/user/dashboards/corporate/charts/cost-by-lot-size-cohort/plotly"
    )
    assert res_cohort.status_code == 200
    assert "Plotly.newPlot" in res_cohort.text

    # 3. Region chart
    res_region = client.get(
        "/v1/user/dashboards/corporate/charts/cost-by-region/plotly"
    )
    assert res_region.status_code == 200
    assert "Plotly.newPlot" in res_region.text

    # 4. Donut chart (cost-distribution-buckets)
    res_buckets = client.get(
        "/v1/user/dashboards/corporate/charts/cost-distribution-buckets/plotly"
    )
    assert res_buckets.status_code == 200
    assert "Plotly.newPlot" in res_buckets.text

    # 5. Monthly cost line chart
    res_monthly = client.get("/v1/user/dashboards/corporate/charts/monthly-cost/plotly")
    assert res_monthly.status_code == 200
    assert "Plotly.newPlot" in res_monthly.text
