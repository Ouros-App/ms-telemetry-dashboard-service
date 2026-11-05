from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime
from typing import Any

from app.clients.prometheus import PrometheusHttpClient
from app.repositories.ai_users import AiUsersRepository
from app.repositories.analytics import (
    AnalyticsQueryError,
    AnalyticsRepository,
    AnalyticsUnavailable,
)
from app.schemas.admin_metrics import (
    AdminAiCostByRegionResponse,
    AdminAiMetricKpiItem,
    AdminAiMetricsKpisResponse,
    AdminAiMonthlyCostResponse,
    AdminLatencyDistributionResponse,
    AdminMidasSessionsResponse,
    AdminRequestSpendChartResponse,
    AdminTokenSpendChartResponse,
    AiCostByRegionPoint,
    AiMonthlyCostPoint,
    LatencyBucketItem,
    MidasSessionAuditItem,
    RequestSpendPoint,
    TokenSpendPoint,
)

BUCKET_175K_PLUS = "175k+"
NO_DATA = "Sem dados"


def _format_compact_brl(value: float) -> str:
    if value >= 1_000_000:
        return f"R$ {value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"R$ {value / 1_000:.2f}k"
    return f"R$ {value:.2f}"


def _format_thousands_dot(value: int) -> str:
    return f"{value:,}".replace(",", ".")


def _matches_session_filter(
    s: dict[str, Any],
    enterprise_id: int | None,
    model: str | None,
    status: str | None,
    search: str | None,
) -> bool:
    if (
        enterprise_id is not None
        and s.get("enterprise_id") is not None
        and int(s["enterprise_id"]) != enterprise_id
    ):
        return False
    if model and str(s.get("model", "")).casefold() != model.strip().casefold():
        return False
    if status and str(s.get("status", "")).casefold() != status.strip().casefold():
        return False
    if search:
        q = search.strip().casefold()
        haystack = f"{s.get('session_id', '')} {s.get('user_name', '')} {s.get('model', '')} {s.get('account_type', '')}".casefold()
        if q not in haystack:
            return False
    return True


def _matches_latency_bucket(latency: int, low: int, high: int | None) -> bool:
    if high is not None:
        return low <= latency < high
    return latency >= low


def _build_latency_bucket_items(
    sessions: list[dict[str, Any]],
) -> list[LatencyBucketItem]:
    bucket_defs = [
        ("0-50k", "0-50ms", 0, 50),
        ("50k-75k", "50-75ms", 50, 75),
        ("75k-100k", "75-100ms", 75, 100),
        ("100k-125k", "100-125ms", 100, 125),
        ("125k-150k", "125-150ms", 125, 150),
        ("150k-175k", "150-175ms", 150, 175),
        (BUCKET_175K_PLUS, "175ms+", 175, None),
    ]
    total = len(sessions)
    items: list[LatencyBucketItem] = []
    for bucket_code, label, low, high in bucket_defs:
        matching = [
            s
            for s in sessions
            if _matches_latency_bucket(int(s.get("latency_ms", 0)), low, high)
        ]
        cnt = len(matching)
        avg_cost = (
            round(
                sum(float(m.get("cost_brl", 0.0)) for m in matching) / cnt,
                2,
            )
            if cnt > 0
            else 0.0
        )
        pct = round((cnt * 100.0) / total, 1) if total > 0 else 0.0
        items.append(
            LatencyBucketItem(
                bucket=bucket_code,
                label=label,
                min_ms=low,
                max_ms=high,
                previous_year_count=max(0, cnt - 1),
                current_year_count=cnt,
                count=cnt,
                percentage=pct,
                avg_cost_brl=avg_cost,
            )
        )
    return items


