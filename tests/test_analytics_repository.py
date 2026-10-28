"""Behavioral tests for MongoDB Analytics with no external database."""

from datetime import UTC, date, datetime, timedelta
from unittest.mock import patch

import pytest
from bson import Decimal128
from pymongo.errors import ServerSelectionTimeoutError

from app.repositories.analytics import (
    AnalyticsQueryError,
    AnalyticsRepository,
    AnalyticsUnavailable,
    _date_filter,
    validate_mongodb_uri,
)

RUN = "snapshot-42"


class Collection:
    def __init__(self, documents):
        self.documents = documents
        self.filters = []

    def find_one(self, selector):
        return next(
            (d for d in self.documents if d.get("_id") == selector["_id"]), None
        )

    def find(self, selector):
        self.filters.append(selector)

        def matches(item):
            for key, expected in selector.items():
                if isinstance(expected, dict) and "$in" in expected:
                    if item.get(key) not in expected["$in"]:
                        return False
                elif item.get(key) != expected:
                    return False
            return True

        return (d for d in self.documents if matches(d))


class Client:
    def __init__(self):
        self.admin = self
        self.closed = False

    def command(self, _name):
        return {"ok": 1}

    def close(self):
        self.closed = True


def repository(*, status="success", run=RUN, missing=False):
    now = datetime.now(UTC)
    rows = [
        {
            "dataset": "dim_farm",
            "_sync_run": RUN,
            "farm_id": 7,
            "enterprise_id": 3,
            "farm_name": "Alpha",
            "chickens_now": 800,
            "poultry_capacity": 1000,
            "state": "SP",
            "regional_management": "Regional Sudeste",
        },
        {
            "dataset": "dim_farm",
            "_sync_run": RUN,
            "farm_id": 9,
            "enterprise_id": 3,
            "farm_name": "Beta",
            "chickens_now": 300,
            "poultry_capacity": 500,
            "state": "GO",
            "regional_management": "Regional Centro",
        },
        {
            "dataset": "dim_farm",
            "_sync_run": RUN,
            "farm_id": 11,
            "enterprise_id": 4,
            "farm_name": "Hidden",
            "chickens_now": 9000,
            "poultry_capacity": 10000,
            "state": "PR",
            "regional_management": "Regional Sul",
        },
        {
            "dataset": "fact_lot",
            "_sync_run": RUN,
            "farm_id": 7,
            "enterprise_id": 3,
            "delivery_date": now - timedelta(days=4),
            "received_chickens": 100,
            "delivered_chickens": 80,
            "lost_chickens": 10,
            "cost": Decimal128("12.50"),
        },
        {
            "dataset": "fact_lot",
            "_sync_run": RUN,
            "farm_id": 9,
            "enterprise_id": 3,
            "delivery_date": now - timedelta(days=4),
            "received_chickens": 50,
            "delivered_chickens": 40,
            "lost_chickens": 5,
            "cost": Decimal128("7.50"),
        },
        {
            "dataset": "fact_lot",
            "_sync_run": RUN,
            "farm_id": 7,
            "enterprise_id": 3,
            "delivery_date": datetime(now.year - 1, 5, 10, tzinfo=UTC),
            "received_chickens": 120,
            "delivered_chickens": 108,
            "lost_chickens": 12,
            "cost": Decimal128("15.00"),
        },
        {
            "dataset": "fact_lot",
            "_sync_run": RUN,
            "farm_id": 11,
            "enterprise_id": 4,
            "delivery_date": now - timedelta(days=4),
            "received_chickens": 1000,
            "delivered_chickens": 900,
            "lost_chickens": 500,
            "cost": Decimal128("900"),
        },
        {
            "dataset": "fact_goal",
            "_sync_run": RUN,
            "farm_id": 7,
            "goal_status": "active",
            "goal_type": "water",
        },
        {
            "dataset": "fact_goal",
            "_sync_run": RUN,
            "farm_id": 9,
            "goal_status": "completed",
            "goal_type": "energy",
        },
        {
            "dataset": "fact_goal",
            "_sync_run": RUN,
            "farm_id": 11,
            "goal_status": "completed",
            "goal_type": "water",
        },
        {
            "dataset": "dim_farm",
            "_sync_run": "old-run",
            "farm_id": 400,
            "enterprise_id": 3,
            "chickens_now": 100000,
        },
    ]
    month = now.date().replace(day=1)
    monthly = [
        {
            "_sync_run": RUN,
            "farm_id": 7,
            "enterprise_id": 3,
            "month_start": datetime(month.year, month.month, 1),
            "water_metrics": {"monthly_total_m3": Decimal128("30")},
            "energy_metrics": {"monthly_total_kwh": Decimal128("100")},
            "chickens_reference": 800,
        },
        {
            "_sync_run": RUN,
            "farm_id": 9,
            "enterprise_id": 3,
            "month_start": datetime(month.year, month.month, 1),
            "water_metrics": {"monthly_total_m3": Decimal128("20")},
            "energy_metrics": {"monthly_total_kwh": Decimal128("50")},
            "chickens_reference": 300,
        },
        {
            "_sync_run": RUN,
            "farm_id": 11,
            "enterprise_id": 4,
            "month_start": datetime(month.year, month.month, 1),
            "water_metrics": {"monthly_total_m3": Decimal128("500")},
            "energy_metrics": {"monthly_total_kwh": Decimal128("500")},
            "chickens_reference": 9000,
        },
    ]
    buckets = [
        {
            "_sync_run": RUN,
            "farm_id": 7,
            "enterprise_id": 3,
            "metric": "water",
            "readings": [
                {"date": now - timedelta(days=2), "value": Decimal128("3.5")},
                {"date": now - timedelta(days=2), "value": Decimal128("2.5")},
            ],
        },
        {
            "_sync_run": RUN,
            "farm_id": 11,
            "enterprise_id": 4,
            "metric": "water",
            "readings": [{"date": now, "value": Decimal128("999")}],
        },
    ]
    state = (
        []
        if missing
        else [
            {
                "_id": "production_to_mongodb_poc",
                "status": status,
                "run_id": run,
                "last_success_at": now - timedelta(minutes=12),
            }
        ]
    )
    result = object.__new__(AnalyticsRepository)
    result._retry_after = 0.0
    result.retry_backoff_seconds = 0.0
    result._client = Client()
    result._database = {
        "poc_sync_state": Collection(state),
        "poc_analytics_rows": Collection(rows),
        "poc_farm_monthly": Collection(monthly),
        "poc_metric_buckets": Collection(buckets),
    }
    return result


