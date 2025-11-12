"""E2B execution environment that runs code in cloud sandboxes."""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING, Self

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.models import ExecutionResult
from anyenv.code_execution.parse_output import parse_output


if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager

    from e2b import AsyncSandbox
    from upathtools.filesystems.e2b_fs import E2BFS

    from anyenv.code_execution.models import Language, ServerInfo


class E2bExecutionEnvironment(ExecutionEnvironment):
    """Executes code in an E2B cloud sandbox."""

    def __init__(
        self,
        lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
        dependencies: list[str] | None = None,
        template: str | None = None,
        timeout: float = 300.0,
        keep_alive: bool = False,
        language: Language = "python",
    ):
        """Initialize E2B environment.

        Args:
            lifespan_handler: Async context manager for tool server (optional)
            dependencies: List of packages to install via pip / npm
            template: E2B template name/ID (uses 'base' if None)
            timeout: Sandbox timeout in seconds
            keep_alive: Keep sandbox running after execution
            language: Programming language to use
        """
        super().__init__(lifespan_handler=lifespan_handler, dependencies=dependencies)
        self.template = template
        self.timeout = timeout
        self.keep_alive = keep_alive
        self.language = language
        self.sandbox: AsyncSandbox | None = None

    async def __aenter__(self) -> Self:
        """Setup E2B sandbox."""
        # Start tool server via base class
        await super().__aenter__()

        # Create sandbox (uses E2B_API_KEY environment variable)
        from e2b import AsyncSandbox

        if self.template:
            self.sandbox = await AsyncSandbox.create(
                template=self.template,
                timeout=int(self.timeout),
            )
        else:
            self.sandbox = await AsyncSandbox.create(timeout=int(self.timeout))

        # Install dependencies if specified
        if self.dependencies:
            deps_str = " ".join(self.dependencies)
            match self.language:
                case "python":
                    install_result = await self.sandbox.commands.run(
                        f"pip install {deps_str}"
                    )
                case "javascript" | "typescript":
                    install_result = await self.sandbox.commands.run(
                        f"npm install {deps_str}"
                    )
                case _:
                    install_result = None

            if install_result and install_result.exit_code != 0:
                # Log warning but don't fail - code might still work
                pass

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Cleanup sandbox."""
        if self.sandbox and not self.keep_alive:
            with contextlib.suppress(Exception):
                await self.sandbox.kill()

        # Cleanup server via base class
        await super().__aexit__(exc_type, exc_val, exc_tb)

    def get_fs(self) -> E2BFS:
        """Return a E2BFs instance for the sandbox."""
        from upathtools.filesystems.e2b_fs import E2BFS

        assert self.sandbox
        return E2BFS(sandbox_id=self.sandbox.sandbox_id)

    async def execute(self, code: str) -> ExecutionResult:
        """Execute code in the E2B sandbox."""
        if not self.sandbox:
            error_msg = "E2B environment not properly initialized"
            raise RuntimeError(error_msg)

        start_time = time.time()

        try:
            # Create a script to execute and capture results
            wrapped_code = self._wrap_code_for_e2b(code)

            # Write the code to a temporary file and execute it
            script_path = self._get_script_path()
            await self.sandbox.files.write(script_path, wrapped_code)

            # Execute the script with language-specific command
            command = self._get_execution_command(script_path)
            result = await self.sandbox.commands.run(command)
            duration = time.time() - start_time

            # Parse the output to extract results
            execution_result, error_info = parse_output(result.stdout)

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
            # Map E2B specific exceptions to our error types
            error_type = type(e).__name__
            error_message = str(e)

            if error_type == "CommandExitException":
                # Check if it's a syntax error based on the error message
                if "SyntaxError:" in error_message:
                    error_type = "SyntaxError"
                elif "IndentationError:" in error_message:
                    error_type = "IndentationError"
                else:
                    error_type = "CommandError"

            return ExecutionResult(
                result=None,
                duration=duration,
                success=False,
                error=str(e),
                error_type=error_type,
            )

    def _get_script_path(self) -> str:
        """Get script path based on language."""
        match self.language:
            case "python":
                return "/tmp/e2b_execution_script.py"
            case "javascript":
                return "/tmp/e2b_execution_script.js"
            case "typescript":
                return "/tmp/e2b_execution_script.ts"
            case _:
                return "/tmp/e2b_execution_script.py"

    def _get_execution_command(self, script_path: str) -> str:
        """Get execution command based on language."""
        match self.language:
            case "python":
                return f"python {script_path}"
            case "javascript":
                return f"node {script_path}"
            case "typescript":
                return f"npx ts-node {script_path}"
            case _:
                return f"python {script_path}"

    def _wrap_code_for_e2b(self, code: str) -> str:
        """Wrap user code for E2B execution with result capture."""
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

    async def execute_command(self, command: str) -> ExecutionResult:
        """Execute a terminal command in the E2B sandbox."""
        if not self.sandbox:
            error_msg = "E2B environment not properly initialized"
            raise RuntimeError(error_msg)

        start_time = time.time()

        try:
            # Execute command using E2B's commands.run() method
            result = await self.sandbox.commands.run(command, timeout=int(self.timeout))
            duration = time.time() - start_time

            success = result.exit_code == 0

            return ExecutionResult(
                result=result.stdout if success else None,
                duration=duration,
                success=success,
                error=result.stderr if not success else None,
                error_type="CommandError" if not success else None,
                stdout=result.stdout,
                stderr=result.stderr,
            )

        except Exception as e:  # noqa: BLE001
            duration = time.time() - start_time
            # Map E2B specific exceptions to our error types
            error_type = type(e).__name__
            error_message = str(e)

            if error_type == "CommandExitException":
                # Check if it's a syntax error based on the error message
                if "SyntaxError:" in error_message:
                    error_type = "SyntaxError"
                elif "IndentationError:" in error_message:
                    error_type = "IndentationError"
                else:
                    error_type = "CommandError"

            return ExecutionResult(
                result=None,
                duration=duration,
                success=False,
                error=str(e),
                error_type=error_type,
            )

    async def execute_command_stream(self, command: str):
        """Execute a terminal command and stream output in the E2B sandbox."""
        if not self.sandbox:
            error_msg = "E2B environment not properly initialized"
            raise RuntimeError(error_msg)

        try:
            # Stream output using E2B's commands.run() with callbacks
            stdout_lines = []
            stderr_lines = []

            def on_stdout(data):
                # E2B passes string data directly to callbacks
                line = data.rstrip("\n\r")
                if line:
                    stdout_lines.append(line)

            def on_stderr(data):
                # E2B passes string data directly to callbacks
                line = data.rstrip("\n\r")
                if line:
                    stderr_lines.append(line)

            # Execute command with streaming callbacks
            result = await self.sandbox.commands.run(
                command,
                timeout=int(self.timeout),
                on_stdout=on_stdout,
                on_stderr=on_stderr,
            )

            # Yield all collected output lines
            for line in stdout_lines:
                yield line
            for line in stderr_lines:
                yield f"STDERR: {line}"

            # Yield final result info
            if result.exit_code != 0:
                yield f"ERROR: Command exited with code {result.exit_code}"

        except Exception as e:  # noqa: BLE001
            yield f"ERROR: {e}"


if __name__ == "__main__":

    async def _main():
        async with E2bExecutionEnvironment() as sandbox:
            await sandbox.execute_command("mkdir test")
            result = await sandbox.execute_command("ls")
            print(result)

    import asyncio

    asyncio.run(_main())
