"""Local execution environment that runs code locally."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import io
import json
import shutil
import sys
import time
from typing import TYPE_CHECKING, Any, Self, TextIO

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.models import ExecutionResult
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
        self.language = language
        self.executable = executable or (
            self._find_executable(language) if isolated else None
        )
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

    def _find_executable(self, language: Language) -> str:
        """Find the best available executable for the given language."""
        match language:
            case "python":
                for candidate in PYTHON_EXECUTABLES:
                    if shutil.which(candidate):
                        return candidate
                error_msg = "No Python executable found"
                raise RuntimeError(error_msg)

            case "javascript":
                candidates = ["node", "nodejs"]
                for candidate in candidates:
                    if shutil.which(candidate):
                        return candidate
                error_msg = "No Node.js executable found"
                raise RuntimeError(error_msg)

            case "typescript":
                node_candidates = ["node", "nodejs"]
                node_exe = None
                for candidate in node_candidates:
                    if shutil.which(candidate):
                        node_exe = candidate
                        break

                if not node_exe:
                    error_msg = "No Node.js executable found (required for TypeScript)"
                    raise RuntimeError(error_msg)

                # Check for TypeScript runners
                ts_runners = ["ts-node", "tsx"]
                for runner in ts_runners:
                    if shutil.which(runner):
                        return node_exe

                return node_exe

            case _:
                candidates = ["python3", "python"]
                for candidate in candidates:
                    if shutil.which(candidate):
                        return candidate
                error_msg = f"No suitable executable found for language: {language}"
                raise RuntimeError(error_msg)

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

        except TimeoutError:
            duration = time.time() - start_time
            return ExecutionResult(
                result=None,
                duration=duration,
                success=False,
                error=f"Execution timed out after {self.timeout} seconds",
                error_type="TimeoutError",
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

    async def _execute_subprocess(self, code: str) -> ExecutionResult:
        """Execute code in subprocess with communication via stdin/stdout."""
        start_time = time.time()

        try:
            wrapped_code = self._wrap_code_for_subprocess(code)
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
                execution_result, error_info = _parse_subprocess_output(stdout)
                if error_info is None:
                    return ExecutionResult(
                        result=execution_result,
                        duration=time.time() - start_time,
                        success=True,
                        stdout=stdout,
                        stderr=stderr,
                    )
                return ExecutionResult(
                    result=None,
                    duration=time.time() - start_time,
                    success=False,
                    error=error_info.get("error", "Subprocess execution failed"),
                    error_type=error_info.get("type", "SubprocessError"),
                    stdout=stdout,
                    stderr=stderr,
                )
            return ExecutionResult(
                result=None,
                duration=time.time() - start_time,
                success=False,
                error=stderr or "Subprocess execution failed",
                error_type="SubprocessError",
                stdout=stdout,
                stderr=stderr,
            )

        except TimeoutError:
            if self.process:
                self.process.kill()
                await self.process.wait()
            return ExecutionResult(
                result=None,
                duration=time.time() - start_time,
                success=False,
                error=f"Execution timed out after {self.timeout} seconds",
                error_type="TimeoutError",
            )
        except Exception as e:  # noqa: BLE001
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

    def _wrap_code_for_subprocess(self, code: str) -> str:
        """Wrap user code for subprocess execution."""
        match self.language:
            case "python":
                return self._wrap_python_code(code)
            case "javascript":
                return self._wrap_javascript_code(code)
            case "typescript":
                return self._wrap_typescript_code(code)
            case _:
                return self._wrap_python_code(code)

    def _wrap_python_code(self, code: str) -> str:
        """Wrap Python code for subprocess execution."""
        server_url = self.server_info.url if self.server_info else "http://localhost:8000"

        if self.server_info:
            return f"""
import asyncio
import json
import traceback
import httpx

# Simple HTTP proxy for tools
async def http_tool_call(tool_name: str, **kwargs):
    async with httpx.AsyncClient() as client:
        response = await client.post(
            f"{server_url}/api/tools/" + tool_name,
            json={{"params": kwargs}}
        )
        result = response.json()
        if result.get("error"):
            raise RuntimeError(f"Tool " + tool_name + f" failed: " + result["error"])
        return result.get("result")

# User code
{code}

# Result handling
async def _anyenv_execute():
    try:
        if "main" in globals() and callable(main):
            if asyncio.iscoroutinefunction(main):
                result = await main()
            else:
                result = main()
        else:
            result = globals().get("_result")

        print("__RESULT_START__")
        print(json.dumps({{"result": result, "type": type(result).__name__}}))
        print("__RESULT_END__")
    except Exception as e:
        print("__ERROR_START__")
        print(json.dumps({{"error": str(e), "type": type(e).__name__, "traceback": traceback.format_exc()}}))
        print("__ERROR_END__")

asyncio.run(_anyenv_execute())
"""  # noqa: E501
        return f"""
import asyncio
import json
import traceback

# User code
{code}

# Result handling
async def _anyenv_execute():
    try:
        if "main" in globals() and callable(main):
            if asyncio.iscoroutinefunction(main):
                result = await main()
            else:
                result = main()
        else:
            result = globals().get("_result")

        print("__RESULT_START__")
        print(json.dumps({{"result": result, "type": type(result).__name__}}))
        print("__RESULT_END__")
    except Exception as e:
        print("__ERROR_START__")
        print(json.dumps({{"error": str(e), "type": type(e).__name__, "traceback": traceback.format_exc()}}))
        print("__ERROR_END__")

