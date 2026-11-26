"""Upath + Path fallback."""

try:
    from upath import UPath as AnyPath
except ImportError:
    from pathlib import Path as AnyPath  # type: ignore[assignment]

__all__ = ["AnyPath"]
