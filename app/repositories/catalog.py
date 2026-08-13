import json
from pathlib import Path

from pydantic import ValidationError

from app.schemas.dashboards import DashboardRecord


class CatalogError(ValueError):
    pass


class DashboardCatalog:
    def __init__(self, dashboards: list[DashboardRecord]) -> None:
        ids = [dashboard.id for dashboard in dashboards]
        if len(ids) != len(set(ids)):
            raise CatalogError("dashboard catalog contains duplicate ids")
        self._dashboards = tuple(dashboards)

    @classmethod
    def from_path(cls, path: Path) -> "DashboardCatalog":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                raise CatalogError("dashboard catalog must be a JSON array")
            return cls([DashboardRecord.model_validate(item) for item in data])
        except (OSError, json.JSONDecodeError, TypeError, ValidationError) as exc:
            raise CatalogError("could not load dashboard catalog") from exc

    def enabled(self) -> list[DashboardRecord]:
        return [dashboard for dashboard in self._dashboards if dashboard.enabled]

    def find_enabled(self, dashboard_id: str) -> DashboardRecord:
        dashboard = next((item for item in self._dashboards if item.id == dashboard_id), None)
        if dashboard is None or not dashboard.enabled:
            raise KeyError(dashboard_id)
        return dashboard
