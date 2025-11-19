"""Local execution environment that runs code locally."""

from __future__ import annotations

import asyncio
import inspect
import shutil
import time
from typing import TYPE_CHECKING, Any, Self

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.local_provider.utils import (
    execute_stream_local,
    find_executable,
)
from anyenv.code_execution.models import ExecutionResult
from anyenv.code_execution.parse_output import parse_output, wrap_code
from anyenv.processes import create_process, create_shell_process


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager
    from types import TracebackType

    from morefs.asyn_local import AsyncLocalFileSystem

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

            duration = time.time() - start_time
            return ExecutionResult(result=result, duration=duration, success=True)

        except Exception as e:  # noqa: BLE001
            duration = time.time() - start_time
            return ExecutionResult(
                result=None,
                duration=duration,
                success=False,
                error=str(e),
                error_type=type(e).__name__,
            )

    async def _execute_subprocess(self, code: str) -> ExecutionResult:
        """Execute code in subprocess with communication via stdin/stdout."""
        start_time = time.time()

        try:
            wrapped_code = wrap_code(code, self.language)
            process = await create_process(
                *self._get_subprocess_args(),
                stdin="pipe",
                stdout="pipe",
                stderr="pipe",
            )
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
            # Cleanup process if it exists
            if self.process:
                self.process.kill()
                await self.process.wait()
            return ExecutionResult(
                result=None,
                duration=time.time() - start_time,
                success=False,
                error=str(e),
                error_type=type(e).__name__,
            )

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

    async def execute_stream(self, code: str) -> AsyncIterator[str]:
        """Execute code and stream output line by line."""
        if self.isolated:
            async for line in self._execute_stream_subprocess(code):
                yield line
        else:
            async for line in execute_stream_local(code, self.timeout):
                yield line

    async def _execute_stream_subprocess(self, code: str) -> AsyncIterator[str]:
        """Execute code in subprocess and stream output line by line."""
        try:
            process = await create_process(
                *self._get_subprocess_args(),
                stdin="pipe",
                stdout="pipe",
                stderr="stdout",
            )
            self.process = process

            # Send code to subprocess
            if process.stdin:
                wrapped_code = wrap_code(code, self.language)
                process.stdin.write(wrapped_code.encode())
                process.stdin.close()

            # Stream output line by line
            if process.stdout:
                while True:
                    try:
                        line = await asyncio.wait_for(
                            process.stdout.readline(), timeout=self.timeout
                        )
                        if not line:
                            break
                        yield line.decode().rstrip("\n\r")
                    except TimeoutError:
                        process.kill()
                        await process.wait()
                        yield f"ERROR: Execution timed out after {self.timeout} seconds"
                        break

            await process.wait()

        except Exception as e:  # noqa: BLE001
            yield f"ERROR: {e}"

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
            duration = time.time() - start_time
            return ExecutionResult(
                result=None,
                duration=duration,
                success=False,
                error=str(e),
                error_type=type(e).__name__,
            )

    async def execute_command_stream(self, command: str) -> AsyncIterator[str]:
        """Execute a shell command and stream output line by line."""
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
                        yield line.decode().rstrip("\n\r")
                    except TimeoutError:
                        process.kill()
                        await process.wait()
                        yield f"ERROR: Command timed out after {self.timeout} seconds"
                        break

            await process.wait()

        except Exception as e:  # noqa: BLE001
            yield f"ERROR: {e}"


if __name__ == "__main__":
    import asyncio

    provider = LocalExecutionEnvironment()

    async def main():
        """Example."""
        async for line in provider.execute_command_stream("ls -l"):
            print(line)

    asyncio.run(main())
