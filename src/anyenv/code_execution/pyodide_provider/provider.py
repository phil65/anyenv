"""Pyodide execution environment using Deno subprocess with JSON-RPC protocol."""

from __future__ import annotations

import asyncio
import contextlib
import json
from pathlib import Path
import shutil
import time
from typing import TYPE_CHECKING, Any, Self

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.events import (
    OutputEvent,
    ProcessCompletedEvent,
    ProcessErrorEvent,
    ProcessStartedEvent,
)
from anyenv.code_execution.models import ExecutionResult
from anyenv.code_execution.pyodide_provider.filesystem import PyodideFS
from anyenv.processes import create_process


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager
    from types import TracebackType

    from anyenv.code_execution.events import ExecutionEvent
    from anyenv.code_execution.models import ServerInfo
    from anyenv.code_execution.pyodide_provider.filesystem import PyodideMethod


# Path to the TypeScript server relative to this file
SERVER_SCRIPT = Path(__file__).parent / "pyodide_server.ts"


def _build_permission_flag(flag: str, value: bool | list[str]) -> str | None:
    """Build a Deno permission flag string."""
    if value is True:
        return flag
    if isinstance(value, list) and value:
        return f"{flag}={','.join(value)}"
    return None


class PyodideExecutionEnvironment(ExecutionEnvironment):
    """Execute Python code in a sandboxed Pyodide/WASM environment via Deno.

    This environment provides:
    - Secure sandboxed execution (Deno + WASM isolation)
    - Persistent state within a session (no serialization needed)
    - Configurable permissions for network, filesystem, etc.
    - Auto-installation of pure Python packages via micropip

    Limitations:
    - Only pure Python packages work (no C extensions)
    - No real shell command support (WASM limitation)
    - ~2-3s startup time for Pyodide initialization
    """

    def __init__(
        self,
        lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
        dependencies: list[str] | None = None,
        *,
        timeout: float = 30.0,
        startup_timeout: float = 60.0,
        allow_net: bool | list[str] = True,
        allow_read: bool | list[str] = False,
        allow_write: bool | list[str] = False,
        allow_env: bool | list[str] = False,
        allow_run: bool | list[str] = False,
        allow_ffi: bool | list[str] = False,
        deno_executable: str | None = None,
    ) -> None:
        """Initialize Pyodide environment.

        Args:
            lifespan_handler: Async context manager for tool server (optional)
            dependencies: List of Python packages to pre-install via micropip
            timeout: Execution timeout in seconds
            startup_timeout: Timeout for Pyodide initialization
            allow_net: Network access (True=all, list=specific hosts, False=none)
            allow_read: File read access
            allow_write: File write access
            allow_env: Environment variable access
            allow_run: Subprocess execution (limited in WASM)
            allow_ffi: Foreign function interface access
            deno_executable: Path to deno executable (auto-detected if None)
        """
        super().__init__(lifespan_handler=lifespan_handler, dependencies=dependencies)
        self.timeout = timeout
        self.startup_timeout = startup_timeout
        self.allow_net = allow_net
        self.allow_read = allow_read
        self.allow_write = allow_write
        self.allow_env = allow_env
        self.allow_run = allow_run
        self.allow_ffi = allow_ffi
        self.deno_executable = deno_executable or shutil.which("deno")

        self._process: asyncio.subprocess.Process | None = None
        self._request_id = 0
        self._lock = asyncio.Lock()

    def _build_command(self) -> list[str]:
        """Build the Deno command with permissions."""
        if not self.deno_executable:
            msg = "Deno executable not found. Install from https://deno.land"
            raise RuntimeError(msg)

        cmd = [self.deno_executable, "run"]

        # Build permission flags
        permission_defs = [
            ("--allow-net", self.allow_net),
            ("--allow-read", self.allow_read),
            ("--allow-write", self.allow_write),
            ("--allow-env", self.allow_env),
            ("--allow-run", self.allow_run),
            ("--allow-ffi", self.allow_ffi),
        ]

        for flag, value in permission_defs:
            perm = _build_permission_flag(flag, value)
            if perm:
                cmd.append(perm)

        # Always need read for node_modules (Pyodide downloads)
        if not self.allow_read:
            cmd.append("--allow-read=node_modules")
        if not self.allow_write:
            cmd.append("--allow-write=node_modules")

        cmd.append("--node-modules-dir=auto")
        cmd.append(str(SERVER_SCRIPT))

        return cmd

    async def __aenter__(self) -> Self:
        """Start the Deno/Pyodide server process."""
        import anyenv

        await super().__aenter__()
        cmd = self._build_command()
        self._process = await create_process(*cmd, stdin="pipe", stdout="pipe", stderr="pipe")
        # Wait for ready signal
        try:
            ready_line = await asyncio.wait_for(self._read_line(), timeout=self.startup_timeout)
            ready_msg = anyenv.load_json(ready_line, return_type=dict)
            if not ready_msg.get("ready"):
                msg = f"Unexpected startup message: {ready_msg}"
                raise RuntimeError(msg)  # noqa: TRY301
        except TimeoutError as e:
            await self._kill_process()
            msg = f"Pyodide initialization timed out after {self.startup_timeout}s"
            raise RuntimeError(msg) from e
        except Exception:
            await self._kill_process()
            raise
        # Pre-install dependencies if specified
        if self.dependencies:
            await self._send_request("install", {"packages": self.dependencies})

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Shutdown the Deno/Pyodide server."""
        if self._process and self._process.returncode is None:
            with contextlib.suppress(Exception):
                await asyncio.wait_for(self._send_request("shutdown", {}), timeout=5.0)
            await self._kill_process()

        await super().__aexit__(exc_type, exc_val, exc_tb)

    async def _kill_process(self) -> None:
        """Forcefully kill the subprocess."""
        if self._process:
            try:
                self._process.terminate()
                await asyncio.wait_for(self._process.wait(), timeout=2.0)
            except TimeoutError:
                self._process.kill()
                await self._process.wait()
            self._process = None

    async def _read_line(self) -> str:
        """Read a single line from stdout."""
        if not self._process or not self._process.stdout:
            msg = "Process not running"
            raise RuntimeError(msg)

        line = await self._process.stdout.readline()
        if not line:
            # Process died - check stderr for error
            if self._process.stderr:
                stderr = await self._process.stderr.read()
                msg = f"Process died unexpectedly: {stderr.decode()}"
                raise RuntimeError(msg)
            msg = "Process died unexpectedly"
            raise RuntimeError(msg)

        return line.decode().strip()

    async def _send_request(self, method: str, params: dict[str, Any]) -> dict[str, Any]:
        """Send a JSON-RPC request and wait for response."""
        import anyenv

        async with self._lock:
            if not self._process or not self._process.stdin:
                msg = "Process not running"
                raise RuntimeError(msg)

            self._request_id += 1
            request = {"id": self._request_id, "method": method, "params": params}
            request_line = anyenv.dump_json(request) + "\n"
            self._process.stdin.write(request_line.encode())  # Send request
            await self._process.stdin.drain()
            response_line = await self._read_line()  # Read response
            response = anyenv.load_json(response_line, return_type=dict)
            if error := response.get("error"):
                msg = f"{error.get('type', 'Error')}: {error.get('message', 'Unknown')}"
                raise RuntimeError(msg)
            return response.get("result", {})  # type: ignore[no-any-return]

    async def _stream_request(
        self,
        method: str,
        params: dict[str, Any],
    ) -> AsyncIterator[dict[str, Any]]:
        """Send a streaming request and yield events."""
        async with self._lock:
            if not self._process or not self._process.stdin:
                msg = "Process not running"
                raise RuntimeError(msg)

            self._request_id += 1
            request_id = self._request_id
            request = {"id": request_id, "method": method, "params": params}
            # Send request
            request_line = json.dumps(request) + "\n"
            self._process.stdin.write(request_line.encode())
            await self._process.stdin.drain()
            # Read events until completion or error
            while True:
                response_line = await self._read_line()
                response = json.loads(response_line)
                if "error" in response:
                    error = response["error"]
                    yield {
                        "type": "error",
                        "error": error.get("message", "Unknown"),
                        "error_type": error.get("type", "Error"),
                    }
                    break
                if "event" in response:
                    event = response["event"]
                    yield event
                    if event.get("type") in ("completed", "error"):
                        break

    async def execute(self, code: str) -> ExecutionResult:
        """Execute Python code in the Pyodide environment."""
        start_time = time.time()
        try:
            callback = self._send_request("execute", {"code": code})
            result = await asyncio.wait_for(callback, timeout=self.timeout)
            return ExecutionResult(
                result=result.get("result"),
                duration=result.get("duration", time.time() - start_time),
                success=result.get("success", False),
                error=result.get("stderr") if not result.get("success") else None,
                error_type="ExecutionError" if not result.get("success") else None,
                stdout=result.get("stdout"),
                stderr=result.get("stderr"),
            )
        except TimeoutError:
            return ExecutionResult(
                result=None,
                duration=time.time() - start_time,
                success=False,
                error=f"Execution timed out after {self.timeout}s",
                error_type="TimeoutError",
            )
        except Exception as e:  # noqa: BLE001
            return ExecutionResult.failed(e, start_time)

    async def stream_code(self, code: str) -> AsyncIterator[ExecutionEvent]:
        """Execute Python code and stream events."""
        process_id = f"pyodide_{self._request_id + 1}"

        try:
            async for event in self._stream_request("stream", {"code": code}):
                event_type = event.get("type")
                pid = event.get("process_id", process_id)

                match event_type:
                    case "started":
                        yield ProcessStartedEvent(
                            process_id=pid,
                            command=f"execute({len(code)} chars)",
                        )
                    case "output":
                        yield OutputEvent(
                            process_id=pid,
                            data=event.get("data", ""),
                            stream=event.get("stream", "stdout"),
                        )
                    case "completed":
                        yield ProcessCompletedEvent(
                            process_id=pid,
                            exit_code=event.get("exit_code", 0),
                            duration=event.get("duration"),
                        )
                    case "error":
                        yield ProcessErrorEvent(
                            process_id=pid,
                            error=event.get("error", "Unknown error"),
                            error_type=event.get("error_type", "ExecutionError"),
                            exit_code=event.get("exit_code", 1),
                        )
        except Exception as e:  # noqa: BLE001
            yield ProcessErrorEvent.failed(e, process_id=process_id)

    async def execute_command(self, command: str) -> ExecutionResult:
        """Execute a shell command (limited support in WASM).

        Note: True shell commands are not supported in Pyodide/WASM.
        This attempts to run the command via Python's subprocess module,
        which has significant limitations in WASM.
        """
        # Wrap command in Python subprocess call
        code = f"""
