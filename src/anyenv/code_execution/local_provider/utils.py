"""Local execution environment that runs code locally."""

from __future__ import annotations

import asyncio
import contextlib
import io
import json
from typing import Any, TextIO


PYTHON_EXECUTABLES = [
    "python3",
    "python",
    "python3.13",
    "python3.12",
    "python3.11",
    "python3.14",
]


class StreamCapture(io.StringIO):
    """Capture and forward output to a queue."""

    def __init__(
        self,
        original_stream: TextIO,
        queue: asyncio.Queue[str],
    ) -> None:
        super().__init__()
        self.original_stream = original_stream
        self.queue = queue

    def write(self, text: str) -> int:
        """Capture and forward output to a queue."""
        result = self.original_stream.write(text)
        if text:
            lines = text.splitlines(keepends=True)
            for line in lines:
                if line.strip():
                    with contextlib.suppress(asyncio.QueueFull):
                        self.queue.put_nowait(line.rstrip("\n\r"))
        return result

    def flush(self) -> None:
        """Flush the stream."""
        return self.original_stream.flush()


def parse_subprocess_output(output: str) -> tuple[Any, dict[str, Any] | None]:
    """Parse subprocess output to extract result or error."""
    lines = output.strip().split("\n")

    # Look for result markers
    result_start: int | None = None
    result_end: int | None = None
    error_start: int | None = None
    error_end: int | None = None

    for i, line in enumerate(lines):
        if "__RESULT_START__" in line:
            result_start = i + 1
        elif "__RESULT_END__" in line:
            result_end = i
        elif "__ERROR_START__" in line:
            error_start = i + 1
        elif "__ERROR_END__" in line:
            error_end = i

    # Parse error first (takes precedence)
    if error_start is not None and error_end is not None:
        try:
            error_json = "\n".join(lines[error_start:error_end])
            return None, json.loads(error_json)
        except json.JSONDecodeError:
            return None, {
                "error": "Failed to parse error output",
                "type": "ParseError",
            }

    # Parse result
    if result_start is not None and result_end is not None:
        try:
            result_json = "\n".join(lines[result_start:result_end])
            result_data = json.loads(result_json)
            return result_data.get("result"), None
        except json.JSONDecodeError:
            return None, {
                "error": "Failed to parse result output",
                "type": "ParseError",
            }

    # No markers found
    return None, {"error": "No execution result found", "type": "ParseError"}
