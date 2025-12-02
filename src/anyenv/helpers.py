"""Helper functions for AnyEnv."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from collections.abc import Callable
    import types


def get_object_name(fn: Callable[..., Any] | types.ModuleType, fallback: str = "<unknown>") -> str:
    """Get the name of a function."""
    name = getattr(fn, "__name__", None)
    if name is None:
        return fallback
    assert isinstance(name, str)
    return name


def get_object_qualname(
    fn: Callable[..., Any] | types.ModuleType, fallback: str = "<unknown>"
) -> str:
    """Get the qualified name of a function."""
    name = getattr(fn, "__qualname__", None)
    if name is None:
        return fallback
    assert isinstance(name, str)
    return name
