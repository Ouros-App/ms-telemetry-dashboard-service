from typing import Literal

from pydantic import BaseModel, Field


class AdminAiMetricKpiItem(BaseModel):
    value: float
    formatted: str
    unit: str | None = None
    year: int | None = None


class AdminAiMetricsKpisResponse(BaseModel):
    token_spend: AdminAiMetricKpiItem
    unit_cost: AdminAiMetricKpiItem
    active_users: AdminAiMetricKpiItem


class TokenSpendPoint(BaseModel):
    period: str
    label: str
    model: str = "Midas LLM"
    previous_year_tokens: int = 0
    current_year_tokens: int = 0
    previous_year_cost_brl: float = 0.0
    current_year_cost_brl: float = 0.0
    tokens: int = 0
    cost_brl: float = 0.0


class AdminTokenSpendChartResponse(BaseModel):
    items: list[TokenSpendPoint] = Field(default_factory=list)


class LatencyBucketItem(BaseModel):
    bucket: str
    label: str
    min_ms: int
    max_ms: int | None = None
    previous_year_count: int = 0
    current_year_count: int = 0
    count: int = 0
    percentage: float = 0.0
    avg_cost_brl: float = 0.0


class AdminLatencyDistributionResponse(BaseModel):
    items: list[LatencyBucketItem] = Field(default_factory=list)


class MidasSessionAuditItem(BaseModel):
    session_id: str
    user_id: int | str
    user_name: str
    account_type: str
    enterprise_id: int | None = None
    farm_id: int | None = None
    model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_brl: float
    latency_ms: int
    accuracy_rate: float = 100.0
    status: Literal["success", "error", "blocked", "timeout"] = "success"
    created_at: str


class AdminMidasSessionsResponse(BaseModel):
    total: int
    page: int
    limit: int
    items: list[MidasSessionAuditItem] = Field(default_factory=list)
