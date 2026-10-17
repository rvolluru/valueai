"""Fail-closed comparable identity gate. Search metadata is not proof of sale price."""
import copy
import math
import re
import unicodedata
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

POLICY_VERSION = "same-brand-comparables-v4"
MATCHING_POLICY = "source-identity-context-v2"


def tokens(value):
    text = re.sub(r"[\u2010-\u2015\u2212]", "-", str(value or ""))
    text = re.sub(r"[\u2018\u2019']", "", text)
    return set(re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()))


def core_product_tokens(value):
    """Remove labelled catalog/size metadata, not arbitrary brand/model numbers."""
    text = str(value or "")
    text = re.sub(r"\(\s*(?:19|20)\d{2}\s*\)", " ", text)
    text = re.sub(r"\([^)]*\b(?:item|sku|size|sz|style|reference|ref)\b[^)]*\)", " ", text, flags=re.I)
    text = re.sub(r"\b(?:trr\s+)?(?:item|sku|size|sz|style|reference|ref)\s*(?:no\.?|[#:]|number)?\s*[a-z0-9/-]+", " ", text, flags=re.I)
    return tokens(text) - {"w", "with", "tags", "tag", "new", "nwt", "pre", "owned", "the", "and"}


# Descriptors can be abbreviated/omitted by search titles. Named models and
# collaboration names must remain supported, even when descriptive overlap is high.
TITLE_DESCRIPTORS = set("monogram workwear denim zip up button front print graphic leather calf lambskin cotton wool silk studded moto motorcycle biker bomber jacket jackets coat coats shirt shirts dress dresses bag bags tote shoulder flap shorts pants skirt blue black brown white grey gray indigo dark light men mens women womens pristine excellent good fair limited edition full point collar ribbed patch pocket pockets utility quilted metallic distressed slim fit".split())
TITLE_DESCRIPTORS.add("patchwork")
TITLE_DESCRIPTORS.update("green beige pink red navy cream purple orange yellow tan burgundy multicolor multicolour removable shearling embellished embroidery embroidered fleece jacquard through hood hooded rtw outerwear large medium small extra size xs xl xxl xxs xxxl authentic authenticity sale sold soldout sold out asking price usd dollars used excellent very condition tag tags nwt nwd nwot nwb nwt pristine with for of in on at to by listing item product details clothing accessories poshmark realreal trr ebay vestiaire collective rebag depop vinted".split())
TITLE_DESCRIPTORS.update({"related", "variant", "colorway", "colourway"})


def product_tokens(value, brand):
    words = core_product_tokens(value)
    # Normalize known aliases only for the already established source brand.
    if brand == {"louis", "vuitton"} and "lv" in words:
        words = (words - {"lv"}) | brand
    if "zipthrough" in words:
        words = (words - {"zipthrough"}) | {"zip", "through"}
    return words


def model_tokens(value, brand):
    text = re.sub(r"^\s*(?:19|20)\d{2}\b", " ", str(value or ""))
    return product_tokens(text, brand) - brand


def source_title_supports(brand, comparable_model, title):
    title_words = product_tokens(title, brand)
    if not brand <= title_words:
        return False
    # Only a leading collection year is optional. Numbers in named models
    # (e.g. Re-Edition 2005 versus 2000) remain distinguishing evidence.
    core = model_tokens(comparable_model, brand)
    distinctive = core - TITLE_DESCRIPTORS
    overlap = core & title_words
    # Source titles often omit color, trim, fabric qualifiers and season. Do not
    # require a percentage of every descriptive word; retain named-model checks.
    return bool(core and distinctive <= title_words and
                len(overlap) >= min(2, len(core)) and (distinctive or len(core) >= 2))


PRODUCT_FAMILIES = (
    {"jacket", "jackets", "coat", "coats", "blouson", "biker", "bomber", "outerwear"},
    {"bag", "bags", "handbag", "handbags", "tote", "wallet", "purse"},
    {"shirt", "shirts", "blouse", "blouses", "tshirt"},
    {"dress", "dresses", "gown"},
    {"shoe", "shoes", "boot", "boots", "sneaker", "sneakers", "sandal", "sandals"},
    {"pants", "trousers", "jeans", "shorts", "skirt", "skirts"},
)


def native_title_conflicts(brand, comparable_model, title):
    words = product_tokens(title, brand)
    if not brand <= words:
        # Only genuinely generic page titles may omit the brand. A title naming
        # another brand must not be overwritten by a model's own summary/URL.
        return bool(words - TITLE_DESCRIPTORS - {"the", "www", "com"})
    core = model_tokens(comparable_model, brand)
    model_families = {i for i, family in enumerate(PRODUCT_FAMILIES) if core & family}
    source_families = {i for i, family in enumerate(PRODUCT_FAMILIES) if (words - brand) & family}
    if model_families and source_families and not model_families & source_families:
        return True
    if (("denim" in core and "leather" in words and "denim" not in words)
            or ("leather" in core and "denim" in words and "leather" not in words)):
        return True
    named = core - TITLE_DESCRIPTORS
    source_named = model_tokens(title, brand) - TITLE_DESCRIPTORS
    # Explicit different model names/numbers remain conflicts; mere omission of
    # a model name from a shortened generic title can use corroborating context.
    return bool(named - words and source_named - named)


