"""Daytona execution environment that runs code in remote sandboxes."""

from __future__ import annotations

import time
from typing import Any

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.models import ExecutionResult


class DaytonaExecutionEnvironment(ExecutionEnvironment):
    """Executes code in a Daytona sandbox with isolated environment."""

    def __init__(
        self,
        api_url: str | None = None,
        api_key: str | None = None,
        target: str | None = None,
        image: str = "python:3.13-slim",
        timeout: float = 300.0,
        keep_alive: bool = False,
    ):
        """Initialize Daytona environment.

        Args:
            api_url: Daytona API server URL (uses DAYTONA_API_URL env var if None)
            api_key: API key for authentication (uses DAYTONA_API_KEY env var if None)
            target: Target location (uses DAYTONA_TARGET env var if None)
            image: Docker image to use for the sandbox
            timeout: Execution timeout in seconds
            keep_alive: Keep sandbox running after execution
        """
        from daytona import AsyncDaytona, DaytonaConfig

        self.image = image
        self.timeout = timeout
        self.keep_alive = keep_alive

        # Create configuration
        if api_url or api_key or target:
            config = DaytonaConfig(
                api_url=api_url,
                api_key=api_key,
                target=target,
            )
            self.daytona = AsyncDaytona(config)
        else:
            # Use environment variables
            self.daytona = AsyncDaytona()

        self.sandbox = None

    async def __aenter__(self) -> ExecutionEnvironment:
        """Setup Daytona client and create sandbox."""
        # Create sandbox with Python image
        from daytona.common.daytona import CodeLanguage, CreateSandboxFromImageParams

        params = CreateSandboxFromImageParams(
            name=f"anyenv-exec-{int(time.time())}",
            image=self.image,
            language=CodeLanguage.PYTHON,
        )
        self.sandbox = await self.daytona.create(params)

        # Start the sandbox and wait for it to be ready
        await self.sandbox.start(timeout=120)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Cleanup sandbox."""
        if self.sandbox and not self.keep_alive:
            try:
                await self.sandbox.stop()
                await self.sandbox.delete()
            except Exception:  # noqa: BLE001
                # Best effort cleanup
                pass

    async def execute(self, code: str) -> ExecutionResult:
        """Execute code in the Daytona sandbox."""
        if not self.sandbox:
            error_msg = "Daytona environment not properly initialized"
            raise RuntimeError(error_msg)

        start_time = time.time()

        try:
            # Wrap code for execution with result capture
            wrapped_code = self._wrap_code_for_daytona(code)

            # Execute code in sandbox
            response = await self.sandbox.process.exec(
                f"python -c '{wrapped_code}'", timeout=int(self.timeout)
            )

            duration = time.time() - start_time

            # Parse execution results
            if response.exit_code == 0:
                result, error_info = self._parse_daytona_output(response.result)

                if error_info is None:
                    return ExecutionResult(
                        result=result,
                        duration=duration,
                        success=True,
                        stdout=response.result,
                        stderr="",
                    )
                return ExecutionResult(
                    result=None,
                    duration=duration,
                    success=False,
                    error=error_info.get("error", "Unknown error"),
                    error_type=error_info.get("type", "ExecutionError"),
                    stdout=response.result,
                    stderr="",
                )

            return ExecutionResult(
                result=None,
                duration=duration,
                success=False,
                error="Command execution failed",
                error_type="CommandError",
                stdout=response.result,
                stderr="",
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

    def _wrap_code_for_daytona(self, code: str) -> str:
        """Wrap user code for Daytona execution with result capture."""
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
        print("__DAYTONA_RESULT__", json.dumps(execution_result, default=str))
    except Exception as e:
        error_result = {{
            "success": False,
            "error": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc()
        }}
        print("__DAYTONA_RESULT__", json.dumps(error_result, default=str))
"""

    def _parse_daytona_output(self, output: str) -> tuple[Any, dict | None]:
        """Parse result from Daytona sandbox output."""
        try:
            lines = output.strip().split("\n")
            for line in lines:
                if line.startswith("__DAYTONA_RESULT__"):
                    result_json = line[len("__DAYTONA_RESULT__") :].strip()

                    import json

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
