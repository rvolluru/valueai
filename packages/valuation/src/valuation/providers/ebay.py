from __future__ import annotations

import os
from typing import Any

from valuation.types import MarketComp, ValuationRequest

from .base import CompsProvider
from .http_utils import build_request_url, firecrawl_enabled, http_get_json, query_for_request


EBAY_FINDING_URL = "https://svcs.ebay.com/services/search/FindingService/v1"


class EbaySoldProvider(CompsProvider):
    name = "ebay"
    last_debug: dict[str, object]

    def __init__(self) -> None:
        self.last_debug = {}

    def fetch_comps(self, request: ValuationRequest) -> list[MarketComp]:
        app_id = os.getenv("EBAY_APP_ID")
        query = query_for_request(request.brand, request.category, request.model_hint, request.title_hint)
        request_url = build_request_url(EBAY_FINDING_URL, {})
        if not app_id:
            self.last_debug = {
                "status": "skipped",
                "reason": "missing_ebay_app_id",
                "query": query,
                "request_url": request_url,
                "used_firecrawl": False,
            }
            return []

        params = {
            "OPERATION-NAME": "findCompletedItems",
            "SERVICE-VERSION": "1.13.0",
            "SECURITY-APPNAME": app_id,
            "RESPONSE-DATA-FORMAT": "JSON",
            "REST-PAYLOAD": "true",
            "keywords": query,
            "paginationInput.entriesPerPage": "20",
            "itemFilter(0).name": "SoldItemsOnly",
            "itemFilter(0).value": "true",
            "itemFilter(1).name": "LocatedIn",
            "itemFilter(1).value": "US",
        }
        try:
            data = http_get_json(EBAY_FINDING_URL, params=params)
        except Exception as exc:
            self.last_debug = {
                "status": "error",
                "reason": "http_or_api_error",
                "query": query,
                "request_url": build_request_url(EBAY_FINDING_URL, params),
                "used_firecrawl": False,
                "error": str(exc),
            }
            return []
        comps = self._parse_finding_response(data)
        self.last_debug = {
            "status": "ok" if comps else "empty",
            "reason": "parsed_completed_items" if comps else "no_completed_items",
            "query": query,
            "request_url": build_request_url(EBAY_FINDING_URL, params),
            "used_firecrawl": False,
            "parsed_count": len(comps),
        }
        return comps

    def _parse_finding_response(self, data: dict[str, Any]) -> list[MarketComp]:
        out: list[MarketComp] = []
        root = (data.get("findCompletedItemsResponse") or [{}])[0]
        search_result = (root.get("searchResult") or [{}])[0]
        items = search_result.get("item") or []
        for item in items:
            selling = (item.get("sellingStatus") or [{}])[0]
            price_obj = (selling.get("currentPrice") or [{}])[0]
            try:
                price = float(price_obj.get("__value__"))
            except Exception:
                continue
            if price <= 0:
                continue
            out.append(
                MarketComp(
                    source="ebay",
                    title=((item.get("title") or ["Unknown item"])[0]).strip(),
                    price=price,
                    currency=price_obj.get("@currencyId", "USD"),
                    is_sold=True,
                    condition_text=(item.get("condition") or [{}])[0].get("conditionDisplayName", [None])[0],
                    sold_at=(item.get("listingInfo") or [{}])[0].get("endTime", [None])[0],
                    url=(item.get("viewItemURL") or [None])[0],
                    metadata={"raw_item_id": (item.get("itemId") or [None])[0]},
                )
            )
        return out
