"""Upath + Path fallback."""

from __future__ import annotations


try:
    from upath import UPath as Path
except ImportError:
    from pathlib import Path  # type: ignore[assignment]  # noqa: F401
