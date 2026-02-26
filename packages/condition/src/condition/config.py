from dataclasses import dataclass


@dataclass(slots=True)
class ConditionConfig:
    category_model_weights_path: str | None = None
    condition_model_weights_path: str | None = None
    rembg_enabled: bool = False
