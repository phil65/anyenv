"""JSON loading functionality with fallback options."""

from __future__ import annotations

import importlib.util
from io import TextIOWrapper
from typing import Any


class JsonLoadError(Exception):
    """Unified exception for all JSON parsing and serialization errors."""


# Find the best available JSON parser for loading
if importlib.util.find_spec("orjson") is not None:
    import orjson

    def load_json(data: str | bytes | TextIOWrapper) -> Any:
        """Load JSON using orjson."""
        try:
            match data:
                case TextIOWrapper():
                    data = data.read()
                case str():
                    data = data.encode()
            return orjson.loads(data)
        except orjson.JSONDecodeError as exc:
            error_msg = f"Invalid JSON: {exc}"
            raise JsonLoadError(error_msg) from exc

elif importlib.util.find_spec("pydantic_core") is not None:
    from pydantic_core import from_json

    def load_json(data: str | bytes | TextIOWrapper) -> Any:
        """Load JSON using pydantic_core."""
        try:
            match data:
                case TextIOWrapper():
                    data = data.read()
            return from_json(data)
        except Exception as exc:
            error_msg = f"Invalid JSON: {exc}"
            raise JsonLoadError(error_msg) from exc

elif importlib.util.find_spec("msgspec") is not None:
    import msgspec.json

    def load_json(data: str | bytes | TextIOWrapper) -> Any:
        """Load JSON using msgspec."""
        try:
            match data:
                case TextIOWrapper():
                    data = data.read()
            return msgspec.json.decode(data)
        except msgspec.DecodeError as exc:
            error_msg = f"Invalid JSON: {exc}"
            raise JsonLoadError(error_msg) from exc

else:
    import json

    def load_json(data: str | bytes | TextIOWrapper) -> Any:
        """Load JSON using stdlib json."""
        try:
            match data:
                case TextIOWrapper():
                    data = data.read()
                case bytes():
                    data = data.decode()
            return json.loads(data)
        except json.JSONDecodeError as exc:
            error_msg = f"Invalid JSON: {exc}"
            raise JsonLoadError(error_msg) from exc