@pytest.mark.parametrize(
    "uri",
    [
        "postgresql://reader@host/analytics",
        "mongodb://host/db?tlsInsecure=true",
        "mongodb://host/db?tlsAllowInvalidCertificates=true",
        "mongodb://host/db?tlsAllowInvalidHostnames=true",
        "mongodb://host/db?tls=false",
    ],
)
def test_insecure_or_wrong_backend_uri_rejected(uri):
    with pytest.raises(ValueError):
        validate_mongodb_uri(uri, "ouros_analytics_poc")


def test_wrong_database_rejected():
    with pytest.raises(ValueError):
        validate_mongodb_uri("mongodb://host/", "production")


@pytest.mark.asyncio
async def test_scope_is_validated_before_reading_business_collections():
    repo = repository()
    for args in ((None, None), (7, 3), (0, None), (True, None)):
        with pytest.raises(AnalyticsQueryError):
            await repo.fetch("current_flock", "current_flock", *args)
    with pytest.raises(AnalyticsQueryError):
        await repo.fetch("raw_command", "drop something", 7, None)


@pytest.mark.asyncio
async def test_farm_owner_cannot_read_other_farms_or_enterprises():
    repo = repository()
    assert await repo.fetch("current_flock", "", 7, None) == [{"value": 800}]
    assert await repo.fetch("farm_capacity", "", 7, None) == [
        {"farm_name": "Alpha", "chickens_now": 800, "poultry_capacity": 1000}
    ]
    assert await repo.fetch("mortality_rate", "", 7, None) == [{"value": 10.0}]
    assert await repo.fetch("capacity_utilization", "", 7, None) == [{"value": 80.0}]
    for col in ("poc_analytics_rows",):
        assert all(
            f.get("farm_id") == 7 for f in repo._database[col].filters if "farm_id" in f
        )


@pytest.mark.asyncio
async def test_employee_sees_enterprise_scope_and_never_other_enterprises():
    repo = repository()
    assert await repo.fetch("current_flock", "", None, 3) == [{"value": 1100}]
    assert await repo.fetch("capacity_utilization", "", None, 3) == [{"value": 73.33}]
    assert await repo.fetch("mortality_rate", "", None, 3) == [{"value": 10.0}]
    assert await repo.fetch("goal_status", "", None, 3) == [
        {"label": "active", "value": 1},
        {"label": "completed", "value": 1},
    ]


@pytest.mark.asyncio
async def test_admin_metrics_are_global_only_when_using_admin_operations():
    repo = repository()
    assert await repo.fetch("farm-count", "") == [{"value": 3}]
    assert await repo.fetch("current-flock", "") == [{"value": 10100}]
    with pytest.raises(AnalyticsQueryError):
        await repo.fetch("current-flock", "", 7, None)


