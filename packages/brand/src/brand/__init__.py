from .config import BrandConfig

__all__ = ["BrandAnalyzer", "BrandConfig"]


def __getattr__(name: str):
    if name == "BrandAnalyzer":
        from .service import BrandAnalyzer

        return BrandAnalyzer
    raise AttributeError(name)
