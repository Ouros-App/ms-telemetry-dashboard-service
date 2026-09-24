from app.core.config import TelemetryTargetKind
from app.schemas.telemetry import (
    CapacityBaselineResponse,
    ResourceUsage,
    ServiceScrapeStatus,
    TelemetrySummaryResponse,
)


def _rounded(value: float, digits: int = 6) -> float:
    return round(value, digits)


def _resources_for_kind(
    statuses: list[ServiceScrapeStatus],
    kind: str,
) -> ResourceUsage | None:
    resources = [
        status.resources
        for status in statuses
        if status.kind == kind and status.resources is not None
    ]
    if not resources:
        return None
    resident = sum(item.resident_memory_bytes or 0 for item in resources)
    cpu_seconds_values = [
        item.cpu_seconds_total
        for item in resources
        if item.cpu_seconds_total is not None
    ]
    uptime_values = [
        item.process_uptime_seconds
        for item in resources
        if item.process_uptime_seconds is not None
    ]
    cpu_values = [
        item.average_cpu_cores
        for item in resources
        if item.average_cpu_cores is not None
    ]
    return ResourceUsage(
        process_uptime_seconds=(
            _rounded(max(uptime_values), 3)
            if uptime_values
            else None
        ),
        resident_memory_bytes=resident or None,
        cpu_seconds_total=(
            _rounded(sum(cpu_seconds_values), 6)
            if cpu_seconds_values
            else None
        ),
        average_cpu_cores=(
            _rounded(sum(cpu_values), 6)
            if cpu_values
            else None
        ),
    )


def _safe_ratio(
    numerator: float,
    denominator: int,
    digits: int,
    *,
    multiplier: float = 1.0,
) -> float | None:
    if denominator <= 0:
        return None
    return _rounded(numerator / denominator * multiplier, digits)


def _resource_value(
    resources: ResourceUsage | None,
    attribute: str,
):
    return getattr(resources, attribute) if resources is not None else None


def _midas_cpu_seconds_per_chat(
    resources: ResourceUsage | None,
    chats: int,
) -> float | None:
    if resources is None or resources.cpu_seconds_total is None:
        return None
    return _safe_ratio(resources.cpu_seconds_total, chats, 6)


def _mcp_cpu_seconds_per_tool(
    resources: ResourceUsage | None,
    tool_calls: int,
) -> float | None:
    if resources is None or resources.cpu_seconds_total is None:
        return None
    return _safe_ratio(resources.cpu_seconds_total, tool_calls, 6)


def _knowledge_mcp_call_count(
    summary: TelemetrySummaryResponse,
) -> int:
    if summary.knowledge_mcp is None:
        return 0
    return sum(
        item.requests + item.failed_requests + item.cancelled_requests
        for item in summary.knowledge_mcp.tools
    )


def _assumptions() -> list[str]:
    return [
        "Os valores sao medias acumuladas desde o ultimo restart dos processos.",
        "O custo por token usa preco de lista versionado, nao o valor efetivamente pago.",
        "Modelos sem preco publico por token ficam fora da estimativa monetaria.",
        "CPU media usa process_cpu_seconds_total dividido pelo uptime e e uma aproximacao de cores ocupados no periodo.",
        "RAM e concorrencia sao snapshots/medias operacionais, nao limites de capacidade.",
        "O baseline nao escolhe hardware, replicas ou margem de seguranca; ele fornece entradas para um simulador posterior.",
    ]


