import re
import unicodedata


_PUNCT_RE = re.compile(r"[^\w\s]+", re.UNICODE)
_SPACE_RE = re.compile(r"\s+")


def normalize_text(value: str) -> str:
    text = unicodedata.normalize("NFKD", value or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold()
    text = _PUNCT_RE.sub(" ", text)
    text = _SPACE_RE.sub(" ", text).strip()
    return text
