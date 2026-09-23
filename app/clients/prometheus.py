from dataclasses import dataclass
import math

import httpx
from prometheus_client.parser import text_string_to_metric_families

from app.core.config import TelemetryTarget


class PrometheusScrapeError(RuntimeError):
    """Raised when an upstream metrics endpoint cannot be scraped safely."""


@dataclass(frozen=True)
class MetricSample:
    name: str
    labels: dict[str, str]
    value: float


@dataclass(frozen=True)
class PrometheusSnapshot:
    samples: tuple[MetricSample, ...]

    def sum(self, name: str, labels: dict[str, str] | None = None) -> float:
        required = labels or {}
        return sum(
            sample.value
            for sample in self.samples
            if sample.name == name
            and all(sample.labels.get(key) == value for key, value in required.items())
        )

    def label_values(self, name: str, *keys: str) -> set[tuple[str, ...]]:
        return {
            tuple(sample.labels.get(key, "") for key in keys)
            for sample in self.samples
            if sample.name == name
        }


class PrometheusScrapeClient:
    def __init__(self, client: httpx.AsyncClient, timeout_seconds: float) -> None:
        self.client = client
        self.timeout_seconds = timeout_seconds

    async def scrape(self, target: TelemetryTarget) -> PrometheusSnapshot:
        headers = {}
        if target.token is not None:
            headers["Authorization"] = f"Bearer {target.token.get_secret_value()}"
        try:
            response = await self.client.get(
                target.url,
                headers=headers,
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except (httpx.HTTPError, httpx.TimeoutException) as exc:
            raise PrometheusScrapeError(type(exc).__name__) from exc

        try:
            families = text_string_to_metric_families(response.text)
            parsed_samples: list[MetricSample] = []
            for family in families:
                for sample in family.samples:
                    value = float(sample.value)
                    if not math.isfinite(value):
                        continue
                    parsed_samples.append(
                        MetricSample(
                            name=sample.name,
                            labels=dict(sample.labels),
                            value=value,
                        )
                    )
            samples = tuple(parsed_samples)
        except (TypeError, ValueError) as exc:
            raise PrometheusScrapeError("invalid_prometheus_payload") from exc
        return PrometheusSnapshot(samples=samples)
