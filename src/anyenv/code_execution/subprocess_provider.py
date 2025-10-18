"""Subprocess execution environment that runs code in a separate Python process."""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any, Self

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.models import ExecutionResult


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager

    from anyenv.code_execution.models import Language, ServerInfo


class SubprocessExecutionEnvironment(ExecutionEnvironment):
    """Executes code in a subprocess with communication via stdin/stdout."""

    def __init__(
        self,
        lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
        executable: str = "python",
        timeout: float = 30.0,
        language: Language = "python",
    ):
        """Initialize subprocess environment.

        Args:
            lifespan_handler: Async context manager for tool server (optional)
            executable: Executable to use (python, node, npx)
            timeout: Execution timeout in seconds
            language: Programming language to use
        """
        super().__init__(lifespan_handler=lifespan_handler)
        self.executable = executable
        self.timeout = timeout
        self.language = language
        self.process: asyncio.subprocess.Process | None = None

    async def __aenter__(self) -> Self:
        # Start tool server via base class
        await super().__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()

        # Cleanup server via base class
        await super().__aexit__(exc_type, exc_val, exc_tb)

    async def execute(self, code: str) -> ExecutionResult:
        """Execute code in subprocess."""
        start_time = time.time()

        try:
            # Wrap code to capture result and handle execution
            wrapped_code = self._wrap_code_for_subprocess(code)

            # Create subprocess with language-specific arguments
            args = self._get_subprocess_args()
            self.process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
            )

            # Wait for completion with timeout
            try:
                stdout_data, stderr_data = await asyncio.wait_for(
                    self.process.communicate(input=wrapped_code.encode()),
                    timeout=self.timeout,
                )
            except TimeoutError:
                self.process.kill()
                await self.process.wait()
                duration = time.time() - start_time
                return ExecutionResult(
                    result=None,
                    duration=duration,
                    success=False,
                    error=f"Execution timed out after {self.timeout} seconds",
                    error_type="TimeoutError",
                )

            duration = time.time() - start_time
            stdout = stdout_data.decode() if stdout_data else ""
            stderr = stderr_data.decode() if stderr_data else ""

            # Parse result from stdout
            result, error_info = self._parse_subprocess_output(stdout)

            if self.process.returncode == 0 and error_info is None:
                return ExecutionResult(
                    result=result,
                    duration=duration,
                    success=True,
                    stdout=stdout,
                    stderr=stderr,
                )
            return ExecutionResult(
                result=None,
                duration=duration,
                success=False,
                error=error_info.get("error", stderr) if error_info else stderr,
                error_type=error_info.get("type") if error_info else "SubprocessError",
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

    def _get_subprocess_args(self) -> list[str]:
        """Get subprocess arguments based on language."""
        match self.language:
            case "python":
                return [
                    self.executable,
                    "-u",
                ]  # Unbuffered output
            case "javascript":
                return [self.executable]  # Read from stdin
            case "typescript":
                return ["npx", "ts-node"]  # Read TypeScript from stdin
            case _:
                return [self.executable, "-u"]

    def _wrap_code_for_subprocess(self, code: str) -> str:
        """Wrap user code for subprocess execution with result capture."""
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
        """Wrap Python code for execution."""
        return f"""
import asyncio
import json
import traceback
import inspect

# User code
{code}

# Execution wrapper
async def _execute_main():
    try:
        if "main" in globals() and callable(globals()["main"]):
            main_func = globals()["main"]
            if inspect.iscoroutinefunction(main_func):
                result = await main_func()
            else:
                result = main_func()
        else:
            result = globals().get("_result")
        return {{"result": result, "success": True}}
    except Exception as e:
        return {{
            "success": False,
            "error": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc()
        }}

# Run and output result
if __name__ == "__main__":
    try:
        execution_result = asyncio.run(_execute_main())
        print("__SUBPROCESS_RESULT__", json.dumps(execution_result, default=str))
    except Exception as e:
        error_result = {{
            "success": False,
            "error": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc()
        }}
        print("__SUBPROCESS_RESULT__", json.dumps(error_result, default=str))
"""

    def _wrap_javascript_code(self, code: str) -> str:
        """Wrap JavaScript code for execution."""
        return f"""
// User code
{code}

// Execution wrapper
async function executeMain() {{
    try {{
        let result;
        if (typeof main === 'function') {{
            result = await main();
        }} else if (typeof _result !== 'undefined') {{
            result = _result;
        }}
        return {{ result: result, success: true }};
    }} catch (error) {{
        return {{
            success: false,
            error: error.message,
            type: error.name,
            traceback: error.stack
        }};
    }}
}}

// Run and output result
executeMain().then(result => {{
    console.log('__SUBPROCESS_RESULT__', JSON.stringify(result));
}}).catch(error => {{
    const errorResult = {{
        success: false,
        error: error.message,
        type: error.name,
        traceback: error.stack
    }};
    console.log('__SUBPROCESS_RESULT__', JSON.stringify(errorResult));
}});
"""

    def _wrap_typescript_code(self, code: str) -> str:
        """Wrap TypeScript code for execution."""
        return f"""
// User code
{code}

// Execution wrapper
async function executeMain(): Promise<{{ result: any; success: boolean; error?: string; type?: string; traceback?: string }}> {{
    try {{
        let result: any;
        if (typeof main === 'function') {{
            result = await main();
        }} else if (typeof _result !== 'undefined') {{
            result = (global as any)._result;
        }}
        return {{ result: result, success: true }};
    }} catch (error: any) {{
        return {{
            success: false,
            error: error.message,
            type: error.name,
            traceback: error.stack
        }};
    }}
}}

// Run and output result
executeMain().then(result => {{
    console.log('__SUBPROCESS_RESULT__', JSON.stringify(result));
}}).catch(error => {{
    const errorResult = {{
        success: false,
        error: error.message,
        type: error.name,
        traceback: error.stack
    }};
    console.log('__SUBPROCESS_RESULT__', JSON.stringify(errorResult));
}});
"""  # noqa: E501

    def _parse_subprocess_output(self, stdout: str) -> tuple[Any, dict | None]:
        """Parse result from subprocess output."""
        import anyenv

        try:
            lines = stdout.strip().split("\n")
            for line in lines:
                if line.startswith("__SUBPROCESS_RESULT__"):
                    result_json = line[len("__SUBPROCESS_RESULT__") :].strip()
                    result_data = anyenv.load_json(result_json, return_type=dict)

                    if result_data.get("success", False):
                        return result_data.get("result"), None
                    return None, {
                        "error": result_data.get("error", "Unknown error"),
                        "type": result_data.get("type", "Unknown"),
                    }
        except json.JSONDecodeError as e:
            return None, {
                "error": f"Failed to parse result: {e}",
                "type": "JSONDecodeError",
            }
        except Exception as e:  # noqa: BLE001
            return None, {"error": str(e), "type": type(e).__name__}
        else:
            return None, {"error": "No execution result found", "type": "ParseError"}

    async def execute_stream(self, code: str) -> AsyncIterator[str]:
        """Execute code and stream output line by line.

        Args:
            code: Python code to execute

        Yields:
            Lines of output as they are produced
        """
        try:
            # Wrap code for execution
            wrapped_code = self._wrap_code_for_subprocess(code)

            # Create subprocess
            args = self._get_subprocess_args()
            process = await asyncio.create_subprocess_exec(
                *args,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,  # Merge stderr into stdout
                stdin=asyncio.subprocess.PIPE,
            )

            # Send code to stdin and close it
            if process.stdin is not None:
                process.stdin.write(wrapped_code.encode())
                process.stdin.close()

            # Stream output line by line
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
                        yield f"ERROR: Execution timed out after {self.timeout} seconds"
                        break

            # Wait for process to complete
            await process.wait()

        except Exception as e:  # noqa: BLE001
            yield f"ERROR: {e}"

    async def execute_command(self, command: str) -> ExecutionResult:
        """Execute a terminal command and return result with metadata."""
        start_time = time.time()

        try:
            # Execute command using subprocess
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

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
        """Execute a terminal command and stream output line by line.

        Args:
            command: Terminal command to execute

        Yields:
            Lines of output as they are produced
        """
        try:
            # Create subprocess
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,  # Merge stderr into stdout
            )

            # Stream output line by line
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

            # Wait for process to complete
            await process.wait()

        except Exception as e:  # noqa: BLE001
            yield f"ERROR: {e}"
