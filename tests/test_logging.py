import json
import logging

from app.core.config import Settings
from app.core.logging import JsonFormatter, reset_request_id, set_request_id


def test_json_formatter_includes_request_context_and_fields() -> None:
    token = set_request_id("request-123")
    try:
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=1,
            msg="request completed",
            args=(),
            exc_info=None,
        )
        record.event = "request_completed"
        record.status_code = 200
        record.duration_ms = 12.5

        payload = json.loads(JsonFormatter().format(record))
    finally:
        reset_request_id(token)

    assert payload["request_id"] == "request-123"
    assert payload["event"] == "request_completed"
    assert payload["status_code"] == 200
    assert payload["duration_ms"] == 12.5


def test_invalid_log_level_is_reported_as_configuration_error() -> None:
    config = Settings(log_level="TRACE")

    assert "LOG_LEVEL_INVALID" in config.configuration_errors()
