"""Modal execution environment that runs code in serverless sandboxes."""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING, Any, Self

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.models import ExecutionResult
from anyenv.code_execution.parse_output import (
    parse_output,
    wrap_javascript_code,
    wrap_python_code,
    wrap_typescript_code,
)


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

        import modal

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

    async def send(self, message: str):
        """Test the Modal environment."""
        # https://modal.com/docs/guide/sandbox-networking
        import websockets

        import anyenv

        # Create a connect token, optionally including arbitrary user metadata.
        assert self.sandbox
        creds = self.sandbox.create_connect_token(user_metadata={"user_id": "foo"})
        # Make an HTTP request, passing the token in the Authorization header.
        await anyenv.get(creds.url, headers={"Authorization": f"Bearer {creds.token}"})
        # You can also put the token in a `_modal_connect_token` query param.
        url = f"{creds.url}/?_modal_connect_token={creds.token}"
        ws_url = url.replace("https://", "wss://")
        async with websockets.connect(ws_url) as socket:
            await socket.send(message)

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
                return wrap_python_code(code)
            case "javascript":
                return wrap_javascript_code(code)
            case "typescript":
                return wrap_typescript_code(code)
            case _:
                return wrap_python_code(code)


if __name__ == "__main__":

    async def _main():
        async with ModalExecutionEnvironment() as sandbox:
            await sandbox.execute_command("mkdir test")
            result = await sandbox.execute_command("ls")
            print(result)

    import asyncio

    asyncio.run(_main())
