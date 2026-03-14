from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
        provider_timings_ms: dict[str, float] = {}

        def run_provider(provider):
            started = time.perf_counter()
            try:
                provider_comps = provider.fetch_comps(request)
                stats = dict(getattr(provider, "last_debug", {}) or {})
                stats.setdefault("returned_comp_count", len(provider_comps))
                return provider.name, provider_comps, stats, None, round((time.perf_counter() - started) * 1000, 2)
            except Exception as exc:  # pragma: no cover
                return (
                    provider.name,
                    [],
                    {
                        "status": "error",
                        "reason": "exception",
                        "error": str(exc),
                        "returned_comp_count": 0,
                    },
                    str(exc),
                    round((time.perf_counter() - started) * 1000, 2),
                )

        max_workers = min(max(len(self.providers), 1), 6)
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(run_provider, provider): provider.name for provider in self.providers}
            for future in as_completed(future_map):
                provider_name, provider_comps, stats, error, elapsed_ms = future.result()
                comps.extend(provider_comps)
                provider_stats[provider_name] = stats
                provider_timings_ms[provider_name] = elapsed_ms
                if error is not None:
                    provider_errors[provider_name] = error
        result = estimate_value(request, comps, self.pricing_config, debug=debug)
        if debug:
            result.debug["providers"] = [p.name for p in self.providers]
            result.debug["provider_errors"] = provider_errors
            result.debug["provider_stats"] = provider_stats
            result.debug["provider_timings_ms"] = provider_timings_ms
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
            "resale_market_value": result.resale_market_value,
            "retail_reference_value": result.retail_reference_value,
        }
        if result.debug:
            payload["_debug"] = result.debug
        return payload