asyncio.run(_anyenv_execute())
"""  # noqa: E501

    def _wrap_javascript_code(self, code: str) -> str:
        """Wrap JavaScript code for subprocess execution."""
        return f"""
const {{ spawn }} = require('child_process');

// User code
{code}

// Result handling
async function _anyenv_execute() {{
    try {{
        let result;
        if (typeof main === 'function') {{
            result = await Promise.resolve(main());
        }} else if (typeof _result !== 'undefined') {{
            result = _result;
        }}

        console.log('__RESULT_START__');
        console.log(JSON.stringify({{result: result, type: typeof result}}));
        console.log('__RESULT_END__');
    }} catch (e) {{
        console.log('__ERROR_START__');
        console.log(JSON.stringify({{error: e.message, type: e.constructor.name, stack: e.stack}}));
        console.log('__ERROR_END__');
    }}
}}

_anyenv_execute();
"""  # noqa: E501

    def _wrap_typescript_code(self, code: str) -> str:
        """Wrap TypeScript code for subprocess execution."""
        return f"""
// User code
{code}

// Result handling
async function _anyenv_execute(): Promise<void> {{
    try {{
        let result: any;
        if (typeof main === 'function') {{
            result = await Promise.resolve(main());
        }} else if (typeof _result !== 'undefined') {{
            result = _result;
        }}

        console.log('__RESULT_START__');
        console.log(JSON.stringify({{result: result, type: typeof result}}));
        console.log('__RESULT_END__');
    }} catch (e: any) {{
        console.log('__ERROR_START__');
        console.log(JSON.stringify({{error: e.message, type: e.constructor.name, stack: e.stack}}));
        console.log('__ERROR_END__');
    }}
}}

_anyenv_execute();
"""  # noqa: E501

    async def execute_stream(self, code: str) -> AsyncIterator[str]:
        """Execute code and stream output line by line."""
        if self.isolated:
            async for line in self._execute_stream_subprocess(code):
                yield line
        else:
            async for line in self._execute_stream_local(code):
                yield line

    async def _execute_stream_local(self, code: str) -> AsyncIterator[str]:
        """Execute code in same process and stream output line by line."""
        try:
            output_queue: asyncio.Queue[str] = asyncio.Queue()

            class StreamCapture(io.StringIO):
                def __init__(
                    self,
                    original_stream: TextIO,
                    queue: asyncio.Queue[str],
                ) -> None:
                    super().__init__()
                    self.original_stream = original_stream
                    self.queue = queue

                def write(self, text: str) -> int:
                    result = self.original_stream.write(text)
                    if text:
                        lines = text.splitlines(keepends=True)
                        for line in lines:
                            if line.strip():
                                with contextlib.suppress(asyncio.QueueFull):
                                    self.queue.put_nowait(line.rstrip("\n\r"))
                    return result

                def flush(self) -> None:
                    return self.original_stream.flush()

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
                        exec(code, namespace)

                        if "main" in namespace and callable(namespace["main"]):
                            main_func = namespace["main"]
                            if inspect.iscoroutinefunction(main_func):
                                result = await asyncio.wait_for(
                                    main_func(), timeout=self.timeout
                                )
                            else:
                                result = await asyncio.wait_for(
                                    asyncio.to_thread(main_func), timeout=self.timeout
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

            while True:
                try:
                    line = await asyncio.wait_for(output_queue.get(), timeout=0.1)
                    if line == "__EXECUTION_COMPLETE__":
                        break
                    yield line
                except TimeoutError:
                    if execution_done and output_queue.empty():
                        break
                    continue
                except Exception as e:  # noqa: BLE001
                    yield f"ERROR: {e}"
                    break

            try:
                await execute_task
            except Exception as e:  # noqa: BLE001
                yield f"ERROR: {e}"

        except Exception as e:  # noqa: BLE001
            yield f"ERROR: {e}"

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
                wrapped_code = self._wrap_code_for_subprocess(code)
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
            )

        except TimeoutError:
            duration = time.time() - start_time
            return ExecutionResult(
                result=None,
                duration=duration,
                success=False,
                error=f"Command timed out after {self.timeout} seconds",
                error_type="TimeoutError",
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


def _parse_subprocess_output(output: str) -> tuple[Any, dict[str, Any] | None]:
    """Parse subprocess output to extract result or error."""
    lines = output.strip().split("\n")

    # Look for result markers
    result_start = None
    result_end = None
    error_start = None
    error_end = None

    for i, line in enumerate(lines):
        if "__RESULT_START__" in line:
            result_start = i + 1
        elif "__RESULT_END__" in line:
            result_end = i
        elif "__ERROR_START__" in line:
            error_start = i + 1
        elif "__ERROR_END__" in line:
            error_end = i

    # Parse error first (takes precedence)
    if error_start is not None and error_end is not None:
        try:
            error_json = "\n".join(lines[error_start:error_end])
            return None, json.loads(error_json)
        except json.JSONDecodeError:
            return None, {
                "error": "Failed to parse error output",
                "type": "ParseError",
            }

    # Parse result
    if result_start is not None and result_end is not None:
        try:
            result_json = "\n".join(lines[result_start:result_end])
            result_data = json.loads(result_json)
            return result_data.get("result"), None
        except json.JSONDecodeError:
            return None, {
                "error": "Failed to parse result output",
                "type": "ParseError",
            }

    # No markers found
    return None, {"error": "No execution result found", "type": "ParseError"}
