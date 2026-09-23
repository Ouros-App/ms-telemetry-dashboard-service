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
    cpu_values = [
        item.average_cpu_cores
        for item in resources
        if item.average_cpu_cores is not None
    ]
    return ResourceUsage(
        resident_memory_bytes=resident or None,
        average_cpu_cores=(
            _rounded(sum(cpu_values), 6)
            if cpu_values
            else None
        ),
    )


def _assumptions() -> list[str]:
    return [
        "Os valores sao medias acumuladas desde o ultimo restart dos processos.",
        "O custo por token usa preco de lista versionado, nao o valor efetivamente pago.",
        "NVIDIA NIM e outros modelos sem preco por token ficam fora da estimativa monetaria.",
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
            current_chat_in_flight=None,
            current_llm_in_flight=None,
            current_mcp_in_flight=None,
            assumptions=_assumptions(),
        )

    chats = max(midas.chat_requests - midas.blocked_requests, 0)
    llm_calls = sum(item.requests + item.failed_requests for item in midas.llm)
    input_tokens = sum(item.input_tokens for item in midas.llm)
    output_tokens = sum(item.output_tokens for item in midas.llm)
    mcp_calls = sum(
        item.requests + item.failed_requests for item in midas.mcp_calls
    )
    mcp_duration = sum(item.latency.total_seconds for item in midas.mcp_calls)
    mcp_duration_count = sum(item.latency.count for item in midas.mcp_calls)
    midas_resources = _resources_for_kind(summary.services, "midas")
    mcp_resources = _resources_for_kind(summary.services, "knowledge_mcp")

    return CapacityBaselineResponse(
        generated_at=summary.generated_at,
        sample_basis=summary.aggregation,
        chat_requests=chats,
        average_chat_latency_ms=midas.chat_latency.average_ms,
        llm_calls_per_chat=_rounded(llm_calls / chats, 4) if chats else None,
        input_tokens_per_chat=_rounded(input_tokens / chats, 4) if chats else None,
        output_tokens_per_chat=_rounded(output_tokens / chats, 4) if chats else None,
        mcp_calls_per_chat=_rounded(mcp_calls / chats, 4) if chats else None,
        average_mcp_latency_ms=(
            _rounded(mcp_duration / mcp_duration_count * 1000, 3)
            if mcp_duration_count
            else None
        ),
        estimated_token_cost_usd_per_chat=(
            _rounded(summary.cost.estimated_token_cost_usd / chats, 8)
            if chats
            else None
        ),
        unpriced_tokens_per_chat=(
            _rounded(summary.cost.unpriced_tokens / chats, 4)
            if chats
            else None
        ),
        midas_average_cpu_cores=(
            midas_resources.average_cpu_cores
            if midas_resources is not None
            else None
        ),
        midas_resident_memory_bytes=(
            midas_resources.resident_memory_bytes
            if midas_resources is not None
            else None
        ),
        knowledge_mcp_average_cpu_cores=(
            mcp_resources.average_cpu_cores
            if mcp_resources is not None
            else None
        ),
        knowledge_mcp_resident_memory_bytes=(
            mcp_resources.resident_memory_bytes
            if mcp_resources is not None
            else None
        ),
        current_chat_in_flight=midas.current_chat_in_flight,
        current_llm_in_flight=midas.current_llm_in_flight,
        current_mcp_in_flight=midas.current_mcp_in_flight,
        assumptions=_assumptions(),
    )
