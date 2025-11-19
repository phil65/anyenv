"""Beam execution environment that runs code in cloud sandboxes."""

from __future__ import annotations

import asyncio
import contextlib
import shlex
import time
from typing import TYPE_CHECKING, Literal, Self

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.beam_provider.helpers import get_image
from anyenv.code_execution.models import ExecutionResult
from anyenv.code_execution.parse_output import parse_output, wrap_code


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager
    from types import TracebackType

    from beam import SandboxInstance
    from upathtools.filesystems.beam_fs import BeamFS

    from anyenv.code_execution.events import ExecutionEvent
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
        self.language: Language = language
        self.instance: SandboxInstance | None = None

    def get_fs(self) -> BeamFS:
        """Return a BeamFS instance for the sandbox."""
        from upathtools.filesystems.beam_fs import BeamFS

        assert self.instance
        return BeamFS(sandbox_id=self.instance.container_id)

    async def __aenter__(self) -> Self:
        """Setup Beam sandbox."""
        await super().__aenter__()
        from beam import Sandbox

        image = get_image(self.language, self.dependencies)
        sandbox = Sandbox(
            cpu=self.cpu,
            memory=self.memory,
            image=image,
            keep_warm_seconds=self.keep_warm_seconds,
        )
        self.instance = sandbox.create()
        self.validate_instance()
        return self

    def validate_instance(self) -> SandboxInstance:
        """Validate the Beam sandbox instance."""
        if not self.instance or not self.instance.ok:
            error_msg = "Beam environment not properly initialized"
            raise RuntimeError(error_msg)
        return self.instance

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

        self.instance = self.validate_instance()
        start_time = time.time()
        try:
            lang: Literal["python", "javascript", "typescript"] = (
                "javascript" if self.language == "typescript" else "python"
            )
            wrapped_code = wrap_code(code, lang)
            response = await asyncio.to_thread(
                self.instance.process.run_code,
                wrapped_code,
                blocking=True,
            )
            assert isinstance(response, SandboxProcessResponse)
            output = response.result
            result, error_info = parse_output(output)
            success = response.exit_code == 0 and error_info is None

            if success:
                return ExecutionResult(
                    result=result,
                    duration=time.time() - start_time,
                    success=True,
                    stdout=output,
                    stderr="",  # Beam combines stdout/stderr in result
                )
            return ExecutionResult(
                result=None,
                duration=time.time() - start_time,
                success=False,
                error=error_info.get("error", output) if error_info else output,
                error_type=error_info.get("type", "CommandError")
                if error_info
                else "CommandError",
                stdout=output,
                stderr="",
            )

        except Exception as e:  # noqa: BLE001
            return ExecutionResult(
                result=None,
                duration=time.time() - start_time,
                success=False,
                error=str(e),
                error_type=type(e).__name__,
            )

    async def execute_command(self, command: str) -> ExecutionResult:
        """Execute a terminal command in the Beam sandbox."""
        self.instance = self.validate_instance()
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

    async def stream_code(self, code: str) -> AsyncIterator[ExecutionEvent]:
        """Execute code and stream events using Beam's real-time streaming."""
        from beam import SandboxProcess

        from anyenv.code_execution.events import (
            OutputEvent,
            ProcessCompletedEvent,
            ProcessErrorEvent,
            ProcessStartedEvent,
        )

        self.instance = self.validate_instance()
        process_id = f"beam_{id(self.instance)}"

        yield ProcessStartedEvent(
            process_id=process_id, command=f"run_code({len(code)} chars)"
        )

        try:
            lang: Literal["python", "javascript", "typescript"] = (
                "javascript" if self.language == "typescript" else "python"
            )
            wrapped_code = wrap_code(code, lang)
            process = self.instance.process.run_code(wrapped_code, blocking=False)
            assert isinstance(process, SandboxProcess)

            for line in process.logs:
                yield OutputEvent(
                    process_id=process_id, data=line.rstrip("\n\r"), stream="combined"
                )

            exit_code = process.exit_code or 0
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
            yield ProcessErrorEvent(
                process_id=process_id, error=str(e), error_type=type(e).__name__
            )

    async def stream_command(self, command: str) -> AsyncIterator[ExecutionEvent]:
        """Execute a terminal command and stream events in the Beam sandbox."""
        from anyenv.code_execution.events import (
            OutputEvent,
            ProcessCompletedEvent,
            ProcessErrorEvent,
            ProcessStartedEvent,
        )

        self.instance = self.validate_instance()
        process_id = f"beam_cmd_{id(self.instance)}"

        yield ProcessStartedEvent(process_id=process_id, command=command)

        try:
            cmd_parts = shlex.split(command)
            if not cmd_parts:
                yield ProcessErrorEvent(
                    process_id=process_id, error="Empty command", error_type="ValueError"
                )
                return

            process = self.instance.process.exec(*cmd_parts)
            for line in process.logs:
                yield OutputEvent(
                    process_id=process_id, data=line.rstrip("\n\r"), stream="combined"
                )

            exit_code = await asyncio.to_thread(process.wait)
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
            yield ProcessErrorEvent(
                process_id=process_id, error=str(e), error_type=type(e).__name__
            )


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
