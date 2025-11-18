"""Microsandbox execution environment that runs code in containerized sandboxes."""

from __future__ import annotations

import contextlib
import shlex
import time
from typing import TYPE_CHECKING, Self

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.models import ExecutionResult


if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager
    from types import TracebackType

    from upathtools.filesystems.microsandbox_fs import MicrosandboxFS

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
        self.sandbox = None

    async def __aenter__(self) -> Self:
        """Setup Microsandbox environment."""
        # Start tool server via base class
        await super().__aenter__()

        from microsandbox import NodeSandbox, PythonSandbox

        # Select appropriate sandbox type based on language
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

        # Install Python dependencies if specified
        if self.dependencies and self.language == "python":
            deps_str = " ".join(self.dependencies)
            assert self.sandbox
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
        from upathtools.filesystems.microsandbox_fs import MicrosandboxFS

        assert self.sandbox
        return MicrosandboxFS(sandbox=self.sandbox)

    async def execute(self, code: str) -> ExecutionResult:
        """Execute code in the Microsandbox environment."""
        if not self.sandbox:
            error_msg = "Microsandbox environment not properly initialized"
            raise RuntimeError(error_msg)

        start_time = time.time()
        try:
            execution = await self.sandbox.run(code)
            duration = time.time() - start_time
            stdout = await execution.output()
            stderr = await execution.error()
            success = not execution.has_error()
            if success:
                return ExecutionResult(
                    result=stdout if stdout else None,
                    duration=duration,
                    success=True,
                    stdout=stdout,
                    stderr=stderr,
                )

            return ExecutionResult(
                result=None,
                duration=duration,
                success=False,
                error=stderr or "Code execution failed",
                error_type="ExecutionError",
                stdout=stdout,
                stderr=stderr,
            )

        except Exception as e:  # noqa: BLE001
            duration = time.time() - start_time
            return ExecutionResult(
                result=None,
                duration=duration,
                success=False,
                error=str(e),
                error_type=type(e).__name__,
            )

    async def execute_command(self, command: str) -> ExecutionResult:
        """Execute a terminal command in the Microsandbox environment."""
        if not self.sandbox:
            error_msg = "Microsandbox environment not properly initialized"
            raise RuntimeError(error_msg)

        start_time = time.time()
        try:
            # Parse command into command and args
            parts = shlex.split(command)
            if not parts:
                error_msg = "Empty command provided"
                raise ValueError(error_msg)  # noqa: TRY301

            cmd = parts[0]
            args = parts[1:] if len(parts) > 1 else []
            execution = await self.sandbox.command.run(cmd, args)
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
            return ExecutionResult(
                result=None,
                duration=time.time() - start_time,
                success=False,
                error=str(e),
                error_type=type(e).__name__,
            )

    # Note: Streaming methods not implemented as Microsandbox doesn't
    # support real-time streaming
    # The base class will raise NotImplementedError for execute_stream()
    # and execute_command_stream()
