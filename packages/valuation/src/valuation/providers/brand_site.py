from __future__ import annotations

import re
from dataclasses import dataclass
from urllib.parse import quote_plus
from urllib.parse import urlparse

from valuation.types import MarketComp, ValuationRequest

from .base import CompsProvider
from .http_utils import (
    best_title,
    best_url,
    extract_json_ld_objects,
    extract_next_data,
    extract_price_from_obj,
    fetch_firecrawl_markdown,
    fetch_page,
    firecrawl_enabled,
    query_for_request,
    walk_json,
)


@dataclass(frozen=True, slots=True)
class BrandSiteConfig:
    site_name: str
    search_url_template: str
    domain: str


BRAND_SITE_CONFIGS: dict[str, BrandSiteConfig] = {
    "Jimmy Choo": BrandSiteConfig(
        site_name="Jimmy Choo",
        search_url_template="https://us.jimmychoo.com/en/search?q={query}",
        domain="us.jimmychoo.com",
    ),
    "Nike": BrandSiteConfig(
        site_name="Nike",
        search_url_template="https://www.nike.com/w?q={query}&vst={query}",
        domain="www.nike.com",
    ),
    "Adidas": BrandSiteConfig(
        site_name="Adidas",
        search_url_template="https://www.adidas.com/us/search?q={query}",
        domain="www.adidas.com",
    ),
    "Gucci": BrandSiteConfig(
        site_name="Gucci",
        search_url_template="https://www.gucci.com/us/en/search?q={query}",
        domain="www.gucci.com",
    ),
    "Prada": BrandSiteConfig(
        site_name="Prada",
        search_url_template="https://www.prada.com/us/en/search.html?q={query}",
        domain="www.prada.com",
    ),
    "Coach": BrandSiteConfig(
        site_name="Coach",
        search_url_template="https://www.coach.com/search?q={query}",
        domain="www.coach.com",
    ),
    "Michael Kors": BrandSiteConfig(
        site_name="Michael Kors",
        search_url_template="https://www.michaelkors.com/search?q={query}",
        domain="www.michaelkors.com",
    ),
}


