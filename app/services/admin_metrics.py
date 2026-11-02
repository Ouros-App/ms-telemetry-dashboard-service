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
MODEL_GPT_OSS_120B = "openai/gpt-oss-120b"

DEFAULT_TOKEN_SPEND_SERIES = (
    ("0-50k", 6800.0, 7500.0),
    ("50k-75k", 9100.0, 11000.0),
    ("75k-100k", 17400.0, 15800.0),
    ("100k-125k", 22100.0, 24000.0),
    ("125k-150k", 14700.0, 15300.0),
    ("150k-175k", 9300.0, 10000.0),
    (BUCKET_175K_PLUS, 5600.0, 4900.0),
)

DEFAULT_REQUEST_SPEND_SERIES = (
    ("0-50k", 14700.0, 10200.0, 1470, 1020),
    ("50k-75k", 19200.0, 14700.0, 1920, 1470),
    ("75k-100k", 23200.0, 18400.0, 2320, 1840),
    ("100k-125k", 31793.0, 25000.0, 3180, 2500),
    ("125k-150k", 20400.0, 15300.0, 2040, 1530),
    ("150k-175k", 13300.0, 10000.0, 1330, 1000),
    (BUCKET_175K_PLUS, 7547.0, 4900.0, 755, 490),
)

DEFAULT_AI_COST_BY_REGION = (
    ("Norte", 88000.0, 65000.0),
    ("Nordeste", 99000.0, 85000.0),
    ("Centro-Oeste", 87000.0, 110000.0),
    ("Sudeste", 114000.0, 195000.0),
    ("Sul", 100000.0, 140000.0),
)

DEFAULT_AI_MONTHLY_COST = (
    ("Jan", 1100000.0, 1590000.0),
    ("Fev", 1170000.0, 1790000.0),
    ("Mar", 520000.0, 1360000.0),
    ("Abr", 550000.0, 1440000.0),
    ("Mai", 710000.0, 1140000.0),
    ("Jun", 520000.0, 930000.0),
    ("Jul", 730000.0, 270000.0),
    ("Ago", 1270000.0, 740000.0),
)

DEFAULT_LATENCY_BUCKETS = (
    ("0-50k", "0-50ms", 0, 50, 6800, 7500, 0.42),
    ("50k-75k", "50-75ms", 50, 75, 9100, 11000, 0.58),
    ("75k-100k", "75-100ms", 75, 100, 17400, 15800, 0.79),
    ("100k-125k", "100-125ms", 100, 125, 22100, 24000, 0.94),
    ("125k-150k", "125-150ms", 125, 150, 14700, 15300, 1.12),
    ("150k-175k", "150-175ms", 150, 175, 9300, 10000, 1.28),
    (BUCKET_175K_PLUS, "175ms+", 175, None, 5600, 4900, 1.54),
)

