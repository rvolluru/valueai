from __future__ import annotations
import re

from valuation.types import MarketComp, ValuationRequest

from .base import CompsProvider
from .http_utils import (
    best_title,
    best_url,
    build_request_url,
    extract_embedded_json_objects,
    extract_json_ld_objects,
    extract_next_data,
    extract_price_from_obj,
    fetch_firecrawl_markdown,
    firecrawl_enabled,
    fetch_page,
    query_for_request,
    walk_json,
)


class PoshmarkProvider(CompsProvider):
    name = "poshmark"
    last_debug: dict[str, object]

    def __init__(self) -> None:
        self.last_debug = {}

    def fetch_comps(self, request: ValuationRequest) -> list[MarketComp]:
        query = query_for_request(request.brand, request.category, request.model_hint, request.title_hint)
        params = {"query": query}
        request_url = build_request_url("https://poshmark.com/search", params)
        try:
            html = fetch_page("https://poshmark.com/search", params=params)
        except Exception as exc:
            self.last_debug = {
                "status": "error",
                "reason": "fetch_failed",
                "query": query,
                "request_url": request_url,
                "used_firecrawl": firecrawl_enabled(),
                "error": str(exc),
            }
            return []
        next_data = extract_next_data(html)
        json_ld = extract_json_ld_objects(html)
        embedded = extract_embedded_json_objects(html)

        out: list[MarketComp] = []
        parser_path = None
        markdown_length = 0
        markdown_candidate_lines = 0
        if next_data:
            out = self._parse_objects([next_data], site_origin="https://poshmark.com", from_walk_json=True)
            if out:
                parser_path = "next_data"

        if not out and json_ld:
            out = self._parse_objects(json_ld, site_origin="https://poshmark.com", from_walk_json=True)
            if out:
                parser_path = "json_ld"

        if not out and embedded:
            out = self._parse_objects(embedded, site_origin="https://poshmark.com", from_walk_json=True)
            if out:
                parser_path = "embedded_json"

        if not out and firecrawl_enabled():
            markdown = fetch_firecrawl_markdown(request_url)
            if markdown:
                markdown_length = len(markdown)
                out, markdown_candidate_lines = self._parse_markdown(markdown)
                if out:
                    parser_path = "firecrawl_markdown"

        self.last_debug = {
            "status": "ok" if out else "empty",
            "reason": (
                f"parsed_{parser_path}_listings"
                if out and parser_path
                else ("missing_next_data" if not next_data else "no_parsable_listings")
            ),
            "query": query,
            "request_url": request_url,
            "used_firecrawl": firecrawl_enabled(),
            "next_data_found": bool(next_data),
            "json_ld_count": len(json_ld),
            "embedded_json_count": len(embedded),
            "markdown_length": markdown_length,
            "markdown_candidate_lines": markdown_candidate_lines,
            "parser_path": parser_path,
            "html_length": len(html),
            "parsed_count": len(out),
        }
        return out

    def _parse_objects(
        self, roots: list[dict], site_origin: str, from_walk_json: bool = True
    ) -> list[MarketComp]:
        out: list[MarketComp] = []
        seen: set[tuple[str, float]] = set()
        iterable = []
        for root in roots:
            if from_walk_json:
                iterable.extend(list(walk_json(root)))
            else:
                iterable.append(root)
        for obj in iterable:
            if not isinstance(obj, dict):
                continue
            price, currency = extract_price_from_obj(obj)
            if price is None:
                continue
            title = best_title(obj)
            status_blob = " ".join(
                str(obj.get(k, "")) for k in ("status", "inventory_status", "availability", "state")
            ).lower()
            is_sold = any(s in status_blob for s in ("sold", "not for sale"))
            key = (title, float(price))
            if key in seen:
                continue
            seen.add(key)
            out.append(
                MarketComp(
                    source="poshmark",
                    title=title,
                    price=float(price),
                    currency=currency or "USD",
                    is_sold=is_sold,
                    condition_text=str(obj.get("condition") or obj.get("condition_text") or "Unknown"),
                    url=best_url(obj, site_origin),
                    metadata={"raw_keys": list(obj.keys())[:20]},
                )
            )
            if len(out) >= 25:
                break
        return out

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
            # Use the same line or preceding line as a title guess.
            title = line
            if len(title) < 8 and i > 0:
                title = lines[i - 1]
            # Clean markdown link syntax.
            title = re.sub(r"^\s*[-*#>\d.\)\(]+\s*", "", title).strip()
            title = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", title)
            title = price_re.sub("", title).strip(" -|:")
            if not title or len(title) < 4:
                continue
            key = (title, price)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                MarketComp(
                    source="poshmark",
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
