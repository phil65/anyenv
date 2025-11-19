"""Process management for background command execution."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Protocol

from anyenv.log import get_logger


if TYPE_CHECKING:
    from pathlib import Path

    from anyenv.process_manager.models import ProcessOutput


logger = get_logger(__name__)


class ProcessManagerProtocol(Protocol):
    """Protocol for managing background processes."""

    async def start_process(
        self,
        command: str,
        args: list[str] | None = None,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        output_limit: int | None = None,
    ) -> str:
        """Start a background process.

        Returns:
            Process ID for tracking
        """
        ...

    async def get_output(self, process_id: str) -> ProcessOutput:
        """Get current output from a process.

        Returns:
            Current process output
        """
        ...

    async def wait_for_exit(self, process_id: str) -> int:
        """Wait for process to complete.

        Returns:
            Exit code
        """
        ...

    async def kill_process(self, process_id: str) -> None:
        """Kill a running process."""
        ...

    async def release_process(self, process_id: str) -> None:
        """Release process resources."""
        ...

    async def list_processes(self) -> list[str]:
        """List all running processes."""
        ...

    async def get_process_info(self, process_id: str) -> dict[str, Any]:
        """Get information about a process.

        Returns:
            Process information
        """
        ...
