"""Tests for process management functionality."""

from __future__ import annotations

import sys
import tempfile
from typing import Any

import anyio
import pytest

from anyenv.process_manager import ProcessManager, ProcessOutput


@pytest.fixture
def process_manager():
    """Create a ProcessManager instance for testing."""
    return ProcessManager()


async def test_process_manager_initialization(process_manager: ProcessManager):
    """Test ProcessManager initializes correctly."""
    assert isinstance(process_manager.processes, dict)
    assert isinstance(process_manager.output_tasks, dict)
    assert len(process_manager.processes) == 0


async def test_start_process_success(process_manager: ProcessManager):
    """Test successfully starting a process."""
    process_id = await process_manager.start_process("echo", ["hello"])

    assert process_id.startswith("proc_")
    assert process_id in process_manager.processes
    assert process_id in process_manager.output_tasks

    running_proc = process_manager.processes[process_id]
    assert running_proc.command == "echo"
    assert running_proc.args == ["hello"]

    await process_manager.cleanup()


async def test_start_process_with_options(process_manager: ProcessManager):
    """Test starting a process with environment and working directory."""
    process_id = await process_manager.start_process(
        "echo",
        args=["hello"],
        cwd=tempfile.gettempdir(),
        env={"TEST_VAR": "test_value"},
        output_limit=1024,
    )

    assert process_id in process_manager.processes
    running_proc = process_manager.processes[process_id]
    assert running_proc.command == "echo"

    await process_manager.cleanup()


async def test_start_process_failure(process_manager: ProcessManager):
    """Test handling process creation failure."""
    with pytest.raises(OSError, match="Failed to start process"):
        await process_manager.start_process(
            "nonexistent_command_that_does_not_exist_12345", args=["arg"]
        )


async def test_get_output_success(process_manager: ProcessManager):
    """Test getting process output."""
    process_id = await process_manager.start_process("echo", ["hello"])

    # Wait for process to complete and output to be collected
    await process_manager.wait_for_exit(process_id)
    await anyio.sleep(0.05)  # Small delay for output collection

    output = await process_manager.get_output(process_id)
    assert isinstance(output, ProcessOutput)
    assert "hello" in output.stdout

    await process_manager.cleanup()


async def test_get_output_nonexistent_process(process_manager: ProcessManager):
    """Test getting output for non-existent process."""
    with pytest.raises(ValueError, match="Process nonexistent not found"):
        await process_manager.get_output("nonexistent")


async def test_wait_for_exit(process_manager: ProcessManager):
    """Test waiting for process completion."""
    # Use shell to get specific exit code
    process_id = await process_manager.start_process(
        sys.executable, ["-c", "import sys; sys.exit(42)"]
    )

    exit_code = await process_manager.wait_for_exit(process_id)
    assert exit_code == 42  # noqa: PLR2004

    await process_manager.cleanup()


async def test_kill_process(process_manager: ProcessManager):
    """Test killing a running process."""
    # Start a long-running process
    process_id = await process_manager.start_process("sleep", ["10"])

    running_proc = process_manager.processes[process_id]
    assert await running_proc.is_running()

    await process_manager.kill_process(process_id)

    # Wait a moment for termination
    await anyio.sleep(0.1)
    assert not await running_proc.is_running()

    await process_manager.cleanup()


async def test_kill_nonexistent_process(process_manager: ProcessManager):
    """Test killing non-existent process."""
    with pytest.raises(ValueError, match="Process nonexistent not found"):
        await process_manager.kill_process("nonexistent")


async def test_release_process(process_manager: ProcessManager):
    """Test releasing process resources."""
    process_id = await process_manager.start_process("echo", ["hello"])

    # Verify process is tracked
    assert process_id in process_manager.processes
    assert process_id in process_manager.output_tasks

    await process_manager.release_process(process_id)

    # Verify process is removed
    assert process_id not in process_manager.processes
    assert process_id not in process_manager.output_tasks


async def test_list_processes(process_manager: ProcessManager):
    """Test listing active processes."""
    assert await process_manager.list_processes() == []

    process_id1 = await process_manager.start_process("echo", ["hello"])
    process_id2 = await process_manager.start_process("echo", ["world"])

    processes = await process_manager.list_processes()
    assert len(processes) == 2  # noqa: PLR2004
    assert process_id1 in processes
    assert process_id2 in processes

    await process_manager.cleanup()


async def test_get_process_info(process_manager: ProcessManager):
    """Test getting process information."""
    process_id = await process_manager.start_process("echo", ["arg1"])

    info = await process_manager.get_process_info(process_id)

    assert info["process_id"] == process_id
    assert info["command"] == "echo"
    assert info["args"] == ["arg1"]
    assert "created_at" in info
    assert "is_running" in info

    await process_manager.cleanup()


async def test_cleanup(process_manager: ProcessManager):
    """Test cleaning up all processes."""
    # Start some long-running processes
    await process_manager.start_process("sleep", ["10"])
    await process_manager.start_process("sleep", ["10"])

    # Verify processes exist
    assert len(process_manager.processes) == 2  # noqa: PLR2004

    await process_manager.cleanup()

    # Verify all processes are cleaned up
    assert len(process_manager.processes) == 0
    assert len(process_manager.output_tasks) == 0


