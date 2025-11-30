"""Local execution environment that runs code locally."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import shutil
import sys
import time
from typing import TYPE_CHECKING, Any, Literal, Self

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.events import (
    OutputEvent,
    ProcessCompletedEvent,
    ProcessErrorEvent,
    ProcessStartedEvent,
)
from anyenv.code_execution.local_provider.utils import StreamCapture, find_executable
from anyenv.code_execution.models import ExecutionResult
from anyenv.code_execution.parse_output import parse_output, wrap_code
from anyenv.processes import create_process, create_shell_process


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager
    from types import TracebackType

    from morefs.asyn_local import AsyncLocalFileSystem

    from anyenv.code_execution.events import ExecutionEvent
    from anyenv.code_execution.models import Language, ServerInfo


PYTHON_EXECUTABLES = [
    "python3",
    "python",
    "python3.13",
    "python3.12",
    "python3.11",
    "python3.14",
]


class LocalExecutionEnvironment(ExecutionEnvironment):
    """Executes code in the same process or isolated subprocess."""

    def __init__(
        self,
        lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
        dependencies: list[str] | None = None,
        timeout: float = 30.0,
        isolated: bool = False,
        executable: str | None = None,
        language: Language = "python",
    ) -> None:
        """Initialize local environment.

        Args:
            lifespan_handler: Async context manager for tool server (optional)
            dependencies: List of Python packages to install via pip / npm
            timeout: Execution timeout in seconds
            isolated: If True, run code in subprocess; if False, run in same process
            executable: Executable to use for isolated mode (if None, auto-detect)
            language: Programming language to use (for isolated mode)
        """
        super().__init__(lifespan_handler=lifespan_handler, dependencies=dependencies)
        self.timeout = timeout
        self.isolated = isolated
        self.language: Language = language
        self.executable = executable or (find_executable(language) if isolated else None)
        self.process: asyncio.subprocess.Process | None = None

    async def __aenter__(self) -> Self:
        # Start tool server via base class
        await super().__aenter__()

        # Install dependencies if specified and in isolated mode
        if self.isolated and self.dependencies and self.language == "python":
            deps_str = " ".join(self.dependencies)
            cmd = f"pip install {deps_str}"
            try:
                process = await create_shell_process(cmd, stdout="pipe", stderr="pipe")
                await asyncio.wait_for(process.communicate(), timeout=self.timeout)
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
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()

        # Cleanup server via base class
        await super().__aexit__(exc_type, exc_val, exc_tb)

    def get_fs(self) -> AsyncLocalFileSystem:
        """Return an AsyncLocalFileSystem for the current working directory."""
        from morefs.asyn_local import AsyncLocalFileSystem

        return AsyncLocalFileSystem()

    async def execute(self, code: str) -> ExecutionResult:
        """Execute code in same process or isolated subprocess."""
        if self.isolated:
            return await self._execute_subprocess(code)
        return await self._execute_local(code)

    async def _execute_local(self, code: str) -> ExecutionResult:
        """Execute code directly in current process."""
        start_time = time.time()

        try:
            namespace = {"__builtins__": __builtins__}
            exec(code, namespace)

            # Try to get result from main() function
            if "main" in namespace and callable(namespace["main"]):
                main_func = namespace["main"]
                if inspect.iscoroutinefunction(main_func):
                    # Run async function in executor to handle blocking calls properly
                    def run_in_thread() -> Any:
                        loop = asyncio.new_event_loop()
                        asyncio.set_event_loop(loop)
                        try:
                            return loop.run_until_complete(main_func())
                        finally:
                            loop.close()

                    result = await asyncio.wait_for(
                        asyncio.to_thread(run_in_thread), timeout=self.timeout
                    )
                else:
                    result = await asyncio.wait_for(
                        asyncio.to_thread(main_func), timeout=self.timeout
                    )
            else:
                result = namespace.get("_result")
            return ExecutionResult(result=result, duration=time.time() - start_time, success=True)

        except Exception as e:  # noqa: BLE001
            return ExecutionResult.failed(e, start_time)

    async def _execute_subprocess(self, code: str) -> ExecutionResult:
        """Execute code in subprocess with communication via stdin/stdout."""
        start_time = time.time()

        try:
            wrapped_code = wrap_code(code, self.language)
            args = self._get_subprocess_args()
            process = await create_process(*args, stdin="pipe", stdout="pipe", stderr="pipe")
            self.process = process
            stdout_data, stderr_data = await asyncio.wait_for(
                process.communicate(wrapped_code.encode()),
                timeout=self.timeout,
            )
            stdout = stdout_data.decode() if stdout_data else ""
            stderr = stderr_data.decode() if stderr_data else ""
            if process.returncode == 0:
                execution_result, error_info = parse_output(stdout)
                if error_info is None:
                    return ExecutionResult(
                        result=execution_result,
                        duration=time.time() - start_time,
                        success=True,
                        exit_code=process.returncode,
                        stdout=stdout,
                        stderr=stderr,
                    )
                return ExecutionResult(
                    result=None,
                    duration=time.time() - start_time,
                    success=False,
                    error=error_info.get("error", "Subprocess execution failed"),
                    error_type=error_info.get("type", "SubprocessError"),
                    exit_code=process.returncode,
                    stdout=stdout,
                    stderr=stderr,
                )
            return ExecutionResult(
                result=None,
                duration=time.time() - start_time,
                success=False,
                error=stderr or "Subprocess execution failed",
                error_type="SubprocessError",
                exit_code=process.returncode,
                stdout=stdout,
                stderr=stderr,
            )

        except Exception as e:  # noqa: BLE001
            if self.process:  # Cleanup process if it exists
                self.process.kill()
                await self.process.wait()
            return ExecutionResult.failed(e, start_time)

    def _get_subprocess_args(self) -> list[str]:
        """Get subprocess arguments based on language."""
        if not self.executable:
            msg = "No executable found for subprocess execution"
            raise RuntimeError(msg)

        match self.language:
            case "python":
                return [self.executable]
            case "javascript":
                return [self.executable]
            case "typescript":
                if shutil.which("ts-node"):
                    return ["ts-node"]
                if shutil.which("tsx"):
                    return ["tsx"]
                return ["npx", "ts-node"]
            case _:
                return [self.executable]

    async def execute_command(self, command: str) -> ExecutionResult:
        """Execute a shell command and return result with metadata."""
        start_time = time.time()

        try:
            process = await create_shell_process(command, stdout="pipe", stderr="pipe")
            stdout_data, stderr_data = await asyncio.wait_for(
                process.communicate(), timeout=self.timeout
            )

            duration = time.time() - start_time
            stdout = stdout_data.decode() if stdout_data else ""
            stderr = stderr_data.decode() if stderr_data else ""
            success = process.returncode == 0

            return ExecutionResult(
                result=stdout if success else None,
                duration=duration,
                success=success,
                error=stderr if not success else None,
                error_type="CommandError" if not success else None,
                stdout=stdout,
                stderr=stderr,
                exit_code=process.returncode,
            )

        except Exception as e:  # noqa: BLE001
            return ExecutionResult.failed(e, start_time)

    async def stream_code(self, code: str) -> AsyncIterator[ExecutionEvent]:
        """Execute code and stream events."""
        from anyenv.code_execution.events import ProcessErrorEvent, ProcessStartedEvent

        process_id = f"local_{id(self)}"
        yield ProcessStartedEvent(process_id=process_id, command=f"execute({len(code)} chars)")

        try:
            if self.isolated:
                async for event in self._stream_code_subprocess(code, process_id):
                    yield event
            else:
                async for event in self._stream_code_local(code, process_id):
                    yield event
        except Exception as e:  # noqa: BLE001
            yield ProcessErrorEvent.failed(e, process_id=process_id)

    async def _stream_code_subprocess(
        self, code: str, process_id: str
    ) -> AsyncIterator[ExecutionEvent]:
        """Execute code in subprocess and stream events."""
        try:
            args = self._get_subprocess_args()
            process = await create_process(*args, stdin="pipe", stdout="pipe", stderr="stdout")
            self.process = process

            if process.stdin:
                wrapped_code = wrap_code(code, self.language)
                process.stdin.write(wrapped_code.encode())
                process.stdin.close()

            if process.stdout:
                while True:
                    try:
                        line = await asyncio.wait_for(
                            process.stdout.readline(), timeout=self.timeout
                        )
                        if not line:
                            break
                        data = line.decode().rstrip("\n\r")
                        yield OutputEvent(process_id=process_id, data=data, stream="combined")
                    except TimeoutError:
                        process.kill()
                        await process.wait()
                        yield ProcessErrorEvent(
                            process_id=process_id,
                            error=f"Process timed out after {self.timeout} seconds",
                            error_type="TimeoutError",
                            exit_code=1,
                        )
                        return

            exit_code = await process.wait()
            if exit_code == 0:
                yield ProcessCompletedEvent(process_id=process_id, exit_code=exit_code)
            else:
                yield ProcessErrorEvent(
                    process_id=process_id,
                    error=f"Process exited with code {exit_code}",
                    error_type="ProcessError",
                    exit_code=exit_code,
                )

        except Exception as e:  # noqa: BLE001
            yield ProcessErrorEvent.failed(e, process_id=process_id)

    async def _stream_code_local(self, code: str, process_id: str) -> AsyncIterator[ExecutionEvent]:
        """Execute code locally and stream events."""
        try:
            output_queue: asyncio.Queue[str] = asyncio.Queue()
            stdout_capture = StreamCapture(sys.stdout, output_queue)
            stderr_capture = StreamCapture(sys.stderr, output_queue)
            execution_done = False

            async def execute_code() -> None:
                nonlocal execution_done
                try:
                    namespace = {"__builtins__": __builtins__}

                    with (
                        contextlib.redirect_stdout(stdout_capture),
                        contextlib.redirect_stderr(stderr_capture),
                    ):
                        lang: Literal["python", "javascript", "typescript"] = (
                            "javascript" if self.language == "typescript" else "python"
                        )
                        wrapped_code = wrap_code(code, lang)

                        if self.language == "python":
                            exec(wrapped_code, namespace)

                            if "main" in namespace and callable(namespace["main"]):
                                main_func = namespace["main"]
                                if inspect.iscoroutinefunction(main_func):
                                    result = await asyncio.wait_for(
                                        main_func(), timeout=self.timeout
                                    )
                                else:
                                    result = await asyncio.wait_for(
                                        asyncio.to_thread(main_func),
                                        timeout=self.timeout,
                                    )

                                if result is not None:
                                    print(f"Result: {result}")
                            else:
                                result = namespace.get("_result")
                                if result is not None:
                                    print(f"Result: {result}")

                except Exception as e:  # noqa: BLE001
                    print(f"ERROR: {e}", file=sys.stderr)
                finally:
                    execution_done = True
                    with contextlib.suppress(asyncio.QueueFull):
                        output_queue.put_nowait("__EXECUTION_COMPLETE__")

            execute_task = asyncio.create_task(execute_code())

            try:
                while True:
                    try:
                        line = await asyncio.wait_for(output_queue.get(), timeout=0.1)
                        if line == "__EXECUTION_COMPLETE__":
                            break
                        if line and line.strip():
                            yield OutputEvent(
                                process_id=process_id,
                                data=line.rstrip("\n\r"),
                                stream="combined",
                            )
                    except TimeoutError:
                        if execution_done and output_queue.empty():
                            break
                        continue

                await execute_task
                yield ProcessCompletedEvent(process_id=process_id, exit_code=0)

            except Exception as e:  # noqa: BLE001
                if not execute_task.done():
                    execute_task.cancel()
                yield ProcessErrorEvent(
                    process_id=process_id, error=str(e), error_type=type(e).__name__
                )

        except Exception as e:  # noqa: BLE001
            yield ProcessErrorEvent.failed(e, process_id=process_id)

    async def stream_command(self, command: str) -> AsyncIterator[ExecutionEvent]:
        """Execute a shell command and stream events."""
        process_id = f"local_cmd_{id(self)}"
        yield ProcessStartedEvent(process_id=process_id, command=command)
        try:
            process = await create_shell_process(command, stdout="pipe", stderr="stdout")
            if process.stdout is not None:
                while True:
                    try:
                        line = await asyncio.wait_for(
                            process.stdout.readline(), timeout=self.timeout
                        )
                        if not line:
                            break
                        yield OutputEvent(
                            process_id=process_id,
                            data=line.decode().rstrip("\n\r"),
                            stream="combined",
                        )
                    except TimeoutError:
                        process.kill()
                        await process.wait()
                        yield ProcessErrorEvent(
                            process_id=process_id,
                            error=f"Command timed out after {self.timeout} seconds",
                            error_type="TimeoutError",
                            exit_code=1,
                        )
                        return

            exit_code = await process.wait()
            if exit_code == 0:
                yield ProcessCompletedEvent(process_id=process_id, exit_code=exit_code)
            else:
                yield ProcessErrorEvent(
                    process_id=process_id,
                    error=f"Command exited with code {exit_code}",
                    error_type="CommandError",
                    exit_code=exit_code,
                )

        except Exception as e:  # noqa: BLE001
            yield ProcessErrorEvent.failed(e, process_id=process_id)


if __name__ == "__main__":
    import asyncio

    provider = LocalExecutionEnvironment()

    async def main():
        """Example."""
        async for line in provider.execute_command_stream("ls -l"):
            print(line)

    asyncio.run(main())
