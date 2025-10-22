"""Base interface for TOML providers."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from io import TextIOWrapper
    from pathlib import Path


class TomlProviderBase(abc.ABC):
    """Base class for all TOML providers."""

    @staticmethod
    @abc.abstractmethod
    def load_toml(data: str | bytes | TextIOWrapper | Path) -> Any:
        """Load TOML data into Python objects."""

    @staticmethod
    @abc.abstractmethod
    def dump_toml(
        data: Any,
        *,
        pretty: bool = False,
    ) -> str:
        """Dump Python objects to TOML string."""


class TomlLoadError(Exception):
    """Unified exception for all TOML parsing errors."""


class TomlDumpError(Exception):
    """Unified exception for all TOML serialization errors."""
