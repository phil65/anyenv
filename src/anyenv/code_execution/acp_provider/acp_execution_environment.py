"""ACP-based execution environment using client capabilities."""

from __future__ import annotations

import contextlib
import time
from typing import TYPE_CHECKING
import uuid

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.events import (
    OutputEvent,
    ProcessCompletedEvent,
    ProcessErrorEvent,
    ProcessStartedEvent,
)
from anyenv.code_execution.models import ExecutionResult
from anyenv.code_execution.parse_output import parse_command


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager

    from acp.acp_requests import ACPRequests
    from fsspec.asyn import AsyncFileSystem

    from anyenv.code_execution.events import ExecutionEvent
    from anyenv.code_execution.models import ServerInfo
    from anyenv.process_manager import ProcessManagerProtocol


class ACPExecutionEnvironment(ExecutionEnvironment):
    """Execution environment that delegates to ACP client capabilities.

    Uses the ACP client's filesystem, process management, and code execution
    capabilities to provide a sandboxed execution environment.
    """

    def __init__(
        self,
        fs: AsyncFileSystem,
        requests: ACPRequests,
        lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
        dependencies: list[str] | None = None,
    ) -> None:
        """Initialize ACP execution environment.

        Args:
            fs: ACP filesystem instance
            requests: ACP requests helper for terminal operations
            lifespan_handler: Optional async context manager for tool server
            dependencies: Optional list of dependencies (handled by client)
        """
        super().__init__(lifespan_handler=lifespan_handler, dependencies=dependencies)
        self._fs = fs
        self._requests = requests

    def get_fs(self) -> AsyncFileSystem:
        """Return ACP filesystem instance."""
        return self._fs

    @property
    def process_manager(self) -> ProcessManagerProtocol:
        """Get ACP process manager for terminal operations."""
        if self._process_manager is None:
            from anyenv.code_execution.acp_provider.process_manager import ACPProcessManager

            self._process_manager = ACPProcessManager(self._requests)
        return self._process_manager

    async def execute(self, code: str) -> ExecutionResult:
        """Execute code using ACP client capabilities.

        Args:
            code: Python code to execute

        Returns:
            ExecutionResult with output and metadata
        """
        start_time = time.perf_counter()
        try:
            script_id = str(uuid.uuid4())[:8]
            script_name = f"temp_script_{script_id}.py"
            # Write code to temporary file using ACP filesystem
            self._fs.write_text(script_name, code)
            # Execute using ACP terminal
            create_response = await self._create_terminal(cmd="python", args=[script_name])
            terminal_id = create_response.terminal_id
            exit_result = await self._requests.wait_for_terminal_exit(terminal_id)
            output_response = await self._requests.terminal_output(terminal_id)
            await self._requests.release_terminal(terminal_id)
            with contextlib.suppress(Exception):
                await self._fs._rm(script_name)  # noqa: SLF001

            exit_code = exit_result.exit_code or 0
            duration = time.perf_counter() - start_time
            output = output_response.output or ""
            return ExecutionResult(
                result=output,
                stdout=output,
                success=exit_code == 0,
                exit_code=exit_code,
                error=None if exit_code == 0 else f"Process exited with code {exit_code}",
                duration=duration,
            )

        except Exception as e:  # noqa: BLE001
            return ExecutionResult.failed(e, start_time)

    async def stream_code(self, code: str) -> AsyncIterator[ExecutionEvent]:
        """Execute code and stream events.

        Args:
            code: Python code to execute

        Yields:
            ExecutionEvent objects as they occur
        """
        start_time = time.perf_counter()
        process_id = str(uuid.uuid4())[:8]
        script_name = f"temp_script_{process_id}.py"
        try:
            self._fs.write_text(script_name, code)
            create_response = await self._create_terminal("python", args=[script_name])
            terminal_id = create_response.terminal_id
            yield ProcessStartedEvent(process_id=process_id, command=f"python {script_name}")
            exit_result = await self._requests.wait_for_terminal_exit(terminal_id)
            response = await self._requests.terminal_output(terminal_id)
            await self._requests.release_terminal(terminal_id)
            with contextlib.suppress(Exception):
                await self._fs._rm(script_name)  # noqa: SLF001
            if response.output:
                yield OutputEvent(process_id=process_id, data=response.output, stream="combined")
            exit_code = exit_result.exit_code or 0
            if exit_code == 0:
                yield ProcessCompletedEvent(
                    process_id=process_id,
                    exit_code=exit_code,
                    duration=time.perf_counter() - start_time,
                )
            else:
                yield ProcessErrorEvent(
                    process_id=process_id,
                    error=f"Process exited with code {exit_code}",
                    error_type="ProcessError",
                    exit_code=exit_code,
                )

        except Exception as e:  # noqa: BLE001
            yield ProcessErrorEvent(
                process_id=process_id,
                error=f"Error executing code via ACP: {e}",
                error_type=type(e).__name__,
                exit_code=1,
            )

    async def _create_terminal(self, cmd: str, args: list[str]):
        """Create a terminal session with the given command and arguments."""
        return await self._requests.create_terminal(cmd, args=args, output_byte_limit=1048576)

    async def execute_command(self, command: str) -> ExecutionResult:
        """Execute a terminal command using ACP terminal capabilities.

        Args:
            command: Terminal command to execute

        Returns:
            ExecutionResult with command output and metadata
        """
        parts = parse_command(command)
        cmd = parts[0]
        start_time = time.perf_counter()
        try:
            args = parts[1:] if len(parts) > 1 else []
            create_response = await self._create_terminal(cmd=cmd, args=args)
            terminal_id = create_response.terminal_id
            exit_result = await self._requests.wait_for_terminal_exit(terminal_id)
            output_response = await self._requests.terminal_output(terminal_id)
            await self._requests.release_terminal(terminal_id)
            exit_code = exit_result.exit_code or 0
            duration = time.perf_counter() - start_time
            output = output_response.output or ""
            return ExecutionResult(
                result=output,
                stdout=output,
                stderr=None,
                success=exit_code == 0,
                exit_code=exit_code,
                error=None if exit_code == 0 else f"Command exited with code {exit_code}",
                duration=duration,
            )
        except Exception as e:  # noqa: BLE001
            return ExecutionResult.failed(e, start_time)

    async def stream_command(self, command: str) -> AsyncIterator[ExecutionEvent]:
        """Execute a terminal command and stream events.

        Args:
            command: Terminal command to execute

        Yields:
            ExecutionEvent objects as they occur
        """
        parts = parse_command(command)
        args = parts[1:] if len(parts) > 1 else []
        start_time = time.perf_counter()
        process_id = str(uuid.uuid4())[:8]
        try:
            create_response = await self._create_terminal(cmd=parts[0], args=args)
            terminal_id = create_response.terminal_id
            yield ProcessStartedEvent(process_id=process_id, command=command)
            exit_result = await self._requests.wait_for_terminal_exit(terminal_id)
            response = await self._requests.terminal_output(terminal_id)
            await self._requests.release_terminal(terminal_id)
            if response.output:
                yield OutputEvent(process_id=process_id, data=response.output, stream="combined")
            exit_code = exit_result.exit_code or 0
            if exit_code == 0:
                yield ProcessCompletedEvent(
                    process_id=process_id,
                    exit_code=exit_code,
                    duration=time.perf_counter() - start_time,
                )
            else:
                yield ProcessErrorEvent(
                    process_id=process_id,
                    error=f"Command exited with code {exit_code}",
                    error_type="ProcessError",
                    exit_code=exit_code,
                )

        except Exception as e:  # noqa: BLE001
            yield ProcessErrorEvent(
                process_id=process_id,
                error=f"Error executing command via ACP: {e}",
                error_type=type(e).__name__,
                exit_code=1,
            )

    # -------------------------------------------------------------------------
    # Polling-based streaming implementation (experimental)
    # -------------------------------------------------------------------------
    # ACP's terminal/output can be polled to get incremental output before
    # the command completes. This provides true streaming at the cost of
    # polling overhead. Uncomment and use if real-time output is needed.
    # -------------------------------------------------------------------------

    # async def _stream_terminal_polling(
    #     self,
    #     terminal_id: str,
    #     process_id: str,
    #     poll_interval: float = 0.1,
    # ) -> AsyncIterator[ExecutionEvent]:
    #     """Poll terminal output and yield events as new data arrives.
    #
    #     Args:
    #         terminal_id: ACP terminal ID
    #         process_id: Process ID for events
    #         poll_interval: Seconds between polls (default 0.1s)
    #
    #     Yields:
    #         OutputEvent for new output chunks
    #         ProcessCompletedEvent or ProcessErrorEvent when done
    #     """
    #     last_output_len = 0
    #     start_time = time.perf_counter()
    #
    #     while True:
    #         response = await self._requests.terminal_output(terminal_id)
    #
    #         # Yield new output if any
    #         current_output = response.output or ""
    #         if len(current_output) > last_output_len:
    #             new_chunk = current_output[last_output_len:]
    #             yield OutputEvent(
    #                 process_id=process_id,
    #                 data=new_chunk,
    #                 stream="combined",
    #             )
    #             last_output_len = len(current_output)
    #
    #         # Check if process has exited
    #         if response.exit_status is not None:
    #             duration = time.perf_counter() - start_time
    #             exit_code = response.exit_status.exit_code or 0
    #
    #             if exit_code == 0:
    #                 yield ProcessCompletedEvent(
    #                     process_id=process_id,
    #                     exit_code=exit_code,
    #                     duration=duration,
    #                 )
    #             else:
    #                 yield ProcessErrorEvent(
    #                     process_id=process_id,
    #                     error=f"Process exited with code {exit_code}",
    #                     error_type="ProcessError",
    #                     exit_code=exit_code,
    #                 )
    #             return
    #
    #         await asyncio.sleep(poll_interval)
    #
    # async def stream_command_polling(
    #     self,
    #     command: str,
    #     poll_interval: float = 0.1,
    # ) -> AsyncIterator[ExecutionEvent]:
    #     """Execute command with polling-based streaming.
    #
    #     Unlike stream_command(), this polls terminal/output periodically
    #     to provide real-time output streaming.
    #
    #     Args:
    #         command: Terminal command to execute
    #         poll_interval: Seconds between output polls
    #
    #     Yields:
    #         ExecutionEvent objects as they occur
    #     """
    #     process_id = str(uuid.uuid4())[:8]
    #
    #     try:
    #         parts = command.split()
    #         if not parts:
    #             yield ProcessErrorEvent(
    #                 process_id=process_id,
    #                 error="Empty command provided",
    #                 error_type="ValueError",
    #                 exit_code=1,
    #             )
    #             return
    #
    #         cmd = parts[0]
    #         args = parts[1:] if len(parts) > 1 else []
    #
    #         create_response = await self._create_terminal(cmd, args)
    #         terminal_id = create_response.terminal_id
    #
    #         yield ProcessStartedEvent(
    #             process_id=process_id,
    #             command=command,
    #             pid=None,
    #         )
    #
    #         # Stream output via polling
    #         async for event in self._stream_terminal_polling(
    #             terminal_id, process_id, poll_interval
    #         ):
    #             yield event
    #
    #         await self._requests.release_terminal(terminal_id)
    #
    #     except Exception as e:
    #         yield ProcessErrorEvent(
    #             process_id=process_id,
    #             error=f"Error executing command via ACP: {e}",
    #             error_type=type(e).__name__,
    #             exit_code=1,
    #         )
    #
    # async def stream_code_polling(
    #     self,
    #     code: str,
    #     poll_interval: float = 0.1,
    # ) -> AsyncIterator[ExecutionEvent]:
    #     """Execute code with polling-based streaming.
    #
    #     Unlike stream_code(), this polls terminal/output periodically
    #     to provide real-time output streaming.
    #
    #     Args:
    #         code: Python code to execute
    #         poll_interval: Seconds between output polls
    #
    #     Yields:
    #         ExecutionEvent objects as they occur
    #     """
    #     process_id = str(uuid.uuid4())[:8]
    #     script_name = f"temp_script_{process_id}.py"
    #     try:
    #         self._fs.write_text(script_name, code)
    #         create_response = await self._create_terminal("python", [script_name])
    #         terminal_id = create_response.terminal_id
    #         yield ProcessStartedEvent(
    #             process_id=process_id,
    #             command=f"python {script_name}",
    #             pid=None,
    #         )
    #         # Stream output via polling
    #         async for event in self._stream_terminal_polling(
    #             terminal_id, process_id, poll_interval
    #         ):
    #             yield event
    #
    #         await self._requests.release_terminal(terminal_id)
    #         with contextlib.suppress(Exception):
    #             await self._fs._rm(script_name)
    #
    #     except Exception as e:
    #         yield ProcessErrorEvent(
    #             process_id=process_id,
    #             error=f"Error executing code via ACP: {e}",
    #             error_type=type(e).__name__,
    #             exit_code=1,
    #         )
