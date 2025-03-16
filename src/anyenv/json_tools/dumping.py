"""JSON dumping functionality with fallback options."""

from __future__ import annotations

import datetime
import importlib.util
from typing import Any


class JsonDumpError(Exception):
    """Unified exception for all JSON serialization errors."""


def _handle_datetimes(data: Any, naive_utc: bool) -> Any:
    """Handle datetime objects consistently across serializers.

    If naive_utc=False: Raise an error for naive datetime objects
    If naive_utc=True: Treat naive datetime objects as UTC
    """

    # Define a recursive conversion function
    def _convert(obj: Any) -> Any:
        if isinstance(obj, datetime.datetime):
            # Check if it's a naive datetime (no tzinfo)
            if obj.tzinfo is None:
                if not naive_utc:
                    msg = (
                        "Naive datetime objects are not allowed. "
                        "Set naive_utc=True or provide timezone."
                    )
                    raise ValueError(msg)
                # Interpret as UTC without changing the actual time
                return obj.replace(tzinfo=datetime.UTC)

        # Handle nested dictionaries
        elif isinstance(obj, dict):
            return {key: _convert(value) for key, value in obj.items()}
        # Handle lists, tuples, and sets
        elif isinstance(obj, list | tuple | set):
            return [_convert(item) for item in obj]

        # Return other types as-is
        return obj

    return _convert(data)


def _prepare_numpy_arrays(data: Any) -> Any:
    """Recursively convert NumPy arrays to Python lists.

    This function detects if NumPy is available and, if so, handles converting
    NumPy arrays to native Python types for JSON serialization.
    """
    # Check if numpy is available
    numpy_available = importlib.util.find_spec("numpy") is not None
    if not numpy_available:
        return data

    import numpy as np

    # Define a recursive conversion function
    def _convert(obj: Any) -> Any:  # noqa: PLR0911
        # Convert numpy arrays to lists
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        # Convert numpy scalar types to Python scalars
        if isinstance(
            obj,
            np.integer
            | np.int_
            | np.intc
            | np.intp
            | np.int8
            | np.int16
            | np.int32
            | np.int64
            | np.uint8
            | np.uint16
            | np.uint32
            | np.uint64,
        ):
            return int(obj)
        if isinstance(obj, np.float_ | np.float16 | np.float32 | np.float64):
            return float(obj)
        if isinstance(obj, (np.bool_)):
            return bool(obj)
        # Handle nested dictionaries
        if isinstance(obj, dict):
            return {key: _convert(value) for key, value in obj.items()}
        # Handle lists, tuples, and sets
        if isinstance(obj, list | tuple | set):
            return [_convert(item) for item in obj]
        # Return other types as-is
        return obj

    return _convert(data)


# Find the best available JSON dumper
if importlib.util.find_spec("orjson") is not None:
    import orjson

    def dump_json(
        data: Any,
        indent: bool = False,
        naive_utc: bool = False,
        serialize_numpy: bool = False,
    ) -> str:
        """Dump data to JSON string using orjson."""
        try:
            options = 0
            if indent:
                options = orjson.OPT_INDENT_2
            if naive_utc:
                options |= orjson.OPT_NAIVE_UTC
            if serialize_numpy:
                options |= orjson.OPT_SERIALIZE_NUMPY
            result = orjson.dumps(data, option=options)
            return result.decode()
        except (TypeError, ValueError) as exc:
            error_msg = f"Cannot serialize to JSON: {exc}"
            raise JsonDumpError(error_msg) from exc

elif importlib.util.find_spec("pydantic_core") is not None:
    from pydantic_core import to_json

    def dump_json(
        data: Any,
        indent: bool = False,
        naive_utc: bool = False,
        serialize_numpy: bool = False,
    ) -> str:
        """Dump data to JSON string using pydantic_core."""
        try:
            # Handle datetime objects first
            data = _handle_datetimes(data, naive_utc)

            # Then process numpy arrays if requested
            if serialize_numpy:
                data = _prepare_numpy_arrays(data)

            return to_json(data, indent=2 if indent else None).decode()
        except Exception as exc:
            error_msg = f"Cannot serialize to JSON: {exc}"
            raise JsonDumpError(error_msg) from exc

elif importlib.util.find_spec("msgspec") is not None:
    import msgspec.json

    def dump_json(
        data: Any,
        indent: bool = False,
        naive_utc: bool = False,
        serialize_numpy: bool = False,
    ) -> str:
        """Dump data to JSON string using msgspec."""
        try:
            # Handle datetime objects first
            data = _handle_datetimes(data, naive_utc)
            # Then process numpy arrays if requested
            if serialize_numpy:
                data = _prepare_numpy_arrays(data)

            result = msgspec.json.encode(data)
            if indent:
                return msgspec.json.format(result, indent=2).decode()
            return result.decode()
        except (TypeError, msgspec.EncodeError) as exc:
            error_msg = f"Cannot serialize to JSON: {exc}"
            raise JsonDumpError(error_msg) from exc

else:
    import json

    def dump_json(
        data: Any,
        indent: bool = False,
        naive_utc: bool = False,
        serialize_numpy: bool = False,
    ) -> str:
        """Dump data to JSON string using stdlib json."""
        try:
            # Handle datetime objects first
            data = _handle_datetimes(data, naive_utc)

            # Then process numpy arrays if requested
            if serialize_numpy:
                data = _prepare_numpy_arrays(data)

            # Standard library's json can't handle datetime objects directly
            # So we need a custom encoder
            class CustomEncoder(json.JSONEncoder):
                def default(self, obj: Any) -> Any:
                    if isinstance(obj, datetime.datetime):
                        return obj.isoformat()
                    return super().default(obj)

            return json.dumps(data, indent=2 if indent else None, cls=CustomEncoder)
        except (TypeError, ValueError) as exc:
            error_msg = f"Cannot serialize to JSON: {exc}"
            raise JsonDumpError(error_msg) from exc
