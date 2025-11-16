"""Process ceation utilities."""

from __future__ import annotations

import asyncio
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
    )


async def create_shell_process(
    command: str,
    stdin: Mode | None = None,
    stdout: Mode | None = None,
    stderr: Mode | None = None,
    limit: int = 10 * 1024 * 1024,
    cwd: str | os.PathLike[str] | None = None,
    env: dict[str, str] | None = None,
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
    )
