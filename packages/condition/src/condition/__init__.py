from .config import ConditionConfig

__all__ = ["ConditionAnalyzer", "ConditionConfig"]


def __getattr__(name: str):
    if name == "ConditionAnalyzer":
        from .service import ConditionAnalyzer

        return ConditionAnalyzer
    raise AttributeError(name)
