from dataclasses import dataclass, field


@dataclass(slots=True)
class ValuationConfig:
    enabled: bool = True
    providers: list[str] = field(default_factory=lambda: ["stub"])
    currency: str = "USD"
    min_comps: int = 3
    max_comps: int = 25
    debug_default: bool = False
