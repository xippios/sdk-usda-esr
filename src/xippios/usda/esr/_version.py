"""Package version, read from the installed distribution metadata."""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("xippios-usda-esr")
except PackageNotFoundError:  # pragma: no cover - only in an unbuilt checkout
    __version__ = "0.0.0"

__all__ = ["__version__"]
