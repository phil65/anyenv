"""JSON loading functionality with fallback options."""

from __future__ import annotations

import importlib.util
from io import TextIOWrapper
from typing import Any


# Find the best available JSON parser
if importlib.util.find_spec("orjson") is not None:
    import orjson

    def load_json(data: str | bytes | TextIOWrapper) -> Any:
        """Load JSON using orjson."""
        match data:
            case TextIOWrapper():
                data = data.read()
            case str():
                data = data.encode()
        return orjson.loads(data)

elif importlib.util.find_spec("pydantic_core") is not None:
    from pydantic_core import from_json

    def load_json(data: str | bytes | TextIOWrapper) -> Any:
        """Load JSON using pydantic_core."""
        match data:
            case TextIOWrapper():
                data = data.read()
        return from_json(data)

else:
    import json

    def load_json(data: str | bytes | TextIOWrapper) -> Any:
        """Load JSON using stdlib json."""
        match data:
            case TextIOWrapper():
                data = data.read()
            case bytes():
                data = data.decode()
        return json.loads(data)