async def test_output_truncation(process_manager: ProcessManager):
    """Test output truncation when limit is exceeded."""
    # Generate output larger than limit
    output_limit = 100
    large_output = "x" * 200

    process_id = await process_manager.start_process(
        sys.executable,
        ["-c", f"print('{large_output}')"],
        output_limit=output_limit,
    )

    await process_manager.wait_for_exit(process_id)
    await anyio.sleep(0.05)  # Small delay for output collection

    output = await process_manager.get_output(process_id)
    assert output.truncated
    assert len(output.stdout.encode()) <= output_limit

    await process_manager.cleanup()


async def test_shell_command(process_manager: ProcessManager):
    """Test running a shell command (no args = shell mode)."""
    process_id = await process_manager.start_process("echo hello && echo world")

    await process_manager.wait_for_exit(process_id)
    await anyio.sleep(0.05)

    output = await process_manager.get_output(process_id)
    assert "hello" in output.stdout
    assert "world" in output.stdout

    await process_manager.cleanup()


class TestRunningProcess:
    """Tests for RunningProcess class."""

    async def test_add_output(self, process_manager: ProcessManager):
        """Test adding output to process."""
        process_id = await process_manager.start_process("echo", ["hello"])
        proc = process_manager.processes[process_id]

        # Manually add some output
        proc.add_output(stdout="manual", stderr="error")

        output = proc.get_output()
        assert "manual" in output.stdout
        assert "error" in output.stderr

        await process_manager.cleanup()

    async def test_is_running(self, process_manager: ProcessManager):
        """Test checking if process is running."""
        # Start a long-running process
        process_id = await process_manager.start_process("sleep", ["10"])
        proc = process_manager.processes[process_id]

        assert await proc.is_running()

        await process_manager.kill_process(process_id)
        await anyio.sleep(0.1)

        assert not await proc.is_running()

        await process_manager.cleanup()


class TestProcessOutput:
    """Tests for ProcessOutput class."""

    def test_process_output_creation(self):
        """Test ProcessOutput creation."""
        output = ProcessOutput(
            stdout="hello",
            stderr="error",
            combined="helloerror",
            truncated=True,
            exit_code=0,
        )

        assert output.stdout == "hello"
        assert output.stderr == "error"
        assert output.combined == "helloerror"
        assert output.truncated is True
        assert output.exit_code == 0
        assert output.signal is None


if __name__ == "__main__":
    pytest.main([__file__, "-vv"])


async def _wait_for_output(manager: ProcessManager, process_id: str) -> str:
    for _ in range(100):
        if out := (await manager.get_output(process_id)).stdout:
            return out
        await anyio.sleep(0.05)
    pytest.fail("no output")


async def _gone(pid: int) -> bool:
    import os

    for _ in range(50):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return True
        await anyio.sleep(0.05)
    return False


@pytest.mark.skipif(sys.platform == "win32", reason="process groups are Unix")
async def test_kill_shell_process_kills_its_children(process_manager: ProcessManager):
    """Killing a shell command kills the workload too, not just the shell."""
    script = "import os, time; print(os.getpid(), flush=True); time.sleep(30)"
    process_id = await process_manager.start_process(f'{sys.executable} -c "{script}"; echo done')
    child = int(await _wait_for_output(process_manager, process_id))
    await process_manager.kill_process(process_id)
    assert await _gone(child)
    await process_manager.cleanup()


async def test_utf8_split_across_chunks(process_manager: ProcessManager):
    """Multi-byte characters across an 8 KiB read boundary decode intact."""
    text = "a" * 8191 + "ä" * 10
    script = f"import sys; sys.stdout.buffer.write({text.encode()!r}); sys.stdout.flush()"
    process_id = await process_manager.start_process(sys.executable, ["-c", script])
    await process_manager.wait_for_exit(process_id)
    assert (await process_manager.get_output(process_id)).stdout == text
    await process_manager.cleanup()


def _running(limit: int):
    from types import SimpleNamespace

    from anyenv.process_manager.process import RunningProcess

    process: Any = SimpleNamespace(returncode=None)
    return RunningProcess("p", "cmd", [], process=process, output_limit=limit)


@pytest.mark.parametrize(
    ("stdout", "stderr"),
    [("o" * 90, "e" * 50), ("o" * 200, "e" * 200), ("o" * 10, "e" * 200), ("ö" * 100, "")],
)
def test_truncation_keeps_output_within_limit(stdout: str, stderr: str):
    """Truncation keeps the combined output (in bytes) within the limit."""
    proc = _running(100)
    proc.add_output(stdout=stdout, stderr=stderr)
    out = proc.get_output()
    assert out.truncated
    assert len(out.stdout.encode()) + len(out.stderr.encode()) <= 100  # noqa: PLR2004
    assert stdout.endswith(out.stdout)
    assert stderr.endswith(out.stderr)
    if stderr:
        assert out.stderr  # the tail of stderr survives