def source_identity_support(brand, comparable_model, key, titles, retrieved, summaries, match_evidence):
    native = titles.get(key, [])
    if any(native_title_conflicts(brand, comparable_model, title) for title in native):
        return None
    if any(source_title_supports(brand, comparable_model, title) for title in native):
        return "native_title"
    if key not in retrieved:
        return None
    # The product slug is provider-retrieved metadata, not a new model URL.
    # Use path only: query parameters can contain arbitrary suggested keywords.
    path = unquote(urlsplit(key).path).replace("/", " ").replace("-", " ").replace("_", " ")
    source_summaries = summaries.get(key, [])
    for summary in source_summaries:
        if not native and source_title_supports(brand, comparable_model, f"{' '.join(brand)} {summary}"):
            return "model_reported_summary_retrieved_url"
    if match_evidence and source_title_supports(brand, comparable_model, path):
        return "retrieved_product_url_identity"
    for summary in source_summaries:
        if source_title_supports(brand, comparable_model, " ".join([*native, path, summary])):
            return "retrieved_url_title_summary_context"
    return None


def url_key(value):
    try:
        p = urlsplit(str(value or ""))
        if p.scheme not in {"https", "http"} or not p.hostname or p.username:
            return ""
        tracking = {"gclid", "fbclid"}
        if re.search(r"(^|\.)ebay\.(com|co\.uk|ca|com\.au|de|fr|it|es)$", p.hostname.lower()):
            tracking |= {"itmmeta", "itmprp", "_trksid", "_trkparms"}
        query = urlencode([(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
                           if not k.lower().startswith("utm_") and k.lower() not in tracking])
        return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip("/"), query, ""))
    except ValueError:
        return ""


def search_titles(raw):
    result = {}
    for output in raw.get("output", []):
        sources = list((output.get("action") or {}).get("sources") or [])
        for part in output.get("content", []):
            sources.extend(a for a in part.get("annotations", []) if a.get("type") == "url_citation")
        for source in sources:
            key = url_key(source.get("url"))
            if key and source.get("title"):
                result.setdefault(key, []).append(source["title"])
    return result


def retrieved_urls(raw):
    """Use provider tool metadata, never the model's own grounding_sources list."""
    result = set(search_titles(raw))
    for output in raw.get("output", []):
        if output.get("type") != "web_search_call":
            continue
        action = output.get("action") or {}
        candidates = [s.get("url") for s in action.get("sources") or []]
        candidates.append(action.get("url"))
        result.update(key for value in candidates if (key := url_key(value)))
    return result


def validate_valuation(data, identity, raw):
    result = copy.deepcopy(data)
    brand = tokens(identity.get("candidate_brand"))
    model = model_tokens(identity.get("candidate_model") or (identity.get("model_identification") or {}).get("name"), brand)
    titles = search_titles(raw)
    retrieved = retrieved_urls(raw)
    summaries = {}
    for source in data.get("grounding_sources") or []:
        key = url_key(source.get("url"))
        if key and str(source.get("snippet") or "").strip():
            summaries.setdefault(key, []).append(source["snippet"])
    source_support = {}
    accepted, rejected = [], []
    for row in data.get("pricing_comparables") or []:
        key = url_key(row.get("url"))
        reason = None
        row_model = model_tokens(row.get("model"), brand)
        exact = row.get("match_type") == "exact" and row.get("variant_match") == "confirmed"
        support = source_identity_support(brand, row.get("model"), key, titles, retrieved, summaries, row.get("match_evidence")) if key else None
        if row.get("match_type") not in {"exact", "related"}:
            reason = "not_a_comparable"
        elif not brand or product_tokens(row.get("brand"), brand) != brand or not row_model:
            reason = "identity_mismatch_or_ambiguous_model"
        elif exact and (not model or not model <= row_model):
            reason = "claimed_exact_model_mismatch"
        elif not exact and (not str(row.get("similarity_basis") or "").strip()
                            or not str(row.get("adjustment_explanation") or "").strip()):
            reason = "missing_similarity_or_adjustment_explanation"
        elif not key or not support:
            reason = "no_supported_source_title_or_summary"
        elif not row.get("match_evidence") or row.get("price_type") not in {"sold_displayed", "asking"}:
            reason = "missing_match_or_price_evidence"
        elif (isinstance(row.get("price"), bool) or not isinstance(row.get("price"), (int, float))
              or not math.isfinite(row["price"]) or row["price"] <= 0 or row.get("currency") != "USD"):
            reason = "invalid_price_or_currency"
        if reason:
            rejected.append({"url": row.get("url"), "reason": reason})
        elif key not in {url_key(r["url"]) for r in accepted}:
            accepted.append(row)
            source_support[key] = support
    allowed = {url_key(row["url"]) for row in accepted}
    refs = (result.get("resale_price_estimate") or {}).get("references") or []
    # Reject the entire valuation if it also anchors to any unqualified comparable.
    passed = bool(allowed and refs and all(url_key(ref.get("url")) in allowed for ref in refs))
    result["pricing_evidence_policy"] = {"version": POLICY_VERSION, "matching_policy": MATCHING_POLICY,
        "status": "qualified" if passed else "needs_review", "accepted": accepted, "rejected": rejected,
        "source_support": source_support,
        "basis": "same_brand_similar_model" if any(r.get("match_type") == "related" or r.get("variant_match") != "confirmed" for r in accepted) else "exact_model",
        "verification": "Normalized source identity supported by native title, provider-retrieved product URL, or corroborating title/URL/summary context. Explicit native brand/model/product conflicts remain blocked. Model-extracted prices, variants and conditions are not independently verified."}
    if not passed:
        for field in ("resale_price_estimate", "retail_price_estimate"):
            estimate = result.get(field)
            if isinstance(estimate, dict):
                estimate.update(estimated_price=None, confidence=0,
                    rationale="Insufficient supported same-brand comparable pricing evidence; manual review required.")
        result["resale_price_breakdown"] = []
    return result
