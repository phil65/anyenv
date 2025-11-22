"""Vercel sandbox execution environment that runs code in cloud sandboxes."""

from __future__ import annotations

import contextlib
import shlex
import time
from typing import TYPE_CHECKING, Any, Literal, Self

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.models import ExecutionResult
from anyenv.code_execution.parse_output import get_script_path, parse_output, wrap_code


# Vercel runtime options based on the API error message
VercelRuntime = Literal[
    "node22",
    "python3.13",
    "v0-next-shadcn",
    "cua-ubuntu-xfce",
    "walleye-python",
]

# Vercel API minimum timeout requirement (1 second in milliseconds)
MIN_TIMEOUT_MILLISECONDS = 1000
# Default timeout in seconds (1 minute, converted to milliseconds for API)
DEFAULT_TIMEOUT_SECONDS = 60


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager
    from types import TracebackType

    from upathtools.filesystems import VercelFS
    from vercel.sandbox import AsyncSandbox

    from anyenv.code_execution.events import ExecutionEvent
    from anyenv.code_execution.models import Language, ServerInfo


class VercelExecutionEnvironment(ExecutionEnvironment):
    """Executes code in a Vercel cloud sandbox."""

    def __init__(
        self,
        lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
        dependencies: list[str] | None = None,
        runtime: VercelRuntime | None = None,
        timeout: int = DEFAULT_TIMEOUT_SECONDS,
        resources: dict[str, Any] | None = None,
        ports: list[int] | None = None,
        language: Language = "python",
        token: str | None = None,
        project_id: str | None = None,
        team_id: str | None = None,
    ):
        """Initialize Vercel sandbox environment.

        Args:
            lifespan_handler: Async context manager for tool server (optional)
            dependencies: List of packages to install via pip / npm
            runtime: Vercel runtime to use (allowed: node22, python3.13,
                v0-next-shadcn, cua-ubuntu-xfce, walleye-python)
            timeout: Sandbox timeout in seconds (minimum 1)
            resources: Resource configuration for the sandbox
            ports: List of ports to expose
            language: Programming language to use
            token: Vercel API token (uses environment if None)
            project_id: Vercel project ID (uses environment if None)
            team_id: Vercel team ID (uses environment if None)
        """
        super().__init__(lifespan_handler=lifespan_handler, dependencies=dependencies)
        self.runtime = runtime
        # Convert timeout from seconds to milliseconds for Vercel API
        self.timeout_ms = timeout * 1000
        # Validate timeout meets Vercel's minimum requirement (1 second = 1000ms)
        if self.timeout_ms < MIN_TIMEOUT_MILLISECONDS:
            error_msg = f"Vercel requires timeout >= 1 second, got {timeout} seconds"
            raise ValueError(error_msg)

        self.resources = resources
        self.ports = ports or [3000]
        self.language: Language = language
        self.token = token
        self.project_id = project_id
        self.team_id = team_id
        self.sandbox: AsyncSandbox | None = None

    async def __aenter__(self) -> Self:
        """Setup Vercel sandbox."""
        # Start tool server via base class
        await super().__aenter__()

        from vercel.sandbox import AsyncSandbox

        self.sandbox = await AsyncSandbox.create(
            runtime=self.runtime or self._get_default_runtime(),
            timeout=self.timeout_ms,
            resources=self.resources,
            ports=self.ports,
            token=self.token,
            project_id=self.project_id,
            team_id=self.team_id,
        )

        # Install Python dependencies if specified
        if self.dependencies and self.language == "python":
            try:
                install_result = await self.sandbox.run_command(
                    "pip", ["install", *self.dependencies]
                )
                if install_result.exit_code != 0:
                    # Log warning but don't fail - code might still work
                    pass
            except Exception:  # noqa: BLE001
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

    async def get_domain(self, port: int) -> str:
        """Get domain for the Vercel sandbox."""
        assert self.sandbox
        return self.sandbox.domain(port)

    def get_fs(self) -> VercelFS:
        """Return a VercelFS instance for the sandbox."""
        from upathtools.filesystems import VercelFS

        assert self.sandbox
        return VercelFS(sandbox=self.sandbox)

    def _get_default_runtime(self) -> VercelRuntime:
        """Get default runtime based on language."""
        match self.language:
            case "python":
                return "python3.13"
            case "javascript":
                return "node22"
            case "typescript":
                return "node22"
            case _:
                return "python3.13"

    async def execute(self, code: str) -> ExecutionResult:
        """Execute code in the Vercel sandbox."""
        if not self.sandbox:
            error_msg = "Vercel environment not properly initialized"
            raise RuntimeError(error_msg)

        start_time = time.time()
        try:
            script_path, wrapped_code = self._prepare_code_execution(code)
            await self.sandbox.write_files([
                {"path": script_path, "content": wrapped_code.encode()}
            ])
            cmd, args = self._get_execution_command(script_path)
            result = await self.sandbox.run_command(cmd, args)
            stdout = await result.stdout()
            stderr = await result.stderr()
            execution_result, error_info = parse_output(stdout)
            if result.exit_code == 0 and error_info is None:
                return ExecutionResult(
                    result=execution_result,
                    duration=time.time() - start_time,
                    success=True,
                    stdout=stdout,
                    exit_code=result.exit_code,
                    stderr=stderr,
                )

            return ExecutionResult(
                result=None,
                duration=time.time() - start_time,
                success=False,
                error=(error_info or {}).get("error", "Command execution failed"),
                exit_code=result.exit_code,
                error_type=(error_info or {}).get("type", "ExecutionError"),
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

    async def execute_command(self, command: str) -> ExecutionResult:
        """Execute a terminal command in the Vercel sandbox."""
        if not self.sandbox:
            error_msg = "Vercel environment not properly initialized"
            raise RuntimeError(error_msg)

        start_time = time.time()
        try:
            parts = shlex.split(command)
            if not parts:
                error_msg = "Empty command provided"
                raise ValueError(error_msg)  # noqa: TRY301

            cmd = parts[0]
            args = parts[1:] if len(parts) > 1 else None
            result = await self.sandbox.run_command(cmd, args)
            stdout = await result.stdout()
            stderr = await result.stderr()
            success = result.exit_code == 0
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

    async def stream_code(self, code: str) -> AsyncIterator[ExecutionEvent]:
        """Execute code and stream events in the Vercel sandbox."""
        from anyenv.code_execution.events import (
            OutputEvent,
            ProcessCompletedEvent,
            ProcessErrorEvent,
            ProcessStartedEvent,
        )

        process_id = f"vercel_{id(self.sandbox)}"
        yield ProcessStartedEvent(
            process_id=process_id, command=f"execute({len(code)} chars)"
        )

        try:
            if not self.sandbox:
                yield ProcessErrorEvent(
                    process_id=process_id,
                    error="Vercel environment not properly initialized",
                    error_type="RuntimeError",
                )
                return

            script_path, wrapped_code = self._prepare_code_execution(code)
            await self.sandbox.write_files([
                {"path": script_path, "content": wrapped_code.encode()}
            ])

            cmd_name, args = self._get_execution_command(script_path)
            cmd = await self.sandbox.run_command_detached(cmd_name, args)

            async for log_line in self.sandbox.client.get_logs(
                sandbox_id=self.sandbox.sandbox_id, cmd_id=cmd.cmd_id
            ):
                if log_line.data:
                    for line in log_line.data.splitlines():
                        if line.strip():
                            yield OutputEvent(
                                process_id=process_id, data=line, stream="combined"
                            )

            finished = await cmd.wait()
            if finished.exit_code == 0:
                yield ProcessCompletedEvent(
                    process_id=process_id, exit_code=finished.exit_code
                )
            else:
                yield ProcessErrorEvent(
                    process_id=process_id,
                    error=f"Process exited with code {finished.exit_code}",
                    error_type="ProcessError",
                    exit_code=finished.exit_code,
                )

        except Exception as e:  # noqa: BLE001
            yield ProcessErrorEvent(
                process_id=process_id, error=str(e), error_type=type(e).__name__
            )

    async def stream_command(self, command: str) -> AsyncIterator[ExecutionEvent]:
        """Execute a terminal command and stream events in the Vercel sandbox."""
        from anyenv.code_execution.events import (
            OutputEvent,
            ProcessCompletedEvent,
            ProcessErrorEvent,
            ProcessStartedEvent,
        )

        process_id = f"vercel_cmd_{id(self.sandbox)}"
        yield ProcessStartedEvent(process_id=process_id, command=command)

        try:
            if not self.sandbox:
                yield ProcessErrorEvent(
                    process_id=process_id,
                    error="Vercel environment not properly initialized",
                    error_type="RuntimeError",
                )
                return

            parts = shlex.split(command)
            if not parts:
                yield ProcessErrorEvent(
                    process_id=process_id, error="Empty command", error_type="ValueError"
                )
                return

            cmd_name = parts[0]
            args = parts[1:] if len(parts) > 1 else None

            cmd = await self.sandbox.run_command_detached(cmd_name, args)

            async for log_line in self.sandbox.client.get_logs(
                sandbox_id=self.sandbox.sandbox_id, cmd_id=cmd.cmd_id
            ):
                if log_line.data:
                    for line in log_line.data.splitlines():
                        if line.strip():
                            yield OutputEvent(
                                process_id=process_id, data=line, stream="combined"
                            )

            finished = await cmd.wait()
            if finished.exit_code == 0:
                yield ProcessCompletedEvent(
                    process_id=process_id, exit_code=finished.exit_code
                )
            else:
                yield ProcessErrorEvent(
                    process_id=process_id,
                    error=f"Command exited with code {finished.exit_code}",
                    error_type="CommandError",
                    exit_code=finished.exit_code,
                )

        except Exception as e:  # noqa: BLE001
            yield ProcessErrorEvent(
                process_id=process_id, error=str(e), error_type=type(e).__name__
            )

    def _prepare_code_execution(self, code: str) -> tuple[str, str]:
        """Prepare code for execution, returning script path and wrapped code."""
        script_path = get_script_path(self.language)
        wrapped_code = wrap_code(code, self.language)
        return script_path, wrapped_code

    def _get_execution_command(self, script_path: str) -> tuple[str, list[str]]:  # noqa: PLR0911
        """Get execution command based on language and runtime.

        Returns:
            Tuple of (cmd, args) where cmd is the executable and args is the arg list.
        """
        runtime = self.runtime or self._get_default_runtime()

        match self.language:
            case "python":
                if runtime == "python3.13":
                    return ("python3", [script_path])
                if runtime == "walleye-python":
                    return ("python", [script_path])
                return ("python3", [script_path])
            case "javascript":
                return ("node", [script_path])
            case "typescript":
                return ("npx", ["ts-node", script_path])
            case _:
                if runtime == "python3.13":
                    return ("python3", [script_path])
                if runtime == "walleye-python":
                    return ("python", [script_path])
                return ("python3", [script_path])


if __name__ == "__main__":

    async def _main() -> None:
        async with VercelExecutionEnvironment() as sandbox:
            await sandbox.execute_command("mkdir test")
            result = await sandbox.execute_command("ls")
            print(result)

    import asyncio

    asyncio.run(_main())