class BrandSiteProvider(CompsProvider):
    name = "brand_site"
    last_debug: dict[str, object]
    _UI_EXACT = {
        "new",
        "women",
        "men",
        "kids",
        "sale",
        "search",
        "filter",
        "sort",
        "size",
        "color",
        "view all",
    }
    _UI_PHRASES = (
        "select size",
        "sort by",
        "filter by",
        "view all",
        "search results",
        "items found",
    )

    def __init__(self) -> None:
        self.last_debug = {}

    def fetch_comps(self, request: ValuationRequest) -> list[MarketComp]:
        if request.condition_grade != "New":
            self.last_debug = {
                "status": "skipped",
                "reason": "condition_not_new",
                "condition_grade": request.condition_grade,
                "returned_comp_count": 0,
            }
            return []

        config = BRAND_SITE_CONFIGS.get(request.brand)
        if not config:
            self.last_debug = {
                "status": "skipped",
                "reason": "unsupported_brand_site",
                "brand": request.brand,
                "returned_comp_count": 0,
            }
            return []

        if not firecrawl_enabled():
            self.last_debug = {
                "status": "skipped",
                "reason": "firecrawl_disabled",
                "brand": request.brand,
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
        request_url = config.search_url_template.format(query=quote_plus(query))
        try:
            html = fetch_page(request_url)
        except Exception as exc:
            self.last_debug = {
                "status": "error",
                "reason": "fetch_failed",
                "brand": request.brand,
                "request_url": request_url,
                "used_firecrawl": True,
                "error": str(exc),
                "returned_comp_count": 0,
            }
            return []

        comps, parser_meta = self._parse_html(html, config)
        parser_path = "html_structured" if comps else None
        markdown_length = 0
        markdown_candidate_lines = 0
        if not comps:
            markdown = fetch_firecrawl_markdown(request_url)
            if markdown:
                markdown_length = len(markdown)
                comps, markdown_candidate_lines = self._parse_markdown(markdown, config)
                if comps:
                    parser_path = "firecrawl_markdown"

        self.last_debug = {
            "status": "ok" if comps else "empty",
            "reason": (
                f"parsed_{parser_path}_listings" if parser_path else "no_parsable_listings"
            ),
            "brand": request.brand,
            "request_url": request_url,
            "used_firecrawl": True,
            "parser_path": parser_path,
            "html_length": len(html),
            "markdown_length": markdown_length,
            "markdown_candidate_lines": markdown_candidate_lines,
            "parsed_count": len(comps),
            "returned_comp_count": len(comps),
            **parser_meta,
        }
        return comps

    def _parse_html(
        self, html: str, config: BrandSiteConfig
    ) -> tuple[list[MarketComp], dict[str, object]]:
        out: list[MarketComp] = []
        seen: set[tuple[str, float]] = set()
        json_ld = extract_json_ld_objects(html)
        json_ld_count = len(json_ld)

        for ld in json_ld:
            nodes = [ld]
            if isinstance(ld.get("@graph"), list):
                nodes.extend([n for n in ld["@graph"] if isinstance(n, dict)])
            for obj in nodes:
                item_type = str(obj.get("@type", "")).lower()
                if item_type == "productgroup":
                    for variant in obj.get("hasVariant", []) or []:
                        if not isinstance(variant, dict):
                            continue
                        title, price, currency, url = self._structured_variant_fields(variant, config)
                        if not title or price is None or not url:
                            continue
                        key = (title, float(price))
                        if key in seen:
                            continue
                        seen.add(key)
                        out.append(
                            MarketComp(
                                source="brand_site",
                                title=title,
                                price=float(price),
                                currency=currency or "USD",
                                is_sold=False,
                                condition_text="New",
                                url=url,
                                metadata={"parsed_from": "json_ld", "brand_site": config.site_name},
                            )
                        )
                        if len(out) >= 25:
                            break
                    if len(out) >= 25:
                        break
                    continue
                if item_type not in {"product", "offer"}:
                    continue
                title = str(obj.get("name") or best_title(obj)).strip()
                offers = obj.get("offers") if isinstance(obj.get("offers"), dict) else obj
                price, currency = extract_price_from_obj(offers if isinstance(offers, dict) else obj)
                url = best_url(obj, f"https://{config.domain}")
                if not self._looks_like_title_line(title):
                    continue
                if price is None or not url or config.domain not in url:
                    continue
                key = (title, float(price))
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    MarketComp(
                        source="brand_site",
                        title=title,
                        price=float(price),
                        currency=currency or "USD",
                        is_sold=False,
                        condition_text="New",
                        url=url,
                        metadata={"parsed_from": "json_ld", "brand_site": config.site_name},
                    )
                )
                if len(out) >= 25:
                    break
            if len(out) >= 25:
                break

        next_data = extract_next_data(html)
        if next_data and len(out) < 25:
            for obj in walk_json(next_data):
                if not isinstance(obj, dict):
                    continue
                price, currency = extract_price_from_obj(obj)
                if price is None:
                    continue
                title = best_title(obj)
                url = best_url(obj, f"https://{config.domain}")
                if not self._looks_like_title_line(title):
                    continue
                if not url or config.domain not in url:
                    continue
                key = (title, float(price))
                if key in seen:
                    continue
                seen.add(key)
                out.append(
                    MarketComp(
                        source="brand_site",
                        title=title,
                        price=float(price),
                        currency=currency or "USD",
                        is_sold=False,
                        condition_text="New",
                        url=url,
                        metadata={"parsed_from": "next_data", "brand_site": config.site_name},
                    )
                )
                if len(out) >= 25:
                    break

        return out, {"json_ld_count": json_ld_count, "next_data_found": bool(next_data)}

    def _structured_variant_fields(
        self, variant: dict, config: BrandSiteConfig
    ) -> tuple[str | None, float | None, str | None, str | None]:
        offers = variant.get("offers") if isinstance(variant.get("offers"), dict) else variant
        price, currency = extract_price_from_obj(offers if isinstance(offers, dict) else variant)
        url = best_url(offers if isinstance(offers, dict) else variant, f"https://{config.domain}")
        if not url:
            url = best_url(variant, f"https://{config.domain}")
        if not url or config.domain not in url:
            return None, None, None, None

        title = self._title_from_product_url(url)
        if not title:
            title = str(variant.get("name") or best_title(variant)).strip()
        if not self._looks_like_title_line(title):
            return None, None, None, None
        if price is None:
            return None, None, None, None
        return title, float(price), currency or "USD", url

    def _title_from_product_url(self, url: str) -> str | None:
        path = urlparse(url).path
        if not path or not path.endswith(".html"):
            return None
        slug = path.rsplit("/", 1)[-1].removesuffix(".html")
        slug = re.sub(r"-[A-Z0-9]{8,}$", "", slug)
        text = slug.replace("-", " ").strip()
        if not text:
            return None
        words = []
        for token in text.split():
            if token.isupper() and len(token) <= 3:
                words.append(token)
            elif any(ch.isdigit() for ch in token):
                words.append(token.upper())
            else:
                words.append(token.capitalize())
        title = " ".join(words)
        return title if self._looks_like_title_line(title) else None

    def _parse_markdown(
        self, markdown: str, config: BrandSiteConfig
    ) -> tuple[list[MarketComp], int]:
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
            title, url = self._extract_listing_context(lines, i, price_re, config.domain)
            if not title or len(title.split()) < 2:
                continue
            key = (title, price)
            if key in seen:
                continue
            seen.add(key)
            out.append(
                MarketComp(
                    source="brand_site",
                    title=title,
                    price=price,
                    currency="USD",
                    is_sold=False,
                    condition_text="New",
                    url=url,
                    metadata={
                        "parsed_from": "firecrawl_markdown",
                        "brand_site": config.site_name,
                    },
                )
            )
            if len(out) >= 25:
                break
        return out, candidate_lines

    def _extract_listing_context(
        self, lines: list[str], price_index: int, price_re: re.Pattern[str], domain: str
    ) -> tuple[str | None, str | None]:
        for idx in range(price_index - 1, max(-1, price_index - 8 - 1), -1):
            line = lines[idx].strip()
            if not line:
                continue
            title, url = self._parse_markdown_link_line(line, domain)
            if title:
                return title, url
            if "](" in line and "http" in line:
                break
            cleaned = re.sub(r"^\s*[-*#>\d.\)\(]+\s*", "", line).strip()
            cleaned = price_re.sub("", cleaned).strip(" -|:")
            if self._looks_like_title_line(cleaned):
                return cleaned, None
        return None, None

    def _parse_markdown_link_line(self, line: str, domain: str) -> tuple[str | None, str | None]:
        match = re.search(r"\[([^\]]+)\]\((https?://[^)]+)\)", line)
        if not match:
            return None, None
        title = match.group(1).strip()
        url = match.group(2).strip()
        if domain not in url:
            return None, None
        if any(path in url for path in ("/search", "/wishlist", "/account", "/cart")):
            return None, None
        if not self._looks_like_title_line(title):
            return None, None
        return title, url

    def _looks_like_title_line(self, line: str) -> bool:
        if not line or len(line) < 4:
            return False
        lowered = line.casefold()
        if lowered in self._UI_EXACT:
            return False
        if any(phrase in lowered for phrase in self._UI_PHRASES):
            return False
        if lowered in {"sale price", "regular price"}:
            return False
        if "complimentary" in lowered or "working days" in lowered or "order by" in lowered:
            return False
        if lowered.startswith("size") or lowered.startswith("color"):
            return False
        if not re.search(r"[a-zA-Z]", line):
            return False
        return True
