"""Beam execution environment that runs code in cloud sandboxes."""

from __future__ import annotations

import contextlib
import shlex
import time
from typing import TYPE_CHECKING, Self

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.models import ExecutionResult
from anyenv.code_execution.parse_output import parse_output, wrap_code


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager
    from types import TracebackType

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
    ) -> None:
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
        await super().__aenter__()
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
                    deps = " ".join(self.dependencies)
                    image.add_commands(f"npm install {deps}")
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

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Cleanup sandbox."""
        if self.instance and not self.instance.terminated:
            with contextlib.suppress(Exception):
                self.instance.terminate()
        await super().__aexit__(exc_type, exc_val, exc_tb)

    async def execute(self, code: str) -> ExecutionResult:
        """Execute code in the Beam sandbox."""
        from beam import SandboxProcessResponse

        if not self.instance or not self.instance.ok:
            error_msg = "Beam environment not properly initialized"
            raise RuntimeError(error_msg)

        start_time = time.time()

        try:
            wrapped_code = wrap_code(
                code, "javascript" if self.language == "typescript" else "python"
            )
            response = await asyncio.to_thread(
                self.instance.process.run_code,
                wrapped_code,
                blocking=True,
            )
            duration = time.time() - start_time
            assert isinstance(response, SandboxProcessResponse)
            output = response.result
            result, error_info = parse_output(output)
            success = response.exit_code == 0 and error_info is None

            if success:
                return ExecutionResult(
                    result=result,
                    duration=duration,
                    success=True,
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

    async def execute_command(self, command: str) -> ExecutionResult:
        """Execute a terminal command in the Beam sandbox."""
        if not self.instance or not self.instance.ok:
            error_msg = "Beam environment not properly initialized"
            raise RuntimeError(error_msg)

        start_time = time.time()
        try:
            cmd_parts = shlex.split(command)
            if not cmd_parts:
                msg = "Empty command"
                raise ValueError(msg)  # noqa: TRY301

            process = self.instance.process.exec(*cmd_parts)
            exit_code = await asyncio.to_thread(process.wait)
            output = "\n".join(line.rstrip("\n\r") for line in process.logs)
            success = exit_code == 0
            return ExecutionResult(
                result=output if success else None,
                duration=time.time() - start_time,
                success=success,
                error=output if not success else None,
                error_type="CommandError" if not success else None,
                exit_code=exit_code,
                stdout=output,
                stderr="",  # Beam combines stdout/stderr
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
        """Execute a terminal command and stream output in the Beam sandbox."""
        if not self.instance or not self.instance.ok:
            error_msg = "Beam environment not properly initialized"
            raise RuntimeError(error_msg)

        try:
            cmd_parts = shlex.split(command)
            if not cmd_parts:
                msg = "Empty command"
                raise ValueError(msg)  # noqa: TRY301

            process = self.instance.process.exec(*cmd_parts)
            for line in process.logs:
                yield line.rstrip("\n\r")

            if process.exit_code > 0:  # Check final exit code if available
                yield f"ERROR: Command exited with code {process.exit_code}"

        except Exception as e:  # noqa: BLE001
            yield f"ERROR: {e}"


if __name__ == "__main__":
    import asyncio

    async def main():
        """Example."""
        async with BeamExecutionEnvironment() as provider:
            result = await provider.execute("""
async def main():
    return "Hello from Beam!"
""")
            print(f"Success: {result.success}, Result: {result.result}")

    asyncio.run(main())
