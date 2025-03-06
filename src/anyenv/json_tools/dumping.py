"""JSON dumping functionality with fallback options."""

from __future__ import annotations

import importlib.util
from typing import Any


class JsonDumpError(Exception):
    """Unified exception for all JSON serialization errors."""


# Find the best available JSON dumper
if importlib.util.find_spec("orjson") is not None:
    import orjson

    def dump_json(data: Any, indent: bool = False) -> str:
        """Dump data to JSON string using orjson."""
        try:
            options = 0
            if indent:
                options = orjson.OPT_INDENT_2

            result = orjson.dumps(data, option=options)
            return result.decode()
        except (TypeError, ValueError) as exc:
            error_msg = f"Cannot serialize to JSON: {exc}"
            raise JsonDumpError(error_msg) from exc

elif importlib.util.find_spec("pydantic_core") is not None:
    from pydantic_core import to_json

    def dump_json(data: Any, indent: bool = False) -> str:
        """Dump data to JSON string using pydantic_core."""
        try:
            return to_json(data, indent=2 if indent else None).decode()
        except Exception as exc:
            error_msg = f"Cannot serialize to JSON: {exc}"
            raise JsonDumpError(error_msg) from exc

elif importlib.util.find_spec("msgspec") is not None:
    import msgspec.json

    def dump_json(data: Any, indent: bool = False) -> str:
        """Dump data to JSON string using msgspec."""
        try:
            result = msgspec.json.encode(data)
            if indent:
                return msgspec.json.format(result, indent=2).decode()
            return result.decode()
        except (TypeError, msgspec.EncodeError) as exc:
            error_msg = f"Cannot serialize to JSON: {exc}"
            raise JsonDumpError(error_msg) from exc

else:
    import json

    def dump_json(data: Any, indent: bool = False) -> str:
        """Dump data to JSON string using stdlib json."""
        try:
            return json.dumps(data, indent=2 if indent else None)
        except (TypeError, ValueError) as exc:
            error_msg = f"Cannot serialize to JSON: {exc}"
            raise JsonDumpError(error_msg) from exc
