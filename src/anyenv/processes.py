"""Process ceation utilities."""

from __future__ import annotations

import asyncio
import sys
from typing import TYPE_CHECKING, Literal


if TYPE_CHECKING:
    from asyncio.subprocess import Process
    import os


Mode = Literal["pipe", "stdout", "devnull"]

MAP: dict[Mode, int] = {
    "pipe": asyncio.subprocess.PIPE,
    "stdout": asyncio.subprocess.STDOUT,
    "devnull": asyncio.subprocess.DEVNULL,
}


async def create_process(
    command: str | os.PathLike[str],
    *args: str | os.PathLike[str],
    stdin: Mode | None = None,
    stdout: Mode | None = None,
    stderr: Mode | None = None,
    limit: int = 10 * 1024 * 1024,
    env: dict[str, str] | None = None,
    cwd: str | os.PathLike[str] | None = None,
    start_new_session: bool = False,
) -> Process:
    """Small create_subprocess_exec wrapper."""
    return await asyncio.create_subprocess_exec(
        command,
        *args,
        stdin=MAP[stdin] if stdin else None,
        stdout=MAP[stdout] if stdout else None,
        stderr=MAP[stderr] if stderr else None,
        limit=limit,
        cwd=cwd,
        env=env,
        start_new_session=start_new_session,
    )


async def create_shell_process(
    command: str,
    stdin: Mode | None = None,
    stdout: Mode | None = None,
    stderr: Mode | None = None,
    limit: int = 10 * 1024 * 1024,
    cwd: str | os.PathLike[str] | None = None,
    env: dict[str, str] | None = None,
    start_new_session: bool = False,
) -> Process:
    """Small create_subprocess_shell wrapper."""
    return await asyncio.create_subprocess_shell(
        command,
        stdin=MAP[stdin] if stdin else None,
        stdout=MAP[stdout] if stdout else None,
        stderr=MAP[stderr] if stderr else None,
        limit=limit,
        cwd=cwd,
        env=env,
        start_new_session=start_new_session,
    )


async def hard_kill(
    process: Process,
    *,
    graceful_timeout: float = 5.0,
    force_timeout: float = 2.0,
) -> None:
    """Kill a process with graceful termination followed by force kill if needed.

    Args:
        process: The subprocess to terminate
        graceful_timeout: Timeout for graceful termination (default: 5.0s)
        force_timeout: Timeout for force kill (default: 2.0s)

    This function handles cross-platform process termination:
    - Windows: Uses terminate() then kill() as fallback
    - Unix: Uses process group kill to terminate child processes too
    """
    if process.returncode is not None:
        # Process already terminated
        return

    try:
        if sys.platform == "win32":
            # On Windows, terminate the process directly
            process.terminate()
            try:
                # Wait with timeout, then force kill if needed
                await asyncio.wait_for(process.wait(), timeout=graceful_timeout)
            except TimeoutError:
                # Force kill if graceful termination failed
                process.kill()
                await asyncio.wait_for(process.wait(), timeout=force_timeout)
        else:
            # On Unix-like systems, kill entire process group to handle children
            import os
            import signal

            try:
                os.killpg(os.getpgid(process.pid), signal.SIGKILL)
                await asyncio.wait_for(process.wait(), timeout=force_timeout)
            except ProcessLookupError:
                # Process group doesn't exist, try direct kill
                process.kill()
                await asyncio.wait_for(process.wait(), timeout=force_timeout)

    except (TimeoutError, ProcessLookupError, OSError):
        # Process already dead or force kill timed out
        pass
