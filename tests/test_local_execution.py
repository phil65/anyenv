"""Tests for LocalExecutionEnvironment."""

import pytest

from anyenv.code_execution import LocalExecutionEnvironment


EXPECTED_RESULT = 84


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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


@pytest.mark.asyncio
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
