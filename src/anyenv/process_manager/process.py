"""Process management for background command execution."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING

from anyenv.log import get_logger
from anyenv.process_manager.models import ProcessOutput
from anyenv.processes import hard_kill


if TYPE_CHECKING:
    import asyncio
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
        """Drop output from the beginning, keeping the combined tail within the limit.

        The budget (90% of the limit, in bytes) is shared: a stream that needs less
        than half keeps all of it, the other gets the rest.
        """
        if not self.output_limit:
            return

        all_stdout = "".join(self._stdout_buffer).encode()
        all_stderr = "".join(self._stderr_buffer).encode()
        budget = int(self.output_limit * 0.9)  # Keep 90% of limit
        stderr_budget = min(len(all_stderr), max(budget // 2, budget - len(all_stdout)))
        stdout_budget = budget - stderr_budget
        stdout = _tail(all_stdout, stdout_budget)
        stderr = _tail(all_stderr, stderr_budget)
        self._stdout_buffer = [stdout] if stdout else []
        self._stderr_buffer = [stderr] if stderr else []
        self._output_size = len(stdout.encode()) + len(stderr.encode())

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
        """Terminate the process and its children (SIGTERM, then SIGKILL)."""
        if await self.is_running():
            await hard_kill(self.process)


def _tail(data: bytes, size: int) -> str:
    """The last `size` bytes of data, decoded; a character cut in half is dropped."""
    if size <= 0:
        return ""
    return data[-size:].decode("utf-8", errors="ignore")
