"""Package for JSON-related tools.

Provides a uniform interface for JSON serialization/deserialization
with automatic selection of the best available backend.
"""

from __future__ import annotations

import importlib.util
from typing import Any, TYPE_CHECKING

from anyenv.json_tools.base import JsonDumpError, JsonLoadError, JsonProviderBase

if TYPE_CHECKING:
    from collections.abc import Callable
    from io import TextIOWrapper

# Determine the best available provider
_provider: type[JsonProviderBase]

if importlib.util.find_spec("orjson") is not None:
    from anyenv.json_tools.orjson_provider.provider import OrJsonProvider

    _provider = OrJsonProvider
elif importlib.util.find_spec("pydantic_core") is not None:
    from anyenv.json_tools.pydantic_provider.provider import PydanticProvider

    _provider = PydanticProvider
elif importlib.util.find_spec("msgspec") is not None:
    from anyenv.json_tools.msgspec_provider.provider import MsgSpecProvider

    _provider = MsgSpecProvider
else:
    from anyenv.json_tools.stdlib_provider.provider import StdLibProvider

    _provider = StdLibProvider


# Export the provider's methods
load_json: Callable[[str | bytes | TextIOWrapper], Any] = _provider.load_json

dump_json: Callable[[Any, bool, bool, bool], str] = _provider.dump_json

# Export the exception classes for user code
__all__ = ["JsonDumpError", "JsonLoadError", "dump_json", "load_json"]
