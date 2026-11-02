from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

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

    def __init__(self, repository: AnalyticsRepository | None = None) -> None:
        self.repository = repository

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

    async def get_kpis(
        self,
        *,
        month: str | None = None,
        enterprise_id: int | None = None,
    ) -> AdminAiMetricsKpisResponse:
        now_year = datetime.now(UTC).year
        rows = await self._fetch_from_repo("admin_ai_kpis", enterprise_id)
        if month and rows:
            month_prefix = month.strip()
            rows = [r for r in rows if str(r.get("created_at", "")).startswith(month_prefix)]
        row = rows[0] if rows else {}
        total_cost = (
            float(row["total_cost_brl"])
            if row.get("total_cost_brl") is not None
            else None
        )
        unit_cost = (
            float(row["unit_cost_brl"])
            if row.get("unit_cost_brl") is not None
            else None
        )
        active_users = (
            int(row["active_users"])
            if row.get("active_users") is not None
            else None
        )
        return AdminAiMetricsKpisResponse(
            token_spend=AdminAiMetricKpiItem(
                value=total_cost,
                formatted=(
                    _format_compact_brl(total_cost)
                    if total_cost is not None
                    else "Sem dados"
                ),
                unit="R$",
                year=now_year - 1 if total_cost is not None else None,
            ),
            unit_cost=AdminAiMetricKpiItem(
                value=unit_cost,
                formatted=(
                    f"R$ {unit_cost:.2f}" if unit_cost is not None else "Sem dados"
                ),
                unit="R$/1k tokens",
                year=now_year if unit_cost is not None else None,
            ),
            active_users=AdminAiMetricKpiItem(
                value=float(active_users) if active_users is not None else None,
                formatted=(
                    _format_thousands_dot(active_users)
                    if active_users is not None
                    else "Sem dados"
                ),
                unit="usuários",
                year=now_year if active_users is not None else None,
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
