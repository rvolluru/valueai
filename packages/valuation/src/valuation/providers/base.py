from __future__ import annotations

from abc import ABC, abstractmethod

from valuation.types import MarketComp, ValuationRequest


class CompsProvider(ABC):
    name: str
    last_debug: dict

    @abstractmethod
    def fetch_comps(self, request: ValuationRequest) -> list[MarketComp]:
        raise NotImplementedError
