"""Subprocess execution environment that runs code in a separate Python process."""

from __future__ import annotations

import asyncio
import json
import time
from typing import Any

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.models import ExecutionResult


class SubprocessExecutionEnvironment(ExecutionEnvironment):
    """Executes code in a subprocess with communication via stdin/stdout."""

    def __init__(self, python_executable: str = "python", timeout: float = 30.0):
        """Initialize subprocess environment.

        Args:
            python_executable: Python executable to use
            timeout: Execution timeout in seconds
        """
        self.python_executable = python_executable
        self.timeout = timeout
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

            # Create subprocess
            self.process = await asyncio.create_subprocess_exec(
                self.python_executable,
                "-c",
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

    def _wrap_code_for_subprocess(self, code: str) -> str:
        """Wrap user code for subprocess execution with result capture."""
        return f"""
import asyncio
import json
import sys
import traceback

# User code
{code}

# Execution wrapper
async def _execute_main():
    try:
        if "main" in globals():
            result = await main()
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
        print("__EXECUTION_RESULT__", json.dumps(execution_result, default=str))
    except Exception as e:
        error_result = {{
            "success": False,
            "error": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc()
        }}
        print("__EXECUTION_RESULT__", json.dumps(error_result, default=str))
"""

    def _parse_subprocess_output(self, stdout: str) -> tuple[Any, dict | None]:
        """Parse result from subprocess stdout."""
        try:
            # Look for our result marker
            lines = stdout.strip().split("\n")
            for line in lines:
                if line.startswith("__EXECUTION_RESULT__"):
                    result_json = line[len("__EXECUTION_RESULT__") :].strip()
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
            # No result marker found
            return None, {"error": "No execution result found", "type": "ParseError"}