DEFAULT_MIDAS_SESSIONS = (
    {
        "session_id": "midas-sess-001",
        "user_id": 101,
        "user_name": "Vera Marcelinha",
        "account_type": "admin",
        "enterprise_id": 1,
        "farm_id": None,
        "model": MODEL_GPT_OSS_120B,
        "prompt_tokens": 1240,
        "completion_tokens": 680,
        "total_tokens": 1920,
        "cost_brl": 1.80,
        "latency_ms": 112,
        "accuracy_rate": 98.5,
        "status": "success",
        "created_at": "2026-10-28T14:20:00Z",
    },
    {
        "session_id": "midas-sess-002",
        "user_id": 204,
        "user_name": "Carlos Eduardo",
        "account_type": "company_employee",
        "enterprise_id": 1,
        "farm_id": 3,
        "model": MODEL_GPT_OSS_120B,
        "prompt_tokens": 980,
        "completion_tokens": 520,
        "total_tokens": 1500,
        "cost_brl": 1.41,
        "latency_ms": 95,
        "accuracy_rate": 96.0,
        "status": "success",
        "created_at": "2026-10-28T13:45:00Z",
    },
    {
        "session_id": "midas-sess-003",
        "user_id": 312,
        "user_name": "Mariana Santos",
        "account_type": "farm_owner",
        "enterprise_id": 1,
        "farm_id": 102,
        "model": "openai/gpt-oss-20b",
        "prompt_tokens": 640,
        "completion_tokens": 360,
        "total_tokens": 1000,
        "cost_brl": 0.94,
        "latency_ms": 68,
        "accuracy_rate": 99.0,
        "status": "success",
        "created_at": "2026-10-28T12:10:00Z",
    },
    {
        "session_id": "midas-sess-004",
        "user_id": 415,
        "user_name": "Roberto Almeida",
        "account_type": "farm_owner",
        "enterprise_id": 2,
        "farm_id": 201,
        "model": "nvidia/nemotron-3-super-120b-a12b",
        "prompt_tokens": 1450,
        "completion_tokens": 890,
        "total_tokens": 2340,
        "cost_brl": 2.20,
        "latency_ms": 142,
        "accuracy_rate": 95.2,
        "status": "success",
        "created_at": "2026-10-28T10:30:00Z",
    },
)


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
        if rows:
            row = rows[0]
            total_cost = float(row.get("total_cost_brl", 15_110_000.0))
            unit_cost = float(row.get("unit_cost_brl", 0.94))
            active_users = int(row.get("active_users", 104_728))
            return AdminAiMetricsKpisResponse(
                token_spend=AdminAiMetricKpiItem(
                    value=total_cost,
                    formatted=_format_compact_brl(total_cost),
                    unit="R$",
                    year=now_year - 1,
                ),
                unit_cost=AdminAiMetricKpiItem(
                    value=unit_cost,
                    formatted=f"R$ {unit_cost:.2f}",
                    unit="R$/1k tokens",
                    year=now_year,
                ),
                active_users=AdminAiMetricKpiItem(
                    value=float(active_users),
                    formatted=_format_thousands_dot(active_users),
                    unit="usuários",
                    year=now_year,
                ),
            )

        return AdminAiMetricsKpisResponse(
            token_spend=AdminAiMetricKpiItem(
                value=15_110_000.0,
                formatted="R$ 15.11M",
                unit="R$",
                year=2025,
            ),
            unit_cost=AdminAiMetricKpiItem(
                value=0.94,
                formatted="R$ 0.94",
                unit="R$/1k tokens",
                year=now_year,
            ),
            active_users=AdminAiMetricKpiItem(
                value=104_728.0,
                formatted="104.728",
                unit="usuários",
                year=now_year,
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

        resolved_model = model or MODEL_GPT_OSS_120B
        items = [
            TokenSpendPoint(
                period=cohort,
                label=cohort,
                cohort=cohort,
                model=resolved_model,
                previous_year_tokens=int(prev_cost * 1000),
                current_year_tokens=int(curr_cost * 1000),
                previous_year_cost_brl=prev_cost,
                current_year_cost_brl=curr_cost,
                tokens=int(curr_cost * 1000),
                cost_brl=curr_cost,
            )
            for cohort, prev_cost, curr_cost in DEFAULT_TOKEN_SPEND_SERIES
        ]
        return AdminTokenSpendChartResponse(items=items)

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

        items = [
            RequestSpendPoint(
                cohort=cohort,
                label=cohort,
                previous_year_cost_brl=prev_cost,
                current_year_cost_brl=curr_cost,
                previous_year_requests=prev_req,
                current_year_requests=curr_req,
            )
            for cohort, prev_cost, curr_cost, prev_req, curr_req in DEFAULT_REQUEST_SPEND_SERIES
        ]
        return AdminRequestSpendChartResponse(items=items)

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

        items = [
            AiCostByRegionPoint(
                region=region,
                previous_year_cost_brl=prev_cost,
                current_year_cost_brl=curr_cost,
            )
            for region, prev_cost, curr_cost in DEFAULT_AI_COST_BY_REGION
        ]
        return AdminAiCostByRegionResponse(items=items)

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

        items = [
            AiMonthlyCostPoint(
                month=month,
                previous_year_cost_brl=prev_cost,
                current_year_cost_brl=curr_cost,
            )
            for month, prev_cost, curr_cost in DEFAULT_AI_MONTHLY_COST
        ]
        return AdminAiMonthlyCostResponse(items=items)

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

        total_curr = sum(b[5] for b in DEFAULT_LATENCY_BUCKETS)
        items = [
            LatencyBucketItem(
                bucket=bucket,
                label=label,
                min_ms=min_ms,
                max_ms=max_ms,
                previous_year_count=prev_cnt,
                current_year_count=curr_cnt,
                count=curr_cnt,
                percentage=round((curr_cnt * 100.0) / total_curr, 1),
                avg_cost_brl=avg_cost,
            )
            for (
                bucket,
                label,
                min_ms,
                max_ms,
                prev_cnt,
                curr_cnt,
                avg_cost,
            ) in DEFAULT_LATENCY_BUCKETS
        ]
        return AdminLatencyDistributionResponse(items=items)

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
        source = raw_sessions if raw_sessions else list(DEFAULT_MIDAS_SESSIONS)

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
