from datetime import datetime

from pydantic import BaseModel, Field


class LatencySummary(BaseModel):
    count: int = 0
    total_seconds: float = 0.0
    average_ms: float | None = None
    p50_ms: float | None = None
    p95_ms: float | None = None
    p99_ms: float | None = None


class ResourceUsage(BaseModel):
    process_uptime_seconds: float | None = None
    resident_memory_bytes: int | None = None
    virtual_memory_bytes: int | None = None
    cpu_seconds_total: float | None = None
    average_cpu_cores: float | None = None
    open_fds: int | None = None
    max_fds: int | None = None


class ServiceScrapeStatus(BaseModel):
    name: str
    kind: str
    available: bool
    scrape_duration_ms: float
    resources: ResourceUsage | None = None
    http_requests: int | None = None
    http_errors: int | None = None
    http_latency: LatencySummary | None = None
    error: str | None = None


class ModelUsage(BaseModel):
    profile: str
    model: str
    requests: int
    failed_requests: int
    input_tokens: int
    cached_input_tokens: int
    output_tokens: int
    latency: LatencySummary
    pricing_mode: str
    provider: str | None = None
    estimated_cost_usd: float | None = None
    pricing_source: str | None = None
    pricing_note: str | None = None


class ToolUsage(BaseModel):
    tool: str
    requests: int
    failed_requests: int
    latency: LatencySummary


class MidasTelemetry(BaseModel):
    chat_requests: int
    blocked_requests: int
    failed_requests: int
    current_chat_in_flight: float
    current_llm_in_flight: float
    current_mcp_in_flight: float
    chat_latency: LatencySummary
    llm: list[ModelUsage] = Field(default_factory=list)
    mcp_calls: list[ToolUsage] = Field(default_factory=list)


class KnowledgeMcpTelemetry(BaseModel):
    http_requests: int
    current_tool_in_flight: float
    http_latency: LatencySummary
    tools: list[ToolUsage] = Field(default_factory=list)


class CostSummary(BaseModel):
    currency: str = "USD"
    pricing_as_of: str | None = None
    estimated_token_cost_usd: float
    priced_input_tokens: int
    priced_output_tokens: int
    unpriced_tokens: int
    note: str


class TelemetrySummaryResponse(BaseModel):
    generated_at: datetime
    aggregation: str
    resets_on_process_restart: bool
    services: list[ServiceScrapeStatus]
    midas: MidasTelemetry | None = None
    knowledge_mcp: KnowledgeMcpTelemetry | None = None
    cost: CostSummary


class CapacityBaselineResponse(BaseModel):
    generated_at: datetime
    sample_basis: str
    chat_requests: int
    average_chat_latency_ms: float | None
    llm_calls_per_chat: float | None
    input_tokens_per_chat: float | None
    output_tokens_per_chat: float | None
    mcp_calls_per_chat: float | None
    average_mcp_latency_ms: float | None
    estimated_token_cost_usd_per_chat: float | None
    unpriced_tokens_per_chat: float | None
    midas_average_cpu_cores: float | None
    midas_resident_memory_bytes: int | None
    knowledge_mcp_average_cpu_cores: float | None
    knowledge_mcp_resident_memory_bytes: int | None
    current_chat_in_flight: float | None
    current_llm_in_flight: float | None
    current_mcp_in_flight: float | None
    assumptions: list[str]
