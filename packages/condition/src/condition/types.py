from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ConditionIssue:
    type: str
    severity: str
    location: str = "unknown"


@dataclass(slots=True)
class ConditionResult:
    category: str
    category_confidence: float
    grade: str
    confidence: float
    issues: list[ConditionIssue] = field(default_factory=list)
    debug: dict[str, Any] = field(default_factory=dict)
