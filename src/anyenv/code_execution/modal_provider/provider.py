"""Modal execution environment that runs code in serverless sandboxes."""

from __future__ import annotations

import contextlib
import shlex
import time
from typing import TYPE_CHECKING, Any, Self

import anyenv
from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.models import ExecutionResult
from anyenv.code_execution.parse_output import get_script_path, parse_output, wrap_code


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager
    from types import TracebackType

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
    ) -> None:
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
        self.language: Language = language
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

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Cleanup sandbox."""
        if self.sandbox:
            with contextlib.suppress(Exception):
                self.sandbox.terminate()

        # Cleanup server via base class
        await super().__aexit__(exc_type, exc_val, exc_tb)

    async def send(self, message: str) -> None:
        """Test the Modal environment."""
        # https://modal.com/docs/guide/sandbox-networking
        import websockets

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
            script_content = wrap_code(code, language=self.language)
            script_path = get_script_path(self.language)

            # Write script to sandbox using filesystem API
            with self.sandbox.open(script_path, "w") as f:
                f.write(script_content)

            command = self._get_execution_command(script_path)
            process = self.sandbox.exec(*command, timeout=self.timeout)
            process.wait()
            stdout = process.stdout.read() if process.stdout else ""
            stderr = process.stderr.read() if process.stderr else ""
            duration = time.time() - start_time
            execution_result, error_info = parse_output(stdout)
            if process.returncode == 0 and error_info is None:
                return ExecutionResult(
                    result=execution_result,
                    duration=duration,
                    success=True,
                    stdout=stdout,
                    exit_code=process.returncode,
                    stderr=stderr,
                )

            return ExecutionResult(
                result=None,
                duration=duration,
                success=False,
                error=error_info.get("error", stderr) if error_info else stderr,
                exit_code=process.returncode,
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
            script_content = wrap_code(code, language=self.language)
            script_path = get_script_path(self.language)
            with self.sandbox.open(script_path, "w") as f:
                f.write(script_content)

            command = self._get_execution_command(script_path)
            process = self.sandbox.exec(*command, timeout=self.timeout)
            for line in process.stdout:
                yield line.rstrip("\n\r")
            process.wait()
            if process.returncode != 0:
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
            parts = shlex.split(command)
            if not parts:
                error_msg = "Empty command provided"
                raise ValueError(error_msg)  # noqa: TRY301

            # Execute command
            process = self.sandbox.exec(*parts, timeout=self.timeout)
            process.wait()

            stdout = process.stdout.read() if process.stdout else ""
            stderr = process.stderr.read() if process.stderr else ""
            success = process.returncode == 0
            return ExecutionResult(
                result=stdout if success else None,
                duration=time.time() - start_time,
                success=success,
                error=stderr if not success else None,
                exit_code=process.returncode,
                error_type="CommandError" if not success else None,
                stdout=stdout,
                stderr=stderr,
            )

        except Exception as e:  # noqa: BLE001
            return ExecutionResult(
                result=None,
                duration=time.time() - start_time,
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
            parts = shlex.split(command)
            if not parts:
                yield "ERROR: Empty command provided"
                return

            process = self.sandbox.exec(*parts, timeout=self.timeout)
            for line in process.stdout:
                yield line.rstrip("\n\r")
            process.wait()
            if process.returncode != 0:
                for line in process.stderr:
                    yield f"ERROR: {line.rstrip()}"

        except Exception as e:  # noqa: BLE001
            yield f"ERROR: {e}"

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


if __name__ == "__main__":

    async def _main() -> None:
        async with ModalExecutionEnvironment() as sandbox:
            await sandbox.execute_command("mkdir test")
            result = await sandbox.execute_command("ls")
            print(result)

    import asyncio

    asyncio.run(_main())
