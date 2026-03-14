from dataclasses import dataclass


@dataclass(slots=True)
class BrandConfig:
    accept_score: int = 78
    accept_score_low: int = 70
    gap_min: int = 8
    enable_logo_classifier: bool = False
    enable_gpt_vision: bool = False
    gpt_vision_model: str = "gpt-5"
    gpt_vision_timeout_s: float = 20.0
    openai_api_key: str | None = None
    debug_default: bool = False
    detector_weights_path: str | None = None
    logo_classifier_weights_path: str | None = None
    force_logo_classifier: bool = False
    logo_model_type: str = "efficientnet"
    logo_yolo_weights_path: str | None = None
    logo_yolo_confidence: float = 0.35
