"""Resolve which httpx flavour (httpx2 or legacy httpx) to use."""

from __future__ import annotations

import importlib
import importlib.util
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from types import ModuleType


HTTPX_MODULE_NAMES = ("httpx2", "httpx")
"""Supported httpx flavours, in order of preference."""


def get_httpx_module(name: str | None = None) -> ModuleType:
    """Return the httpx module to use.

    Args:
        name: Explicit module name ("httpx2" or "httpx"). If omitted, httpx2 is
              preferred and legacy httpx is used as a fallback.

    Raises:
        ImportError: If no httpx flavour is installed.
    """
    if name is not None:
        return importlib.import_module(name)
    for candidate in HTTPX_MODULE_NAMES:
        if importlib.util.find_spec(candidate):
            return importlib.import_module(candidate)
    msg = "No httpx flavour installed. Install `anyenv[httpx2]` (recommended)."
    raise ImportError(msg)
