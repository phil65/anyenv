"""Output parsing utilities."""

from __future__ import annotations

from typing import Any


def parse_output(output: str) -> tuple[Any, dict[str, Any] | None]:
    """Parse result from sandbox output."""
    import anyenv

    try:
        lines = output.strip().split("\n")
        for line in lines:
            if line.startswith("__RESULT__"):
                result_json = line[len("__RESULT__") :].strip()
                result_data = anyenv.load_json(result_json, return_type=dict)

                if result_data.get("success", False):
                    return result_data.get("result"), None
                return None, {
                    "error": result_data.get("error", "Unknown error"),
                    "type": result_data.get("type", "Unknown"),
                }
    except anyenv.JsonLoadError as e:
        return None, {
            "error": f"Failed to parse result: {e}",
            "type": "JSONDecodeError",
        }
    except Exception as e:  # noqa: BLE001
        return None, {"error": str(e), "type": type(e).__name__}
    else:
        return None, {"error": "No execution result found", "type": "ParseError"}
