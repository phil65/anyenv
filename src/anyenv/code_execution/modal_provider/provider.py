"""Modal execution environment that runs code in serverless sandboxes."""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING, Self

import anyenv
from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.events import (
    OutputEvent,
    ProcessCompletedEvent,
    ProcessErrorEvent,
    ProcessStartedEvent,
)
from anyenv.code_execution.models import ExecutionResult
from anyenv.code_execution.parse_output import (
    get_script_path,
    parse_command,
    parse_output,
    wrap_code,
)


if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Collection
    from contextlib import AbstractAsyncContextManager
    import os
    from types import TracebackType

    import modal
    from modal import App, Image, Sandbox
    from upathtools.filesystems import ModalFS

    from anyenv.code_execution.events import ExecutionEvent
    from anyenv.code_execution.models import Language, ServerInfo


def _get_execution_command(language: Language, script_path: str) -> list[str]:
    """Get execution command based on language."""
    match language:
        case "python":
            return ["python", script_path]
        case "javascript":
            return ["node", script_path]
        case "typescript":
            return ["npx", "ts-node", script_path]
        case _:
            return ["python", script_path]


class ModalExecutionEnvironment(ExecutionEnvironment):
    """Executes code in a Modal serverless sandbox."""

    def __init__(
        self,
        lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
        dependencies: list[str] | None = None,
        app_name: str | None = None,
        image: Image | None = None,
        volumes: dict[
            str | os.PathLike, modal.volume.Volume | modal.cloud_bucket_mount.CloudBucketMount
        ]
        | None = None,
        secrets: Collection[modal.secret.Secret] | None = None,
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
        self.volumes = volumes or {}
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

    def _ensure_initialized(self) -> Sandbox:
        """Validate that the environment is properly initialized.

        Returns:
            The sandbox instance.

        Raises:
            RuntimeError: If environment not entered via async context manager.
        """
        if self.sandbox is None:
            msg = "Modal environment not initialized. Use 'async with' context manager."
            raise RuntimeError(msg)
        return self.sandbox

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
        self.sandbox = await modal.Sandbox.create.aio(
            app=self.app,
            image=self.image,
            timeout=self.timeout,
            workdir=self.workdir,
            volumes=self.volumes,
            secrets=self.secrets,
            cpu=self.cpu,
            memory=self.memory,
            gpu=self.gpu,
            idle_timeout=self.idle_timeout,
        )
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
        creds = await self.sandbox.create_connect_token.aio(user_metadata={"user_id": "foo"})
        # Make an HTTP request, passing the token in the Authorization header.
        await anyenv.get(creds.url, headers={"Authorization": f"Bearer {creds.token}"})
        # You can also put the token in a `_modal_connect_token` query param.
        url = f"{creds.url}/?_modal_connect_token={creds.token}"
        ws_url = url.replace("https://", "wss://")
        async with websockets.connect(ws_url) as socket:
            await socket.send(message)

    def get_fs(self) -> ModalFS:
        """Return a ModalFS instance for the sandbox."""
        from upathtools.filesystems import ModalFS

        sandbox = self._ensure_initialized()
        return ModalFS(sandbox_id=sandbox.object_id)

    async def execute(self, code: str) -> ExecutionResult:
        """Execute code in the Modal sandbox."""
        sandbox = self._ensure_initialized()
        start_time = time.time()
        try:
            # Create temporary script file
            script_content = wrap_code(code, language=self.language)
            script_path = get_script_path(self.language)

            # Write script to sandbox using filesystem API
            with await sandbox.open.aio(script_path, "w") as f:
                await f.write.aio(script_content)

            command = _get_execution_command(self.language, script_path)
            process = await sandbox.exec.aio(*command, timeout=self.timeout)
            await process.wait.aio()
            stdout = await process.stdout.read.aio() if process.stdout else ""
            stderr = await process.stderr.read.aio() if process.stderr else ""
            execution_result, error_info = parse_output(stdout)
            if process.returncode == 0 and error_info is None:
                return ExecutionResult(
                    result=execution_result,
                    duration=time.time() - start_time,
                    success=True,
                    stdout=stdout,
                    exit_code=process.returncode,
                    stderr=stderr,
                )

            return ExecutionResult(
                result=None,
                duration=time.time() - start_time,
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
            return ExecutionResult.failed(e, start_time)

    async def execute_command(self, command: str) -> ExecutionResult:
        """Execute a terminal command in the Modal sandbox."""
        sandbox = self._ensure_initialized()
        parts = parse_command(command)
        start_time = time.time()

        try:
            # Execute command
            process = await sandbox.exec.aio(*parts, timeout=self.timeout)
            await process.wait.aio()

            stdout = await process.stdout.read.aio() if process.stdout else ""
            stderr = await process.stderr.read.aio() if process.stderr else ""
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
            return ExecutionResult.failed(e, start_time)

    async def stream_code(self, code: str) -> AsyncIterator[ExecutionEvent]:
        """Execute code and stream events in the Modal sandbox."""
        sandbox = self._ensure_initialized()
        process_id = f"modal_{id(sandbox)}"
        yield ProcessStartedEvent(process_id=process_id, command=f"execute({len(code)} chars)")

        try:
            script_content = wrap_code(code, language=self.language)
            script_path = get_script_path(self.language)
            with await sandbox.open.aio(script_path, "w") as f:
                await f.write.aio(script_content)
            exec_command = _get_execution_command(self.language, script_path)
            process = await sandbox.exec.aio(*exec_command, timeout=self.timeout)

            async for line in process.stdout:
                yield OutputEvent(process_id=process_id, data=line.rstrip("\n\r"), stream="stdout")

            async for line in process.stderr:
                yield OutputEvent(process_id=process_id, data=line.rstrip("\n\r"), stream="stderr")

            exit_code = await process.wait.aio()
            if exit_code == 0:
                yield ProcessCompletedEvent(process_id=process_id, exit_code=exit_code)
            else:
                yield ProcessErrorEvent(
                    process_id=process_id,
                    error=f"Process exited with code {exit_code}",
                    error_type="ProcessError",
                    exit_code=exit_code,
                )

        except Exception as e:  # noqa: BLE001
            yield ProcessErrorEvent.failed(e, process_id=process_id)

    async def stream_command(self, command: str) -> AsyncIterator[ExecutionEvent]:
        """Execute a terminal command and stream events in the Modal sandbox."""
        sandbox = self._ensure_initialized()
        parts = parse_command(command)
        process_id = f"modal_cmd_{id(sandbox)}"
        yield ProcessStartedEvent(process_id=process_id, command=command)
        try:
            process = await sandbox.exec.aio(*parts, timeout=self.timeout)
            async for line in process.stdout:
                yield OutputEvent(process_id=process_id, data=line.rstrip("\n\r"), stream="stdout")
            async for line in process.stderr:
                yield OutputEvent(process_id=process_id, data=line.rstrip("\n\r"), stream="stderr")

            exit_code = await process.wait.aio()
            if exit_code == 0:
                yield ProcessCompletedEvent(process_id=process_id, exit_code=exit_code)
            else:
                yield ProcessErrorEvent(
                    process_id=process_id,
                    error=f"Command exited with code {exit_code}",
                    error_type="CommandError",
                    exit_code=exit_code,
                )

        except Exception as e:  # noqa: BLE001
            yield ProcessErrorEvent.failed(e, process_id=process_id)


if __name__ == "__main__":

    async def _main() -> None:
        async with ModalExecutionEnvironment() as sandbox:
            await sandbox.execute_command("mkdir test")
            result = await sandbox.execute_command("ls")
            print(result)

    import asyncio

    asyncio.run(_main())
