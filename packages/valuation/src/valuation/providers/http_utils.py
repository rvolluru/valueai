from __future__ import annotations

import json
import os
import re
from typing import Any
from urllib.parse import urlencode

import httpx


DEFAULT_UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
)


def provider_timeout_s() -> float:
    try:
        return float(os.getenv("VALUATION_PROVIDER_TIMEOUT_S", "12"))
    except Exception:
        return 12.0


def provider_user_agent() -> str:
    return os.getenv("VALUATION_PROVIDER_USER_AGENT", DEFAULT_UA)


def http_get(url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> str:
    merged_headers = {"User-Agent": provider_user_agent(), "Accept": "*/*"}
    if headers:
        merged_headers.update(headers)
    with httpx.Client(timeout=provider_timeout_s(), follow_redirects=True) as client:
        resp = client.get(url, params=params, headers=merged_headers)
        resp.raise_for_status()
        return resp.text


def firecrawl_enabled() -> bool:
    return str(os.getenv("VALUATION_USE_FIRECRAWL", "false")).strip().lower() in {"1", "true", "yes", "on"}


def firecrawl_api_key() -> str | None:
    return os.getenv("FIRECRAWL_API_KEY")


def firecrawl_base_url() -> str:
    return os.getenv("FIRECRAWL_API_BASE_URL", "https://api.firecrawl.dev").rstrip("/")


def _firecrawl_scrape_data(url: str, formats: list[str] | None = None) -> dict[str, Any]:
    api_key = firecrawl_api_key()
    if not api_key:
        raise RuntimeError("FIRECRAWL_API_KEY missing")
    payload = {
        "url": url,
        # rawHtml retains scripts/embedded JSON for parser extraction
        "formats": formats or ["rawHtml", "html"],
        "onlyMainContent": False,
    }
    with httpx.Client(timeout=provider_timeout_s(), follow_redirects=True) as client:
        resp = client.post(
            f"{firecrawl_base_url()}/v2/scrape",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        data = resp.json()
    body = data.get("data") if isinstance(data, dict) else None
    if not isinstance(body, dict):
        raise RuntimeError("Unexpected Firecrawl response shape")
    return body


def _firecrawl_scrape(url: str) -> str:
    body = _firecrawl_scrape_data(url, formats=["rawHtml", "html"])
    for key in ("rawHtml", "html", "markdown"):
        val = body.get(key)
        if isinstance(val, str) and val.strip():
            return val
    raise RuntimeError("Firecrawl response missing html/markdown content")


def fetch_page(url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None) -> str:
    # Optional Firecrawl path for JS-heavy pages. Falls back to direct HTTP.
    if firecrawl_enabled():
        try:
            full_url = url if not params else f"{url}?{urlencode(params, doseq=True)}"
            return _firecrawl_scrape(full_url)
        except Exception:
            pass
    return http_get(url, params=params, headers=headers)


def fetch_firecrawl_markdown(url: str) -> str | None:
    if not firecrawl_enabled():
        return None
    try:
        body = _firecrawl_scrape_data(url, formats=["markdown"])
    except Exception:
        return None
    md = body.get("markdown")
    return md if isinstance(md, str) and md.strip() else None


def build_request_url(url: str, params: dict[str, Any] | None = None) -> str:
    if not params:
        return url
    return f"{url}?{urlencode(params, doseq=True)}"


def http_get_json(
    url: str, params: dict[str, Any] | None = None, headers: dict[str, str] | None = None
) -> dict[str, Any]:
    merged_headers = {"User-Agent": provider_user_agent(), "Accept": "application/json"}
    if headers:
        merged_headers.update(headers)
    with httpx.Client(timeout=provider_timeout_s(), follow_redirects=True) as client:
        resp = client.get(url, params=params, headers=merged_headers)
        resp.raise_for_status()
        return resp.json()


def build_search_query(*parts: str | None) -> str:
    cleaned_parts = [p.strip() for p in parts if p and p.strip()]
    deduped: list[str] = []

    def normalize(text: str) -> str:
        return re.sub(r"[^a-z0-9]+", " ", text.casefold()).strip()

    for part in cleaned_parts:
        normalized_part = normalize(part)
        if not normalized_part:
            continue
        skip = False
        replace_index: int | None = None
        for idx, existing in enumerate(deduped):
            normalized_existing = normalize(existing)
            if normalized_part == normalized_existing:
                skip = True
                break
            if normalized_part in normalized_existing:
                skip = True
                break
            if normalized_existing in normalized_part:
                if normalized_part.startswith(f"{normalized_existing} "):
                    replace_index = idx
                    break
                if len(normalized_existing.split()) >= 3:
                    replace_index = idx
                    break
        if skip:
            continue
        if replace_index is not None:
            deduped[replace_index] = part
        else:
            deduped.append(part)

    return " ".join(deduped)


def extract_json_ld_objects(html: str) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for m in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.I | re.S,
    ):
        raw = m.group(1).strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        if isinstance(data, dict):
            out.append(data)
        elif isinstance(data, list):
            out.extend([x for x in data if isinstance(x, dict)])
    return out


def extract_embedded_json_objects(html: str) -> list[dict[str, Any]]:
    """Best-effort extraction of JSON-like blobs embedded in scripts.

    This is intentionally conservative: only parse brace blocks that look like JSON
    and contain common listing keys.
    """
    out: list[dict[str, Any]] = []
    for m in re.finditer(r"<script[^>]*>(.*?)</script>", html, flags=re.I | re.S):
        script = m.group(1)
        if not script or "{" not in script or "}" not in script:
            continue
        # Find JSON-looking assignments: foo = {...}; or window.__x = {...};
        for m2 in re.finditer(r"(?:=|:)\s*(\{.*?\})\s*;?", script, flags=re.S):
            blob = m2.group(1).strip()
            if not blob:
                continue
            # Quick filter to avoid huge non-JSON JS code.
            lower = blob.lower()
            if not any(k in lower for k in ('"price"', '"title"', '"name"', '"listing"')):
                continue
            try:
                parsed = json.loads(blob)
            except Exception:
                continue
            if isinstance(parsed, dict):
                out.append(parsed)
    return out


def extract_next_data(html: str) -> dict[str, Any] | None:
    m = re.search(
        r'<script[^>]+id=["\']__NEXT_DATA__["\'][^>]*type=["\']application/json["\'][^>]*>(.*?)</script>',
        html,
        flags=re.I | re.S,
    )
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except Exception:
        return None


def walk_json(node: Any):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from walk_json(v)
    elif isinstance(node, list):
        for v in node:
            yield from walk_json(v)


def extract_price_from_obj(obj: dict[str, Any]) -> tuple[float | None, str | None]:
    # common patterns
    for key in ("price", "currentPrice", "displayPrice", "amount", "listingPrice"):
        if key not in obj:
            continue
        val = obj[key]
        if isinstance(val, (int, float)):
            return float(val), (obj.get("currency") or "USD")
        if isinstance(val, str):
            m = re.search(r"([0-9]+(?:\.[0-9]+)?)", val.replace(",", ""))
            if m:
                return float(m.group(1)), (obj.get("currency") or "USD")
        if isinstance(val, dict):
            for amount_key in ("value", "amount", "__value__", "raw"):
                amount = val.get(amount_key)
                if isinstance(amount, (int, float)):
                    return float(amount), str(val.get("currency") or val.get("currencyCode") or "USD")
                if isinstance(amount, str):
                    m = re.search(r"([0-9]+(?:\.[0-9]+)?)", amount.replace(",", ""))
                    if m:
                        return float(m.group(1)), str(
                            val.get("currency") or val.get("currencyCode") or "USD"
                        )
    return None, None


def looks_like_listing(obj: dict[str, Any]) -> bool:
    title_keys = {"title", "name", "listingTitle", "productName"}
    if not any(k in obj and isinstance(obj.get(k), str) and obj.get(k) for k in title_keys):
        return False
    price, _ = extract_price_from_obj(obj)
    return price is not None and price > 0


def best_title(obj: dict[str, Any]) -> str:
    for key in ("title", "name", "listingTitle", "productName"):
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return "Unknown item"


def best_url(obj: dict[str, Any], site_origin: str) -> str | None:
    for key in ("url", "itemWebUrl", "share_url", "link", "canonicalUrl", "slug"):
        val = obj.get(key)
        if isinstance(val, str) and val.strip():
            if val.startswith("http://") or val.startswith("https://"):
                return val
            if val.startswith("/"):
                return site_origin.rstrip("/") + val
            if " " not in val and "/" in val:
                return site_origin.rstrip("/") + "/" + val.lstrip("/")
    return None


def query_for_request(
    brand: str,
    category: str,
    model_hint: str | None,
    title_hint: str | None,
    item_description: str | None = None,
    size: str | None = None,
) -> str:
    return build_search_query(brand, item_description, model_hint, title_hint, size, category)
