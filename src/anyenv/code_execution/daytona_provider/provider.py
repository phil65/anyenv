"""Daytona execution environment that runs code in remote sandboxes."""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING, Self

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.daytona_provider.helpers import convert_language
from anyenv.code_execution.models import ExecutionResult
from anyenv.code_execution.parse_output import parse_output, wrap_python_code


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager
    from types import TracebackType

    from daytona._async.sandbox import AsyncSandbox
    from upathtools.filesystems.daytona_fs import DaytonaFS

    from anyenv.code_execution.events import ExecutionEvent
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
        self.language: Language = language
        config = DaytonaConfig(api_url=api_url, api_key=api_key, target=target)
        self.daytona = AsyncDaytona(config)
        self._sandbox: AsyncSandbox | None = None

    @property
    def sandbox(self) -> AsyncSandbox:
        """Return the initialized sandbox."""
        assert self._sandbox is not None, "Sandbox not initialized"
        return self._sandbox

    async def __aenter__(self) -> Self:
        """Setup Daytona client and create sandbox."""
        await super().__aenter__()
        from daytona.common.daytona import CreateSandboxFromImageParams

        language = convert_language(self.language)
        params = CreateSandboxFromImageParams(image=self.image, language=language)
        self._sandbox = await self.daytona.create(params)
        await self.sandbox.start(timeout=self.timeout)
        if self.dependencies and self.language == "python":
            deps_str = " ".join(self.dependencies)
            result = await self.sandbox.process.exec(f"pip install {deps_str}")
            if result.exit_code != 0:
                msg = f"Failed to install dependencies: {deps_str}"
                raise RuntimeError(msg)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Cleanup sandbox."""
        if not self.keep_alive:
            with contextlib.suppress(Exception):
                await self.sandbox.stop()
                await self.sandbox.delete()
        await super().__aexit__(exc_type, exc_val, exc_tb)

    async def get_domain(self, port: int) -> str:
        """Return the domain name for the sandbox."""
        info = await self.sandbox.get_preview_link(port)
        return info.url

    def get_fs(self) -> DaytonaFS:
        """Return a DaytonaFS instance for the sandbox."""
        from upathtools.filesystems.daytona_fs import DaytonaFS

        return DaytonaFS(sandbox_id=self.sandbox.id)

    async def execute(self, code: str) -> ExecutionResult:
        """Execute code in the Daytona sandbox."""
        start_time = time.time()
        wrapped_code = wrap_python_code(code)
        try:
            response = await self.sandbox.process.exec(
                f"python -c '{wrapped_code}'", timeout=int(self.timeout)
            )
            # Parse execution results
            if response.exit_code == 0:
                result, error_info = parse_output(response.result)
                if error_info is None:
                    return ExecutionResult(
                        result=result,
                        duration=time.time() - start_time,
                        success=True,
                        stdout=response.result,
                        stderr="",
                        exit_code=int(response.exit_code),
                    )
                return ExecutionResult(
                    result=None,
                    duration=time.time() - start_time,
                    success=False,
                    error=error_info.get("error", "Unknown error"),
                    error_type=error_info.get("type", "ExecutionError"),
                    stdout=response.result,
                    stderr="",
                    exit_code=int(response.exit_code),
                )

            return ExecutionResult(
                result=None,
                duration=time.time() - start_time,
                success=False,
                error=response.result if response.result else "Command execution failed",
                exit_code=int(response.exit_code),
                error_type="CommandError",
                stdout=response.result,
                stderr="",
            )

        except Exception as e:  # noqa: BLE001
            return ExecutionResult(
                result=None,
                duration=time.time() - start_time,
                success=False,
                error=str(e),
                error_type=type(e).__name__,
            )

    async def execute_command(self, command: str) -> ExecutionResult:
        """Execute a terminal command in the Daytona sandbox."""
        start_time = time.time()
        try:
            response = await self.sandbox.process.exec(command, timeout=int(self.timeout))
            success = response.exit_code == 0
            return ExecutionResult(
                result=response.result if success else None,
                duration=time.time() - start_time,
                success=success,
                error=response.result if not success else None,
                error_type="CommandError" if not success else None,
                exit_code=int(response.exit_code),
                stdout=response.result,
                stderr="",  # Daytona combines stdout/stderr in result
            )

        except Exception as e:  # noqa: BLE001
            return ExecutionResult(
                result=None,
                duration=time.time() - start_time,
                success=False,
                error=str(e),
                error_type=type(e).__name__,
            )

    async def stream_code(self, code: str) -> AsyncIterator[ExecutionEvent]:
        """Execute code and stream events in the Daytona sandbox."""
        from anyenv.code_execution.events import (
            OutputEvent,
            ProcessCompletedEvent,
            ProcessErrorEvent,
            ProcessStartedEvent,
        )

        process_id = f"daytona_{id(self.sandbox)}"
        yield ProcessStartedEvent(
            process_id=process_id, command=f"execute({len(code)} chars)"
        )

        try:
            result = await self.execute(code)

            if result.stdout:
                yield OutputEvent(
                    process_id=process_id, data=result.stdout, stream="combined"
                )

            if result.success:
                yield ProcessCompletedEvent(
                    process_id=process_id, exit_code=result.exit_code or 0
                )
            else:
                yield ProcessErrorEvent(
                    process_id=process_id,
                    error=result.error or "Unknown error",
                    error_type=result.error_type or "ExecutionError",
                    exit_code=result.exit_code,
                )

        except Exception as e:  # noqa: BLE001
            yield ProcessErrorEvent(
                process_id=process_id, error=str(e), error_type=type(e).__name__
            )

    async def stream_command(self, command: str) -> AsyncIterator[ExecutionEvent]:
        """Execute terminal command and stream events in the Daytona sandbox."""
        from anyenv.code_execution.events import (
            OutputEvent,
            ProcessCompletedEvent,
            ProcessErrorEvent,
            ProcessStartedEvent,
        )

        process_id = f"daytona_cmd_{id(self.sandbox)}"
        yield ProcessStartedEvent(process_id=process_id, command=command)

        try:
            result = await self.execute_command(command)

            if result.stdout:
                yield OutputEvent(
                    process_id=process_id, data=result.stdout, stream="combined"
                )

            if result.success:
                yield ProcessCompletedEvent(
                    process_id=process_id, exit_code=result.exit_code or 0
                )
            else:
                yield ProcessErrorEvent(
                    process_id=process_id,
                    error=result.error or "Unknown error",
                    error_type=result.error_type or "CommandError",
                    exit_code=result.exit_code,
                )

        except Exception as e:  # noqa: BLE001
            yield ProcessErrorEvent(
                process_id=process_id, error=str(e), error_type=type(e).__name__
            )


if __name__ == "__main__":

    async def _main() -> None:
        async with DaytonaExecutionEnvironment() as sandbox:
            async for p in sandbox.execute_command_stream("echo 'Hello, Daytona!'"):
                print(p)

    import asyncio

    asyncio.run(_main())
