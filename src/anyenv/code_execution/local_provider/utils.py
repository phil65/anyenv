"""Local execution environment that runs code locally."""

from __future__ import annotations

import asyncio
import contextlib
import io
from typing import TextIO


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
