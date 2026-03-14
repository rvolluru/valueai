from dataclasses import dataclass


@dataclass(slots=True)
class ConditionConfig:
    category_model_weights_path: str | None = None
    condition_model_weights_path: str | None = None
    rembg_enabled: bool = False
    force_category_classifier: bool = False
    force_efficientnet: bool = False
