"""Daytona execution environment that runs code in remote sandboxes."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Self

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.models import ExecutionResult


if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager

    from anyenv.code_execution.models import Language, ServerInfo


class DaytonaExecutionEnvironment(ExecutionEnvironment):
    """Executes code in a Daytona sandbox with isolated environment."""

    def __init__(
        self,
        lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
        api_url: str | None = None,
        api_key: str | None = None,
        target: str | None = None,
        image: str = "python:3.13-slim",
        timeout: float = 300.0,
        keep_alive: bool = False,
        language: Language = "python",
    ):
        """Initialize Daytona environment.

        Args:
            lifespan_handler: Async context manager for tool server (optional)
            api_url: Daytona API server URL (uses DAYTONA_API_URL env var if None)
            api_key: API key for authentication (uses DAYTONA_API_KEY env var if None)
            target: Target location (uses DAYTONA_TARGET env var if None)
            image: Docker image to use for the sandbox
            timeout: Execution timeout in seconds
            keep_alive: Keep sandbox running after execution
            language: Programming language to use for execution
        """
        from daytona import AsyncDaytona, DaytonaConfig

        super().__init__(lifespan_handler=lifespan_handler)
        self.image = image
        self.timeout = timeout
        self.keep_alive = keep_alive
        self.language = language

        # Create configuration
        if api_url or api_key or target:
            config = DaytonaConfig(api_url=api_url, api_key=api_key, target=target)
            self.daytona = AsyncDaytona(config)
        else:
            # Use environment variables
            self.daytona = AsyncDaytona()

        self.sandbox = None

    async def __aenter__(self) -> Self:
        """Setup Daytona client and create sandbox."""
        # Start tool server via base class
        await super().__aenter__()
        # Create sandbox with Python image
        from daytona.common.daytona import CodeLanguage, CreateSandboxFromImageParams

        match self.language:
            case "python":
                language = CodeLanguage.PYTHON
            case "javascript":
                language = CodeLanguage.JAVASCRIPT
            case "typescript":
                language = CodeLanguage.TYPESCRIPT
            case _:
                msg = f"Unsupported language: {self.language}"
                raise ValueError(msg)
        params = CreateSandboxFromImageParams(
            name=f"anyenv-exec-{int(time.time())}", image=self.image, language=language
        )
        self.sandbox = await self.daytona.create(params)
        assert self.sandbox, "Failed to create sandbox"
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

        # Cleanup server via base class
        await super().__aexit__(exc_type, exc_val, exc_tb)

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
                error=response.result if response.result else "Command execution failed",
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

                    import anyenv

                    result_data = anyenv.load_json(result_json, return_type=dict)

                    if result_data.get("success", False):
                        return result_data.get("result"), None
                    return None, {
                        "error": result_data.get("error", "Unknown error"),
                        "type": result_data.get("type", "Unknown"),
                    }
        except anyenv.JsonLoadError as e:
            return None, {
                "error": f"Failed to parse result: {e}",
                "type": "JSONDecodeError",
            }
        except Exception as e:  # noqa: BLE001
            return None, {"error": str(e), "type": type(e).__name__}
        else:
            return None, {"error": "No execution result found", "type": "ParseError"}

    async def execute_command(self, command: str) -> ExecutionResult:
        """Execute a terminal command in the Daytona sandbox."""
        if not self.sandbox:
            error_msg = "Daytona environment not properly initialized"
            raise RuntimeError(error_msg)

        start_time = time.time()

        try:
            # Execute command using Daytona's process.exec() method
            response = await self.sandbox.process.exec(command, timeout=int(self.timeout))
            duration = time.time() - start_time

            success = response.exit_code == 0

            return ExecutionResult(
                result=response.result if success else None,
                duration=duration,
                success=success,
                error=response.result if not success else None,
                error_type="CommandError" if not success else None,
                stdout=response.result,
                stderr="",  # Daytona combines stdout/stderr in result
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

    async def execute_command_stream(self, command: str):
        """Execute a terminal command and stream output in the Daytona sandbox."""
        if not self.sandbox:
            error_msg = "Daytona environment not properly initialized"
            raise RuntimeError(error_msg)

        try:
            # Execute command and collect output
            response = await self.sandbox.process.exec(command, timeout=int(self.timeout))

            # Split result into lines and yield them
            if response.result:
                for line in response.result.split("\n"):
                    if line.strip():  # Only yield non-empty lines
                        yield line

            # Yield exit code info if command failed
            if response.exit_code != 0:
                yield f"ERROR: Command exited with code {response.exit_code}"

        except Exception as e:  # noqa: BLE001
            yield f"ERROR: {e}"
