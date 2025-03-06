"""JSON dumping functionality with fallback options."""

from __future__ import annotations

import importlib.util
from typing import Any


# Find the best available JSON dumper
if importlib.util.find_spec("orjson") is not None:
    import orjson

    def dump_json(data: Any, indent: bool = False) -> str:
        """Dump data to JSON string using orjson."""
        options = 0
        if indent:
            options = orjson.OPT_INDENT_2

        result = orjson.dumps(data, option=options)
        return result.decode()

elif importlib.util.find_spec("pydantic_core") is not None:
    from pydantic_core import to_json

    def dump_json(data: Any, indent: bool = False) -> str:
        """Dump data to JSON string using pydantic_core."""
        return to_json(data, indent=2 if indent else None).decode()

else:
    import json

    def dump_json(data: Any, indent: bool = False) -> str:
        """Dump data to JSON string using stdlib json."""
        return json.dumps(data, indent=2 if indent else None)
