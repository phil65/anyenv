"""Docker execution environment that runs code in isolated containers."""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING, Any, Self

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.models import ExecutionResult


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager

    from testcontainers.core.container import DockerContainer

    from anyenv.code_execution.models import Language, ServerInfo


class DockerExecutionEnvironment(ExecutionEnvironment):
    """Executes code in a Docker container with HTTP tool callbacks."""

    def __init__(
        self,
        lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
        image: str = "python:3.13-slim",
        timeout: float = 60.0,
        language: Language = "python",
    ):
        """Initialize Docker environment.

        Args:
            lifespan_handler: Async context manager for tool server (optional)
            image: Docker image to use
            timeout: Execution timeout in seconds
            language: Programming language to use
        """
        super().__init__(lifespan_handler=lifespan_handler)
        self.image = image
        self.timeout = timeout
        self.language = language
        self.container: DockerContainer | None = None

    async def __aenter__(self) -> Self:
        # Start tool server via base class
        await super().__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        # Cleanup container
        if self.container:
            with contextlib.suppress(Exception):
                self.container.stop()

        # Cleanup server via base class
        await super().__aexit__(exc_type, exc_val, exc_tb)

    async def execute(self, code: str) -> ExecutionResult:
        """Execute code in Docker container."""
        start_time = time.time()

        try:
            from testcontainers.core.container import DockerContainer

            self.container = DockerContainer(self.image)
            if self.server_info:
                # Install httpx if we have a tool server
                self.container = self.container.with_command([
                    "sh",
                    "-c",
                    "pip install httpx && sleep infinity",
                ]).with_kwargs(network_mode="host")  # Allow access to host for HTTP calls
            else:
                # Just start the container for simple execution
                self.container = self.container.with_command([
                    "sh",
                    "-c",
                    "sleep infinity",
                ])

            self.container.start()
            wrapped_code = self._wrap_code_for_docker(code)  # Create execution script

            # Write code to a temporary file in the container using Python
            self.container.exec("mkdir -p /tmp/anyenv")

            # Use Python to write the file to avoid shell quoting issues
            import base64

            encoded_code = base64.b64encode(wrapped_code.encode()).decode()
            cmd = (
                f'python -c "import base64; '
                f"open('/tmp/anyenv/script.py', 'w').write("
                f"base64.b64decode('{encoded_code}').decode())\""
            )
            self.container.exec(cmd)

            # Execute the script
            command = self._get_execution_command()
            result = self.container.exec(command)
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

    def _get_execution_command(self) -> str:
        """Get the appropriate execution command based on language."""
        match self.language:
            case "python":
                return "python /tmp/anyenv/script.py"
            case "javascript":
                return "node /tmp/anyenv/script.js"
            case "typescript":
                return "npx ts-node /tmp/anyenv/script.ts"
            case _:
                return "python /tmp/anyenv/script.py"

    def _wrap_code_for_docker(self, code: str) -> str:
        """Wrap user code for Docker execution with HTTP tool calls."""
        server_url = self.server_info.url if self.server_info else "http://localhost:8000"

        match self.language:
            case "python":
                return self._wrap_python_code(code, server_url)
            case "javascript":
                return self._wrap_javascript_code(code, server_url)
            case "typescript":
                return self._wrap_typescript_code(code, server_url)
            case _:
                return self._wrap_python_code(code, server_url)

    def _wrap_python_code(self, code: str, server_url: str) -> str:
        """Wrap Python code for execution."""
        if self.server_info:
            # With tool server
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
        # Without tool server
        return f"""
import asyncio
import json
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

    def _wrap_javascript_code(self, code: str, server_url: str) -> str:
        """Wrap JavaScript code for execution."""
        return f"""
const axios = require('axios');

// Simple HTTP proxy for tools
async function httpToolCall(toolName, kwargs) {{
    try {{
        const response = await axios.post(
            `{server_url}/api/tools/${{toolName}}`,
            {{ params: kwargs }}
        );
        if (response.data.error) {{
            throw new Error(`Tool ${{toolName}} failed: ${{response.data.error}}`);
        }}
        return response.data.result;
    }} catch (error) {{
        throw error;
    }}
}}

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
    console.log('__EXECUTION_RESULT__', JSON.stringify(result));
}}).catch(error => {{
    const errorResult = {{
        success: false,
        error: error.message,
        type: error.name,
        traceback: error.stack
    }};
    console.log('__EXECUTION_RESULT__', JSON.stringify(errorResult));
}});
"""

    def _wrap_typescript_code(self, code: str, server_url: str) -> str:
        """Wrap TypeScript code for execution."""
        return f"""
import axios from 'axios';