class AdminMetricsService:
    """Service providing Midas AI financial and technical observability for ADM."""

    def __init__(
        self,
        repository: AnalyticsRepository | None = None,
        prometheus: PrometheusHttpClient | None = None,
        ai_users_repository: AiUsersRepository | None = None,
    ) -> None:
        self.repository = repository
        self.prometheus = prometheus
        self.ai_users_repository = ai_users_repository

    @staticmethod
    def _prometheus_period(month: str | None) -> tuple[datetime, datetime, str]:
        now = datetime.now(UTC)
        selected_month = month or f"{now.year:04}-{now.month:02}"
        start = datetime.strptime(selected_month, "%Y-%m").replace(tzinfo=UTC)
        if start > now:
            return start, start, selected_month
        if start.month == 12:
            next_month = datetime(start.year + 1, 1, 1, tzinfo=UTC)
        else:
            next_month = datetime(start.year, start.month + 1, 1, tzinfo=UTC)
        return start, min(next_month, now), selected_month

    async def _prometheus_increase(
        self,
        metric: str,
        *,
        start: datetime,
        end: datetime,
    ) -> float | None:
        if self.prometheus is None:
            return None
        duration_seconds = int((end - start).total_seconds())
        if duration_seconds <= 0:
            return None
        rows = await self.prometheus.query(
            f"increase({metric}[{duration_seconds}s])",
            timestamp=end.timestamp(),
        )
        total = 0.0
        found = False
        for row in rows:
            sample = row.get("value")
            if not isinstance(sample, list) or len(sample) < 2:
                continue
            try:
                sample_value = float(sample[1])
            except (TypeError, ValueError):
                continue
            if not math.isfinite(sample_value):
                continue
            total += sample_value
            found = True
        return total if found else None

    async def _fetch_from_repo(
        self, operation: str, enterprise_id: int | None = None
    ) -> list[dict[str, Any]]:
        if self.repository is None:
            return []
        try:
            args = (enterprise_id,) if enterprise_id is not None else ()
            return await self.repository.fetch(operation, operation, *args)
        except (AnalyticsUnavailable, AnalyticsQueryError):
            return []

    async def _prometheus_kpi_totals(
        self,
        month: str | None,
        enterprise_id: int | None,
    ) -> tuple[float | None, float | None, str | None]:
        if self.prometheus is None or enterprise_id is not None:
            return None, None, None

        start, end, period = self._prometheus_period(month)
        cost, input_tokens, output_tokens = await asyncio.gather(
            self._prometheus_increase(
                "midas_jev_cost_usd_total", start=start, end=end
            ),
            self._prometheus_increase(
                "midas_jev_input_tokens_total", start=start, end=end
            ),
            self._prometheus_increase(
                "midas_jev_output_tokens_total", start=start, end=end
            ),
        )
        tokens = (
            input_tokens + output_tokens
            if input_tokens is not None and output_tokens is not None
            else None
        )
        return cost, tokens, period

    def _cost_kpi_items(
        self,
        row: dict[str, Any],
        *,
        month: str | None,
        now_year: int,
        enterprise_id: int | None,
        prom_cost: float | None,
        prom_tokens: float | None,
        period: str | None,
    ) -> tuple[AdminAiMetricKpiItem, AdminAiMetricKpiItem]:
        use_prometheus = self.prometheus is not None and enterprise_id is None
        db_totals_available = month is None
        db_cost_value = row.get("total_cost_brl")
        db_unit_cost_value = row.get("unit_cost_brl")
        db_cost = (
            float(db_cost_value)
            if db_totals_available and db_cost_value is not None
            else None
        )
        db_unit_cost = (
            float(db_unit_cost_value)
            if db_totals_available and db_unit_cost_value is not None
            else None
        )

        if use_prometheus:
            cost = prom_cost
            unit_cost = (
                prom_cost / prom_tokens * 1000
                if prom_cost is not None and prom_tokens is not None and prom_tokens > 0
                else None
            )
            cost_unit = "US$"
            unit_cost_unit = "US$/1k tokens"
            cost_formatted = (
                f"US$ {cost:.6f}" if cost is not None else NO_DATA
            )
            unit_cost_formatted = (
                f"US$ {unit_cost:.6f}" if unit_cost is not None else NO_DATA
            )
            cost_year = None
            unit_cost_year = None
        else:
            cost = db_cost
            unit_cost = db_unit_cost
            cost_unit = "R$"
            unit_cost_unit = "R$/1k tokens"
            cost_formatted = (
                _format_compact_brl(cost) if cost is not None else NO_DATA
            )
            unit_cost_formatted = (
                f"R$ {unit_cost:.2f}" if unit_cost is not None else NO_DATA
            )
            cost_year = now_year - 1 if cost is not None else None
            unit_cost_year = now_year if unit_cost is not None else None

        return (
            AdminAiMetricKpiItem(
                value=cost,
                formatted=cost_formatted,
                unit=cost_unit,
                year=cost_year,
                period=period,
            ),
            AdminAiMetricKpiItem(
                value=unit_cost,
                formatted=unit_cost_formatted,
                unit=unit_cost_unit,
                year=unit_cost_year,
                period=period,
            ),
        )

    async def get_kpis(
        self,
        *,
        month: str | None = None,
        enterprise_id: int | None = None,
    ) -> AdminAiMetricsKpisResponse:
        now_year = datetime.now(UTC).year
        prom_cost, prom_tokens, period = await self._prometheus_kpi_totals(
            month, enterprise_id
        )
        rows = await self._fetch_from_repo("admin_ai_kpis", enterprise_id)
        row = rows[0] if rows else {}
        token_spend, unit_cost = self._cost_kpi_items(
            row,
            month=month,
            now_year=now_year,
            enterprise_id=enterprise_id,
            prom_cost=prom_cost,
            prom_tokens=prom_tokens,
            period=period,
        )
        active_users_value = (
            await self.ai_users_repository.count_distinct_user_ids()
            if self.ai_users_repository is not None
            else None
        )
        analytics_tokens = row.get("total_tokens")
        uses_prometheus_tokens = (
            self.prometheus is not None and enterprise_id is None
        )
        if uses_prometheus_tokens:
            total_tokens = prom_tokens
        elif month is None and analytics_tokens is not None:
            total_tokens = float(analytics_tokens)
        else:
            total_tokens = None

        return AdminAiMetricsKpisResponse(
            token_spend=token_spend,
            unit_cost=unit_cost,
            active_users=AdminAiMetricKpiItem(
                value=(
                    float(active_users_value)
                    if active_users_value is not None
                    else None
                ),
                formatted=(
                    _format_thousands_dot(active_users_value)
                    if active_users_value is not None
                    else NO_DATA
                ),
                unit="usuários",
                year=now_year if active_users_value is not None else None,
            ),
            total_tokens=AdminAiMetricKpiItem(
                value=total_tokens,
                formatted=(
                    _format_thousands_dot(round(total_tokens))
                    if total_tokens is not None
                    else NO_DATA
                ),
                unit="tokens",
                period=period,
            ),
        )

    async def get_token_spend_chart(
        self,
        *,
        month: str | None = None,
        model: str | None = None,
        enterprise_id: int | None = None,
    ) -> AdminTokenSpendChartResponse:
        sessions = await self._fetch_from_repo("admin_ai_token_spend", enterprise_id)
        if month and sessions:
            month_prefix = month.strip()
            sessions = [s for s in sessions if str(s.get("created_at", "")).startswith(month_prefix)]
        if model:
            sessions = [
                s
                for s in sessions
                if str(s.get("model", "")).casefold() == model.strip().casefold()
            ]

        if sessions:
            points: list[TokenSpendPoint] = []
            for idx, s in enumerate(sessions):
                label = str(s.get("period") or s.get("cohort") or f"P{idx + 1}")
                curr_cost = float(s.get("cost_brl") or s.get("current_year_cost_brl") or 0.0)
                prev_cost = float(s.get("previous_year_cost_brl") or 0.0)
                curr_tok = int(s.get("total_tokens") or s.get("current_year_tokens") or 0)
                prev_tok = int(s.get("previous_year_tokens") or 0)
                points.append(
                    TokenSpendPoint(
                        period=label,
                        label=label,
                        cohort=label,
                        model=str(s.get("model") or model or "Midas LLM"),
                        previous_year_tokens=prev_tok,
                        current_year_tokens=curr_tok,
                        previous_year_cost_brl=round(prev_cost, 2),
                        current_year_cost_brl=round(curr_cost, 2),
                        tokens=curr_tok,
                        cost_brl=round(curr_cost, 2),
                    )
                )
            return AdminTokenSpendChartResponse(items=points)

        return AdminTokenSpendChartResponse()

    async def get_request_spend_chart(
        self,
        *,
        month: str | None = None,
        model: str | None = None,
        enterprise_id: int | None = None,
    ) -> AdminRequestSpendChartResponse:
        sessions = await self._fetch_from_repo("admin_ai_request_spend", enterprise_id)
        if month and sessions:
            month_prefix = month.strip()
            sessions = [s for s in sessions if str(s.get("created_at", "")).startswith(month_prefix)]
        if model:
            sessions = [
                s
                for s in sessions
                if str(s.get("model", "")).casefold() == model.strip().casefold()
            ]

        if sessions:
            points: list[RequestSpendPoint] = []
            for s in sessions:
                cohort = str(s.get("cohort") or s.get("label") or "0-50k")
                curr_cost = float(s.get("cost_brl") or s.get("current_year_cost_brl") or 0.0)
                prev_cost = float(s.get("previous_year_cost_brl") or 0.0)
                curr_req = int(s.get("current_year_requests") or s.get("requests") or 0)
                prev_req = int(s.get("previous_year_requests") or 0)
                points.append(
                    RequestSpendPoint(
                        cohort=cohort,
                        label=cohort,
                        previous_year_cost_brl=round(prev_cost, 2),
                        current_year_cost_brl=round(curr_cost, 2),
                        previous_year_requests=prev_req,
                        current_year_requests=curr_req,
                    )
                )
            return AdminRequestSpendChartResponse(items=points)

        return AdminRequestSpendChartResponse()

    async def get_cost_by_region_chart(
        self,
        *,
        month: str | None = None,
        enterprise_id: int | None = None,
    ) -> AdminAiCostByRegionResponse:
        rows = await self._fetch_from_repo("admin_ai_cost_by_region", enterprise_id)
        if month and rows:
            month_prefix = month.strip()
            rows = [r for r in rows if str(r.get("created_at", "")).startswith(month_prefix)]

        if rows:
            items = [
                AiCostByRegionPoint(
                    region=str(r.get("region")),
                    previous_year_cost_brl=float(r.get("previous_year_cost_brl", 0.0)),
                    current_year_cost_brl=float(r.get("current_year_cost_brl", 0.0)),
                )
                for r in rows
                if "region" in r
            ]
            if items:
                return AdminAiCostByRegionResponse(items=items)

        return AdminAiCostByRegionResponse()

    async def get_monthly_cost_chart(
        self,
        *,
        enterprise_id: int | None = None,
    ) -> AdminAiMonthlyCostResponse:
        rows = await self._fetch_from_repo("admin_ai_monthly_cost", enterprise_id)
        if rows:
            items = [
                AiMonthlyCostPoint(
                    month=str(r.get("month")),
                    previous_year_cost_brl=float(r.get("previous_year_cost_brl", 0.0)),
                    current_year_cost_brl=float(r.get("current_year_cost_brl", 0.0)),
                )
                for r in rows
                if "month" in r
            ]
            if items:
                return AdminAiMonthlyCostResponse(items=items)

        return AdminAiMonthlyCostResponse()

    async def get_latency_distribution_chart(
        self,
        *,
        month: str | None = None,
        model: str | None = None,
        enterprise_id: int | None = None,
    ) -> AdminLatencyDistributionResponse:
        sessions = await self._fetch_from_repo(
            "admin_ai_latency_distribution", enterprise_id
        )
        if month and sessions:
            month_prefix = month.strip()
            sessions = [s for s in sessions if str(s.get("created_at", "")).startswith(month_prefix)]
        if model:
            sessions = [
                s
                for s in sessions
                if str(s.get("model", "")).casefold() == model.strip().casefold()
            ]

        if sessions and all("latency_ms" in s for s in sessions):
            return AdminLatencyDistributionResponse(
                items=_build_latency_bucket_items(sessions)
            )

        return AdminLatencyDistributionResponse()

    async def get_sessions(
        self,
        *,
        page: int = 1,
        limit: int = 10,
        search: str | None = None,
        model: str | None = None,
        status: str | None = None,
        enterprise_id: int | None = None,
    ) -> AdminMidasSessionsResponse:
        raw_sessions = await self._fetch_from_repo("admin_ai_sessions", enterprise_id)
        source = raw_sessions
        filtered = [
            s for s in source
            if _matches_session_filter(s, enterprise_id, model, status, search)
        ]

        total = len(filtered)
        safe_page = max(1, page)
        safe_limit = max(1, min(limit, 100))
        offset = (safe_page - 1) * safe_limit
        paged = filtered[offset : offset + safe_limit]

        items = [MidasSessionAuditItem.model_validate(item) for item in paged]
        return AdminMidasSessionsResponse(
            total=total,
            page=safe_page,
            limit=safe_limit,
            items=items,
        )
