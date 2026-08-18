import contextvars
import json
import logging
import sys
from datetime import datetime, timezone
from typing import Any

_request_id: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)
_LOG_FIELDS = {
    "event",
    "method",
    "path",
    "status_code",
    "duration_ms",
    "operation",
    "attempt",
    "max_retries",
    "upstream_status",
    "retry_reason",
    "retryable",
    "outcome",
    "errors",
    "configured",
    "databricks_configured",
    "catalog_path",
    "catalog_entries",
    "expires_in",
}
_LOG_LEVELS = {
    "CRITICAL": logging.CRITICAL,
    "ERROR": logging.ERROR,
    "WARNING": logging.WARNING,
    "INFO": logging.INFO,
    "DEBUG": logging.DEBUG,
}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        request_id = _request_id.get()
        if request_id:
            payload["request_id"] = request_id
        for field in _LOG_FIELDS:
            if hasattr(record, field):
                payload[field] = getattr(record, field)
        if record.exc_info:
            payload["exception"] = {
                "type": record.exc_info[0].__name__,
                "message": str(record.exc_info[1]),
                "traceback": self.formatException(record.exc_info),
            }
        return json.dumps(payload, ensure_ascii=False, default=str)


def configure_logging(level_name: str = "INFO") -> None:
    level = _LOG_LEVELS.get(level_name.upper(), logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.setLevel(level)
    for logger_name in ("uvicorn.access", "uvicorn.error"):
        uvicorn_logger = logging.getLogger(logger_name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.addHandler(handler)
        uvicorn_logger.setLevel(level)
        uvicorn_logger.propagate = False


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def set_request_id(request_id: str) -> contextvars.Token[str | None]:
    return _request_id.set(request_id)


def reset_request_id(token: contextvars.Token[str | None]) -> None:
    _request_id.reset(token)
