"""Mock execution environment for testing."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import TYPE_CHECKING, Any
import uuid

from fsspec.implementations.asyn_wrapper import AsyncFileSystemWrapper
from fsspec.implementations.memory import MemoryFileSystem

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.events import (
    OutputEvent,
    ProcessCompletedEvent,
    ProcessStartedEvent,
)
from anyenv.code_execution.models import ExecutionResult
from anyenv.process_manager.models import ProcessOutput
from anyenv.process_manager.protocol import ProcessManagerProtocol


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from pathlib import Path

    from fsspec.asyn import AsyncFileSystem

    from anyenv.code_execution.events import (
        ExecutionEvent,
    )


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


class MockExecutionEnvironment(ExecutionEnvironment):
    """Mock execution environment for testing with memory FS and fake processes."""

    def __init__(
        self,
        code_results: dict[str, ExecutionResult] | None = None,
        command_results: dict[str, ExecutionResult] | None = None,
        default_result: ExecutionResult | None = None,
        process_outputs: dict[str, ProcessOutput] | None = None,
        default_process_output: ProcessOutput | None = None,
    ) -> None:
        """Initialize mock execution environment.

        Args:
            code_results: Map of code string -> result for execute()
            command_results: Map of command string -> result for execute_command()
            default_result: Default result when no match found
            process_outputs: Map of command -> output for process manager
            default_process_output: Default output for process manager
        """
        super().__init__()
        self._code_results = code_results or {}
        self._command_results = command_results or {}
        self._default_result = default_result or ExecutionResult(
            result=None,
            duration=0.001,
            success=True,
            stdout="",
            stderr="",
            exit_code=0,
        )
        self._sync_fs = MemoryFileSystem()
        self._fs = AsyncFileSystemWrapper(self._sync_fs)
        self._process_manager = MockProcessManager(
            default_output=default_process_output,
            command_outputs=process_outputs,
        )

    @property
    def process_manager(self) -> MockProcessManager:
        """Get the mock process manager."""
        return self._process_manager

    def get_fs(self) -> AsyncFileSystem:
        """Return the async-wrapped memory filesystem."""
        return self._fs

    async def execute(self, code: str) -> ExecutionResult:
        """Execute code and return mock result."""
        return self._code_results.get(code, self._default_result)

    async def execute_command(self, command: str) -> ExecutionResult:
        """Execute command and return mock result."""
        return self._command_results.get(command, self._default_result)

    async def stream_code(self, code: str) -> AsyncIterator[ExecutionEvent]:
        """Stream mock code execution events."""
        result = self._code_results.get(code, self._default_result)
        process_id = f"stream_{uuid.uuid4().hex[:8]}"

        yield ProcessStartedEvent(process_id=process_id, command="python", pid=12345)
        if result.stdout:
            yield OutputEvent(process_id=process_id, data=result.stdout, stream="stdout")
        if result.stderr:
            yield OutputEvent(process_id=process_id, data=result.stderr, stream="stderr")

        yield ProcessCompletedEvent(
            process_id=process_id,
            exit_code=result.exit_code or (0 if result.success else 1),
            duration=result.duration,
        )

    async def stream_command(self, command: str) -> AsyncIterator[ExecutionEvent]:
        """Stream mock command execution events."""
        result = self._command_results.get(command, self._default_result)
        process_id = f"cmd_{uuid.uuid4().hex[:8]}"

        yield ProcessStartedEvent(process_id=process_id, command=command, pid=12345)
        if result.stdout:
            yield OutputEvent(process_id=process_id, data=result.stdout, stream="stdout")
        if result.stderr:
            yield OutputEvent(process_id=process_id, data=result.stderr, stream="stderr")

        yield ProcessCompletedEvent(
            process_id=process_id,
            exit_code=result.exit_code or (0 if result.success else 1),
            duration=result.duration,
        )
