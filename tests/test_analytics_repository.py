"""Behavioral tests for MongoDB Analytics with no external database."""
from datetime import UTC, datetime, timedelta
from unittest.mock import patch

import pytest
from bson import Decimal128
from pymongo.errors import ServerSelectionTimeoutError

from app.repositories.analytics import (
    AnalyticsQueryError, AnalyticsRepository, AnalyticsUnavailable,
    validate_mongodb_uri,
)

RUN = "snapshot-42"


class Collection:
    def __init__(self, documents):
        self.documents = documents
        self.filters = []

    def find_one(self, selector):
        return next((d for d in self.documents if d.get("_id") == selector["_id"]), None)

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
        {"dataset": "dim_farm", "_sync_run": RUN, "farm_id": 7,
         "enterprise_id": 3, "farm_name": "Alpha", "chickens_now": 800,
         "poultry_capacity": 1000},
        {"dataset": "dim_farm", "_sync_run": RUN, "farm_id": 9,
         "enterprise_id": 3, "farm_name": "Beta", "chickens_now": 300,
         "poultry_capacity": 500},
        {"dataset": "dim_farm", "_sync_run": RUN, "farm_id": 11,
         "enterprise_id": 4, "farm_name": "Hidden", "chickens_now": 9000,
         "poultry_capacity": 10000},
        {"dataset": "fact_lot", "_sync_run": RUN, "farm_id": 7,
         "enterprise_id": 3, "delivery_date": now - timedelta(days=4),
         "received_chickens": 100, "delivered_chickens": 80,
         "lost_chickens": 10, "cost": Decimal128("12.50")},
        {"dataset": "fact_lot", "_sync_run": RUN, "farm_id": 9,
         "enterprise_id": 3, "delivery_date": now - timedelta(days=4),
         "received_chickens": 50, "delivered_chickens": 40,
         "lost_chickens": 5, "cost": Decimal128("7.50")},
        {"dataset": "fact_lot", "_sync_run": RUN, "farm_id": 11,
         "enterprise_id": 4, "delivery_date": now - timedelta(days=4),
         "received_chickens": 1000, "delivered_chickens": 900,
         "lost_chickens": 500, "cost": Decimal128("900")},
        {"dataset": "fact_goal", "_sync_run": RUN, "farm_id": 7,
         "goal_status": "active", "goal_type": "water"},
        {"dataset": "fact_goal", "_sync_run": RUN, "farm_id": 9,
         "goal_status": "completed", "goal_type": "energy"},
        {"dataset": "fact_goal", "_sync_run": RUN, "farm_id": 11,
         "goal_status": "completed", "goal_type": "water"},
        {"dataset": "dim_farm", "_sync_run": "old-run", "farm_id": 400,
         "enterprise_id": 3, "chickens_now": 100000},
    ]
    month = now.date().replace(day=1)
    monthly = [
        {"_sync_run": RUN, "farm_id": 7, "enterprise_id": 3,
         "month_start": datetime(month.year, month.month, 1),
         "water_metrics": {"monthly_total_m3": Decimal128("30")},
         "energy_metrics": {"monthly_total_kwh": Decimal128("100")},
         "chickens_reference": 800},
        {"_sync_run": RUN, "farm_id": 9, "enterprise_id": 3,
         "month_start": datetime(month.year, month.month, 1),
         "water_metrics": {"monthly_total_m3": Decimal128("20")},
         "energy_metrics": {"monthly_total_kwh": Decimal128("50")},
         "chickens_reference": 300},
        {"_sync_run": RUN, "farm_id": 11, "enterprise_id": 4,
         "month_start": datetime(month.year, month.month, 1),
         "water_metrics": {"monthly_total_m3": Decimal128("500")},
         "energy_metrics": {"monthly_total_kwh": Decimal128("500")},
         "chickens_reference": 9000},
    ]
    buckets = [
        {"_sync_run": RUN, "farm_id": 7, "enterprise_id": 3, "metric": "water",
         "readings": [{"date": now - timedelta(days=2), "value": Decimal128("3.5")},
                      {"date": now - timedelta(days=2), "value": Decimal128("2.5")}]},
        {"_sync_run": RUN, "farm_id": 11, "enterprise_id": 4, "metric": "water",
         "readings": [{"date": now, "value": Decimal128("999")}]},
    ]
    state = [] if missing else [{
        "_id": "production_to_mongodb_poc", "status": status,
        "run_id": run, "last_success_at": now - timedelta(minutes=12),
    }]
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


@pytest.mark.parametrize("uri", [
    "postgresql://reader@host/analytics",
    "mongodb://host/db?tlsInsecure=true",
    "mongodb://host/db?tlsAllowInvalidCertificates=true",
    "mongodb://host/db?tlsAllowInvalidHostnames=true",
    "mongodb://host/db?tls=false",
])
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
        assert all(f.get("farm_id") == 7 for f in repo._database[col].filters
                   if "farm_id" in f)


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
    assert (await repo.fetch("monthly-water-consumption", ""))[0]["water_consumed_m3"] == 550.0


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
    assert (await repo.fetch("lot_mortality", "", None, 3, 30))[0]["mortality_rate_pct"] == 10.0


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
    assert await repo.fetch("sync_status", "") == [{
        "last_updated_at": None, "has_error": False,
    }]
    with pytest.raises(AnalyticsUnavailable):
        await repo.fetch("current_flock", "", 7, None)


@pytest.mark.asyncio
async def test_mongodb_transport_failure_is_reported_as_unavailable():
    repo = repository()
    with patch.object(repo, "_state", side_effect=ServerSelectionTimeoutError("offline")):
        with pytest.raises(AnalyticsUnavailable):
            await repo.fetch("current_flock", "", 7, None)


@pytest.mark.asyncio
async def test_close_releases_mongo_client():
    repo = repository()
    await repo.close()
    assert repo._client.closed
