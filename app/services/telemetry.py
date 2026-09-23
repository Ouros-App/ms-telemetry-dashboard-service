import asyncio
from datetime import datetime, timezone
from pathlib import Path
from time import perf_counter

from app.clients.prometheus import (
    PrometheusScrapeClient,
    PrometheusScrapeError,
    PrometheusSnapshot,
)
from app.core.config import TelemetryTarget
from app.core.metrics import observe_upstream_scrape
from app.schemas.telemetry import (
    CapacityBaselineResponse,
    KnowledgeMcpTelemetry,
    MidasTelemetry,
    ModelUsage,
    ServiceScrapeStatus,
    TelemetrySummaryResponse,
)
from app.services.capacity import build_capacity_baseline
from app.services.metrics_analysis import (
    label_values,
    latency_summary,
    metric_sum,
    resource_usage,
    rounded,
    service_http_summary,
    tool_usage,
)
from app.services.pricing import PricingCatalog


class TelemetryService:
    """Aggregate low-cardinality process metrics without ingesting user data."""

    def __init__(
        self,
        client: PrometheusScrapeClient,
        targets: list[TelemetryTarget],
        pricing_path: Path,
    ) -> None:
        self.client = client
        self.targets = list(targets)
        self.pricing = PricingCatalog(pricing_path)

    async def _scrape_target(
        self,
        target: TelemetryTarget,
    ) -> tuple[ServiceScrapeStatus, PrometheusSnapshot | None]:
        started_at = perf_counter()
        try:
            snapshot = await self.client.scrape(target)
        except PrometheusScrapeError as exc:
            duration = perf_counter() - started_at
            observe_upstream_scrape(target.kind, "error", duration)
            return (
                ServiceScrapeStatus(
                    name=target.name,
                    kind=target.kind,
                    available=False,
                    scrape_duration_ms=rounded(duration * 1000, 3),
                    error=str(exc),
                ),
                None,
            )

        duration = perf_counter() - started_at
        observe_upstream_scrape(target.kind, "success", duration)
        http_requests, http_errors, http_latency = service_http_summary(
            snapshot,
            target.kind,
        )
        return (
            ServiceScrapeStatus(
                name=target.name,
                kind=target.kind,
                available=True,
                scrape_duration_ms=rounded(duration * 1000, 3),
                resources=resource_usage(snapshot),
                http_requests=http_requests,
                http_errors=http_errors,
                http_latency=http_latency,
            ),
            snapshot,
        )

    async def _scrape_all(
        self,
    ) -> tuple[list[ServiceScrapeStatus], dict[str, list[PrometheusSnapshot]]]:
        results = await asyncio.gather(
            *(self._scrape_target(target) for target in self.targets)
        )
        statuses: list[ServiceScrapeStatus] = []
        by_kind: dict[str, list[PrometheusSnapshot]] = {}
        for target, (status, snapshot) in zip(self.targets, results, strict=True):
            statuses.append(status)
            if snapshot is not None:
                by_kind.setdefault(target.kind, []).append(snapshot)
        return statuses, by_kind

    def _llm_usage(
        self,
        snapshots: list[PrometheusSnapshot],
    ) -> list[ModelUsage]:
        keys = label_values(
            snapshots,
            "ai_server_llm_requests_total",
            "profile",
            "model",
        )
        result: list[ModelUsage] = []
        for profile, model in sorted(keys):
            labels = {"profile": profile, "model": model}
            pricing = self.pricing.model(model)
            input_tokens = int(
                metric_sum(
                    snapshots,
                    "ai_server_llm_input_tokens_total",
                    labels,
                )
            )
            cached_tokens = int(
                metric_sum(
                    snapshots,
                    "ai_server_llm_cached_input_tokens_total",
                    labels,
                )
            )
            output_tokens = int(
                metric_sum(
                    snapshots,
                    "ai_server_llm_output_tokens_total",
                    labels,
                )
            )
            result.append(
                ModelUsage(
                    profile=profile,
                    model=model,
                    requests=int(
                        metric_sum(
                            snapshots,
                            "ai_server_llm_requests_total",
                            {**labels, "outcome": "success"},
                        )
                    ),
                    failed_requests=int(
                        metric_sum(
                            snapshots,
                            "ai_server_llm_requests_total",
                            {**labels, "outcome": "error"},
                        )
                    ),
                    input_tokens=input_tokens,
                    cached_input_tokens=cached_tokens,
                    output_tokens=output_tokens,
                    latency=latency_summary(
                        snapshots,
                        "ai_server_llm_request_duration_seconds",
                        labels,
                    ),
                    pricing_mode=str(
                        pricing.get("pricing_mode") or "unknown"
                    ),
                    provider=(
                        str(pricing["provider"])
                        if pricing.get("provider")
                        else None
                    ),
                    estimated_cost_usd=PricingCatalog.model_cost(
                        pricing,
                        input_tokens,
                        cached_tokens,
                        output_tokens,
                    ),
                    pricing_source=(
                        str(pricing["source"])
                        if pricing.get("source")
                        else None
                    ),
                    pricing_note=(
                        str(pricing["note"])
                        if pricing.get("note")
                        else None
                    ),
                )
            )
        return result

    def _midas(self, snapshots: list[PrometheusSnapshot]) -> MidasTelemetry:
        return MidasTelemetry(
            chat_requests=int(
                metric_sum(snapshots, "ai_server_chat_requests_total")
            ),
            blocked_requests=int(
                metric_sum(
                    snapshots,
                    "ai_server_chat_requests_total",
                    {"outcome": "blocked"},
                )
            ),
            failed_requests=int(
                metric_sum(
                    snapshots,
                    "ai_server_chat_requests_total",
                    {"outcome": "error"},
                )
                + metric_sum(
                    snapshots,
                    "ai_server_chat_requests_total",
                    {"outcome": "timeout"},
                )
            ),
            current_chat_in_flight=metric_sum(
                snapshots,
                "ai_server_chat_in_flight",
            ),
            current_llm_in_flight=metric_sum(
                snapshots,
                "ai_server_llm_in_flight",
            ),
            current_mcp_in_flight=metric_sum(
                snapshots,
                "ai_server_mcp_in_flight",
            ),
            chat_latency=latency_summary(
                snapshots,
                "ai_server_chat_duration_seconds",
            ),
            llm=self._llm_usage(snapshots),
            mcp_calls=tool_usage(
                snapshots,
                request_metric="ai_server_mcp_requests_total",
                duration_metric="ai_server_mcp_request_duration_seconds",
            ),
        )

    @staticmethod
    def _knowledge_mcp(
        snapshots: list[PrometheusSnapshot],
    ) -> KnowledgeMcpTelemetry:
        return KnowledgeMcpTelemetry(
            http_requests=int(
                metric_sum(snapshots, "ouros_mcp_http_requests_total")
            ),
            current_tool_in_flight=metric_sum(
                snapshots,
                "ouros_mcp_tool_in_flight",
            ),
            http_latency=latency_summary(
                snapshots,
                "ouros_mcp_http_request_duration_seconds",
                {"route": "/mcp"},
            ),
            tools=tool_usage(
                snapshots,
                request_metric="ouros_mcp_tool_calls_total",
                duration_metric="ouros_mcp_tool_duration_seconds",
            ),
        )

    async def summary(self) -> TelemetrySummaryResponse:
        statuses, by_kind = await self._scrape_all()
        midas_snapshots = by_kind.get("midas", [])
        mcp_snapshots = by_kind.get("knowledge_mcp", [])
        midas = self._midas(midas_snapshots) if midas_snapshots else None
        knowledge_mcp = (
            self._knowledge_mcp(mcp_snapshots) if mcp_snapshots else None
        )
        return TelemetrySummaryResponse(
            generated_at=datetime.now(timezone.utc),
            aggregation="process_lifetime_counters",
            resets_on_process_restart=True,
            services=statuses,
            midas=midas,
            knowledge_mcp=knowledge_mcp,
            cost=self.pricing.summary(midas),
        )

    async def capacity_baseline(self) -> CapacityBaselineResponse:
        return build_capacity_baseline(await self.summary())
