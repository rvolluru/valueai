from __future__ import annotations

import re
from statistics import median
from typing import Any
from urllib.parse import quote_plus, urlparse

from valuation.types import MarketComp, ValuationRequest

from .base import CompsProvider
from .http_utils import firecrawl_api_key, firecrawl_base_url, provider_timeout_s, query_for_request
from .http_utils import _firecrawl_scrape_data  # reuse Firecrawl scrape transport


RETAIL_DOMAINS = {
    "jimmychoo.com",
    "gucci.com",
    "prada.com",
    "adidas.com",
    "nike.com",
    "coach.com",
    "michaelkors.com",
    "neimanmarcus.com",
    "nordstrom.com",
    "saksfifthavenue.com",
    "bergdorfgoodman.com",
    "bloomingdales.com",
    "farfetch.com",
}

RESALE_DOMAINS = {
    "ebay.com",
    "poshmark.com",
    "therealreal.com",
    "shop.rebag.com",
    "rebag.com",
    "fashionphile.com",
    "vestiairecollective.com",
    "depop.com",
    "mercari.com",
    "grailed.com",
    "stockx.com",
    "goat.com",
}

PRICE_RE = re.compile(r"\$([0-9][0-9,]*(?:\.[0-9]{2})?)")
LINK_RE = re.compile(r"\[([^\]]+)\]\((https?://[^)]+)\)")


def _google_results_url(query: str) -> str:
    return f"https://www.google.com/search?q={quote_plus(query)}&hl=en&gl=us"


