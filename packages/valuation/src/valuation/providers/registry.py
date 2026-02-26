from __future__ import annotations

from valuation.providers.base import CompsProvider
from valuation.providers.ebay import EbaySoldProvider
from valuation.providers.poshmark import PoshmarkProvider
from valuation.providers.rebag import RebagProvider
from valuation.providers.stub import StubCompsProvider
from valuation.providers.the_realreal import TheRealRealProvider


PROVIDER_MAP = {
    "stub": StubCompsProvider,
    "ebay": EbaySoldProvider,
    "poshmark": PoshmarkProvider,
    "the_realreal": TheRealRealProvider,
    "rebag": RebagProvider,
}


def build_providers(names: list[str]) -> list[CompsProvider]:
    providers: list[CompsProvider] = []
    for name in names:
        cls = PROVIDER_MAP.get(name)
        if cls is None:
            continue
        providers.append(cls())
    return providers
