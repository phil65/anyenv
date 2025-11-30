"""Process management for background command execution."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from anyenv.log import get_logger
from anyenv.process_manager.models import ProcessOutput


if TYPE_CHECKING:
    from pathlib import Path


logger = get_logger(__name__)


@dataclass
class RunningProcess:
    """Represents a running background process."""

    process_id: str
    command: str
    args: list[str]
    process: asyncio.subprocess.Process
    cwd: Path | None = None
    env: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    output_limit: int | None = None
    _stdout_buffer: list[str] = field(default_factory=list)
    _stderr_buffer: list[str] = field(default_factory=list)
    _output_size: int = 0
    _truncated: bool = False

    def add_output(self, stdout: str = "", stderr: str = "") -> None:
        """Add output to buffers, applying size limits."""
        if stdout:
            self._stdout_buffer.append(stdout)
            self._output_size += len(stdout.encode())
        if stderr:
            self._stderr_buffer.append(stderr)
            self._output_size += len(stderr.encode())

        # Apply truncation if limit exceeded
        if self.output_limit and self._output_size > self.output_limit:
            self._truncate_output()
            self._truncated = True

    def _truncate_output(self) -> None:
        """Truncate output from beginning to stay within limit."""
        if not self.output_limit:
            return

        # Combine all output to measure total size
        all_stdout = "".join(self._stdout_buffer)
        all_stderr = "".join(self._stderr_buffer)

        # Calculate how much to keep
        target_size = int(self.output_limit * 0.9)  # Keep 90% of limit

        # Truncate stdout first, then stderr if needed
        if len(all_stdout.encode()) > target_size:
            # Find character boundary for truncation
            truncated_stdout = all_stdout[-target_size:].lstrip()
            self._stdout_buffer = [truncated_stdout]
            self._stderr_buffer = [all_stderr]
        else:
            remaining = target_size - len(all_stdout.encode())
            truncated_stderr = all_stderr[-remaining:].lstrip()
            self._stdout_buffer = [all_stdout]
            self._stderr_buffer = [truncated_stderr]

        # Update size counter
        self._output_size = sum(
            len(chunk.encode()) for chunk in self._stdout_buffer + self._stderr_buffer
        )

    def get_output(self) -> ProcessOutput:
        """Get current process output."""
        stdout = "".join(self._stdout_buffer)
        stderr = "".join(self._stderr_buffer)
        combined = stdout + stderr
        return ProcessOutput(
            stdout=stdout,
            stderr=stderr,
            combined=combined,
            truncated=self._truncated,
            exit_code=self.process.returncode,
            signal=None,  # TODO: Extract signal info if available,
        )

    async def is_running(self) -> bool:
        """Check if process is still running."""
        return self.process.returncode is None

    async def wait_for_exit(self) -> int:
        """Wait for process to complete and return exit code."""
        return await self.process.wait()

    async def kill(self) -> None:
        """Terminate the process."""
        if await self.is_running():
            try:
                self.process.terminate()
                # Give it a moment to terminate gracefully
                try:
                    await asyncio.wait_for(self.process.wait(), timeout=5.0)
                except TimeoutError:
                    # Force kill if it doesn't terminate
                    self.process.kill()
                    await self.process.wait()
            except ProcessLookupError:
                # Process already dead
                pass