// Simple HTTP proxy for tools
async function httpToolCall(toolName: string, kwargs: any): Promise<any> {{
    try {{
        const response = await axios.post(
            `{server_url}/api/tools/${{toolName}}`,
            {{ params: kwargs }}
        );
        if (response.data.error) {{
            throw new Error(`Tool ${{toolName}} failed: ${{response.data.error}}`);
        }}
        return response.data.result;
    }} catch (error) {{
        throw error;
    }}
}}

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
    console.log('__EXECUTION_RESULT__', JSON.stringify(result));
}}).catch(error => {{
    const errorResult = {{
        success: false,
        error: error.message,
        type: error.name,
        traceback: error.stack
    }};
    console.log('__EXECUTION_RESULT__', JSON.stringify(errorResult));
}});
"""  # noqa: E501

    def _parse_docker_output(self, output: str) -> tuple[Any, dict | None]:
        """Parse result from Docker container output."""
        import anyenv

        try:
            lines = output.strip().split("\n")
            for line in lines:
                if line.startswith("__EXECUTION_RESULT__"):
                    result_json = line[len("__EXECUTION_RESULT__") :].strip()
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

    async def execute_stream(self, code: str) -> AsyncIterator[str]:
        """Execute code in Docker container and stream output line by line.

        Args:
            code: Code to execute

        Yields:
            Lines of output as they are produced
        """
        try:
            from testcontainers.core.container import DockerContainer

            self.container = DockerContainer(self.image)
            if self.server_info:
                # Install httpx if we have a tool server
                self.container = self.container.with_command([
                    "sh",
                    "-c",
                    "pip install httpx && sleep infinity",
                ]).with_kwargs(network_mode="host")  # Allow access to host for HTTP calls
            else:
                # Just start the container for simple execution
                self.container = self.container.with_command([
                    "sh",
                    "-c",
                    "sleep infinity",
                ])

            self.container.start()
            wrapped_code = self._wrap_code_for_docker(code)  # Create execution script

            # Write code to a temporary file in the container using Python
            self.container.exec("mkdir -p /tmp/anyenv")

            # Use Python to write the file to avoid shell quoting issues
            import base64

            encoded_code = base64.b64encode(wrapped_code.encode()).decode()
            cmd = (
                f'python -c "import base64; '
                f"open('/tmp/anyenv/script.py', 'w').write("
                f"base64.b64decode('{encoded_code}').decode())\""
            )
            self.container.exec(cmd)

            # Execute the script with streaming using underlying docker container
            command = self._get_execution_command()
            docker_container = self.container.get_wrapped_container()
            result = docker_container.exec_run(command, stream=True)

            # Stream output line by line
            for chunk in result.output:
                if isinstance(chunk, bytes):
                    chunk = chunk.decode()
                for line in chunk.split("\n"):
                    if line.strip():  # Only yield non-empty lines
                        yield line

        except Exception as e:  # noqa: BLE001
            yield f"ERROR: {e}"

    async def execute_command(self, command: str) -> ExecutionResult:
        """Execute a terminal command in Docker container and return result."""
        start_time = time.time()

        try:
            from testcontainers.core.container import DockerContainer

            self.container = DockerContainer(self.image)
            self.container = self.container.with_command([
                "sh",
                "-c",
                "sleep infinity",
            ])

            self.container.start()

            # Execute the command directly
            result = self.container.exec(command)
            duration = time.time() - start_time

            stdout = result.output.decode() if result.output else ""
            success = result.exit_code == 0

            return ExecutionResult(
                result=stdout if success else None,
                duration=duration,
                success=success,
                error=stdout
                if not success
                else None,  # Docker exec puts errors in stdout
                error_type="CommandError" if not success else None,
                stdout=stdout,
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

    async def execute_command_stream(self, command: str) -> AsyncIterator[str]:
        """Execute a terminal command in Docker container and stream output line by line.

        Args:
            command: Terminal command to execute

        Yields:
            Lines of output as they are produced
        """
        try:
            from testcontainers.core.container import DockerContainer

            self.container = DockerContainer(self.image)
            self.container = self.container.with_command([
                "sh",
                "-c",
                "sleep infinity",
            ])

            self.container.start()

            # Execute and stream output using underlying docker container
            docker_container = self.container.get_wrapped_container()
            result = docker_container.exec_run(command, stream=True)

            # Stream output line by line
            for chunk in result.output:
                if isinstance(chunk, bytes):
                    chunk = chunk.decode()
                for line in chunk.split("\n"):
                    if line.strip():  # Only yield non-empty lines
                        yield line

        except Exception as e:  # noqa: BLE001
            yield f"ERROR: {e}"