@pytest.mark.asyncio
async def test_periodic_resource_totals_and_efficiency_use_atlas_nested_fields():
    repo = repository()
    rows = await repo.fetch("monthly_consumption", "", None, 3, 30)
    assert len(rows) == 1
    assert rows[0]["water_consumed_m3"] == 50.0
    assert rows[0]["energy_consumed_kwh"] == 150.0
    efficiency = await repo.fetch("resource_efficiency", "", None, 3, 30)
    assert efficiency[0]["water_m3_per_chicken"] == 0.0455
    assert efficiency[0]["energy_kwh_per_chicken"] == 0.1364
    assert (await repo.fetch("monthly-water-consumption", ""))[0][
        "water_consumed_m3"
    ] == 550.0


@pytest.mark.asyncio
async def test_bucket_readings_only_include_signed_farm():
    repo = repository()
    rows = await repo.fetch("water_consumption_by_reading", "", 7, None, 10)
    assert len(rows) == 1
    assert rows[0]["water_consumed_m3"] == 6.0


@pytest.mark.asyncio
async def test_lot_trend_aggregates_without_cross_tenant_data():
    repo = repository()
    rows = await repo.fetch("lot_throughput", "", None, 3, 30)
    assert rows[0]["received_chickens"] == 150
    assert rows[0]["delivered_chickens"] == 120
    assert (await repo.fetch("lot_cost", "", None, 3, 30))[0]["cost"] == 20.0
    assert (await repo.fetch("lot_mortality", "", None, 3, 30))[0][
        "mortality_rate_pct"
    ] == 10.0


@pytest.mark.asyncio
async def test_incomplete_snapshot_is_unavailable_and_status_is_stale():
    for state in ("running", "failed"):
        repo = repository(status=state)
        with pytest.raises(AnalyticsUnavailable):
            await repo.fetch("current_flock", "", 7, None)
        status = await repo.fetch("sync_status", "")
        assert status[0]["has_error"] is True


@pytest.mark.asyncio
async def test_missing_or_old_checkpoint_does_not_expose_partial_data():
    repo = repository(missing=True)
    assert await repo.fetch("sync_status", "") == [
        {
            "last_updated_at": None,
            "has_error": False,
        }
    ]
    with pytest.raises(AnalyticsUnavailable):
        await repo.fetch("current_flock", "", 7, None)


@pytest.mark.asyncio
async def test_mongodb_transport_failure_is_reported_as_unavailable():
    repo = repository()
    with (
        patch.object(
            repo, "_state", side_effect=ServerSelectionTimeoutError("offline")
        ),
        pytest.raises(AnalyticsUnavailable),
    ):
        await repo.fetch("current_flock", "", 7, None)


@pytest.mark.asyncio
async def test_null_nested_metrics_are_zero_without_http_500():
    repo = repository()
    monthly = repo._database["poc_farm_monthly"].documents[0]
    monthly["water_metrics"] = None
    monthly["energy_metrics"] = None
    rows = await repo.fetch("monthly_consumption", "", 7, None, 30)
    assert rows[0]["water_consumed_m3"] == 0.0
    assert rows[0]["energy_consumed_kwh"] == 0.0


def test_mongo_socket_timeout_limits_blocking_network_reads():
    with patch("app.repositories.analytics.MongoClient") as client:
        AnalyticsRepository("mongodb+srv://reader:password@atlas.example.net/")
    assert client.call_args.kwargs["serverSelectionTimeoutMS"] == 5000
    assert client.call_args.kwargs["connectTimeoutMS"] == 5000
    assert client.call_args.kwargs["socketTimeoutMS"] == 15000


@pytest.mark.asyncio
async def test_close_releases_mongo_client():
    repo = repository()
    await repo.close()
    assert repo._client.closed


def test_date_filter_accepts_up_to_732_days_and_covers_previous_year_for_monthly():
    today = datetime.now(UTC).date()
    assert _date_filter(732) is not None
    with pytest.raises(AnalyticsQueryError):
        _date_filter(733)
    cutoff_monthly = _date_filter(30, monthly=True)
    expected_prev_year_start = date(today.year - 1, 1, 1)
    assert cutoff_monthly <= expected_prev_year_start


@pytest.mark.asyncio
async def test_relative_consumption_calculates_normalized_percentage():
    repo = repository()
    rows = await repo.fetch("relative_consumption", "", 7, None, 30)
    assert len(rows) == 1
    assert "month_start" in rows[0]
    assert "relative_consumption_pct" in rows[0]
    assert 0.0 <= rows[0]["relative_consumption_pct"] <= 100.0