def _clean_text(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def _domain(url: str) -> str:
    host = urlparse(url).netloc.lower()
    return host[4:] if host.startswith("www.") else host


def _market_kind(url: str, title: str, context: str) -> str | None:
    host = _domain(url)
    combined = f"{title} {context}".lower()
    if any(host == d or host.endswith(f".{d}") for d in RESALE_DOMAINS):
        return "resale"
    if any(host == d or host.endswith(f".{d}") for d in RETAIL_DOMAINS):
        return "new"
    if any(token in combined for token in ("pre-owned", "preowned", "used", "resale", "consignment")):
        return "resale"
    if any(token in combined for token in ("new", "retail", "shop now", "in stock", "sale")):
        return "new"
    return None


def _title_match_score(query: str, title: str) -> float:
    query_tokens = {t for t in re.findall(r"[a-z0-9]+", query.lower()) if len(t) > 2}
    title_tokens = {t for t in re.findall(r"[a-z0-9]+", title.lower()) if len(t) > 2}
    if not query_tokens or not title_tokens:
        return 0.0
    overlap = len(query_tokens & title_tokens)
    return overlap / len(query_tokens)


class FirecrawlAgentProvider(CompsProvider):
    name = "firecrawl_agent"
    last_debug: dict[str, Any]

    def __init__(self) -> None:
        self.last_debug = {}

    def fetch_comps(self, request: ValuationRequest) -> list[MarketComp]:
        api_key = firecrawl_api_key()
        if not api_key:
            self.last_debug = {
                "status": "skipped",
                "reason": "missing_firecrawl_api_key",
                "returned_comp_count": 0,
            }
            return []

        query = query_for_request(
            request.brand,
            request.category,
            request.model_hint,
            request.title_hint,
            request.item_description,
            request.size,
        )
        request_url = _google_results_url(query)

        try:
            body = _firecrawl_scrape_data(request_url, formats=["markdown", "rawHtml", "html"])
        except Exception as exc:
            self.last_debug = {
                "status": "error",
                "reason": "scrape_request_failed",
                "request_url": request_url,
                "error": str(exc),
                "returned_comp_count": 0,
            }
            return []

        markdown = ""
        for key in ("markdown", "rawHtml", "html"):
            value = body.get(key)
            if isinstance(value, str) and value.strip():
                markdown = value
                if key != "markdown":
                    markdown = self._markdown_from_html(value)
                break

        entries = self._extract_entries(markdown, query)
        comps = self._normalize_entries(query, entries)
        self.last_debug = {
            "status": "ok" if comps else "empty",
            "reason": "parsed_google_results_page" if comps else "no_google_result_comps",
            "request_url": request_url,
            "used_firecrawl": True,
            "timeout_s": provider_timeout_s(),
            "entry_count": len(entries),
            "returned_comp_count": len(comps),
            "entries_preview": [
                {
                    "title": entry["title"],
                    "price_usd": entry["price_usd"],
                    "market_kind": entry["market_kind"],
                    "url": entry["url"],
                }
                for entry in entries[:8]
            ],
        }
        return comps

    def _markdown_from_html(self, html: str) -> str:
        text = re.sub(r"<script.*?</script>", " ", html, flags=re.I | re.S)
        text = re.sub(r"<style.*?</style>", " ", text, flags=re.I | re.S)
        text = re.sub(r"<[^>]+>", "\n", text)
        return _clean_text(text.replace("\xa0", " "))

    def _extract_entries(self, markdown: str, query: str) -> list[dict[str, Any]]:
        lines = [_clean_text(line) for line in markdown.splitlines()]
        lines = [line for line in lines if line]
        entries: list[dict[str, Any]] = []

        for idx, line in enumerate(lines):
            for title, url in LINK_RE.findall(line):
                title = _clean_text(title)
                if not title or len(title) < 8:
                    continue
                context_lines = [line]
                for offset in range(1, 4):
                    if idx + offset < len(lines):
                        context_lines.append(lines[idx + offset])
                context = " ".join(context_lines)
                price = self._first_price(context_lines)
                if price is None:
                    continue
                market_kind = _market_kind(url, title, context)
                if market_kind is None:
                    continue
                if _title_match_score(query, title) < 0.35:
                    continue
                entries.append(
                    {
                        "title": title,
                        "url": url,
                        "price_usd": price,
                        "market_kind": market_kind,
                        "context": context,
                    }
                )
        deduped: dict[tuple[str, float, str], dict[str, Any]] = {}
        for entry in entries:
            key = (entry["title"], float(entry["price_usd"]), entry["market_kind"])
            deduped[key] = entry
        return list(deduped.values())

    def _normalize_result(self, data: dict[str, Any]) -> list[MarketComp]:
        item_name = str(data.get("item_name") or "").strip() or "Market summary"
        sources = data.get("sources") if isinstance(data.get("sources"), list) else []
        entries: list[dict[str, Any]] = []
        for source in sources:
            if not isinstance(source, dict):
                continue
            price = source.get("price_usd")
            condition = str(source.get("condition") or "").strip().lower()
            if not isinstance(price, (int, float)) or price <= 0:
                continue
            if condition not in {"new", "resale"}:
                continue
            entries.append(
                {
                    "title": str(source.get("title") or item_name),
                    "url": source.get("url"),
                    "price_usd": float(price),
                    "market_kind": condition,
                }
            )
        seen_kinds = {entry["market_kind"] for entry in entries}
        resale_price = data.get("median_resale_price_usd")
        new_price = data.get("median_new_price_usd")
        if "resale" not in seen_kinds and isinstance(resale_price, (int, float)) and resale_price > 0:
            entries.append(
                {
                    "title": item_name,
                    "url": None,
                    "price_usd": float(resale_price),
                    "market_kind": "resale",
                }
            )
        if "new" not in seen_kinds and isinstance(new_price, (int, float)) and new_price > 0:
            entries.append(
                {
                    "title": item_name,
                    "url": None,
                    "price_usd": float(new_price),
                    "market_kind": "new",
                }
            )
        return self._normalize_entries(item_name, entries)

    def _first_price(self, lines: list[str]) -> float | None:
        for line in lines:
            match = PRICE_RE.search(line)
            if match:
                return float(match.group(1).replace(",", ""))
        return None

    def _normalize_entries(self, query: str, entries: list[dict[str, Any]]) -> list[MarketComp]:
        grouped: dict[str, list[dict[str, Any]]] = {"new": [], "resale": []}
        for entry in entries:
            grouped[entry["market_kind"]].append(entry)

        out: list[MarketComp] = []
        for market_kind, condition_text, is_sold in (
            ("resale", "Resale", True),
            ("new", "New", False),
        ):
            prices = [float(entry["price_usd"]) for entry in grouped[market_kind] if float(entry["price_usd"]) > 0]
            if not prices:
                continue
            out.append(
                MarketComp(
                    source="firecrawl_agent",
                    title=query,
                    price=float(median(prices)),
                    currency="USD",
                    is_sold=is_sold,
                    condition_text=condition_text,
                    metadata={
                        "market_kind": market_kind,
                        "comp_count": len(prices),
                        "agent_sources": [
                            {
                                "title": entry["title"],
                                "price_usd": entry["price_usd"],
                                "condition": market_kind,
                                "url": entry["url"],
                            }
                            for entry in grouped[market_kind]
                        ],
                    },
                )
            )
        return out
