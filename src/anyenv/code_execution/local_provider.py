"""Local execution environment that runs code in the same process."""

from __future__ import annotations

import asyncio
import contextlib
import inspect
import io
import sys
import time
from typing import TYPE_CHECKING, Self

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.models import ExecutionResult


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager

    from anyenv.code_execution.models import ServerInfo


class LocalExecutionEnvironment(ExecutionEnvironment):
    """Executes code in the same process (current behavior)."""

    def __init__(
        self,
        lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
        timeout: float = 30.0,
    ):
        """Initialize local environment.

        Args:
            lifespan_handler: Async context manager for tool server (optional)
            timeout: Execution timeout in seconds
        """
        super().__init__(lifespan_handler=lifespan_handler)
        self.timeout = timeout

    async def __aenter__(self) -> Self:
        # Start tool server via base class
        await super().__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        # Cleanup server via base class
        await super().__aexit__(exc_type, exc_val, exc_tb)

    async def execute(self, code: str) -> ExecutionResult:
        """Execute code directly in current process."""
        start_time = time.time()

        try:
            import asyncio

            namespace = {"__builtins__": __builtins__}
            exec(code, namespace)

            # Try to get result from main() function
            if "main" in namespace and callable(namespace["main"]):
                main_func = namespace["main"]
                if inspect.iscoroutinefunction(main_func):
                    result = await asyncio.wait_for(main_func(), timeout=self.timeout)
                else:
                    # Run sync function with timeout using asyncio
                    result = await asyncio.wait_for(
                        asyncio.to_thread(main_func), timeout=self.timeout
                    )
            else:
                result = namespace.get("_result")

            duration = time.time() - start_time
            return ExecutionResult(result=result, duration=duration, success=True)

        except TimeoutError:
            duration = time.time() - start_time
            return ExecutionResult(
                result=None,
                duration=duration,
                success=False,
                error=f"Execution timed out after {self.timeout} seconds",
                error_type="TimeoutError",
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
        """Execute code and stream output line by line.

        Args:
            code: Python code to execute

        Yields:
            Lines of output as they are produced
        """
        try:
            # Create a queue to capture stdout/stderr
            output_queue: asyncio.Queue[str] = asyncio.Queue()

            # Custom StringIO that writes to both original stdout and our queue
            class StreamCapture(io.StringIO):
                def __init__(self, original_stream, queue: asyncio.Queue[str]):
                    super().__init__()
                    self.original_stream = original_stream
                    self.queue = queue

                def write(self, text: str) -> int:
                    # Write to original stream for normal output
                    result = self.original_stream.write(text)
                    # Also add to queue for streaming (split by lines)
                    if text:
                        lines = text.splitlines(keepends=True)
                        for line in lines:
                            if line.strip():  # Only queue non-empty lines
                                with contextlib.suppress(asyncio.QueueFull):
                                    self.queue.put_nowait(line.rstrip("\n\r"))
                    return result

                def flush(self):
                    return self.original_stream.flush()

            # Set up stdout/stderr capture
            stdout_capture = StreamCapture(sys.stdout, output_queue)
            stderr_capture = StreamCapture(sys.stderr, output_queue)

            # Track if execution is done
            execution_done = False

            async def execute_code():
                nonlocal execution_done
                try:
                    namespace = {"__builtins__": __builtins__}

                    # Redirect stdout/stderr
                    with (
                        contextlib.redirect_stdout(stdout_capture),
                        contextlib.redirect_stderr(stderr_capture),
                    ):
                        exec(code, namespace)

                        # Try to get result from main() function
                        if "main" in namespace and callable(namespace["main"]):
                            main_func = namespace["main"]
                            if inspect.iscoroutinefunction(main_func):
                                result = await asyncio.wait_for(
                                    main_func(), timeout=self.timeout
                                )
                            else:
                                # Run sync function with timeout
                                result = await asyncio.wait_for(
                                    asyncio.to_thread(main_func), timeout=self.timeout
                                )

                            # Print result if it exists
                            if result is not None:
                                print(f"Result: {result}")
                        else:
                            result = namespace.get("_result")
                            if result is not None:
                                print(f"Result: {result}")

                except Exception as e:  # noqa: BLE001
                    # Print error to stderr (which will be captured)
                    print(f"ERROR: {e}", file=sys.stderr)
                finally:
                    execution_done = True
                    # Signal completion
                    with contextlib.suppress(asyncio.QueueFull):
                        output_queue.put_nowait("__EXECUTION_COMPLETE__")

            # Start code execution in background
            execute_task = asyncio.create_task(execute_code())

            # Stream output as it comes
            while True:
                try:
                    # Wait for output with timeout
                    line = await asyncio.wait_for(output_queue.get(), timeout=0.1)

                    if line == "__EXECUTION_COMPLETE__":
                        break

                    yield line

                except TimeoutError:
                    # Check if execution is done
                    if execution_done and output_queue.empty():
                        break
                    continue
                except Exception as e:  # noqa: BLE001
                    yield f"ERROR: {e}"
                    break

            # Wait for execution to complete
            try:
                await execute_task
            except Exception as e:  # noqa: BLE001
                yield f"ERROR: {e}"

        except Exception as e:  # noqa: BLE001
            yield f"ERROR: {e}"

    async def execute_command(self, command: str) -> ExecutionResult:
        """Execute a terminal command and return result with metadata."""
        start_time = time.time()

        try:
            # Execute command using subprocess
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout_data, stderr_data = await asyncio.wait_for(
                process.communicate(), timeout=self.timeout
            )

            duration = time.time() - start_time
            stdout = stdout_data.decode() if stdout_data else ""
            stderr = stderr_data.decode() if stderr_data else ""

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

        except TimeoutError:
            duration = time.time() - start_time
            return ExecutionResult(
                result=None,
                duration=duration,
                success=False,
                error=f"Command timed out after {self.timeout} seconds",
                error_type="TimeoutError",
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
        """Execute a terminal command and stream output line by line.

        Args:
            command: Terminal command to execute

        Yields:
            Lines of output as they are produced
        """
        try:
            # Create subprocess
            process = await asyncio.create_subprocess_shell(
                command,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.STDOUT,  # Merge stderr into stdout
            )

            # Stream output line by line
            if process.stdout is not None:
                while True:
                    try:
                        line = await asyncio.wait_for(
                            process.stdout.readline(), timeout=self.timeout
                        )
                        if not line:
                            break
                        yield line.decode().rstrip("\n\r")
                    except TimeoutError:
                        process.kill()
                        await process.wait()
                        yield f"ERROR: Command timed out after {self.timeout} seconds"
                        break

            # Wait for process to complete
            await process.wait()

        except Exception as e:  # noqa: BLE001
            yield f"ERROR: {e}"
