"""MsgSpec provider implementation."""

from __future__ import annotations

from io import TextIOWrapper
from typing import Any

from anyenv.json_tools.base import JsonDumpError, JsonLoadError, JsonProviderBase
from anyenv.json_tools.utils import handle_datetimes, prepare_numpy_arrays


def _extract_msgspec_error_info(exc: Exception) -> tuple[str, int | None, int | None]:
    """Extract line and column info from msgspec error message.

    msgspec errors may include position info in various formats.
    """
    msg = str(exc)
    line: int | None = None
    column: int | None = None

    # msgspec typically reports byte position, not line/column
    # Try to extract position info if available
    if " at position " in msg:
        try:
            parts = msg.rsplit(" at position ", 1)
            if len(parts) == 2:
                # Position is byte offset, not line/column
                # We could convert this but would need the source
                pass
        except (ValueError, IndexError):
            pass

    return msg, line, column


class MsgSpecProvider(JsonProviderBase):
    """MsgSpec implementation of the JSON provider interface."""

    @staticmethod
    def load_json(data: str | bytes | TextIOWrapper) -> Any:
        """Load JSON using msgspec."""
        import msgspec.json

        try:
            source_content: str | None = None
            match data:
                case TextIOWrapper():
                    data = data.read()
                    source_content = data
                case str():
                    source_content = data
                case bytes():
                    source_content = data.decode(errors="replace")
            return msgspec.json.decode(data)
        except msgspec.DecodeError as exc:
            msg, line, column = _extract_msgspec_error_info(exc)
            raise JsonLoadError(
                f"Invalid JSON: {msg}",
                line=line,
                column=column,
                source_content=source_content,
            ) from exc

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
