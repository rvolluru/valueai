from __future__ import annotations

from typing import Any

from .config import ValuationConfig
from .engine import PricingConfig, estimate_value
from .providers import build_providers
from .types import MarketComp, ValuationRequest, ValuationResult


class ValuationService:
    def __init__(self, config: ValuationConfig | None = None):
        self.config = config or ValuationConfig()
        self.providers = build_providers(self.config.providers)
        self.pricing_config = PricingConfig(
            min_comps=self.config.min_comps,
            max_comps=self.config.max_comps,
            currency=self.config.currency,
        )

    def evaluate(self, request: ValuationRequest, debug: bool = False) -> ValuationResult:
        comps: list[MarketComp] = []
        provider_errors: dict[str, str] = {}
        provider_stats: dict[str, dict[str, Any]] = {}
        for provider in self.providers:
            try:
                provider_comps = provider.fetch_comps(request)
                comps.extend(provider_comps)
                stats = dict(getattr(provider, "last_debug", {}) or {})
                stats.setdefault("returned_comp_count", len(provider_comps))
                provider_stats[provider.name] = stats
            except Exception as exc:  # pragma: no cover
                provider_errors[provider.name] = str(exc)
                provider_stats[provider.name] = {
                    "status": "error",
                    "reason": "exception",
                    "error": str(exc),
                    "returned_comp_count": 0,
                }
        result = estimate_value(request, comps, self.pricing_config, debug=debug)
        if debug:
            result.debug["providers"] = [p.name for p in self.providers]
            result.debug["provider_errors"] = provider_errors
            result.debug["provider_stats"] = provider_stats
            result.debug["raw_comp_count"] = len(comps)
        return result

    @staticmethod
    def serialize(result: ValuationResult) -> dict[str, Any]:
        payload = {
            "estimated_value": result.estimated_value,
            "currency": result.currency,
            "range_low": result.range_low,
            "range_high": result.range_high,
            "confidence": result.confidence,
            "basis": result.basis,
            "comps_summary": result.comps_summary,
        }
        if result.debug:
            payload["_debug"] = result.debug
        return payload
