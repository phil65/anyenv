"""Beam execution environment that runs code in cloud sandboxes."""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING, Self

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.models import ExecutionResult


if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from anyenv.code_execution.models import Language


class BeamExecutionEnvironment(ExecutionEnvironment):
    """Executes code in a Beam cloud sandbox."""

    def __init__(
        self,
        cpu: float | str = 1.0,
        memory: int | str = 128,
        keep_warm_seconds: int = 600,
        timeout: float = 300.0,
        language: Language = "python",
    ):
        """Initialize Beam environment.

        Args:
            cpu: CPU cores allocated to the container
            memory: Memory allocated to the container (MiB or string with units)
            keep_warm_seconds: Seconds to keep sandbox alive (-1 for no timeout)
            timeout: Execution timeout in seconds
            language: Programming language to use
        """
        self.cpu = cpu
        self.memory = memory
        self.keep_warm_seconds = keep_warm_seconds
        self.timeout = timeout
        self.language = language
        self.sandbox = None
        self.instance = None

    async def __aenter__(self) -> Self:
        """Setup Beam sandbox."""
        # Configure image based on language
        from beam import Image, Sandbox

        match self.language:
            case "python":
                image = Image(python_version="python3.12")
            case "javascript" | "typescript":
                # Use a Node.js base image for JS/TS
                image = Image(base_image="node:20")
            case _:
                image = Image(python_version="python3.12")

        self.sandbox = Sandbox(
            cpu=self.cpu,
            memory=self.memory,
            image=image,
            keep_warm_seconds=self.keep_warm_seconds,
        )
        self.instance = self.sandbox.create()

        if not self.instance.ok:
            error_msg = f"Failed to create Beam sandbox: {self.instance.error_msg}"
            raise RuntimeError(error_msg)

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Cleanup sandbox."""
        if self.instance and not self.instance.terminated:
            with contextlib.suppress(Exception):
                self.instance.terminate()

    async def execute(self, code: str) -> ExecutionResult:
        """Execute code in the Beam sandbox."""
        from beam import SandboxProcessResponse

        if not self.instance or not self.instance.ok:
            error_msg = "Beam environment not properly initialized"
            raise RuntimeError(error_msg)

        start_time = time.time()

        try:
            # Execute code using Beam's process.run_code() method (blocking)
            # This returns a SandboxProcessResponse with result and exit_code
            response = self.instance.process.run_code(code, blocking=True)
            duration = time.time() - start_time
            success = response.exit_code == 0
            assert isinstance(response, SandboxProcessResponse)
            output = response.result

            return ExecutionResult(
                result=output if success else None,
                duration=duration,
                success=success,
                error=output if not success else None,
                error_type="CommandError" if not success else None,
                stdout=output,
                stderr="",  # Beam combines stdout/stderr in result
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
