"""E2B execution environment that runs code in cloud sandboxes."""

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
from anyenv.code_execution.parse_output import get_script_path, parse_output, wrap_code


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager
    from types import TracebackType

    from e2b import AsyncSandbox
    from upathtools.filesystems import E2BFS

    from anyenv.code_execution.events import ExecutionEvent
    from anyenv.code_execution.models import Language, ServerInfo


def _get_error_type(e: Exception):
    error_type = type(e).__name__
    error_message = str(e)
    if error_type == "CommandExitException":
        # Check if it's a syntax error based on the error message
        if "SyntaxError:" in error_message:
            return "SyntaxError"
        if "IndentationError:" in error_message:
            return "IndentationError"
        return "CommandError"
    return error_type


def _get_execution_command(language: Language, script_path: str) -> str:
    """Get execution command based on language."""
    match language:
        case "python":
            return f"python {script_path}"
        case "javascript":
            return f"node {script_path}"
        case "typescript":
            return f"npx ts-node {script_path}"
        case _:
            return f"python {script_path}"


class E2bExecutionEnvironment(ExecutionEnvironment):
    """Executes code in an E2B cloud sandbox."""

    def __init__(
        self,
        lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
        dependencies: list[str] | None = None,
        template: str | None = None,
        timeout: float = 300.0,
        keep_alive: bool = False,
        language: Language = "python",
    ) -> None:
        """Initialize E2B environment.

        Args:
            lifespan_handler: Async context manager for tool server (optional)
            dependencies: List of packages to install via pip / npm
            template: E2B template name/ID (uses 'base' if None)
            timeout: Sandbox timeout in seconds
            keep_alive: Keep sandbox running after execution
            language: Programming language to use
        """
        super().__init__(lifespan_handler=lifespan_handler, dependencies=dependencies)
        self.template = template
        self.timeout = timeout
        self.keep_alive = keep_alive
        self.language: Language = language
        self.sandbox: AsyncSandbox | None = None

    def _ensure_initialized(self) -> AsyncSandbox:
        """Ensure async context."""
        if self.sandbox is None:
            msg = "E2B environment not initialized. Use 'async with' context manager."
            raise RuntimeError(msg)
        return self.sandbox

    async def __aenter__(self) -> Self:
        """Setup E2B sandbox."""
        from e2b import AsyncSandbox

        await super().__aenter__()
        self.sandbox = await AsyncSandbox.create(template=self.template, timeout=int(self.timeout))
        if self.dependencies:  # Install dependencies if specified
            deps_str = " ".join(self.dependencies)
            match self.language:
                case "python":
                    install_result = await self.sandbox.commands.run(f"pip install {deps_str}")
                case "javascript" | "typescript":
                    install_result = await self.sandbox.commands.run(f"npm install {deps_str}")
                case _:
                    install_result = None
            if install_result and install_result.exit_code != 0:
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
            with contextlib.suppress(Exception):
                await self.sandbox.kill()
        await super().__aexit__(exc_type, exc_val, exc_tb)

    def get_fs(self) -> E2BFS:
        """Return a E2BFs instance for the sandbox."""
        from upathtools.filesystems import E2BFS

        sandbox = self._ensure_initialized()
        return E2BFS(sandbox_id=sandbox.sandbox_id)

    async def get_domain(self, port: int) -> str:
        """Return the domain name for the sandbox."""
        sandbox = self._ensure_initialized()
        return sandbox.get_host(port)

    async def execute(self, code: str) -> ExecutionResult:
        """Execute code in the E2B sandbox."""
        sandbox = self._ensure_initialized()
        start_time = time.time()
        try:
            wrapped_code = wrap_code(code, language=self.language)
            script_path = get_script_path(self.language)
            await sandbox.files.write(script_path, wrapped_code)
            command = _get_execution_command(self.language, script_path)
            result = await sandbox.commands.run(command)
            execution_result, error_info = parse_output(result.stdout)
            if result.exit_code == 0 and error_info is None:
                return ExecutionResult(
                    result=execution_result,
                    duration=time.time() - start_time,
                    success=True,
                    exit_code=result.exit_code,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )

            return ExecutionResult(
                result=None,
                duration=time.time() - start_time,
                success=False,
                exit_code=result.exit_code,
                error=(error_info or {}).get("error", "Command execution failed"),
                error_type=(error_info or {}).get("type", "ExecutionError"),
                stdout=result.stdout,
                stderr=result.stderr,
            )

        except Exception as e:  # noqa: BLE001
            # Map E2B specific exceptions to our error types
            error_type = _get_error_type(e)
            return ExecutionResult.failed(e, start_time, error_type=error_type)

    async def execute_command(self, command: str) -> ExecutionResult:
        """Execute a terminal command in the E2B sandbox."""
        sandbox = self._ensure_initialized()
        start_time = time.time()
        try:
            result = await sandbox.commands.run(command, timeout=int(self.timeout))
            success = result.exit_code == 0
            return ExecutionResult(
                result=result.stdout if success else None,
                duration=time.time() - start_time,
                success=success,
                error=result.stderr if not success else None,
                error_type="CommandError" if not success else None,
                stdout=result.stdout,
                stderr=result.stderr,
            )
        except Exception as e:  # noqa: BLE001
            error_type = _get_error_type(e)
            return ExecutionResult.failed(e, start_time, error_type=error_type)

    async def stream_code(self, code: str) -> AsyncIterator[ExecutionEvent]:
        """Execute code and stream events in the E2B sandbox."""
        sandbox = self._ensure_initialized()
        process_id = f"e2b_{id(sandbox)}"
        # Write code to script file and execute via commands.run
        wrapped_code = wrap_code(code, language=self.language)
        script_path = get_script_path(self.language)
        await sandbox.files.write(script_path, wrapped_code)
        command = _get_execution_command(self.language, script_path)
        yield ProcessStartedEvent(process_id=process_id, command=f"execute({len(code)} chars)")
        try:
            stdout_events: list[OutputEvent] = []
            stderr_events: list[OutputEvent] = []

            def on_stdout(data: str) -> None:
                line = data.rstrip("\n\r")
                if line:
                    event = OutputEvent(process_id=process_id, data=line, stream="stdout")
                    stdout_events.append(event)

            def on_stderr(data: str) -> None:
                line = data.rstrip("\n\r")
                if line:
                    event = OutputEvent(process_id=process_id, data=line, stream="stderr")
                    stderr_events.append(event)

            result = await sandbox.commands.run(
                command,
                timeout=int(self.timeout),
                on_stdout=on_stdout,
                on_stderr=on_stderr,
            )

            for event in stdout_events:
                yield event
            for event in stderr_events:
                yield event

            if result.exit_code != 0:
                yield ProcessErrorEvent(
                    process_id=process_id,
                    error=result.stderr or f"Command exited with code {result.exit_code}",
                    error_type="ExecutionError",
                    exit_code=result.exit_code,
                )
            else:
                yield ProcessCompletedEvent(process_id=process_id, exit_code=0)

        except Exception as e:  # noqa: BLE001
            yield ProcessErrorEvent.failed(e, process_id=process_id)

    async def stream_command(self, command: str) -> AsyncIterator[ExecutionEvent]:
        """Execute a terminal command and stream events in the E2B sandbox."""
        sandbox = self._ensure_initialized()
        process_id = f"e2b_cmd_{id(sandbox)}"
        yield ProcessStartedEvent(process_id=process_id, command=command)
        try:
            stdout_events = []
            stderr_events = []

            def on_stdout(data: str) -> None:
                line = data.rstrip("\n\r")
                if line:
                    event = OutputEvent(process_id=process_id, data=line, stream="stdout")
                    stdout_events.append(event)

            def on_stderr(data: str) -> None:
                line = data.rstrip("\n\r")
                if line:
                    event = OutputEvent(process_id=process_id, data=line, stream="stderr")
                    stderr_events.append(event)

            result = await sandbox.commands.run(
                command,
                timeout=int(self.timeout),
                on_stdout=on_stdout,
                on_stderr=on_stderr,
            )

            for event in stdout_events:
                yield event
            for event in stderr_events:
                yield event

            if result.exit_code == 0:
                yield ProcessCompletedEvent(process_id=process_id, exit_code=result.exit_code)
            else:
                yield ProcessErrorEvent(
                    process_id=process_id,
                    error=f"Command exited with code {result.exit_code}",
                    error_type="CommandError",
                    exit_code=result.exit_code,
                )

        except Exception as e:  # noqa: BLE001
            yield ProcessErrorEvent.failed(e, process_id=process_id)


if __name__ == "__main__":

    async def _main() -> None:
        async with E2bExecutionEnvironment() as sandbox:
            await sandbox.execute_command("mkdir test")
            result = await sandbox.execute_command("ls")
            print(result)

    import asyncio

    asyncio.run(_main())
