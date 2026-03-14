from __future__ import annotations
import json
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
        query = query_for_request(
            request.brand,
            request.category,
            request.model_hint,
            request.title_hint,
            request.item_description,
            request.size,
        )
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

        shopify_products = self._extract_shopify_products(html)
        if shopify_products and len(out) < 25:
            for product in shopify_products:
                if not isinstance(product, dict):
                    continue
                title = self._shopify_product_title(product)
                if not title:
                    continue
                handle = str(product.get("handle") or "").strip()
                url = (
                    f"https://shop.rebag.com/products/{handle}"
                    if handle
                    else None
                )
                variants = product.get("variants") if isinstance(product.get("variants"), list) else []
                variant = variants[0] if variants and isinstance(variants[0], dict) else {}
                raw_price = variant.get("price")
                if isinstance(raw_price, str) and raw_price.isdigit():
                    price = float(raw_price) / 100.0
                elif isinstance(raw_price, (int, float)):
                    price = float(raw_price) / 100.0 if float(raw_price) > 10000 else float(raw_price)
                else:
                    price = None
                if price is None or price <= 0:
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
                        currency="USD",
                        is_sold=False,
                        url=url,
                        metadata={"parsed_from": "shopify_meta_products"},
                    )
                )
                if len(out) >= 25:
                    break

        return out[:25], {
            "json_ld_count": json_ld_count,
            "next_data_found": bool(next_data),
            "shopify_products_count": len(shopify_products),
        }

    def _extract_shopify_products(self, html: str) -> list[dict]:
        marker = "var meta ="
        start = html.find(marker)
        if start == -1:
            return []
        brace_start = html.find("{", start)
        if brace_start == -1:
            return []
        depth = 0
        in_string = False
        escape = False
        end = -1
        for idx in range(brace_start, len(html)):
            ch = html[idx]
            if in_string:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == '"':
                    in_string = False
                continue
            if ch == '"':
                in_string = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    end = idx + 1
                    break
        if end == -1:
            return []
        try:
            data = json.loads(html[brace_start:end])
        except Exception:
            return []
        products = data.get("products")
        return [p for p in products if isinstance(p, dict)] if isinstance(products, list) else []

    def _shopify_product_title(self, product: dict) -> str | None:
        vendor = str(product.get("vendor") or "").strip()
        variants = product.get("variants") if isinstance(product.get("variants"), list) else []
        variant = variants[0] if variants and isinstance(variants[0], dict) else {}
        variant_name = str(variant.get("name") or product.get("title") or "").strip()
        if " - " in variant_name:
            variant_name = variant_name.split(" - ", 1)[0]
        if not variant_name:
            variant_name = str(product.get("title") or "").strip()
        parts = [vendor, variant_name]
        title = " ".join(part for part in parts if part)
        title = re.sub(r"\s*\/\s*", " ", title)
        title = " ".join(title.split())
        return title or None

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
