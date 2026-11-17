"""Reviewed source policy. Never infer an official domain from model output."""
import re
import unicodedata
from urllib.parse import urlsplit

SOURCE_POLICY_VERSION = "approved-pricing-sources-v2"
RESALE_DOMAINS = (
    "therealreal.com", "poshmark.com", "poshmark.ca",
    "vestiairecollective.com", "rebag.com", "depop.com",
    "vinted.com", "vinted.co.uk", "vinted.fr", "vinted.de", "vinted.it",
    "vinted.es", "vinted.nl", "vinted.be", "vinted.ca", "vinted.pl",
    "ebay.com", "ebay.co.uk", "ebay.ca", "ebay.com.au", "ebay.de",
    "ebay.fr", "ebay.it", "ebay.es",
)


# Retailers can supply new-item asking comparables, never invented used/sold
# prices or official-brand MSRP. Keep their market role explicit.
RETAIL_COMPARABLE_DOMAINS = ("cettire.com",)
COMPARABLE_DOMAINS = (*RESALE_DOMAINS, *RETAIL_COMPARABLE_DOMAINS)


def retail_comparable_rejection(row):
    if url_in_domains(row.get("url"), RETAIL_COMPARABLE_DOMAINS):
        if row.get("price_type") != "asking" or row.get("condition") not in {"New", "NewWithTags"}:
            return "retail_listing_requires_new_asking_price"
    return None


def brand_key(value):
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode()
    return " ".join(re.findall(r"[a-z0-9]+", text.lower()))


# Explicitly maintained canonical sites, not model-supplied URLs. Add brands and
# regional domains only after reviewing their official site. Exact aliases only:
# collaborations/diffusion lines must not silently inherit another brand's site.
BRAND_DOMAINS = {
    "louis vuitton": ("louisvuitton.com",),
    "gucci": ("gucci.com",), "prada": ("prada.com",),
    "chanel": ("chanel.com",), "hermes": ("hermes.com",),
    "dior": ("dior.com",), "christian dior": ("dior.com",),
    "burberry": ("burberry.com",), "theory": ("theory.com",),
    "free people": ("freepeople.com",), "zimmermann": ("zimmermann.com",),
    "cinq a sept": ("cinqasept.nyc",),
    "alice olivia": ("aliceandolivia.com",),
    "alice and olivia": ("aliceandolivia.com",),
    "herve leger": ("herveleger.com",), "rhode": ("shoprhode.com",),
    "john varvatos": ("johnvarvatos.com",),
    "reformation": ("thereformation.com",),
}


def official_domains(identity):
    return BRAND_DOMAINS.get(brand_key(identity.get("candidate_brand")), ())


def allowed_domains(identity):
    return [*COMPARABLE_DOMAINS, *official_domains(identity)]


def url_in_domains(url, domains):
    """Hostname boundary checks, not substring checks or caller-reported domains."""
    try:
        parsed = urlsplit(str(url or ""))
        host = (parsed.hostname or "").lower().rstrip(".")
        if parsed.scheme != "https" or parsed.username or parsed.password or parsed.port not in (None, 443):
            return False
        return bool(host and any(host == domain or host.endswith("." + domain) for domain in domains))
    except ValueError:
        return False


def source_prompt(identity):
    official = official_domains(identity)
    return (
        "MANDATORY SOURCE RESTRICTIONS (override all other source suggestions): "
        "Resale evidence must come ONLY from these approved domains: " + ", ".join(RESALE_DOMAINS) + ". "
        "Approved multi-brand retail listing domains: " + ", ".join(RETAIL_COMPARABLE_DOMAINS) + ". "
        "Cettire may supply displayed regular new-item asking comparables only: price_type asking, "
        "condition New (NewWithTags only with explicit evidence). Never label retail listings used or sold; "
        "explain condition differences when estimating a used item. These prices are not official-brand MSRP. "
        "Official brand domains for this image-analysis identity: " + (", ".join(official) or "none registered") + ". "
        "Use official brand sites only for product identity, specifications and original full retail price, "
        "never as resale anchors. Do not guess official sites or use other brands' sites. "
        "If no official domain is registered or MSRP cannot be verified, leave retail price null; "
        "this alone does not prevent an evidence-supported resale estimate. "
        "Use displayed regular listing prices, not crossed-out historical prices or promotional/offer prices. "
        "Do not invent sold prices, conditions or details when pages are inaccessible. "
        "An approved website is not proof that the product, condition or price matches.\n\n"
    )
