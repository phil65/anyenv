"""Docker execution environment that runs code in isolated containers."""

from __future__ import annotations

import contextlib
import json
import time
from typing import TYPE_CHECKING, Any

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.models import ExecutionResult


if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager

    from testcontainers.core.container import DockerContainer

    from anyenv.code_execution.models import ServerInfo


class DockerExecutionEnvironment(ExecutionEnvironment):
    """Executes code in a Docker container with HTTP tool callbacks."""

    def __init__(
        self,
        lifespan_handler: AbstractAsyncContextManager[ServerInfo],
        image: str = "python:3.13-slim",
        timeout: float = 60.0,
    ):
        """Initialize Docker environment.

        Args:
            lifespan_handler: Async context manager for tool server
            image: Docker image to use
            timeout: Execution timeout in seconds
        """
        self.lifespan_handler = lifespan_handler
        self.image = image
        self.timeout = timeout
        self.server_info: ServerInfo | None = None
        self.container: DockerContainer | None = None

    async def __aenter__(self) -> ExecutionEnvironment:
        # Start tool server
        self.server_info = await self.lifespan_handler.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        # Cleanup container
        if self.container:
            with contextlib.suppress(Exception):
                self.container.stop()

        # Cleanup server
        await self.lifespan_handler.__aexit__(exc_type, exc_val, exc_tb)

    async def execute(self, code: str) -> ExecutionResult:
        """Execute code in Docker container."""
        start_time = time.time()

        try:
            from testcontainers.core.container import DockerContainer

            self.container = DockerContainer(self.image)
            self.container = self.container.with_command([
                "sh",
                "-c",
                "pip install httpx && sleep infinity",
            ]).with_kwargs(network_mode="host")  # Allow access to host for HTTP calls

            self.container.start()
            wrapped_code = self._wrap_code_for_docker(code)  # Create execution script
            result = self.container.exec(f"python -c '{wrapped_code}'")
            duration = time.time() - start_time
            # Parse output
            execution_result, error_info = self._parse_docker_output(
                result.output.decode() if result.output else ""
            )

            if result.exit_code == 0 and error_info is None:
                return ExecutionResult(
                    result=execution_result,
                    duration=duration,
                    success=True,
                    stdout=result.output.decode() if result.output else "",
                    stderr="",
                )
            return ExecutionResult(
                result=None,
                duration=duration,
                success=False,
                error=error_info.get("error", "Container execution failed")
                if error_info
                else "Container execution failed",
                error_type=error_info.get("type", "ContainerError")
                if error_info
                else "ContainerError",
                stdout=result.output.decode() if result.output else "",
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

    def _wrap_code_for_docker(self, code: str) -> str:
        """Wrap user code for Docker execution with HTTP tool calls."""
        server_url = self.server_info.url if self.server_info else "http://localhost:8000"
        return f"""
import asyncio
import httpx
import json
import traceback

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

    def _parse_docker_output(self, output: str) -> tuple[Any, dict | None]:
        """Parse result from Docker container output."""
        try:
            lines = output.strip().split("\n")
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
            return None, {"error": "No execution result found", "type": "ParseError"}