def build_capacity_baseline(
    summary: TelemetrySummaryResponse,
) -> CapacityBaselineResponse:
    midas = summary.midas
    if midas is None:
        return CapacityBaselineResponse(
            generated_at=summary.generated_at,
            sample_basis=summary.aggregation,
            chat_requests=0,
            average_chat_latency_ms=None,
            llm_calls_per_chat=None,
            input_tokens_per_chat=None,
            output_tokens_per_chat=None,
            mcp_calls_per_chat=None,
            average_mcp_latency_ms=None,
            estimated_token_cost_usd_per_chat=None,
            unpriced_tokens_per_chat=None,
            midas_average_cpu_cores=None,
            midas_resident_memory_bytes=None,
            knowledge_mcp_average_cpu_cores=None,
            knowledge_mcp_resident_memory_bytes=None,
            midas_process_uptime_seconds=None,
            midas_cpu_seconds_per_chat=None,
            knowledge_mcp_process_uptime_seconds=None,
            knowledge_mcp_cpu_seconds_per_tool_call=None,
            current_chat_in_flight=None,
            current_llm_in_flight=None,
            current_mcp_in_flight=None,
            assumptions=_assumptions(),
        )

    chats = max(midas.chat_requests - midas.blocked_requests, 0)
    llm_calls = sum(
        item.requests + item.failed_requests + item.cancelled_requests
        for item in midas.llm
    )
    input_tokens = sum(item.input_tokens for item in midas.llm)
    output_tokens = sum(item.output_tokens for item in midas.llm)
    mcp_calls = sum(
        item.requests + item.failed_requests + item.cancelled_requests
        for item in midas.mcp_calls
    )
    mcp_duration = sum(item.latency.total_seconds for item in midas.mcp_calls)
    mcp_duration_count = sum(item.latency.count for item in midas.mcp_calls)

    midas_resources = _resources_for_kind(
        summary.services,
        TelemetryTargetKind.MIDAS,
    )
    mcp_resources = _resources_for_kind(
        summary.services,
        TelemetryTargetKind.KNOWLEDGE_MCP,
    )
    knowledge_mcp_calls = _knowledge_mcp_call_count(summary)

    return CapacityBaselineResponse(
        generated_at=summary.generated_at,
        sample_basis=summary.aggregation,
        chat_requests=chats,
        average_chat_latency_ms=midas.chat_latency.average_ms,
        llm_calls_per_chat=_safe_ratio(llm_calls, chats, 4),
        input_tokens_per_chat=_safe_ratio(input_tokens, chats, 4),
        output_tokens_per_chat=_safe_ratio(output_tokens, chats, 4),
        mcp_calls_per_chat=_safe_ratio(mcp_calls, chats, 4),
        average_mcp_latency_ms=_safe_ratio(
            mcp_duration,
            mcp_duration_count,
            3,
            multiplier=1000,
        ),
        estimated_token_cost_usd_per_chat=_safe_ratio(
            summary.cost.estimated_token_cost_usd,
            chats,
            8,
        ),
        unpriced_tokens_per_chat=_safe_ratio(
            summary.cost.unpriced_tokens,
            chats,
            4,
        ),
        midas_average_cpu_cores=_resource_value(
            midas_resources,
            "average_cpu_cores",
        ),
        midas_resident_memory_bytes=_resource_value(
            midas_resources,
            "resident_memory_bytes",
        ),
        knowledge_mcp_average_cpu_cores=_resource_value(
            mcp_resources,
            "average_cpu_cores",
        ),
        knowledge_mcp_resident_memory_bytes=_resource_value(
            mcp_resources,
            "resident_memory_bytes",
        ),
        midas_process_uptime_seconds=_resource_value(
            midas_resources,
            "process_uptime_seconds",
        ),
        midas_cpu_seconds_per_chat=_midas_cpu_seconds_per_chat(
            midas_resources,
            chats,
        ),
        knowledge_mcp_process_uptime_seconds=_resource_value(
            mcp_resources,
            "process_uptime_seconds",
        ),
        knowledge_mcp_cpu_seconds_per_tool_call=_mcp_cpu_seconds_per_tool(
            mcp_resources,
            knowledge_mcp_calls,
        ),
        current_chat_in_flight=midas.current_chat_in_flight,
        current_llm_in_flight=midas.current_llm_in_flight,
        current_mcp_in_flight=midas.current_mcp_in_flight,
        assumptions=_assumptions(),
    )
