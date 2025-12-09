"""OrJSON provider implementation."""

from __future__ import annotations

from io import TextIOWrapper
from typing import Any

from anyenv.json_tools.base import JsonDumpError, JsonLoadError, JsonProviderBase


def _extract_orjson_error_info(exc: Exception) -> tuple[str, int | None, int | None]:
    """Extract line and column info from orjson error message.

    orjson errors have format like "trailing comma is not allowed: line 4 column 20 (char 40)"
    """
    import re

    msg = str(exc)
    line: int | None = None
    column: int | None = None

    # Pattern: "line X column Y"
    match = re.search(r"line (\d+) column (\d+)", msg)
    if match:
        line = int(match.group(1))
        column = int(match.group(2))

    return msg, line, column


class OrJsonProvider(JsonProviderBase):
    """OrJSON implementation of the JSON provider interface."""

    @staticmethod
    def load_json(data: str | bytes | TextIOWrapper) -> Any:
        """Load JSON using orjson."""
        import orjson

        try:
            source_content: str | None = None
            match data:
                case TextIOWrapper():
                    data = data.read()
                    source_content = data
                case str():
                    source_content = data
                    data = data.encode()
                case bytes():
                    source_content = data.decode(errors="replace")
            return orjson.loads(data)
        except orjson.JSONDecodeError as exc:
            msg, line, column = _extract_orjson_error_info(exc)
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
        """Dump data to JSON string using orjson."""
        import orjson

        try:
            options = 0
            if indent:
                options = orjson.OPT_INDENT_2
            if naive_utc:
                options |= orjson.OPT_NAIVE_UTC
            if serialize_numpy:
                options |= orjson.OPT_SERIALIZE_NUMPY
            if sort_keys:
                options |= orjson.OPT_SORT_KEYS
            result = orjson.dumps(data, option=options)
            return result.decode()
        except (TypeError, ValueError) as exc:
            error_msg = f"Cannot serialize to JSON: {exc}"
            raise JsonDumpError(error_msg) from exc
