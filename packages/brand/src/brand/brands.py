import json
from dataclasses import dataclass
from importlib import resources

from .normalization import normalize_text


@dataclass(slots=True)
class BrandRecord:
    canonical: str
    aliases: list[str]


def load_brands() -> list[BrandRecord]:
    with resources.files("brand").joinpath("brands.json").open("r", encoding="utf-8") as f:
        payload = json.load(f)
    out: list[BrandRecord] = []
    for row in payload:
        canonical = row["name"]
        aliases = list(dict.fromkeys([canonical, *row.get("aliases", [])]))
        out.append(BrandRecord(canonical=canonical, aliases=aliases))
    return out


def alias_lookup(records: list[BrandRecord]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for rec in records:
        for alias in rec.aliases:
            mapping[normalize_text(alias)] = rec.canonical
    return mapping
