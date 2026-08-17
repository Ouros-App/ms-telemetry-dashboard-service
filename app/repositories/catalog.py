import json
from pathlib import Path

from pydantic import ValidationError

from app.schemas.dashboards import DashboardRecord


class CatalogError(ValueError):
    pass


class DashboardCatalog:
    def __init__(self, dashboards: list[DashboardRecord]) -> None:
        public_ids = [dashboard.id for dashboard in dashboards]
        internal_ids = [dashboard.dashboard_id for dashboard in dashboards]
        if len(public_ids) != len(set(public_ids)):
            raise CatalogError("dashboard catalog contains duplicate public ids")
        if len(internal_ids) != len(set(internal_ids)):
            raise CatalogError("dashboard catalog contains duplicate Databricks ids")
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

    def find_by_dashboard_id(self, dashboard_id: str) -> DashboardRecord | None:
        return next((item for item in self._dashboards if item.dashboard_id == dashboard_id), None)
