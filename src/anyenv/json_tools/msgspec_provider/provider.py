"""MsgSpec provider implementation."""

from __future__ import annotations

from io import TextIOWrapper
from typing import Any

from anyenv.json_tools.base import JsonDumpError, JsonLoadError, JsonProviderBase
from anyenv.json_tools.utils import handle_datetimes, prepare_numpy_arrays


class MsgSpecProvider(JsonProviderBase):
    """MsgSpec implementation of the JSON provider interface."""

    @staticmethod
    def load_json(data: str | bytes | TextIOWrapper) -> Any:
        """Load JSON using msgspec."""
        import msgspec.json

        try:
            match data:
                case TextIOWrapper():
                    data = data.read()
            return msgspec.json.decode(data)
        except msgspec.DecodeError as exc:
            error_msg = f"Invalid JSON: {exc}"
            raise JsonLoadError(error_msg) from exc

    @staticmethod
    def dump_json(
        data: Any,
        indent: bool = False,
        naive_utc: bool = False,
        serialize_numpy: bool = False,
        sort_keys: bool = False,
    ) -> str:
        """Dump data to JSON string using msgspec."""
        import msgspec.json

        try:
            # Handle datetime objects first
            data = handle_datetimes(data, naive_utc)

            # Then process numpy arrays if requested
            if serialize_numpy:
                data = prepare_numpy_arrays(data)
            result = msgspec.json.encode(data, order="sorted" if sort_keys else None)
            if indent:
                return msgspec.json.format(result, indent=2).decode()
            return result.decode()
        except (TypeError, msgspec.EncodeError) as exc:
            error_msg = f"Cannot serialize to JSON: {exc}"
            raise JsonDumpError(error_msg) from exc
