"""E2B execution environment that runs code in cloud sandboxes."""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING, Any

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.models import ExecutionResult


if TYPE_CHECKING:
    from e2b import Sandbox


class E2bExecutionEnvironment(ExecutionEnvironment):
    """Executes code in an E2B cloud sandbox."""

    def __init__(
        self,
        template: str | None = None,
        timeout: int = 300,
        keep_alive: bool = False,
    ):
        """Initialize E2B environment.

        Args:
            template: E2B template name/ID (uses 'base' if None)
            timeout: Sandbox timeout in seconds
            keep_alive: Keep sandbox running after execution
        """
        self.template = template
        self.timeout = timeout
        self.keep_alive = keep_alive
        self.sandbox: Sandbox | None = None

    async def __aenter__(self) -> ExecutionEnvironment:
        """Setup E2B sandbox."""
        # Create sandbox (uses E2B_API_KEY environment variable)
        from e2b import Sandbox

        if self.template:
            self.sandbox = Sandbox.create(
                template=self.template,
                timeout=self.timeout,
            )
        else:
            self.sandbox = Sandbox.create(timeout=self.timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Cleanup sandbox."""
        if self.sandbox and not self.keep_alive:
            with contextlib.suppress(Exception):
                self.sandbox.kill()

    async def execute(self, code: str) -> ExecutionResult:
        """Execute code in the E2B sandbox."""
        if not self.sandbox:
            error_msg = "E2B environment not properly initialized"
            raise RuntimeError(error_msg)

        start_time = time.time()

        try:
            # Create a Python script to execute and capture results
            wrapped_code = self._wrap_code_for_e2b(code)

            # Write the code to a temporary file and execute it
            script_path = "/tmp/e2b_execution_script.py"
            self.sandbox.files.write(script_path, wrapped_code)

            # Execute the script
            result = self.sandbox.commands.run(f"python {script_path}")
            duration = time.time() - start_time

            # Parse the output to extract results
            execution_result, error_info = self._parse_e2b_output(result.stdout)

            if result.exit_code == 0 and error_info is None:
                return ExecutionResult(
                    result=execution_result,
                    duration=duration,
                    success=True,
                    stdout=result.stdout,
                    stderr=result.stderr,
                )

            return ExecutionResult(
                result=None,
                duration=duration,
                success=False,
                error=error_info.get("error", "Command execution failed")
                if error_info
                else "Command execution failed",
                error_type=error_info.get("type", "ExecutionError")
                if error_info
                else "ExecutionError",
                stdout=result.stdout,
                stderr=result.stderr,
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

    def _wrap_code_for_e2b(self, code: str) -> str:
        """Wrap user code for E2B execution with result capture."""
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
        print("__E2B_RESULT__", json.dumps(execution_result, default=str))
    except Exception as e:
        error_result = {{
            "success": False,
            "error": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc()
        }}
        print("__E2B_RESULT__", json.dumps(error_result, default=str))
"""

    def _parse_e2b_output(self, output: str) -> tuple[Any, dict | None]:
        """Parse result from E2B sandbox output."""
        try:
            lines = output.strip().split("\n")
            for line in lines:
                if line.startswith("__E2B_RESULT__"):
                    result_json = line[len("__E2B_RESULT__") :].strip()

                    import json

                    result_data = json.loads(result_json)

                    if result_data.get("success", False):
                        return result_data.get("result"), None
                    return None, {
                        "error": result_data.get("error", "Unknown error"),
                        "type": result_data.get("type", "Unknown"),
                    }
        except Exception as e:  # noqa: BLE001
            return None, {"error": str(e), "type": type(e).__name__}
        else:
            return None, {"error": "No execution result found", "type": "ParseError"}
