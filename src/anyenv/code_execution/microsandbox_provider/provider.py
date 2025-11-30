"""Microsandbox execution environment that runs code in lightweight sandboxes."""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING, Self

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.events import (
    OutputEvent,
    ProcessCompletedEvent,
    ProcessErrorEvent,
    ProcessStartedEvent,
)
from anyenv.code_execution.models import ExecutionResult
from anyenv.code_execution.parse_output import parse_command


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager
    from types import TracebackType

    from microsandbox import NodeSandbox, PythonSandbox
    from upathtools.filesystems import MicrosandboxFS

    from anyenv.code_execution.events import ExecutionEvent
    from anyenv.code_execution.models import Language, ServerInfo


class MicrosandboxExecutionEnvironment(ExecutionEnvironment):
    """Executes code in a Microsandbox containerized environment."""

    def __init__(
        self,
        lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
        dependencies: list[str] | None = None,
        server_url: str | None = None,
        namespace: str = "default",
        api_key: str | None = None,
        memory: int = 512,
        cpus: float = 1.0,
        timeout: float = 180.0,
        language: Language = "python",
        image: str | None = None,
    ) -> None:
        """Initialize Microsandbox environment.

        Args:
            lifespan_handler: Async context manager for tool server (optional)
            dependencies: List of packages to install via pip / npm
            server_url: Microsandbox server URL (defaults to MSB_SERVER_URL env var)
            namespace: Sandbox namespace
            api_key: API key for authentication (uses MSB_API_KEY env var if None)
            memory: Memory limit in MB
            cpus: CPU limit
            timeout: Sandbox start timeout in seconds
            language: Programming language to use
            image: Custom Docker image (uses default for language if None)
        """
        super().__init__(lifespan_handler=lifespan_handler, dependencies=dependencies)
        self.server_url = server_url
        self.namespace = namespace
        self.api_key = api_key
        self.memory = memory
        self.cpus = cpus
        self.timeout = timeout
        self.language = language
        self.image = image
        self.sandbox: PythonSandbox | NodeSandbox | None = None

    def _ensure_initialized(self) -> PythonSandbox | NodeSandbox:
        """Validate that the environment is properly initialized.

        Returns:
            The sandbox instance.

        Raises:
            RuntimeError: If environment not entered via async context manager.
        """
        if self.sandbox is None:
            msg = "Microsandbox environment not initialized. Use 'async with' context manager."
            raise RuntimeError(msg)
        return self.sandbox

    async def __aenter__(self) -> Self:
        """Setup Microsandbox environment."""
        # Start tool server via base class
        await super().__aenter__()
        from microsandbox import NodeSandbox, PythonSandbox

        match self.language:
            case "python":
                sandbox_class = PythonSandbox
            case "javascript" | "typescript":
                sandbox_class = NodeSandbox
            case _:
                sandbox_class = PythonSandbox
        # Create sandbox with context manager
        self.sandbox = await sandbox_class.create(
            server_url=self.server_url,  # type: ignore
            namespace=self.namespace,
            api_key=self.api_key,
        ).__aenter__()

        # Configure sandbox resources if needed
        # Note: Microsandbox handles resource config during start()
        # which is already called by the context manager
        if self.dependencies and self.language == "python":
            deps_str = " ".join(self.dependencies)
            install_result = await self.sandbox.command.run(f"pip install {deps_str}")
            if install_result.exit_code != 0:
                # Log warning but don't fail - code might still work
                pass

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Cleanup sandbox."""
        if self.sandbox:
            with contextlib.suppress(Exception):
                await self.sandbox.stop()

        await super().__aexit__(exc_type, exc_val, exc_tb)

    def get_fs(self) -> MicrosandboxFS:
        """Return a MicrosandboxFS instance for the sandbox."""
        from upathtools.filesystems import MicrosandboxFS

        sandbox = self._ensure_initialized()
        return MicrosandboxFS(sandbox=sandbox)

    async def execute(self, code: str) -> ExecutionResult:
        """Execute code in the Microsandbox environment."""
        sandbox = self._ensure_initialized()
        start_time = time.time()
        try:
            execution = await sandbox.run(code)
            stdout = await execution.output()
            stderr = await execution.error()
            success = not execution.has_error()
            if success:
                return ExecutionResult(
                    result=stdout if stdout else None,
                    duration=time.time() - start_time,
                    success=True,
                    stdout=stdout,
                    stderr=stderr,
                )

            return ExecutionResult(
                result=None,
                duration=time.time() - start_time,
                success=False,
                error=stderr or "Code execution failed",
                error_type="ExecutionError",
                stdout=stdout,
                stderr=stderr,
            )

        except Exception as e:  # noqa: BLE001
            return ExecutionResult.failed(e, start_time)

    async def execute_command(self, command: str) -> ExecutionResult:
        """Execute a terminal command in the Microsandbox environment."""
        sandbox = self._ensure_initialized()
        cmd, args = parse_command(command)
        start_time = time.time()
        try:
            execution = await sandbox.command.run(cmd, args)
            stdout = await execution.output()
            stderr = await execution.error()
            success = execution.success
            return ExecutionResult(
                result=stdout if success else None,
                duration=time.time() - start_time,
                success=success,
                error=stderr if not success else None,
                error_type="CommandError" if not success else None,
                stdout=stdout,
                stderr=stderr,
            )

        except Exception as e:  # noqa: BLE001
            return ExecutionResult.failed(e, start_time)

    # Note: Streaming methods not implemented as Microsandbox doesn't
    # support real-time streaming
    # The base class will raise NotImplementedError for execute_stream()
    # and execute_command_stream()

    async def stream_code(self, code: str) -> AsyncIterator[ExecutionEvent]:
        """Execute code and emit combined events (no real-time streaming)."""
        process_id = f"microsandbox_{id(self.sandbox)}"
        yield ProcessStartedEvent(process_id=process_id, command=f"execute({len(code)} chars)")

        try:
            result = await self.execute(code)  # Emit output as single combined event
            if result.stdout:
                yield OutputEvent(process_id=process_id, data=result.stdout, stream="combined")
            if result.success:
                yield ProcessCompletedEvent(process_id=process_id, exit_code=result.exit_code or 0)
            else:
                yield ProcessErrorEvent(
                    process_id=process_id,
                    error=result.error or "Unknown error",
                    error_type=result.error_type or "ExecutionError",
                    exit_code=result.exit_code,
                )

        except Exception as e:  # noqa: BLE001
            yield ProcessErrorEvent.failed(e, process_id=process_id)

    async def stream_command(self, command: str) -> AsyncIterator[ExecutionEvent]:
        """Execute terminal command and emit combined events (no real-time streaming)."""
        process_id = f"microsandbox_cmd_{id(self.sandbox)}"
        yield ProcessStartedEvent(process_id=process_id, command=command)
        try:
            result = await self.execute_command(command)
            if result.stdout:  # Emit output as single combined event
                yield OutputEvent(process_id=process_id, data=result.stdout, stream="combined")
            if result.success:
                yield ProcessCompletedEvent(process_id=process_id, exit_code=result.exit_code or 0)
            else:
                yield ProcessErrorEvent(
                    process_id=process_id,
                    error=result.error or "Unknown error",
                    error_type=result.error_type or "CommandError",
                    exit_code=result.exit_code,
                )

        except Exception as e:  # noqa: BLE001
            yield ProcessErrorEvent.failed(e, process_id=process_id)
