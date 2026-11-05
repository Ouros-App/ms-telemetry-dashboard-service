"""Atlas connection configuration must not take down unrelated providers."""
import importlib
from unittest.mock import patch

import pytest

from app.core.config import Settings


@pytest.mark.asyncio
async def test_invalid_atlas_client_does_not_abort_telemetry_startup():
    app_module = importlib.import_module("app.main")
    settings = Settings(
        _env_file=None,
        analytics_mongodb_uri="mongodb+srv://reader:password@atlas.example.net/",
        databricks_host=None,
        databricks_client_id=None,
        databricks_client_secret=None,
        prometheus_url=None,
    )
    with (
        patch.object(app_module, "settings", settings),
        patch.object(app_module, "AnalyticsRepository", side_effect=ValueError("InvalidURI")),
    ):
        async with app_module.lifespan(app_module.app):
            assert app_module.app.state.analytics_repository is None
            assert app_module.app.state.analytics_ready is False
            assert app_module.app.state.dashboard_service is not None
            assert app_module.app.state.user_dashboard_service is not None


@pytest.mark.asyncio
async def test_invalid_ai_users_client_does_not_abort_telemetry_startup():
    """A bad optional database client must not block unrelated providers."""
    app_module = importlib.import_module("app.main")
    settings = Settings(
        _env_file=None,
        analytics_mongodb_uri=None,
        ai_users_mongodb_uri="mongodb+srv://reader:password@atlas.example.net/",
        databricks_host=None,
        databricks_client_id=None,
        databricks_client_secret=None,
        prometheus_url=None,
    )
    with (
        patch.object(app_module, "settings", settings),
        patch.object(
            app_module,
            "AiUsersRepository",
            side_effect=ValueError("InvalidURI"),
        ),
    ):
        async with app_module.lifespan(app_module.app):
            assert app_module.app.state.ai_users_repository is None
            assert app_module.app.state.admin_metrics_service is not None
            assert app_module.app.state.dashboard_service is not None
