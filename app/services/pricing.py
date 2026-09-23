import json
from pathlib import Path
from typing import Any

from app.schemas.telemetry import CostSummary, MidasTelemetry


class PricingCatalog:
    def __init__(self, path: Path) -> None:
        self.payload = self._load(path)

    @staticmethod
    def _load(path: Path) -> dict[str, Any]:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {"as_of": None, "currency": "USD", "models": {}}
        if not isinstance(payload, dict) or not isinstance(
            payload.get("models"),
            dict,
        ):
            return {"as_of": None, "currency": "USD", "models": {}}
        return payload

    def model(self, model_name: str) -> dict[str, Any]:
        models = self.payload.get("models", {})
        value = models.get(model_name, {}) if isinstance(models, dict) else {}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def model_cost(
        pricing: dict[str, Any],
        input_tokens: int,
        cached_tokens: int,
        output_tokens: int,
    ) -> float | None:
        if pricing.get("pricing_mode") != "token":
            return None
        input_rate = pricing.get("input_usd_per_million")
        output_rate = pricing.get("output_usd_per_million")
        if not isinstance(input_rate, (int, float)) or not isinstance(
            output_rate,
            (int, float),
        ):
            return None
        cached_rate = pricing.get("cached_input_usd_per_million", input_rate)
        if not isinstance(cached_rate, (int, float)):
            cached_rate = input_rate

        cached = min(max(cached_tokens, 0), max(input_tokens, 0))
        uncached = max(input_tokens - cached, 0)
        cost = (
            uncached * float(input_rate)
            + cached * float(cached_rate)
            + max(output_tokens, 0) * float(output_rate)
        ) / 1_000_000
        return round(cost, 8)

    def summary(self, midas: MidasTelemetry | None) -> CostSummary:
        priced_input = 0
        priced_output = 0
        unpriced = 0
        estimated = 0.0
        for usage in midas.llm if midas is not None else []:
            if usage.estimated_cost_usd is None:
                unpriced += usage.input_tokens + usage.output_tokens
                continue
            priced_input += usage.input_tokens
            priced_output += usage.output_tokens
            estimated += usage.estimated_cost_usd
        return CostSummary(
            currency=str(self.payload.get("currency") or "USD"),
            pricing_as_of=(
                str(self.payload["as_of"])
                if self.payload.get("as_of")
                else None
            ),
            estimated_token_cost_usd=round(estimated, 8),
            priced_input_tokens=priced_input,
            priced_output_tokens=priced_output,
            unpriced_tokens=unpriced,
            note=(
                "Estimativa de custo de lista, nao fatura real. Modelos com "
                "precificacao por infraestrutura ficam em unpriced_tokens."
            ),
        )
