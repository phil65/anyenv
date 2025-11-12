"""Modal execution environment that runs code in serverless sandboxes."""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING, Any, Self

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.models import ExecutionResult
from anyenv.code_execution.parse_output import parse_output


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager

    from modal import App, Image, Sandbox
    from upathtools.filesystems.modal_fs import ModalFS

    from anyenv.code_execution.models import Language, ServerInfo


class ModalExecutionEnvironment(ExecutionEnvironment):
    """Executes code in a Modal serverless sandbox."""

    def __init__(
        self,
        lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
        dependencies: list[str] | None = None,
        app_name: str | None = None,
        image: Image | None = None,
        volumes: dict[str, Any] | None = None,
        secrets: list[Any] | None = None,
        cpu: float | None = None,
        memory: int | None = None,
        gpu: str | None = None,
        timeout: int = 300,
        idle_timeout: int | None = None,
        workdir: str = "/tmp",
        language: Language = "python",
    ):
        """Initialize Modal sandbox environment.

        Args:
            lifespan_handler: Async context manager for tool server (optional)
            dependencies: List of packages to install via pip / npm
            app_name: Modal app name (creates if missing)
            image: Modal Image object (uses default if None)
            volumes: Dict of mount paths to Modal Volume objects
            secrets: List of Modal Secret objects
            cpu: CPU allocation (cores)
            memory: Memory allocation (MB)
            gpu: GPU type (e.g., "T4", "A100")
            timeout: Maximum sandbox lifetime in seconds
            idle_timeout: Idle timeout in seconds
            workdir: Working directory in sandbox
            language: Programming language to use
        """
        super().__init__(lifespan_handler=lifespan_handler, dependencies=dependencies)
        self.app_name = app_name or "anyenv-execution"
        self.image = image
        self.volumes = volumes
        self.secrets = secrets
        self.cpu = cpu
        self.memory = memory
        self.gpu = gpu
        self.timeout = timeout
        self.idle_timeout = idle_timeout
        self.workdir = workdir
        self.language = language
        self.app: App | None = None
        self.sandbox: Sandbox | None = None

    async def __aenter__(self) -> Self:
        """Setup Modal sandbox."""
        # Start tool server via base class
        await super().__aenter__()

        # Import here to avoid import issues if modal package not installed
        try:
            import modal
        except ImportError as e:
            error_msg = (
                "modal package is required for ModalExecutionEnvironment. "
                "Install it with: pip install modal"
            )
            raise ImportError(error_msg) from e

        # Create or lookup app
        self.app = modal.App.lookup(self.app_name, create_if_missing=True)

        # Use default image if none provided
        if self.image is None:
            match self.language:
                case "python":
                    base_image = modal.Image.debian_slim().pip_install("python", "pip")
                    if self.dependencies:
                        self.image = base_image.pip_install(*self.dependencies)
                    else:
                        self.image = base_image
                case "javascript":
                    self.image = modal.Image.debian_slim().apt_install("nodejs", "npm")
                case "typescript":
                    self.image = (
                        modal.Image.debian_slim()
                        .apt_install("nodejs", "npm")
                        .run_commands("npm install -g typescript ts-node")
                    )
                case _:
                    self.image = modal.Image.debian_slim().pip_install("python", "pip")
        # Create sandbox with configuration
        sandbox_kwargs: dict[str, Any] = {
            "app": self.app,
            "image": self.image,
            "timeout": self.timeout,
            "workdir": self.workdir,
        }

        if self.volumes:
            sandbox_kwargs["volumes"] = self.volumes
        if self.secrets:
            sandbox_kwargs["secrets"] = self.secrets
        if self.cpu is not None:
            sandbox_kwargs["cpu"] = self.cpu
        if self.memory is not None:
            sandbox_kwargs["memory"] = self.memory
        if self.gpu is not None:
            sandbox_kwargs["gpu"] = self.gpu
        if self.idle_timeout is not None:
            sandbox_kwargs["idle_timeout"] = self.idle_timeout

        self.sandbox = modal.Sandbox.create(**sandbox_kwargs)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Cleanup sandbox."""
        if self.sandbox:
            with contextlib.suppress(Exception):
                self.sandbox.terminate()

        # Cleanup server via base class
        await super().__aexit__(exc_type, exc_val, exc_tb)

    def get_fs(self) -> ModalFS:
        """Return a ModalFS instance for the sandbox."""
        from upathtools.filesystems.modal_fs import ModalFS

        assert self.sandbox
        return ModalFS(sandbox_id=self.sandbox.object_id)

    async def execute(self, code: str) -> ExecutionResult:
        """Execute code in the Modal sandbox."""
        if not self.sandbox:
            error_msg = "Modal environment not properly initialized"
            raise RuntimeError(error_msg)

        start_time = time.time()

        try:
            # Create temporary script file
            script_content = self._wrap_code_for_modal(code)
            script_path = self._get_script_path()

            # Write script to sandbox using filesystem API
            with self.sandbox.open(script_path, "w") as f:
                f.write(script_content)

            # Execute the script
            command = self._get_execution_command(script_path)
            process = self.sandbox.exec(*command, timeout=self.timeout)

            # Wait for completion and get output
            process.wait()
            stdout = process.stdout.read() if process.stdout else ""
            stderr = process.stderr.read() if process.stderr else ""

            duration = time.time() - start_time

            # Parse the output to extract results
            execution_result, error_info = parse_output(stdout)

            if process.returncode == 0 and error_info is None:
                return ExecutionResult(
                    result=execution_result,
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
                error_type=error_info.get("type", "ExecutionError")
                if error_info
                else "ExecutionError",
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

    async def execute_stream(self, code: str) -> AsyncIterator[str]:
        """Execute code and stream output line by line."""
        if not self.sandbox:
            error_msg = "Modal environment not properly initialized"
            raise RuntimeError(error_msg)

        try:
            # Create temporary script file
            script_content = self._wrap_code_for_modal(code)
            script_path = self._get_script_path()

            # Write script to sandbox
            with self.sandbox.open(script_path, "w") as f:
                f.write(script_content)

            # Execute the script
            command = self._get_execution_command(script_path)
            process = self.sandbox.exec(*command, timeout=self.timeout)

            # Stream output line by line
            for line in process.stdout:
                yield line.rstrip("\n\r")

            # Wait for completion and check for errors
            process.wait()
            if process.returncode != 0:
                # Stream any stderr content
                for line in process.stderr:
                    yield f"ERROR: {line.rstrip()}"

        except Exception as e:  # noqa: BLE001
            yield f"ERROR: {e}"

    async def execute_command(self, command: str) -> ExecutionResult:
        """Execute a terminal command in the Modal sandbox."""
        if not self.sandbox:
            error_msg = "Modal environment not properly initialized"
            raise RuntimeError(error_msg)

        start_time = time.time()

        try:
            # Parse command into parts
            import shlex

            parts = shlex.split(command)
            if not parts:
                error_msg = "Empty command provided"
                raise ValueError(error_msg)  # noqa: TRY301

            # Execute command
            process = self.sandbox.exec(*parts, timeout=self.timeout)
            process.wait()

            stdout = process.stdout.read() if process.stdout else ""
            stderr = process.stderr.read() if process.stderr else ""

            duration = time.time() - start_time
            success = process.returncode == 0

            return ExecutionResult(
                result=stdout if success else None,
                duration=duration,
                success=success,
                error=stderr if not success else None,
                error_type="CommandError" if not success else None,
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

    async def execute_command_stream(self, command: str) -> AsyncIterator[str]:
        """Execute a terminal command and stream output line by line."""
        if not self.sandbox:
            error_msg = "Modal environment not properly initialized"
            raise RuntimeError(error_msg)

        try:
            # Parse command into parts
            import shlex

            parts = shlex.split(command)
            if not parts:
                yield "ERROR: Empty command provided"
                return

            # Execute command
            process = self.sandbox.exec(*parts, timeout=self.timeout)

            # Stream stdout
            for line in process.stdout:
                yield line.rstrip("\n\r")

            # Wait for completion
            process.wait()

            # Stream stderr if there were errors
            if process.returncode != 0:
                for line in process.stderr:
                    yield f"ERROR: {line.rstrip()}"

        except Exception as e:  # noqa: BLE001
            yield f"ERROR: {e}"

    def _get_script_path(self) -> str:
        """Get script path based on language."""
        match self.language:
            case "python":
                return "/tmp/modal_execution_script.py"
            case "javascript":
                return "/tmp/modal_execution_script.js"
            case "typescript":
                return "/tmp/modal_execution_script.ts"
            case _:
                return "/tmp/modal_execution_script.py"

    def _get_execution_command(self, script_path: str) -> list[str]:
        """Get execution command based on language."""
        match self.language:
            case "python":
                return ["python", script_path]
            case "javascript":
                return ["node", script_path]
            case "typescript":
                return ["npx", "ts-node", script_path]
            case _:
                return ["python", script_path]

    def _wrap_code_for_modal(self, code: str) -> str:
        """Wrap user code for Modal execution with result capture."""
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

    def _wrap_typescript_code(self, code: str) -> str:
        """Wrap TypeScript code for execution."""
        return f"""
// User code
{code}

// Execution wrapper
async function executeMain(): Promise<{{
    result: any;
    success: boolean;
    error?: string;
    type?: string;
    traceback?: string;
}}> {{
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
"""


if __name__ == "__main__":

    async def _main():
        async with ModalExecutionEnvironment() as sandbox:
            await sandbox.execute_command("mkdir test")
            result = await sandbox.execute_command("ls")
            print(result)

    import asyncio

    asyncio.run(_main())