import subprocess
result = subprocess.run({command!r}, shell=True, capture_output=True, text=True)
print(result.stdout, end='')
if result.stderr:
    import sys
    print(result.stderr, end='', file=sys.stderr)
result.returncode
"""
        result = await self.execute(code)
        # Extract exit code from result if available
        exit_code = result.result if isinstance(result.result, int) else None
        return ExecutionResult(
            result=result.stdout,
            duration=result.duration,
            success=result.success and (exit_code == 0 if exit_code is not None else True),
            error=result.error,
            error_type=result.error_type,
            stdout=result.stdout,
            stderr=result.stderr,
            exit_code=exit_code,
        )

    async def stream_command(self, command: str) -> AsyncIterator[ExecutionEvent]:
        """Stream a shell command (limited support in WASM)."""
        # Delegate to execute_command since streaming shell commands
        # is not really supported in Pyodide
        process_id = f"pyodide_cmd_{self._request_id + 1}"

        yield ProcessStartedEvent(process_id=process_id, command=command)

        try:
            result = await self.execute_command(command)

            if result.stdout:
                yield OutputEvent(process_id=process_id, data=result.stdout, stream="stdout")
            if result.stderr:
                yield OutputEvent(process_id=process_id, data=result.stderr, stream="stderr")

            if result.success:
                yield ProcessCompletedEvent(
                    process_id=process_id,
                    exit_code=result.exit_code or 0,
                    duration=result.duration,
                )
            else:
                yield ProcessErrorEvent(
                    process_id=process_id,
                    error=result.error or "Command failed",
                    error_type=result.error_type or "CommandError",
                    exit_code=result.exit_code,
                )
        except Exception as e:  # noqa: BLE001
            yield ProcessErrorEvent.failed(e, process_id=process_id)

    async def install_packages(self, packages: list[str]) -> None:
        """Install Python packages via micropip.

        Args:
            packages: List of package names to install

        Raises:
            RuntimeError: If installation fails
        """
        await self._send_request("install", {"packages": packages})

    def get_fs(self) -> PyodideFS:
        """Return a PyodideFS instance for the sandbox."""

        async def fs_callback(method: PyodideMethod, params: dict[str, Any]) -> Any:
            """Filesystem-specific callback wrapper."""
            return await self._send_request(method, params)

        return PyodideFS(request_callback=fs_callback)
