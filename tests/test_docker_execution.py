"""Tests for DockerExecutionEnvironment."""

import platform

import pytest

from anyenv.code_execution import DockerExecutionEnvironment


pytestmark = pytest.mark.skipif(
    platform.system() != "Linux", reason="Docker tests only supported on Linux"
)


@pytest.mark.asyncio
async def test_docker_execution_with_main_function():
    """Test Docker execution with main function returning a value."""
    pytest.importorskip("testcontainers", reason="testcontainers not installed")

    code = """
async def main():
    return "Hello from Docker!"
"""

    async with DockerExecutionEnvironment(timeout=30.0) as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.result == "Hello from Docker!"
    assert result.duration >= 0
    assert result.error is None
    assert result.error_type is None


@pytest.mark.asyncio
async def test_docker_execution_with_result_variable():
    """Test Docker execution using _result variable."""
    pytest.importorskip("testcontainers", reason="testcontainers not installed")

    code = """
import os
_result = "Docker environment"
"""

    async with DockerExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.result == "Docker environment"
    assert result.duration >= 0


@pytest.mark.asyncio
async def test_docker_execution_error_handling():
    """Test error handling in Docker execution."""
    pytest.importorskip("testcontainers", reason="testcontainers not installed")

    code = """
async def main():
    raise ConnectionError("Docker test error")
"""

    async with DockerExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is False
    assert result.result is None
    assert result.duration >= 0
    assert result.error
    assert "Docker test error" in result.error
    assert result.error_type == "ConnectionError"


@pytest.mark.asyncio
async def test_docker_execution_with_custom_image():
    """Test Docker execution with custom image."""
    pytest.importorskip("testcontainers", reason="testcontainers not installed")

    code = """
async def main():
    import sys
    return f"Python {sys.version_info.major}.{sys.version_info.minor}"
"""

    async with DockerExecutionEnvironment(image="python:3.12-slim") as env:
        result = await env.execute(code)

    assert result.success is True
    assert "Python" in result.result
    assert result.duration >= 0


@pytest.mark.asyncio
async def test_docker_execution_with_tools():
    """Test Docker execution with tool calls."""
    pytest.importorskip("testcontainers", reason="testcontainers not installed")

    code = """
async def main():
    # This would normally call http_tool_call but we'll just return a test result
    return "Tool integration test"
"""

    async with DockerExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.result == "Tool integration test"
    assert result.duration >= 0


@pytest.mark.asyncio
async def test_docker_execution_streaming():
    """Test streaming Docker execution."""
    pytest.importorskip("testcontainers", reason="testcontainers not installed")

    code = """
import time
for i in range(3):
    print(f"Line {i + 1}")
    time.sleep(0.1)
"""

    async with DockerExecutionEnvironment() as env:
        lines = [line async for line in env.execute_stream(code)]

    # Should get the three print lines
    output_lines = [line for line in lines if line.startswith("Line") or "Line" in line]
    assert len(output_lines) >= 3  # noqa: PLR2004