@pytest.mark.asyncio
async def test_corporate_operations_reject_farm_owner_or_missing_enterprise():
    repo = repository()
    with pytest.raises(
        AnalyticsQueryError, match="Corporate operations require enterprise scope"
    ):
        await repo.fetch("corporate_kpis", "", 7, None)
    with pytest.raises(
        AnalyticsQueryError, match="Corporate operations require enterprise scope"
    ):
        await repo.fetch("corporate_kpis", "", None, None)
    with pytest.raises(AnalyticsQueryError, match="Signed analytics scope is missing"):
        await repo.fetch("corporate_kpis", "")


@pytest.mark.asyncio
async def test_corporate_kpis_aggregation_and_filters():
    repo = repository()
    rows = await repo.fetch("corporate_kpis", "", None, 3)
    assert len(rows) == 1
    kpis = rows[0]
    assert kpis["spend_current_year"]["value"] == 20.0  # 12.50 + 7.50
    assert kpis["spend_previous_year"]["value"] == 15.0  # 15.00
    assert kpis["spend_current_year"]["unit"] == "R$"
    assert kpis["total_lots"]["value"] == 2.0  # 2 lots in current year

    # Filter by state
    sp_rows = await repo.fetch("corporate_kpis", "", None, 3, {"state": "SP"})
    assert sp_rows[0]["spend_current_year"]["value"] == 12.50
    assert sp_rows[0]["spend_previous_year"]["value"] == 15.00


@pytest.mark.asyncio
async def test_corporate_charts_operations():
    repo = repository()
    # trend_kwh_aves
    kwh_rows = await repo.fetch("trend_kwh_aves", "", None, 3)
    assert len(kwh_rows) == 1
    assert kwh_rows[0]["chickens"] == 1100
    assert kwh_rows[0]["energy_kwh"] == 150.0

    # trend_liters_aves
    liters_rows = await repo.fetch("trend_liters_aves", "", None, 3)
    assert len(liters_rows) == 1
    assert liters_rows[0]["chickens"] == 1100
    assert liters_rows[0]["water_liters"] == 50000.0  # (30 + 20) * 1000

    # cost_distribution_buckets (Adaptive universal bucketing)
    bucket_rows = await repo.fetch("cost_distribution_buckets", "", None, 3)
    assert len(bucket_rows) >= 1
    assert sum(r["count"] for r in bucket_rows) == 3
    for r in bucket_rows:
        assert "bucket" in r
        assert "total_cost" in r
        assert "color" in r

    # cost_by_lot_size_cohort (Adaptive binning)
    cohort_rows = await repo.fetch("cost_by_lot_size_cohort", "", None, 3)
    assert len(cohort_rows) == 1
    assert cohort_rows[0]["cohort"] == "0-1k"
    assert cohort_rows[0]["current_year_cost"] == 20.0
    assert cohort_rows[0]["previous_year_cost"] == 15.0
    assert cohort_rows[0]["current_year_lots"] == 2
    assert cohort_rows[0]["previous_year_lots"] == 1

    # cost_by_region (5 macroregions)
    region_rows = await repo.fetch("cost_by_region", "", None, 3)
    assert len(region_rows) == 5
    region_map = {r["region"]: r for r in region_rows}
    assert region_map["Sudeste"]["current_year_cost"] == 12.50
    assert region_map["Sudeste"]["previous_year_cost"] == 15.00
    assert region_map["Centro-Oeste"]["current_year_cost"] == 7.50
    assert "previous_year" in region_map["Sudeste"]
    assert "current_year" in region_map["Sudeste"]

    # monthly_cost (12 calendar months Jan-Dez)
    monthly_rows = await repo.fetch("monthly_cost", "", None, 3)
    assert len(monthly_rows) == 12
    assert monthly_rows[0]["month"] == 1
    assert monthly_rows[0]["month_label"] == "Jan"
    assert "previous_year_cost" in monthly_rows[0]
    assert "current_year_cost" in monthly_rows[0]
    assert "cost" in monthly_rows[0]


@pytest.mark.asyncio
async def test_corporate_farms_table_pagination_and_search():
    repo = repository()
    table_rows = await repo.fetch(
        "corporate_farms_table", "", None, 3, {"page": 1, "limit": 10}
    )
    assert len(table_rows) == 1
    table = table_rows[0]
    assert table["total"] == 2  # Alpha (7) and Beta (9)
    assert len(table["items"]) == 2

    # Search for Alpha
    search_rows = await repo.fetch(
        "corporate_farms_table", "", None, 3, {"search": "Alpha"}
    )
    assert search_rows[0]["total"] == 1
    assert search_rows[0]["items"][0]["farm_name"] == "Alpha"

    # Filter by state
    go_rows = await repo.fetch("corporate_farms_table", "", None, 3, {"state": "GO"})
    assert go_rows[0]["total"] == 1
    assert go_rows[0]["items"][0]["farm_name"] == "Beta"


