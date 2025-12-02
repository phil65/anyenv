"""Tests for MockExecutionEnvironment."""

from __future__ import annotations

import pytest

from anyenv.code_execution import MockExecutionEnvironment, MockProcessManager
from anyenv.code_execution.events import OutputEvent, ProcessCompletedEvent, ProcessStartedEvent
from anyenv.code_execution.models import ExecutionResult
from anyenv.process_manager.models import ProcessOutput


@pytest.fixture
def mock_env() -> MockExecutionEnvironment:
    """Create a mock environment with predefined responses."""
    return MockExecutionEnvironment(
        code_results={
            "print(1)": ExecutionResult(
                result=1,
                duration=0.01,
                success=True,
                stdout="1\n",
            ),
            "raise ValueError()": ExecutionResult(
                result=None,
                duration=0.01,
                success=False,
                stderr="ValueError\n",
                exit_code=1,
            ),
        },
        command_results={
            "echo hello": ExecutionResult(
                result=None,
                duration=0.01,
                success=True,
                stdout="hello\n",
                exit_code=0,
            ),
            "ls /nonexistent": ExecutionResult(
                result=None,
                duration=0.01,
                success=False,
                stderr="No such file or directory\n",
                exit_code=2,
            ),
        },
        process_outputs={
            "echo": ProcessOutput(
                stdout="hello world",
                stderr="",
                combined="hello world",
                exit_code=0,
            ),
            "sleep": ProcessOutput(
                stdout="",
                stderr="",
                combined="",
                exit_code=0,
            ),
        },
    )


async def test_execute_returns_predefined_result(mock_env: MockExecutionEnvironment):
    """Test that execute returns the predefined result for matching code."""
    result = await mock_env.execute("print(1)")

    assert result.success is True
    assert result.stdout == "1\n"
    assert result.result == 1


async def test_execute_returns_default_for_unknown_code(mock_env: MockExecutionEnvironment):
    """Test that execute returns default result for unknown code."""
    result = await mock_env.execute("unknown_code()")

    assert result.success is True
    assert result.stdout == ""


async def test_execute_command_returns_predefined_result(mock_env: MockExecutionEnvironment):
    """Test that execute_command returns predefined result."""
    result = await mock_env.execute_command("echo hello")

    assert result.success is True
    assert result.stdout == "hello\n"
    assert result.exit_code == 0


async def test_execute_command_failure(mock_env: MockExecutionEnvironment):
    """Test that execute_command handles failure results."""
    result = await mock_env.execute_command("ls /nonexistent")

    assert result.success is False
    assert result.stderr == "No such file or directory\n"
    assert result.exit_code == 2  # noqa: PLR2004


async def test_stream_code_emits_events(mock_env: MockExecutionEnvironment):
    """Test that stream_code emits proper events."""
    events = [event async for event in mock_env.stream_code("print(1)")]

    assert len(events) == 3  # noqa: PLR2004
    assert isinstance(events[0], ProcessStartedEvent)
    assert events[0].command == "python"

    assert isinstance(events[1], OutputEvent)
    assert events[1].data == "1\n"
    assert events[1].stream == "stdout"

    assert isinstance(events[2], ProcessCompletedEvent)
    assert events[2].exit_code == 0


async def test_stream_code_emits_stderr_for_errors(mock_env: MockExecutionEnvironment):
    """Test that stream_code emits stderr events for failures."""
    events = [event async for event in mock_env.stream_code("raise ValueError()")]

    output_events = [e for e in events if isinstance(e, OutputEvent)]
    assert len(output_events) == 1
    assert output_events[0].stream == "stderr"
    assert output_events[0].data == "ValueError\n"

    completed = [e for e in events if isinstance(e, ProcessCompletedEvent)]
    assert len(completed) == 1
    assert completed[0].exit_code == 1


async def test_stream_command_emits_events(mock_env: MockExecutionEnvironment):
    """Test that stream_command emits proper events."""
    events = [event async for event in mock_env.stream_command("echo hello")]

    assert len(events) == 3  # noqa: PLR2004
    assert isinstance(events[0], ProcessStartedEvent)
    assert events[0].command == "echo hello"

    assert isinstance(events[1], OutputEvent)
    assert events[1].data == "hello\n"

    assert isinstance(events[2], ProcessCompletedEvent)


async def test_process_manager_start_process(mock_env: MockExecutionEnvironment):
    """Test starting a process through process manager."""
    process_id = await mock_env.process_manager.start_process("echo", ["hello", "world"])

    assert process_id.startswith("mock_")
    processes = await mock_env.process_manager.list_processes()
    assert process_id in processes


