"""MCP Python execution environment using FastMCP client."""

from __future__ import annotations

import re
import time
from typing import TYPE_CHECKING, Any, Self

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.models import ExecutionResult


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager
    from types import TracebackType

    from fastmcp import Client

    from anyenv.code_execution.models import ServerInfo


class McpPythonExecutionEnvironment(ExecutionEnvironment):
    """MCP Python execution environment using FastMCP client.

    Provides secure Python code execution in a WebAssembly sandbox using Pyodide
    via the FastMCP client connecting to @pydantic/mcp-run-python JSR package.
    Code runs isolated from the host system with optional package dependencies.
    """

    def __init__(
        self,
        lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
        dependencies: list[str] | None = None,
        allow_networking: bool = True,
        timeout: float = 30.0,
    ) -> None:
        """Initialize MCP Python execution environment.

        Args:
            lifespan_handler: Async context manager for tool server (optional)
            dependencies: List of Python packages to install via micropip
            allow_networking: Whether to allow network access during code execution
            timeout: Execution timeout in seconds
        """
        super().__init__(lifespan_handler=lifespan_handler, dependencies=dependencies)
        self.allow_networking = allow_networking
        self.timeout = timeout
        self._client: Client | None = None
        self._server_config = build_server_config()

    async def __aenter__(self) -> Self:
        """Setup the MCP Python environment."""
        # Start tool server via base class
        await super().__aenter__()

        from fastmcp import Client

        self._client = Client(self._server_config)
        await self._client.__aenter__()

        # Test connection
        await self._client.ping()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Cleanup the MCP Python environment."""
        if self._client:
            await self._client.__aexit__(exc_type, exc_val, exc_tb)

        # Cleanup server via base class
        await super().__aexit__(exc_type, exc_val, exc_tb)

    async def execute(
        self, code: str, global_vars: dict[str, Any] | None = None
    ) -> ExecutionResult:
        """Execute Python code using the MCP server.

        Args:
            code: Python code to execute
            global_vars: Optional global variables to make available during execution

        Returns:
            ExecutionResult with output, return value, and execution metadata
        """
        from mcp.types import TextContent

        if not self._client:
            msg = "Environment not initialized. Use 'async with' to setup."
            raise RuntimeError(msg)

        start_time = time.time()

        try:
            # Prepare arguments for the tool
            tool_args: dict[str, Any] = {"python_code": code}
            if global_vars:
                tool_args["global_variables"] = global_vars

            # Call the run_python_code tool with timeout
            import asyncio

            result = await asyncio.wait_for(
                self._client.call_tool("run_python_code", tool_args), timeout=self.timeout
            )
            duration = time.time() - start_time

            # Parse the result content
            if not result.content:
                return ExecutionResult(
                    result=None,
                    duration=duration,
                    success=False,
                    stdout=None,
                    stderr=None,
                    error="No content in MCP response",
                    error_type="MCPError",
                )

            # Get the text content
            content_text = (
                result.content[0].text
                if result.content and isinstance(result.content[0], TextContent)
                else ""
            )

            # Parse based on format (XML by default)
            if content_text.startswith("<status>"):
                return _parse_xml_result(content_text, duration)
            # Try JSON format
            import anyenv

            try:
                result_data = anyenv.load_json(content_text, return_type=dict)
                return ExecutionResult(
                    result=result_data.get("return_value"),
                    duration=duration,
                    success=result_data.get("status") == "success",
                    stdout="\n".join(result_data.get("output", []))
                    if result_data.get("output")
                    else None,
                    stderr=None,
                    error=result_data.get("error"),
                    error_type=result_data.get("status")
                    if result_data.get("status") != "success"
                    else None,
                )
            except anyenv.JsonLoadError:
                # Fallback to treating as plain text
                return ExecutionResult(
                    result=content_text,
                    duration=duration,
                    success=True,
                    stdout=content_text,
                    stderr=None,
                    error=None,
                    error_type=None,
                )

        except Exception as e:  # noqa: BLE001
            duration = time.time() - start_time
            return ExecutionResult(
                result=None,
                duration=duration,
                success=False,
                stdout=None,
                stderr=None,
                error=str(e),
                error_type=type(e).__name__,
            )

    async def execute_command(self, command: str) -> ExecutionResult:
        """Execute a terminal command (not supported in MCP Python environment)."""
        msg = "Terminal command execution is not supported in MCP Python environment"
        raise NotImplementedError(msg)

    async def execute_command_stream(self, command: str) -> AsyncIterator[str]:
        """Execute a terminal command and stream output.

        (not supported in MCP Python environment).
        """
        msg = "Terminal command streaming is not supported in MCP Python environment"
        raise NotImplementedError(msg)
        yield


def _parse_xml_result(xml_content: str, duration: float) -> ExecutionResult:
    """Parse XML-formatted result from MCP server."""
    import anyenv

    # Extract status
    status_match = re.search(r"<status>(.*?)</status>", xml_content, re.DOTALL)
    status = status_match.group(1).strip() if status_match else "unknown"

    # Extract output
    output_match = re.search(r"<output>(.*?)</output>", xml_content, re.DOTALL)
    output = output_match.group(1).strip() if output_match else None

    # Extract return value
    return_value: Any = None
    return_match = re.search(
        r"<return_value>(.*?)</return_value>", xml_content, re.DOTALL
    )
    if return_match:
        return_text = return_match.group(1).strip()
        try:
            return_value = anyenv.load_json(return_text, return_type=dict)
        except anyenv.JsonLoadError:
            return_value = return_text

    # Extract error
    error_match = re.search(r"<error>(.*?)</error>", xml_content, re.DOTALL)
    error = error_match.group(1).strip() if error_match else None

    return ExecutionResult(
        result=return_value,
        duration=duration,
        success=status == "success",
        stdout=output,
        stderr=None,
        error=error,
        error_type=status if status != "success" else None,
    )


def build_server_config() -> dict[str, Any]:
    """Build MCP server configuration for deno + JSR package."""
    cmd = [
        "deno",
        "run",
        "-N",
        "-R=node_modules",
        "-W=node_modules",
        "--node-modules-dir=auto",
        "jsr:@pydantic/mcp-run-python",
        "stdio",
    ]

    return {
        "mcpServers": {
            "python_executor": {
                "transport": "stdio",
                "command": cmd[0],
                "args": cmd[1:],
            }
        }
    }


if __name__ == "__main__":
    import asyncio

    async def test() -> None:
        """Quick test of MCP Python execution."""
        print("Testing FastMCP Python execution environment...")

        try:
            # Test 1: Basic execution
            print("1. Basic test...")
            async with McpPythonExecutionEnvironment() as env:
                result = await env.execute("print('Hello FastMCP!'); 2 + 2")
                print(f"   Success: {result.success}")
                print(f"   Result: {result.result}")
                print(f"   Stdout: {result.stdout}")
                if not result.success:
                    print(f"   Error: {result.error}")
                print()

            # Test 2: Error handling
            print("2. Testing error handling...")
            async with McpPythonExecutionEnvironment() as env:
                result = await env.execute("print(undefined_variable)")
                print(f"   Success: {result.success}")
                print(f"   Error: {result.error}")
                print()

            # Test 3: Global variables
            print("3. Testing with global variables...")
            async with McpPythonExecutionEnvironment() as env:
                result = await env.execute(
                    "print(f'x={x}, y={y}'); x * y", global_vars={"x": 10, "y": 20}
                )
                print(f"   Success: {result.success}")
                print(f"   Result: {result.result}")
                print(f"   Stdout: {result.stdout}")
                print()

            print("✅ All tests completed!")

        except Exception as e:  # noqa: BLE001
            print(f"❌ Test failed with exception: {e}")
            import traceback

            traceback.print_exc()

    asyncio.run(test())
