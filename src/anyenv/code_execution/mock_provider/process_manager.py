"""Mock process manager for testing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any
import uuid

from anyenv.process_manager.models import ProcessOutput
from anyenv.process_manager.protocol import ProcessManagerProtocol


if TYPE_CHECKING:
    from pathlib import Path


@dataclass
class MockProcessInfo:
    """Information about a mock process."""

    process_id: str
    command: str
    args: list[str]
    cwd: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    created_at: datetime = field(default_factory=datetime.now)
    output: ProcessOutput | None = None
    running: bool = True
    exit_code: int | None = None


class MockProcessManager(ProcessManagerProtocol):
    """Mock process manager that returns predefined outputs."""

    def __init__(
        self,
        default_output: ProcessOutput | None = None,
        command_outputs: dict[str, ProcessOutput] | None = None,
    ) -> None:
        """Initialize mock process manager.

        Args:
            default_output: Default output for any command
            command_outputs: Map of command -> output for specific commands
        """
        self._default_output = default_output or ProcessOutput(
            stdout="",
            stderr="",
            combined="",
            exit_code=0,
        )
        self._command_outputs = command_outputs or {}
        self._processes: dict[str, MockProcessInfo] = {}

    async def start_process(
        self,
        command: str,
        args: list[str] | None = None,
        cwd: str | Path | None = None,
        env: dict[str, str] | None = None,
        output_limit: int | None = None,
    ) -> str:
        """Start a mock process."""
        process_id = f"mock_{uuid.uuid4().hex[:8]}"
        args = args or []

        # Determine output based on command
        full_command = f"{command} {' '.join(args)}".strip()
        output = self._command_outputs.get(
            full_command,
            self._command_outputs.get(command, self._default_output),
        )

        self._processes[process_id] = MockProcessInfo(
            process_id=process_id,
            command=command,
            args=args,
            cwd=str(cwd) if cwd else None,
            env=env or {},
            output=output,
            running=True,
        )
        return process_id

    async def get_output(self, process_id: str) -> ProcessOutput:
        """Get output from a mock process."""
        if process_id not in self._processes:
            msg = f"Process {process_id} not found"
            raise ValueError(msg)

        proc = self._processes[process_id]
        return proc.output or self._default_output

    async def wait_for_exit(self, process_id: str) -> int:
        """Wait for mock process to complete (returns immediately)."""
        if process_id not in self._processes:
            msg = f"Process {process_id} not found"
            raise ValueError(msg)

        proc = self._processes[process_id]
        proc.running = False
        exit_code = proc.output.exit_code if proc.output else 0
        proc.exit_code = exit_code
        return exit_code or 0

    async def kill_process(self, process_id: str) -> None:
        """Kill a mock process."""
        if process_id not in self._processes:
            msg = f"Process {process_id} not found"
            raise ValueError(msg)

        proc = self._processes[process_id]
        proc.running = False
        proc.exit_code = 130  # SIGINT

    async def release_process(self, process_id: str) -> None:
        """Release mock process resources."""
        if process_id not in self._processes:
            msg = f"Process {process_id} not found"
            raise ValueError(msg)

        del self._processes[process_id]

    async def list_processes(self) -> list[str]:
        """List all mock processes."""
        return list(self._processes.keys())

    async def get_process_info(self, process_id: str) -> dict[str, Any]:
        """Get information about a mock process."""
        if process_id not in self._processes:
            msg = f"Process {process_id} not found"
            raise ValueError(msg)

        proc = self._processes[process_id]
        return {
            "process_id": proc.process_id,
            "command": proc.command,
            "args": proc.args,
            "cwd": proc.cwd,
            "created_at": proc.created_at.isoformat(),
            "is_running": proc.running,
            "exit_code": proc.exit_code,
        }
