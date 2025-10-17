"""Subprocess execution environment that runs code in a separate Python process."""

from __future__ import annotations

import asyncio
import json
import time
from typing import TYPE_CHECKING, Any

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.models import ExecutionResult


if TYPE_CHECKING:
    from anyenv.code_execution.models import Language


class SubprocessExecutionEnvironment(ExecutionEnvironment):
    """Executes code in a subprocess with communication via stdin/stdout."""

    def __init__(
        self,
        executable: str = "python",
        timeout: float = 30.0,
        language: Language = "python",
    ):
        """Initialize subprocess environment.

        Args:
            executable: Executable to use (python, node, npx)
            timeout: Execution timeout in seconds
            language: Programming language to use
        """
        self.executable = executable
        self.timeout = timeout
        self.language = language
        self.process: asyncio.subprocess.Process | None = None

    async def __aenter__(self) -> ExecutionEnvironment:
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        if self.process and self.process.returncode is None:
            self.process.terminate()
            try:
                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except TimeoutError:
                self.process.kill()
                await self.process.wait()

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
                wrapped_code,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                stdin=asyncio.subprocess.PIPE,
            )

            # Wait for completion with timeout
            try:
                stdout_data, stderr_data = await asyncio.wait_for(
                    self.process.communicate(), timeout=self.timeout
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
                return [self.executable, "-u"]  # Unbuffered output
            case "javascript":
                return [self.executable, "-e"]  # Execute inline
            case "typescript":
                return ["npx", "ts-node", "-e"]  # Execute TypeScript inline
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
        try:
            lines = stdout.strip().split("\n")
            for line in lines:
                if line.startswith("__SUBPROCESS_RESULT__"):
                    result_json = line[len("__SUBPROCESS_RESULT__") :].strip()
                    result_data = json.loads(result_json)

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
