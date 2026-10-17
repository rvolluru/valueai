"""Fail-closed comparable identity gate. Search metadata is not proof of sale price."""
import copy
import math
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit
from .pricing_sources import RESALE_DOMAINS, SOURCE_POLICY_VERSION, official_domains, url_in_domains

POLICY_VERSION = "same-brand-comparables-v5"


def tokens(value):
    return set(re.findall(r"[a-z0-9]+", unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()))


def core_product_tokens(value):
    """Remove labelled catalog/size metadata, not arbitrary brand/model numbers."""
    text = str(value or "")
    text = re.sub(r"\([^)]*\b(?:item|sku|size|sz|style|reference|ref)\b[^)]*\)", " ", text, flags=re.I)
    text = re.sub(r"\b(?:trr\s+)?(?:item|sku|size|sz|style|reference|ref)\s*(?:no\.?|[#:]|number)?\s*[a-z0-9/-]+", " ", text, flags=re.I)
    return tokens(text) - {"w", "with", "tags", "tag", "new", "nwt", "pre", "owned", "the", "and"}


# Descriptors can be abbreviated/omitted by search titles. Named models and
# collaboration names must remain supported, even when descriptive overlap is high.
TITLE_DESCRIPTORS = set("monogram workwear denim zip up button front print graphic leather calf lambskin cotton wool silk studded moto motorcycle biker bomber jacket jackets coat coats shirt shirts dress dresses bag bags tote shoulder flap shorts pants skirt blue black brown white grey gray indigo dark light men mens women womens pristine excellent good fair limited edition full point collar ribbed patch pocket pockets utility quilted metallic distressed slim fit".split())
TITLE_DESCRIPTORS.add("patchwork")


def source_title_supports(brand, comparable_model, title):
    title_words = core_product_tokens(title)
    if not brand <= title_words:
        return False
    # Only a leading collection year is optional. Numbers in named models
    # (e.g. Re-Edition 2005 versus 2000) remain distinguishing evidence.
    model_text = re.sub(r"^\s*(?:19|20)\d{2}\b", " ", str(comparable_model or ""))
    core = core_product_tokens(model_text) - brand
    distinctive = core - TITLE_DESCRIPTORS
    overlap = core & title_words
    return bool(core and distinctive <= title_words and
                len(overlap) >= min(2, len(core)) and len(overlap) / len(core) >= .6)


def url_key(value):
    try:
        p = urlsplit(str(value or ""))
        if p.scheme not in {"https", "http"} or not p.hostname or p.username:
            return ""
        return urlunsplit((p.scheme, p.netloc.lower(), p.path.rstrip("/"), p.query, ""))
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
    model = tokens(identity.get("candidate_model") or (identity.get("model_identification") or {}).get("name")) - brand
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
        row_model = tokens(row.get("model")) - brand
        exact = row.get("match_type") == "exact" and row.get("variant_match") == "confirmed"
        native_support = any(source_title_supports(brand, row.get("model"), title) for title in titles.get(key, []))
        # Fallback only when metadata has NO title for this retrieved URL. A
        # contradictory native title must not be overridden by generated text.
        summary_support = (key in retrieved and not titles.get(key) and any(
            source_title_supports(brand, row.get("model"), f"{row.get('brand', '')} {summary}")
            for summary in summaries.get(key, [])))
        if not url_in_domains(row.get("url"), RESALE_DOMAINS):
            reason = "unapproved_resale_source"
        elif row.get("match_type") not in {"exact", "related"}:
            reason = "not_a_comparable"
        elif not brand or tokens(row.get("brand")) != brand or not row_model:
            reason = "identity_mismatch_or_ambiguous_model"
        elif exact and (not model or not model <= row_model):
            reason = "claimed_exact_model_mismatch"
        elif not exact and (not str(row.get("similarity_basis") or "").strip()
                            or not str(row.get("adjustment_explanation") or "").strip()):
            reason = "missing_similarity_or_adjustment_explanation"
        elif not key or not (native_support or summary_support):
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
            source_support[key] = "native_title" if native_support else "model_reported_summary_retrieved_url"
    allowed = {url_key(row["url"]) for row in accepted}
    refs = (result.get("resale_price_estimate") or {}).get("references") or []
    # Reject the entire valuation if it also anchors to any unqualified comparable.
    passed = bool(allowed and refs and all(url_key(ref.get("url")) in allowed for ref in refs))
    result["pricing_evidence_policy"] = {"version": POLICY_VERSION,
        "source_policy_version": SOURCE_POLICY_VERSION,
        "approved_resale_domains": list(RESALE_DOMAINS),
        "official_brand_domains": list(official_domains(identity)),
        "status": "qualified" if passed else "needs_review", "accepted": accepted, "rejected": rejected,
        "source_support": source_support,
        "basis": "same_brand_similar_model" if any(r.get("match_type") == "related" or r.get("variant_match") != "confirmed" for r in accepted) else "exact_model",
        "verification": "Native-title match, or model product-name/summary consistency for provider-retrieved URLs when titles are absent. Generated summaries, variants, conditions and prices are not independently verified."}
    # MSRP is separate from resale: a missing/unapproved official reference must
    # not erase otherwise supported resale evidence.
    retail = result.get("retail_price_estimate")
    if isinstance(retail, dict) and retail.get("estimated_price") is not None:
        retail_refs = retail.get("references") or []
        if not retail_refs or not all(
            url_in_domains(ref.get("url"), official_domains(identity))
            and url_key(ref.get("url")) in retrieved for ref in retail_refs
        ):
            retail.update(estimated_price=None, confidence=0,
                          rationale="No provider-retrieved reference from the registered official brand website.")
    if not passed:
        for field in ("resale_price_estimate", "retail_price_estimate"):
            estimate = result.get(field)
            if isinstance(estimate, dict):
                estimate.update(estimated_price=None, confidence=0,
                    rationale="Insufficient supported same-brand comparable pricing evidence; manual review required.")
        result["resale_price_breakdown"] = []
    return result