@pytest.mark.asyncio
async def test_corporate_filters_operation():
    repo = repository()
    filter_rows = await repo.fetch("corporate_filters", "", None, 3)
    assert len(filter_rows) == 1
    f = filter_rows[0]
    assert "SP" in f["states"]
    assert "GO" in f["states"]
    assert "Regional Sudeste" in f["regional_managements"]


def test_resolve_region_hierarchical():
    from app.repositories.analytics import _resolve_region

    # 1. Direct region field takes priority
    assert _resolve_region({"region": "sudeste"}) == "Sudeste"
    assert _resolve_region({"region": "sul"}) == "Sul"
    assert _resolve_region({}, {"region": "norte"}) == "Norte"
    assert _resolve_region({"region": "centro-oeste"}) == "Centro-Oeste"

    # 2. State / UF mapping
    assert _resolve_region({"state": "SP"}) == "Sudeste"
    assert _resolve_region({"uf": "PR"}) == "Sul"
    assert _resolve_region({"state": "BA"}) == "Nordeste"
    assert _resolve_region({"state": "MT"}) == "Centro-Oeste"
    assert _resolve_region({"state": "PA"}) == "Norte"

    # 3. Regional management text matching
    assert _resolve_region({"regional_management": "Regional Sudeste 1"}) == "Sudeste"
    assert _resolve_region({"management": "Gerencia Sul"}) == "Sul"

    # 4. Fallback
    assert _resolve_region({}) == "Centro-Oeste"


def test_calculate_dynamic_cost_buckets():
    from app.repositories.analytics import _calculate_dynamic_cost_buckets
    from app.schemas.user_dashboards import CorporateCostBucketItem

    # 1. Commercial poultry scale (max ~40k)
    lots_commercial = [
        {"cost": 8500.0},
        {"cost": 15000.0},
        {"cost": 22000.0},
        {"cost": 38000.0},
    ]
    buckets = _calculate_dynamic_cost_buckets(lots_commercial)
    assert len(buckets) == 7
    assert buckets[0]["bucket"] == "R$ 5k - 10k"
    assert buckets[0]["count"] == 1
    assert buckets[2]["bucket"] == "R$ 15k - 20k"
    assert buckets[2]["count"] == 1
    assert sum(b["count"] for b in buckets) == 4
    for b in buckets:
        CorporateCostBucketItem.model_validate(b)

    # 2. Million scale (universal multi-tenant adaptivity)
    lots_million = [
        {"cost": 800000.0},
        {"cost": 1200000.0},
        {"cost": 2100000.0},
    ]
    buckets_m = _calculate_dynamic_cost_buckets(lots_million)
    assert len(buckets_m) >= 3
    assert sum(b["count"] for b in buckets_m) == 3
    for b in buckets_m:
        CorporateCostBucketItem.model_validate(b)


def test_calc_box_stats_and_lot_cohort():
    from decimal import Decimal

    from app.repositories.analytics import _calc_box_stats, _lot_cohort

    # 1. Box stats calculation
    stats = _calc_box_stats(
        [
            Decimal("10.0"),
            Decimal("20.0"),
            Decimal("30.0"),
            Decimal("40.0"),
            Decimal("50.0"),
        ]
    )
    assert stats["min"] == 10.0
    assert stats["median"] == 30.0
    assert stats["max"] == 50.0
    assert stats["lots_count"] == 5
    assert stats["total_cost"] == 150.0

    # Empty stats
    empty = _calc_box_stats([])
    assert empty["min"] == 0.0
    assert empty["lots_count"] == 0

    # 2. 7 Figma cohorts resolution
    assert _lot_cohort(Decimal(30_000)) == "0-50k"
    assert _lot_cohort(Decimal(50_000)) == "50k-75k"
    assert _lot_cohort(Decimal(75_000)) == "75k-100k"
    assert _lot_cohort(Decimal(100_000)) == "100k-125k"
    assert _lot_cohort(Decimal(125_000)) == "125k-150k"
    assert _lot_cohort(Decimal(150_000)) == "150k-175k"
    assert _lot_cohort(Decimal(175_000)) == "175k+"
    assert _lot_cohort(Decimal(200_000)) == "175k+"
