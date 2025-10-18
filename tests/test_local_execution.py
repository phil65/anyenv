"""Tests for LocalExecutionEnvironment."""

from anyenv.code_execution import LocalExecutionEnvironment


EXPECTED_RESULT = 84


async def test_local_execution_with_main_function():
    """Test execution with main function returning a value."""
    code = """
async def main():
    return "Hello from local execution!"
"""

    async with LocalExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.result == "Hello from local execution!"
    assert result.duration >= 0
    assert result.error is None
    assert result.error_type is None


async def test_local_execution_with_result_variable():
    """Test execution using _result variable."""
    code = """
_result = 42 * 2
"""

    async with LocalExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.result == EXPECTED_RESULT
    assert result.duration >= 0
    assert result.error is None


async def test_local_execution_error_handling():
    """Test error handling in local execution."""
    code = """
async def main():
    raise ValueError("Test error message")
"""

    async with LocalExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is False
    assert result.result is None
    assert result.duration >= 0
    assert "Test error message" in result.error
    assert result.error_type == "ValueError"


async def test_local_execution_no_result():
    """Test execution when no result or main function is present."""
    code = """
x = 1 + 1
print("This should not be the result")
"""

    async with LocalExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.result is None
    assert result.duration >= 0
    assert result.error is None


async def test_local_execution_streaming():
    """Test streaming execution with print statements."""
    code = """
import time
import asyncio

async def main():
    print("Starting execution")
    await asyncio.sleep(0.1)
    print("Middle of execution")
    await asyncio.sleep(0.1)
    print("Ending execution")
    return "Stream test complete"
"""

    async with LocalExecutionEnvironment() as env:
        output_lines = [line async for line in env.execute_stream(code)]

    # Check that we got the expected output lines
    min_expected_lines = 3
    assert len(output_lines) >= min_expected_lines
    assert any("Starting execution" in line for line in output_lines)
    assert any("Middle of execution" in line for line in output_lines)
    assert any("Ending execution" in line for line in output_lines)
    assert any("Result: Stream test complete" in line for line in output_lines)
