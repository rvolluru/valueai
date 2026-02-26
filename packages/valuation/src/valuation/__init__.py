from .config import ValuationConfig

__all__ = ["ValuationService", "ValuationConfig"]


def __getattr__(name: str):
    if name == "ValuationService":
        from .service import ValuationService

        return ValuationService
    raise AttributeError(name)
