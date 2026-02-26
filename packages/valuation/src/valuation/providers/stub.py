from __future__ import annotations

from statistics import median

from valuation.types import MarketComp, ValuationRequest

from .base import CompsProvider


class StubCompsProvider(CompsProvider):
    name = "stub"
    last_debug: dict[str, object]

    def __init__(self) -> None:
        self.last_debug = {}

    def fetch_comps(self, request: ValuationRequest) -> list[MarketComp]:
        brand = request.brand
        category = request.category
        seed = (sum(ord(c) for c in f"{brand}:{category}") % 180) + 40
        base = float(seed)
        if category == "handbag":
            base *= 6.5
        elif category == "shoes":
            base *= 2.1
        else:
            base *= 1.6

        comps: list[MarketComp] = []
        for i, mult in enumerate([0.82, 0.91, 0.97, 1.0, 1.06, 1.14, 1.26], start=1):
            comps.append(
                MarketComp(
                    source="stub",
                    title=f"{brand} {category} comp {i}",
                    price=round(base * mult, 2),
                    currency="USD",
                    is_sold=True,
                    condition_text="Pre-owned",
                    sold_at=f"2026-01-{10 + i:02d}",
                    url=f"https://example.test/stub/{brand}/{category}/{i}",
                )
            )
        self.last_debug = {
            "status": "ok",
            "query": f"{brand} {category}",
            "generated_count": len(comps),
            "reason": "deterministic_stub_comps",
        }
        return comps
