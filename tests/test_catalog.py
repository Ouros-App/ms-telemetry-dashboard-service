import json

import pytest

from app.repositories.catalog import DashboardCatalog
from app.schemas.dashboards import DashboardRecord


def dashboard(identifier: str, enabled: bool = True) -> DashboardRecord:
    return DashboardRecord(
        id=identifier,
        provider="databricks",
        title=identifier,
        description="description",
        dashboard_id=f"internal-{identifier}",
        enabled=enabled,
    )


def test_catalog_lists_only_enabled_dashboards() -> None:
    catalog = DashboardCatalog([dashboard("enabled"), dashboard("disabled", False)])

    assert [item.id for item in catalog.enabled()] == ["enabled"]


def test_catalog_finds_enabled_dashboard_and_rejects_other_ids() -> None:
    catalog = DashboardCatalog([dashboard("enabled"), dashboard("disabled", False)])

    assert catalog.find_enabled("enabled").dashboard_id == "internal-enabled"
    with pytest.raises(KeyError):
        catalog.find_enabled("missing")
    with pytest.raises(KeyError):
        catalog.find_enabled("disabled")


def test_catalog_loads_json(tmp_path) -> None:
    path = tmp_path / "dashboards.json"
    path.write_text(json.dumps([dashboard("one").model_dump()]), encoding="utf-8")

    assert DashboardCatalog.from_path(path).find_enabled("one").id == "one"
