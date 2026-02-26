from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ImageInput:
    image_id: str
    filename: str
    content_type: str
    bytes_data: bytes
    role_hint: str | None = None


@dataclass(slots=True)
class EvidenceBox:
    image_id: str
    box_id: str
    kind: str
    x1: int
    y1: int
    x2: int
    y2: int
    score: float
    fallback: bool = False


@dataclass(slots=True)
class OcrLine:
    text: str
    confidence: float


@dataclass(slots=True)
class OcrResult:
    image_id: str
    box_id: str
    evidence_kind: str
    lines: list[OcrLine] = field(default_factory=list)
    backend: str = "stub"
    preprocess_steps: list[str] = field(default_factory=list)


@dataclass(slots=True)
class BrandCandidate:
    name: str
    score: float
    evidence: str
    metadata: dict[str, Any] = field(default_factory=dict)

