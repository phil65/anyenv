"""Base interface for JSON providers."""

from __future__ import annotations

import abc
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from io import TextIOWrapper


class JsonProviderBase(abc.ABC):
    """Base class for all JSON providers."""

    @staticmethod
    @abc.abstractmethod
    def load_json(data: str | bytes | TextIOWrapper) -> Any:
        """Load JSON data into Python objects."""

    @staticmethod
    @abc.abstractmethod
    def dump_json(
        data: Any,
        indent: bool = False,
        naive_utc: bool = False,
        serialize_numpy: bool = False,
        sort_keys: bool = False,
    ) -> str:
        """Dump Python objects to JSON string."""


class JsonLoadError(Exception):
    """Unified exception for all JSON parsing errors."""


class JsonDumpError(Exception):
    """Unified exception for all JSON serialization errors."""