async def test_process_manager_get_output(mock_env: MockExecutionEnvironment):
    """Test getting output from process manager."""
    process_id = await mock_env.process_manager.start_process("echo", ["test"])
    output = await mock_env.process_manager.get_output(process_id)

    assert output.stdout == "hello world"
    assert output.exit_code == 0


async def test_process_manager_kill_process(mock_env: MockExecutionEnvironment):
    """Test killing a process."""
    process_id = await mock_env.process_manager.start_process("sleep", ["100"])
    await mock_env.process_manager.kill_process(process_id)

    info = await mock_env.process_manager.get_process_info(process_id)
    assert info["is_running"] is False
    assert info["exit_code"] == 130  # SIGINT # noqa: PLR2004


async def test_process_manager_release_process(mock_env: MockExecutionEnvironment):
    """Test releasing a process."""
    process_id = await mock_env.process_manager.start_process("echo")
    await mock_env.process_manager.release_process(process_id)

    processes = await mock_env.process_manager.list_processes()
    assert process_id not in processes


async def test_process_manager_wait_for_exit(mock_env: MockExecutionEnvironment):
    """Test waiting for process exit."""
    process_id = await mock_env.process_manager.start_process("echo")
    exit_code = await mock_env.process_manager.wait_for_exit(process_id)

    assert exit_code == 0
    info = await mock_env.process_manager.get_process_info(process_id)
    assert info["is_running"] is False


async def test_process_manager_get_process_info(mock_env: MockExecutionEnvironment):
    """Test getting process info."""
    process_id = await mock_env.process_manager.start_process(
        "echo",
        args=["hello"],
        cwd="/tmp",
    )
    info = await mock_env.process_manager.get_process_info(process_id)

    assert info["process_id"] == process_id
    assert info["command"] == "echo"
    assert info["args"] == ["hello"]
    assert info["cwd"] == "/tmp"
    assert "created_at" in info


async def test_process_manager_not_found_errors(mock_env: MockExecutionEnvironment):
    """Test that process manager raises errors for unknown processes."""
    with pytest.raises(ValueError, match="not found"):
        await mock_env.process_manager.get_output("nonexistent")

    with pytest.raises(ValueError, match="not found"):
        await mock_env.process_manager.kill_process("nonexistent")

    with pytest.raises(ValueError, match="not found"):
        await mock_env.process_manager.release_process("nonexistent")


async def test_memory_filesystem_operations(mock_env: MockExecutionEnvironment):
    """Test memory filesystem helper methods."""
    await mock_env.set_file_content("/test/file.txt", "hello world")
    content = await mock_env.get_file_content("/test/file.txt")

    assert content == b"hello world"


async def test_memory_filesystem_binary_content(mock_env: MockExecutionEnvironment):
    """Test memory filesystem with binary content."""
    binary_data = b"\x00\x01\x02\x03"
    await mock_env.set_file_content("/binary.bin", binary_data)
    content = await mock_env.get_file_content("/binary.bin")

    assert content == binary_data


async def test_get_fs_returns_memory_filesystem(mock_env: MockExecutionEnvironment):
    """Test that get_fs returns the memory filesystem."""
    fs = mock_env.get_fs()
    await mock_env.set_file_content("/via_helper.txt", "test")

    # Should be the same filesystem
    assert await fs._cat_file("/via_helper.txt") == b"test"


async def test_default_result_configuration():
    """Test configuring custom default result."""
    custom_default = ExecutionResult(
        result="custom",
        duration=1.0,
        success=True,
        stdout="custom output",
    )
    env = MockExecutionEnvironment(default_result=custom_default)

    result = await env.execute("any code")

    assert result.stdout == "custom output"
    assert result.result == "custom"


async def test_mock_process_manager_standalone():
    """Test MockProcessManager can be used standalone."""
    default_output = ProcessOutput(
        stdout="default output",
        stderr="",
        combined="default output",
        exit_code=0,
    )
    manager = MockProcessManager(
        default_output=default_output,
        command_outputs={
            "custom cmd": ProcessOutput(
                stdout="custom",
                stderr="",
                combined="custom",
                exit_code=42,
            ),
        },
    )

    # Test default output
    pid1 = await manager.start_process("unknown")
    output1 = await manager.get_output(pid1)
    assert output1.stdout == "default output"

    # Test custom output
    pid2 = await manager.start_process("custom", ["cmd"])
    output2 = await manager.get_output(pid2)
    assert output2.stdout == "custom"
    assert output2.exit_code == 42  # noqa: PLR2004


async def test_context_manager_protocol(mock_env: MockExecutionEnvironment):
    """Test that MockExecutionEnvironment works as async context manager."""
    async with mock_env as env:
        result = await env.execute("print(1)")
        assert result.stdout == "1\n"
