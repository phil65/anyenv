"""Docker execution environment that runs code in isolated containers."""

from __future__ import annotations

import contextlib
import tempfile
import time
from typing import TYPE_CHECKING, Self

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.models import ExecutionResult
from anyenv.code_execution.parse_output import parse_output


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager
    from types import TracebackType

    from fsspec.implementations.dirfs import DirFileSystem
    from testcontainers.core.container import DockerContainer

    from anyenv.code_execution.models import Language, ServerInfo


class DockerExecutionEnvironment(ExecutionEnvironment):
    """Executes code in a Docker container with HTTP tool callbacks."""

    def __init__(
        self,
        lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
        dependencies: list[str] | None = None,
        image: str = "python:3.13-slim",
        timeout: float = 60.0,
        language: Language = "python",
    ) -> None:
        """Initialize Docker environment.

        Args:
            lifespan_handler: Async context manager for tool server (optional)
            dependencies: List of packages to install (pip for Python, npm for JS/TS)
            image: Docker image to use
            timeout: Execution timeout in seconds
            language: Programming language to use
        """
        super().__init__(lifespan_handler=lifespan_handler, dependencies=dependencies)
        self.image = image
        self.timeout = timeout
        self.language = language
        self.container: DockerContainer | None = None
        self.host_workdir: str | None = None

    async def __aenter__(self) -> Self:
        # Start tool server via base class
        await super().__aenter__()

        # Create temporary directory on host for shared filesystem
        self.host_workdir = tempfile.mkdtemp()

        # Create and setup Docker container
        from testcontainers.core.container import DockerContainer

        self.container = DockerContainer(self.image).with_volume_mapping(
            self.host_workdir, "/workspace", "rw"
        )

        # Build install commands
        install_commands = []
        if self.server_info:
            install_commands.append("pip install httpx")
        if self.dependencies:
            deps_str = " ".join(self.dependencies)
            match self.language:
                case "python":
                    install_commands.append(f"pip install {deps_str}")
                case "javascript" | "typescript":
                    install_commands.append(f"npm install {deps_str}")

        if install_commands:
            full_command = " && ".join(install_commands) + " && sleep infinity"
            self.container = self.container.with_command([
                "sh",
                "-c",
                full_command,
            ])
            if self.server_info:
                self.container = self.container.with_kwargs(network_mode="host")
        else:
            # Just start the container for simple execution
            self.container = self.container.with_command([
                "sh",
                "-c",
                "sleep infinity",
            ])

        self.container.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        # Cleanup container
        if self.container:
            with contextlib.suppress(Exception):
                self.container.stop()

        # Cleanup host working directory
        if self.host_workdir:
            import shutil

            with contextlib.suppress(Exception):
                shutil.rmtree(self.host_workdir)

        # Cleanup server via base class
        await super().__aexit__(exc_type, exc_val, exc_tb)

    def get_fs(self) -> DirFileSystem:
        """Return a DirFileSystem instance for the shared host directory."""
        from fsspec.implementations.dirfs import DirFileSystem
        from morefs.asyn_local import AsyncLocalFileSystem

        if not self.host_workdir:
            msg = "Docker environment not started"
            raise RuntimeError(msg)

        return DirFileSystem(path=self.host_workdir, fs=AsyncLocalFileSystem())

    async def execute(self, code: str) -> ExecutionResult:
        """Execute code in Docker container."""
        start_time = time.time()

        try:
            if not self.container:
                error_msg = "Docker environment not properly initialized"
                raise RuntimeError(error_msg)  # noqa: TRY301

            if not self.host_workdir:
                error_msg = "Host working directory not initialized"
                raise RuntimeError(error_msg)  # noqa: TRY301

            # Write code directly to shared filesystem
            wrapped_code = self._wrap_code_for_docker(code)
            script_extension = {
                "python": ".py",
                "javascript": ".js",
                "typescript": ".ts",
            }.get(self.language, ".py")

            script_path = f"{self.host_workdir}/script{script_extension}"
            with open(script_path, "w") as f:  # noqa: PTH123
                f.write(wrapped_code)

            command = self._get_execution_command()
            result = self.container.exec(command)  # Execute the script
            duration = time.time() - start_time
            # Parse output
            execution_result, error_info = parse_output(
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
                return "sh -c 'cd /workspace && python script.py'"
            case "javascript":
                return "sh -c 'cd /workspace && node script.js'"
            case "typescript":
                return "sh -c 'cd /workspace && npx ts-node script.ts'"
            case _:
                return "sh -c 'cd /workspace && python script.py'"

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
        print("__RESULT__", json.dumps(execution_result, default=str))
    except Exception as e:
        error_result = {{
            "success": False,
            "error": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc()
        }}
        print("__RESULT__", json.dumps(error_result, default=str))
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
        print("__RESULT__", json.dumps(execution_result, default=str))
    except Exception as e:
        error_result = {{
            "success": False,
            "error": str(e),
            "type": type(e).__name__,
            "traceback": traceback.format_exc()
        }}
        print("__RESULT__", json.dumps(error_result, default=str))
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
    console.log('__RESULT__', JSON.stringify(result));
}}).catch(error => {{
    const errorResult = {{
        success: false,
        error: error.message,
        type: error.name,
        traceback: error.stack
    }};
    console.log('__RESULT__', JSON.stringify(errorResult));
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
    console.log('__RESULT__', JSON.stringify(result));
}}).catch(error => {{
    const errorResult = {{
        success: false,
        error: error.message,
        type: error.name,
        traceback: error.stack
    }};
    console.log('__RESULT__', JSON.stringify(errorResult));
}});
"""  # noqa: E501

    async def execute_stream(self, code: str) -> AsyncIterator[str]:
        """Execute code in Docker container and stream output line by line.

        Args:
            code: Code to execute

        Yields:
            Lines of output as they are produced
        """
        try:
            if not self.container:
                error_msg = "Docker environment not properly initialized"
                raise RuntimeError(error_msg)  # noqa: TRY301

            if not self.host_workdir:
                error_msg = "Host working directory not initialized"
                raise RuntimeError(error_msg)  # noqa: TRY301

            # Write code directly to shared filesystem
            wrapped_code = self._wrap_code_for_docker(code)
            script_extension = {
                "python": ".py",
                "javascript": ".js",
                "typescript": ".ts",
            }.get(self.language, ".py")

            script_path = f"{self.host_workdir}/script{script_extension}"
            with open(script_path, "w") as f:  # noqa: PTH123
                f.write(wrapped_code)

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
            if not self.container:
                error_msg = "Docker environment not properly initialized"
                raise RuntimeError(error_msg)  # noqa: TRY301

            # Install dependencies first if needed (output goes to /dev/null)
            if self.dependencies:
                deps_str = " ".join(self.dependencies)
                if self.language == "python":
                    install_cmd = f"pip install {deps_str} > /dev/null 2>&1"
                elif self.language in ("javascript", "typescript"):
                    install_cmd = f"npm install {deps_str} > /dev/null 2>&1"
                else:
                    install_cmd = None

                if install_cmd:
                    install_result = self.container.exec(["sh", "-c", install_cmd])
                    if install_result.exit_code != 0:
                        error_msg = f"Failed to install dependencies: {self.dependencies}"
                        return ExecutionResult(
                            result=None,
                            duration=time.time() - start_time,
                            success=False,
                            error=error_msg,
                            error_type="DependencyError",
                            stdout="",
                            stderr=install_result.output.decode()
                            if install_result.output
                            else "",
                        )

            # Execute the command cleanly (no dependency installation output)
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
        """Execute a shell command and stream output line by line.

        Args:
            command: Shell command to execute

        Yields:
            Lines of output as they are produced
        """
        try:
            if not self.container:
                error_msg = "Docker environment not properly initialized"
                raise RuntimeError(error_msg)  # noqa: TRY301

            # Execute command in /workspace directory with streaming
            full_command = f"sh -c 'cd /workspace && {command}'"
            docker_container = self.container.get_wrapped_container()
            result = docker_container.exec_run(full_command, stream=True)

            # Stream output line by line
            for chunk in result.output:
                if isinstance(chunk, bytes):
                    chunk = chunk.decode()
                for line in chunk.split("\n"):
                    if line.strip():  # Only yield non-empty lines
                        yield line

        except Exception as e:  # noqa: BLE001
            yield f"ERROR: {e}"
