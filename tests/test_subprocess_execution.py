"""Tests for SubprocessExecutionEnvironment."""

from anyenv.code_execution import SubprocessExecutionEnvironment


EXPECTED_SQRT_RESULT = 4.0
MIN_PYTHON_MAJOR_VERSION = 3


async def test_subprocess_execution_with_main_function():
    """Test subprocess execution with main function returning a value."""
    code = """
async def main():
    return "Hello from subprocess!"
"""

    async with SubprocessExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.result == "Hello from subprocess!"
    assert result.duration >= 0
    assert result.error is None
    assert result.error_type is None
    assert result.stdout is not None
    assert result.stderr is not None


async def test_subprocess_execution_with_result_variable():
    """Test subprocess execution using _result variable."""
    code = """
import math
_result = math.sqrt(16)
"""

    async with SubprocessExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.result == EXPECTED_SQRT_RESULT
    assert result.duration >= 0
    assert result.error is None


async def test_subprocess_execution_error_handling():
    """Test error handling in subprocess execution."""
    code = """
async def main():
    raise RuntimeError("Subprocess test error")
"""

    async with SubprocessExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is False
    assert result.result is None
    assert result.duration >= 0
    assert result.error
    assert "Subprocess test error" in result.error
    assert result.error_type == "RuntimeError"
    assert result.stdout is not None
    assert result.stderr is not None


async def test_subprocess_execution_timeout():
    """Test timeout handling in subprocess execution."""
    code = """
import time
async def main():
    time.sleep(2)  # Sleep longer than timeout
    return "Should not reach here"
"""

    async with SubprocessExecutionEnvironment(timeout=0.5) as env:
        result = await env.execute(code)

    assert result.success is False
    assert result.result is None
    assert result.error
    assert "timed out" in result.error.lower()
    assert result.error_type == "TimeoutError"


async def test_subprocess_execution_custom_python():
    """Test subprocess execution with custom Python executable."""
    code = """
import sys
async def main():
    return sys.version_info.major
"""

    async with SubprocessExecutionEnvironment(executable="python3") as env:
        result = await env.execute(code)

    assert result.success is True
    assert isinstance(result.result, int)
    assert result.result >= MIN_PYTHON_MAJOR_VERSION


async def test_subprocess_execution_streaming():
    """Test streaming subprocess execution."""
    code = """
import time
for i in range(3):
    print(f"Line {i + 1}")
    time.sleep(0.1)
"""

    async with SubprocessExecutionEnvironment() as env:
        lines = [line async for line in env.execute_stream(code)]

    # Should get the three print lines
    output_lines = [line for line in lines if line.startswith("Line")]
    assert len(output_lines) == 3  # noqa: PLR2004
    assert "Line 1" in output_lines[0]
    assert "Line 2" in output_lines[1]
    assert "Line 3" in output_lines[2]
