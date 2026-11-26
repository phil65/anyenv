"""Tests for anyenv.processes."""

from __future__ import annotations

import asyncio
import os
import signal
import subprocess
import sys
import textwrap

import pytest

from anyenv.processes import create_process, create_shell_process, hard_kill


pytestmark = pytest.mark.skipif(sys.platform == "win32", reason="process groups are Unix")

IGNORE_TERM = textwrap.dedent(
    """
    import signal, time
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    print("ready", flush=True)
    time.sleep(30)
    """
)


def test_hard_kill_spares_caller_sharing_the_process_group():
    """A child in the caller's process group must not take the caller down with it."""
    script = textwrap.dedent(
        """
        import asyncio
        from anyenv.processes import create_process, hard_kill

        async def main():
            proc = await create_process("sleep", "30")
            await hard_kill(proc, graceful_timeout=2)
            print("alive", proc.returncode, flush=True)

        asyncio.run(main())
        """
    )
    # Own session, so a regression kills only this helper, not pytest.
    result = subprocess.run(
        [sys.executable, "-c", script],
        capture_output=True,
        text=True,
        timeout=30,
        start_new_session=True,
        check=False,
    )
    assert result.returncode == 0, (result.returncode, result.stderr)
    assert result.stdout.split() == ["alive", str(-signal.SIGTERM)]


# The children below get their own session: a regression must not SIGKILL pytest.


async def test_hard_kill_terminates_gracefully_first(tmp_path):
    """SIGTERM comes first, so the process can clean up."""
    marker = tmp_path / "terminated"
    script = textwrap.dedent(
        f"""
        import signal, sys, time
        def on_term(*_):
            open({str(marker)!r}, "w").close()
            sys.exit(0)
        signal.signal(signal.SIGTERM, on_term)
        print("ready", flush=True)
        time.sleep(30)
        """
    )
    proc = await create_process(sys.executable, "-c", script, stdout="pipe", start_new_session=True)
    assert proc.stdout
    await proc.stdout.readline()
    await hard_kill(proc, graceful_timeout=5)
    assert marker.exists()
    assert proc.returncode == 0


async def test_hard_kill_kills_when_term_is_ignored():
    """After graceful_timeout, SIGKILL follows."""
    proc = await create_process(
        sys.executable, "-c", IGNORE_TERM, stdout="pipe", start_new_session=True
    )
    assert proc.stdout
    await proc.stdout.readline()
    await hard_kill(proc, graceful_timeout=0.2)
    assert proc.returncode == -signal.SIGKILL


async def _gone(pid: int) -> bool:
    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        await asyncio.sleep(0.05)
    return False


async def test_hard_kill_kills_own_process_group():
    """A group leader's children die with it, even if they ignore SIGTERM."""
    child = f"{sys.executable} -c '{IGNORE_TERM}'"
    proc = await create_shell_process(
        f"{child} & echo $!; wait", stdout="pipe", start_new_session=True
    )
    assert proc.stdout
    grandchild = int(await proc.stdout.readline())
    await hard_kill(proc, graceful_timeout=0.5)
    assert await _gone(grandchild)
