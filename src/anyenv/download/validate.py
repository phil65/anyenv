from __future__ import annotations

import importlib.util
from typing import Any, cast


_has_pydantic = importlib.util.find_spec("pydantic") is not None


def validate_json_data[T](data: Any, return_type: type[T] | None) -> T:
    """Validate and convert JSON data to the requested return type.

    Args:
        data: The JSON data to validate
        return_type: The expected return type

    Returns:
        The validated data

    Raises:
        TypeError: If validation fails
    """
    if return_type is None:
        return cast(T, data)

    # Simple type check for built-in types
    if return_type in (dict, list, str, int, float, bool, None):
        if not isinstance(data, return_type):
            error_msg = f"Expected {return_type.__name__}, got {type(data).__name__}"
            raise TypeError(error_msg)
        return cast(T, data)

    # If it's a Pydantic model
    if _has_pydantic and hasattr(return_type, "model_validate"):
        try:
            from pydantic import ValidationError

            try:
                return return_type.model_validate(data)  # type: ignore
            except ValidationError as e:
                error_msg = f"Pydantic validation error: {e}"
                raise TypeError(error_msg) from e
        except ImportError:
            error_msg = "Pydantic is required for model validation"
            raise ImportError(error_msg)  # noqa: B904

    # Fallback - simple isinstance check
    if not isinstance(data, return_type):
        error_msg = f"Expected {return_type.__name__}, got {type(data).__name__}"
        raise TypeError(error_msg)

    return cast(T, data)
