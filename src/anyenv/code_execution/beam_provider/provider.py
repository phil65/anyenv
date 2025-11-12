"""Beam execution environment that runs code in cloud sandboxes."""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING, Any, Self

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.models import ExecutionResult


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager

    from beam import Sandbox, SandboxInstance
    from upathtools.filesystems.beam_fs import BeamFS

    from anyenv.code_execution.models import Language, ServerInfo


class BeamExecutionEnvironment(ExecutionEnvironment):
    """Executes code in a Beam cloud sandbox."""

    def __init__(
        self,
        lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
        dependencies: list[str] | None = None,
        cpu: float | str = 1.0,
        memory: int | str = 128,
        keep_warm_seconds: int = 600,
        timeout: float = 300.0,
        language: Language = "python",
    ):
        """Initialize Beam environment.

        Args:
            lifespan_handler: Async context manager for tool server (optional)
            dependencies: List of packages to install via pip / npm
            cpu: CPU cores allocated to the container
            memory: Memory allocated to the container (MiB or string with units)
            keep_warm_seconds: Seconds to keep sandbox alive (-1 for no timeout)
            timeout: Execution timeout in seconds
            language: Programming language to use
        """
        super().__init__(lifespan_handler=lifespan_handler, dependencies=dependencies)
        self.cpu = cpu
        self.memory = memory
        self.keep_warm_seconds = keep_warm_seconds
        self.timeout = timeout
        self.language = language
        self.sandbox: Sandbox | None = None
        self.instance: SandboxInstance | None = None

    def get_fs(self) -> BeamFS:
        """Return a BeamFS instance for the sandbox."""
        from upathtools.filesystems.beam_fs import BeamFS

        assert self.instance
        return BeamFS(sandbox_id=self.instance.container_id)

    async def __aenter__(self) -> Self:
        """Setup Beam sandbox."""
        # Start tool server via base class
        await super().__aenter__()

        # Configure image based on language
        from beam import Image, Sandbox

        match self.language:
            case "python":
                image = Image(
                    python_version="python3.12",
                    python_packages=self.dependencies,
                )
            case "javascript" | "typescript":
                # Use a Node.js base image for JS/TS
                image = Image(base_image="node:20")
                if self.dependencies:
                    image.add_commands(f"npm install {' '.join(self.dependencies)}")
            case _:
                image = Image(
                    python_version="python3.12",
                    python_packages=self.dependencies,
                )

        self.sandbox = Sandbox(
            cpu=self.cpu,
            memory=self.memory,
            image=image,
            keep_warm_seconds=self.keep_warm_seconds,
        )
        assert self.sandbox
        self.instance = self.sandbox.create()
        assert self.instance
        if not self.instance.ok:
            error_msg = f"Failed to create Beam sandbox: {self.instance.error_msg}"
            raise RuntimeError(error_msg)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Cleanup sandbox."""
        if self.instance and not self.instance.terminated:
            with contextlib.suppress(Exception):
                self.instance.terminate()

        # Cleanup server via base class
        await super().__aexit__(exc_type, exc_val, exc_tb)

    async def execute(self, code: str) -> ExecutionResult:
        """Execute code in the Beam sandbox."""
        from beam import SandboxProcessResponse

        if not self.instance or not self.instance.ok:
            error_msg = "Beam environment not properly initialized"
            raise RuntimeError(error_msg)

        start_time = time.time()

        try:
            # Wrap code to capture result similar to subprocess provider
            wrapped_code = self._wrap_code_for_execution(code)

            # Execute code using Beam's process.run_code() method (blocking)
            # This returns a SandboxProcessResponse with result and exit_code
            response = self.instance.process.run_code(wrapped_code, blocking=True)
            duration = time.time() - start_time
            assert isinstance(response, SandboxProcessResponse)
            output = response.result

            # Parse result from output
            result, error_info = _parse_beam_output(output)
            success = response.exit_code == 0 and error_info is None

            if success:
                return ExecutionResult(
                    result=result,
                    duration=duration,
                    success=True,
                    error=None,
                    error_type=None,
                    stdout=output,
                    stderr="",  # Beam combines stdout/stderr in result
                )
            return ExecutionResult(
                result=None,
                duration=duration,
                success=False,
                error=error_info.get("error", output) if error_info else output,
                error_type=error_info.get("type", "CommandError")
                if error_info
                else "CommandError",
                stdout=output,
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

    async def execute_stream(self, code: str) -> AsyncIterator[str]:
        """Execute code and stream output using Beam's real-time streaming."""
        from beam import SandboxProcess

        if not self.instance or not self.instance.ok:
            error_msg = "Beam environment not properly initialized"
            raise RuntimeError(error_msg)

        try:
            process = self.instance.process.run_code(code, blocking=False)
            assert isinstance(process, SandboxProcess)
            for line in process.logs:
                yield line.rstrip("\n\r")

        except Exception as e:  # noqa: BLE001
            yield f"ERROR: {e}"

    def _wrap_code_for_execution(self, code: str) -> str:
        """Wrap user code for execution with result capture."""
        match self.language:
            case "python":
                return self._wrap_python_code(code)
            case "javascript" | "typescript":
                return self._wrap_javascript_code(code)
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
(async () => {{
    try {{
        const executionResult = await executeMain();
        console.log("__RESULT__", JSON.stringify(executionResult));
    }} catch (error) {{
        const errorResult = {{
            success: false,
            error: error.message,
            type: error.name,
            traceback: error.stack
        }};
        console.log("__RESULT__", JSON.stringify(errorResult));
    }}
}})();
"""

    async def execute_command(self, command: str) -> ExecutionResult:
        """Execute a terminal command in the Beam sandbox."""
        if not self.instance or not self.instance.ok:
            error_msg = "Beam environment not properly initialized"
            raise RuntimeError(error_msg)

        start_time = time.time()

        try:
            # Execute command using Beam's process.exec() method
            # Split command into parts (simple space split for now)
            import shlex

            cmd_parts = shlex.split(command)
            if not cmd_parts:
                msg = "Empty command"
                raise ValueError(msg)  # noqa: TRY301

            process = self.instance.process.exec(*cmd_parts)
            exit_code = process.wait()
            duration = time.time() - start_time
            output_lines = [line.rstrip("\n\r") for line in process.logs]
            output = "\n".join(output_lines)
            success = exit_code == 0

            return ExecutionResult(
                result=output if success else None,
                duration=duration,
                success=success,
                error=output if not success else None,
                error_type="CommandError" if not success else None,
                stdout=output,
                stderr="",  # Beam combines stdout/stderr
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
        """Execute a terminal command and stream output in the Beam sandbox."""
        if not self.instance or not self.instance.ok:
            error_msg = "Beam environment not properly initialized"
            raise RuntimeError(error_msg)

        try:
            # Execute command without blocking (if supported)
            import shlex

            cmd_parts = shlex.split(command)
            if not cmd_parts:
                msg = "Empty command"
                raise ValueError(msg)  # noqa: TRY301

            process = self.instance.process.exec(*cmd_parts)
            # Stream output as it happens
            for line in process.logs:
                yield line.rstrip("\n\r")

            if process.exit_code > 0:  # Check final exit code if available
                yield f"ERROR: Command exited with code {process.exit_code}"

        except Exception as e:  # noqa: BLE001
            yield f"ERROR: {e}"


def _parse_beam_output(output: str) -> tuple[Any, dict[str, Any] | None]:
    """Parse the execution output to extract result and error information."""
    import anyenv

    if not output:
        return None, None

    lines = output.strip().split("\n")

    for line in lines:
        if "__RESULT__" in line:
            try:
                json_part = line.split("__RESULT__", 1)[1].strip()
                result_data = anyenv.load_json(json_part, return_type=dict)

                if result_data.get("success"):
                    return result_data.get("result"), None
                return None, {
                    "error": result_data.get("error"),
                    "type": result_data.get("type"),
                    "traceback": result_data.get("traceback"),
                }
            except (anyenv.JsonLoadError, IndexError, ValueError):
                continue

    # If no structured result found, check for common patterns
    # Look for Python output that might indicate successful execution with no return
    if output.strip() and not any(
        keyword in output.lower() for keyword in ["error", "traceback", "exception"]
    ):
        # If output looks like print statements, return None
        # (successful execution, no result)
        return None, None

    # If we have output but no structured result, it might be an error
    if output.strip():
        return None, {"error": output.strip(), "type": "ExecutionError"}

    return None, None


if __name__ == "__main__":

    async def _main():
        async with BeamExecutionEnvironment() as sandbox:
            await sandbox.execute_command("mkdir test")
            result = await sandbox.execute_command("ls")
            print(result)

    import asyncio

    asyncio.run(_main())
