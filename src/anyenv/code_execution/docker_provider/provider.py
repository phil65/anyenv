"""Docker execution environment that runs code in isolated containers."""

from __future__ import annotations

import contextlib
import shutil
import tempfile
import time
from typing import TYPE_CHECKING, Self

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.models import ExecutionResult
from anyenv.code_execution.parse_output import parse_output, wrap_code


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
        self.language: Language = language
        self.container: DockerContainer | None = None
        self.host_workdir: str | None = None

    async def __aenter__(self) -> Self:
        from testcontainers.core.container import DockerContainer

        await super().__aenter__()
        self.host_workdir = tempfile.mkdtemp()  # Create temp dir on host for shared fs
        self.container = DockerContainer(self.image).with_volume_mapping(
            self.host_workdir, "/workspace", "rw"
        )

        install_commands: list[str] = []  # Build install commands
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
            cmd = ["sh", "-c", full_command]
            self.container = self.container.with_command(cmd)
            if self.server_info:
                self.container = self.container.with_kwargs(network_mode="host")
        else:
            cmd = ["sh", "-c", "sleep infinity"]  # Just start the container for execution
            self.container = self.container.with_command(cmd)

        self.container.start()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        if self.container:  # Cleanup container
            with contextlib.suppress(Exception):
                self.container.stop()
        if self.host_workdir:  # Cleanup host working directory
            with contextlib.suppress(Exception):
                shutil.rmtree(self.host_workdir)
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
        if not self.container:
            error_msg = "Docker environment not properly initialized"
            raise RuntimeError(error_msg)
        if not self.host_workdir:
            error_msg = "Host working directory not initialized"
            raise RuntimeError(error_msg)
        # Write code directly to shared filesystem
        wrapped_code = wrap_code(code, self.language)
        # Use simple script names that match get_execution_command expectations
        script_extensions = {"python": ".py", "javascript": ".js", "typescript": ".ts"}
        ext = script_extensions.get(self.language, ".py")
        host_script_path = f"{self.host_workdir}/script{ext}"
        try:
            with open(host_script_path, "w") as f:  # noqa: PTH123
                f.write(wrapped_code)
            command = get_execution_command(self.language)
            result = self.container.exec(command)  # Execute the script
            duration = time.time() - start_time
            output = result.output.decode() if result.output else ""
            execution_result, error_info = parse_output(output)
            if result.exit_code == 0 and error_info is None:
                return ExecutionResult(
                    result=execution_result,
                    duration=duration,
                    success=True,
                    exit_code=result.exit_code,
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
                exit_code=result.exit_code,
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
            wrapped_code = wrap_code(code, self.language)
            # Use simple script names that match get_execution_command expectations
            script_extensions = {
                "python": ".py",
                "javascript": ".js",
                "typescript": ".ts",
            }
            ext = script_extensions.get(self.language, ".py")
            host_script_path = f"{self.host_workdir}/script{ext}"
            with open(host_script_path, "w") as f:  # noqa: PTH123
                f.write(wrapped_code)
            command = get_execution_command(self.language)
            docker_container = self.container.get_wrapped_container()
            result = docker_container.exec_run(command, stream=True)
            for chunk in result.output:  # Stream output line by line
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

            if self.dependencies:  # Install deps first if needed (output -> /dev/null)
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
                            exit_code=install_result.exit_code,
                            stdout="",
                            stderr=install_result.output.decode()
                            if install_result.output
                            else "",
                        )

            # Execute the command cleanly (no dependency installation output)
            # Run in /workspace directory to match execute_command_stream behavior
            full_command = f"sh -c 'cd /workspace && {command}'"
            result = self.container.exec(full_command)
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
                exit_code=result.exit_code,
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
            for chunk in result.output:  # Stream output line by line
                if isinstance(chunk, bytes):
                    chunk = chunk.decode()
                for line in chunk.split("\n"):
                    if line.strip():  # Only yield non-empty lines
                        yield line

        except Exception as e:  # noqa: BLE001
            yield f"ERROR: {e}"


def get_execution_command(language: Language) -> str:
    """Get the appropriate execution command based on language."""
    match language:
        case "python":
            return "sh -c 'cd /workspace && python script.py'"
        case "javascript":
            return "sh -c 'cd /workspace && node script.js'"
        case "typescript":
            return "sh -c 'cd /workspace && npx ts-node script.ts'"
        case _:
            return "sh -c 'cd /workspace && python script.py'"


if __name__ == "__main__":
    import asyncio

    async def main():
        """Example."""
        async with DockerExecutionEnvironment() as provider:
            await provider.execute_command("mkdir test")
            async for line in provider.execute_command_stream("ls"):
                print(line)

    asyncio.run(main())
