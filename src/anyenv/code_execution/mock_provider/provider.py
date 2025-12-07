"""Mock execution environment for testing."""

from __future__ import annotations

from typing import TYPE_CHECKING
import uuid

from fsspec.implementations.asyn_wrapper import (  # type: ignore[import-untyped]
    AsyncFileSystemWrapper,
)
from fsspec.implementations.memory import MemoryFileSystem  # type: ignore[import-untyped]

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.events import (
    OutputEvent,
    ProcessCompletedEvent,
    ProcessStartedEvent,
)
from anyenv.code_execution.mock_provider.process_manager import MockProcessManager
from anyenv.code_execution.models import ExecutionResult


if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from fsspec.asyn import AsyncFileSystem  # type: ignore[import-untyped]

    from anyenv.code_execution.events import ExecutionEvent
    from anyenv.process_manager.models import ProcessOutput


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
        self._mock_process_manager = MockProcessManager(
            default_output=default_process_output,
            command_outputs=process_outputs,
        )

    @property
    def process_manager(self) -> MockProcessManager:
        """Get the mock process manager."""
        return self._mock_process_manager

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
