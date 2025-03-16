"""Pydantic provider implementation."""

from __future__ import annotations

from io import TextIOWrapper
from typing import Any

from anyenv.json_tools.base import JsonDumpError, JsonLoadError, JsonProviderBase
from anyenv.json_tools.utils import handle_datetimes, prepare_numpy_arrays


class PydanticProvider(JsonProviderBase):
    """Pydantic implementation of the JSON provider interface."""

    @staticmethod
    def load_json(data: str | bytes | TextIOWrapper) -> Any:
        """Load JSON using pydantic_core."""
        from pydantic_core import from_json

        try:
            match data:
                case TextIOWrapper():
                    data = data.read()
            return from_json(data)
        except Exception as exc:
            error_msg = f"Invalid JSON: {exc}"
            raise JsonLoadError(error_msg) from exc

    @staticmethod
    def dump_json(
        data: Any,
        indent: bool = False,
        naive_utc: bool = False,
        serialize_numpy: bool = False,
    ) -> str:
        """Dump data to JSON string using pydantic_core."""
        from pydantic_core import to_json

        try:
            # Handle datetime objects first
            data = handle_datetimes(data, naive_utc)

            # Then process numpy arrays if requested
            if serialize_numpy:
                data = prepare_numpy_arrays(data)

            return to_json(data, indent=2 if indent else None).decode()
        except Exception as exc:
            error_msg = f"Cannot serialize to JSON: {exc}"
            raise JsonDumpError(error_msg) from exc
