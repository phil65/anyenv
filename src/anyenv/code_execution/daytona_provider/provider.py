"""Daytona execution environment that runs code in remote sandboxes."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Self

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.models import ExecutionResult
from anyenv.code_execution.parse_output import parse_output, wrap_python_code


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager
    from types import TracebackType

    from daytona._async.sandbox import AsyncSandbox
    from upathtools.filesystems.daytona_fs import DaytonaFS

    from anyenv.code_execution.models import Language, ServerInfo


class DaytonaExecutionEnvironment(ExecutionEnvironment):
    """Executes code in a Daytona sandbox with isolated environment."""

    def __init__(
        self,
        lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
        dependencies: list[str] | None = None,
        api_url: str | None = None,
        api_key: str | None = None,
        target: str | None = None,
        image: str = "python:3.13-slim",
        timeout: float = 300.0,
        keep_alive: bool = False,
        language: Language = "python",
    ) -> None:
        """Initialize Daytona environment.

        Args:
            lifespan_handler: Async context manager for tool server (optional)
            dependencies: List of packages to install via pip / npm
            api_url: Daytona API server URL (uses DAYTONA_API_URL env var if None)
            api_key: API key for authentication (uses DAYTONA_API_KEY env var if None)
            target: Target location (uses DAYTONA_TARGET env var if None)
            image: Docker image to use for the sandbox
            timeout: Execution timeout in seconds
            keep_alive: Keep sandbox running after execution
            language: Programming language to use for execution
        """
        from daytona import AsyncDaytona, DaytonaConfig

        super().__init__(lifespan_handler=lifespan_handler, dependencies=dependencies)
        self.image = image
        self.timeout = timeout
        self.keep_alive = keep_alive
        self.language = language

        # Create configuration
        if api_url or api_key or target:
            config = DaytonaConfig(api_url=api_url, api_key=api_key, target=target)
            self.daytona = AsyncDaytona(config)
        else:
            # Use environment variables
            self.daytona = AsyncDaytona()

        self.sandbox: AsyncSandbox | None = None

    async def __aenter__(self) -> Self:
        """Setup Daytona client and create sandbox."""
        # Start tool server via base class
        await super().__aenter__()
        # Create sandbox with Python image
        from daytona.common.daytona import CodeLanguage, CreateSandboxFromImageParams

        match self.language:
            case "python":
                language = CodeLanguage.PYTHON
            case "javascript":
                language = CodeLanguage.JAVASCRIPT
            case "typescript":
                language = CodeLanguage.TYPESCRIPT
            case _:
                msg = f"Unsupported language: {self.language}"
                raise ValueError(msg)
        params = CreateSandboxFromImageParams(image=self.image, language=language)
        self.sandbox = await self.daytona.create(params)
        assert self.sandbox, "Failed to create sandbox"
        # Start the sandbox and wait for it to be ready
        await self.sandbox.start(timeout=120)

        # Install Python dependencies if specified
        if self.dependencies and self.language == "python":
            deps_str = " ".join(self.dependencies)
            install_result = await self.sandbox.process.exec(f"pip install {deps_str}")
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
        if self.sandbox and not self.keep_alive:
            try:
                await self.sandbox.stop()
                await self.sandbox.delete()
            except Exception:  # noqa: BLE001
                # Best effort cleanup
                pass

        # Cleanup server via base class
        await super().__aexit__(exc_type, exc_val, exc_tb)

    async def get_domain(self, port: int) -> str:
        """Return the domain name for the sandbox."""
        assert self.sandbox
        info = await self.sandbox.get_preview_link(port)
        return info.url

    def get_fs(self) -> DaytonaFS:
        """Return a DaytonaFS instance for the sandbox."""
        from upathtools.filesystems.daytona_fs import DaytonaFS

        assert self.sandbox
        return DaytonaFS(sandbox_id=self.sandbox.id)

    async def execute(self, code: str) -> ExecutionResult:
        """Execute code in the Daytona sandbox."""
        if not self.sandbox:
            error_msg = "Daytona environment not properly initialized"
            raise RuntimeError(error_msg)

        start_time = time.time()

        try:
            # Wrap code for execution with result capture
            wrapped_code = wrap_python_code(code)
            # Execute code in sandbox
            response = await self.sandbox.process.exec(
                f"python -c '{wrapped_code}'", timeout=int(self.timeout)
            )

            duration = time.time() - start_time

            # Parse execution results
            if response.exit_code == 0:
                result, error_info = parse_output(response.result)

                if error_info is None:
                    return ExecutionResult(
                        result=result,
                        duration=duration,
                        success=True,
                        stdout=response.result,
                        stderr="",
                        exit_code=int(response.exit_code),
                    )
                return ExecutionResult(
                    result=None,
                    duration=duration,
                    success=False,
                    error=error_info.get("error", "Unknown error"),
                    error_type=error_info.get("type", "ExecutionError"),
                    stdout=response.result,
                    stderr="",
                    exit_code=int(response.exit_code),
                )

            return ExecutionResult(
                result=None,
                duration=duration,
                success=False,
                error=response.result if response.result else "Command execution failed",
                exit_code=int(response.exit_code),
                error_type="CommandError",
                stdout=response.result,
                stderr="",
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
        """Execute a terminal command in the Daytona sandbox."""
        if not self.sandbox:
            error_msg = "Daytona environment not properly initialized"
            raise RuntimeError(error_msg)

        start_time = time.time()

        try:
            # Execute command using Daytona's process.exec() method
            response = await self.sandbox.process.exec(command, timeout=int(self.timeout))
            duration = time.time() - start_time

            success = response.exit_code == 0

            return ExecutionResult(
                result=response.result if success else None,
                duration=duration,
                success=success,
                error=response.result if not success else None,
                error_type="CommandError" if not success else None,
                stdout=response.result,
                stderr="",  # Daytona combines stdout/stderr in result
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

    async def execute_command_stream(self, command: str) -> AsyncIterator[str]:
        """Execute a terminal command and stream output in the Daytona sandbox."""
        if not self.sandbox:
            error_msg = "Daytona environment not properly initialized"
            raise RuntimeError(error_msg)

        try:
            # Execute command and collect output
            response = await self.sandbox.process.exec(command, timeout=int(self.timeout))

            # Split result into lines and yield them
            if response.result:
                for line in response.result.split("\n"):
                    if line.strip():  # Only yield non-empty lines
                        yield line

            # Yield exit code info if command failed
            if response.exit_code != 0:
                yield f"ERROR: Command exited with code {response.exit_code}"

        except Exception as e:  # noqa: BLE001
            yield f"ERROR: {e}"


if __name__ == "__main__":

    async def _main() -> None:
        async with DaytonaExecutionEnvironment() as sandbox:
            await sandbox.execute_command("mkdir test")
            result = await sandbox.execute_command("ls")
            print(result)

    import asyncio

    asyncio.run(_main())
