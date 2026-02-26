from __future__ import annotations
import re

from valuation.types import MarketComp, ValuationRequest

from .base import CompsProvider
from .http_utils import (
    best_title,
    best_url,
    build_request_url,
    extract_json_ld_objects,
    extract_next_data,
    extract_price_from_obj,
    fetch_firecrawl_markdown,
    firecrawl_enabled,
    fetch_page,
    query_for_request,
    walk_json,
)


class RebagProvider(CompsProvider):
    name = "rebag"
    last_debug: dict[str, object]

    def __init__(self) -> None:
        self.last_debug = {}

    def fetch_comps(self, request: ValuationRequest) -> list[MarketComp]:
        query = query_for_request(request.brand, request.category, request.model_hint, request.title_hint)
        html = None
        fetched_from = None
        request_url = None
        for url in ("https://shop.rebag.com/search", "https://rebag.com/search"):
            try:
                params = {"q": query}
                request_url = build_request_url(url, params)
                html = fetch_page(url, params=params)
                fetched_from = url
                break
            except Exception:
                continue
        if not html:
            self.last_debug = {
                "status": "empty",
                "reason": "fetch_failed_all_urls",
                "query": query,
                "request_url": request_url,
                "used_firecrawl": firecrawl_enabled(),
            }
            return []
        comps, parser_meta = self._parse(html)
        parser_path = "html_structured" if comps else None
        markdown_length = 0
        markdown_candidate_lines = 0
        if not comps and firecrawl_enabled() and request_url:
            markdown = fetch_firecrawl_markdown(request_url)
            if markdown:
                markdown_length = len(markdown)
                comps, markdown_candidate_lines = self._parse_markdown(markdown)
                if comps:
                    parser_path = "firecrawl_markdown"
        self.last_debug = {
            "status": "ok" if comps else "empty",
            "reason": (
                f"parsed_{parser_path}_listings" if parser_path else "no_parsable_listings"
            ),
            "query": query,
            "request_url": request_url,
            "used_firecrawl": firecrawl_enabled(),
            "parsed_count": len(comps),
            "fetched_from": fetched_from,
            "html_length": len(html),
            "markdown_length": markdown_length,
            "markdown_candidate_lines": markdown_candidate_lines,
            "parser_path": parser_path,
            **parser_meta,
        }
        return comps

    def _parse(self, html: str) -> tuple[list[MarketComp], dict]:
        out: list[MarketComp] = []
        seen: set[tuple[str, float]] = set()
        json_ld = extract_json_ld_objects(html)
        json_ld_count = len(json_ld)

        for ld in json_ld:
            nodes = [ld]
            if isinstance(ld.get("@graph"), list):
                nodes.extend([n for n in ld["@graph"] if isinstance(n, dict)])
            for obj in nodes:
                if str(obj.get("@type", "")).lower() not in {"product", "offer"}:
                    continue
                title = str(obj.get("name") or "Unknown item")
                offers = obj.get("offers") if isinstance(obj.get("offers"), dict) else obj
                price, currency = extract_price_from_obj(offers if isinstance(offers, dict) else obj)
                if price is None:
                    continue
                key = (title, float(price))
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    MarketComp(
                        source="rebag",
                        title=title,
                        price=float(price),
                        currency=currency or "USD",
                        is_sold=False,
                        url=best_url(obj, "https://rebag.com"),
                    )
                )

        next_data = extract_next_data(html)
        if next_data:
            for obj in walk_json(next_data):
                if not isinstance(obj, dict):
                    continue
                price, currency = extract_price_from_obj(obj)
                if price is None:
                    continue
                title = best_title(obj)
                key = (title, float(price))
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    MarketComp(
                        source="rebag",
                        title=title,
                        price=float(price),
                        currency=currency or "USD",
                        is_sold=False,
                        url=best_url(obj, "https://rebag.com"),
                        metadata={"raw_keys": list(obj.keys())[:20]},
                    )
                )
                if len(out) >= 25:
                    break
        return out[:25], {"json_ld_count": json_ld_count, "next_data_found": bool(next_data)}

    def _parse_markdown(self, markdown: str) -> tuple[list[MarketComp], int]:
        out: list[MarketComp] = []
        seen: set[tuple[str, float]] = set()
        candidate_lines = 0
        lines = [ln.strip() for ln in markdown.splitlines() if ln.strip()]
        price_re = re.compile(r"\$([0-9][0-9,]*(?:\.[0-9]{2})?)")
        for i, line in enumerate(lines):
            m = price_re.search(line)
            if not m:
                continue
            candidate_lines += 1
            price = float(m.group(1).replace(",", ""))
            title = line if len(line) >= 8 else (lines[i - 1] if i > 0 else line)
            title = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", title)
            title = price_re.sub("", title).strip(" -|:")
            if len(title) < 4:
                continue
            key = (title, price)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                MarketComp(
                    source="rebag",
                    title=title,
                    price=price,
                    currency="USD",
                    is_sold=False,
                    condition_text="Unknown",
                    url=None,
                    metadata={"parsed_from": "firecrawl_markdown"},
                )
            )
            if len(out) >= 25:
                break
        return out, candidate_lines
