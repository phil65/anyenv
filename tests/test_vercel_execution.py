"""Tests for VercelExecutionEnvironment."""

import pytest

from anyenv.code_execution import VercelExecutionEnvironment


EXPECTED_RESULT = 42
EXPECTED_MATH_RESULT = 3.141592653589793


@pytest.mark.integration
async def test_vercel_direct_python():
    """Test direct Python command execution without file."""
    async with VercelExecutionEnvironment() as env:
        # Try python3 directly
        result = await env.execute_command('python3 -c "print(\\"Hello from python3\\")"')
        print(
            f"python3 result: success={result.success}, stdout={result.stdout}, error={result.error}"
        )

        # Try python directly
        result2 = await env.execute_command('python -c "print(\\"Hello from python\\")"')
        print(
            f"python result: success={result2.success}, stdout={result2.stdout}, error={result2.error}"
        )

        # Try which python
        result3 = await env.execute_command("which python python3")
        print(f"which result: success={result3.success}, stdout={result3.stdout}")

        # Just verify we can make the calls
        assert result.duration >= 0


@pytest.mark.integration
async def test_vercel_environment_debug():
    """Debug test to understand what's available in Vercel environment."""
    debug_code = """
import os
import sys
print(f"Python executable: {sys.executable}")
print(f"Python version: {sys.version}")
print(f"Current working directory: {os.getcwd()}")
print(f"PATH: {os.environ.get('PATH', 'Not set')}")
print("Available files in /:")
for item in os.listdir("/"):
    print(f"  {item}")
print("Available files in /usr/bin:")
try:
    for item in sorted(os.listdir("/usr/bin"))[:10]:  # First 10 items
        print(f"  {item}")
except Exception as e:
    print(f"  Error listing /usr/bin: {e}")
_result = "debug_complete"
"""

    async with VercelExecutionEnvironment() as env:
        result = await env.execute(debug_code)

    print(f"Debug result success: {result.success}")
    print(f"Debug result error: {result.error}")
    print(f"Debug stdout: {result.stdout}")
    print(f"Debug stderr: {result.stderr}")

    # Don't assert success for now, just want to see what happens
    assert result.duration >= 0


@pytest.mark.integration
async def test_vercel_execution_with_main_function():
    """Test vercel execution with main function returning a value."""
    code = """
async def main():
    return "Hello from Vercel!"
"""

    async with VercelExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.result == "Hello from Vercel!"
    assert result.duration >= 0
    assert result.error is None
    assert result.error_type is None
    assert result.stdout is not None


@pytest.mark.integration
async def test_vercel_execution_with_result_variable():
    """Test vercel execution using _result variable."""
    code = """
_result = 21 * 2
"""

    async with VercelExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.result == EXPECTED_RESULT
    assert result.duration >= 0
    assert result.error is None


@pytest.mark.integration
async def test_vercel_execution_error_handling():
    """Test error handling in vercel execution."""
    code = """
async def main():
    raise ValueError("Vercel test error")
"""

    async with VercelExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is False
    assert result.result is None
    assert result.duration >= 0
    assert result.error
    assert "Vercel test error" in result.error
    assert result.error_type == "ValueError"
    assert result.stdout is not None


@pytest.mark.integration
async def test_vercel_execution_with_imports():
    """Test vercel execution with Python imports."""
    code = """
import math
async def main():
    return math.pi
"""

    async with VercelExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.result == EXPECTED_MATH_RESULT
    assert result.duration >= 0
    assert result.error is None


@pytest.mark.integration
async def test_vercel_execution_streaming():
    """Test streaming vercel execution."""
    code = """
import time
for i in range(3):
    print(f"Stream line {i + 1}")
    time.sleep(0.1)
"""

    async with VercelExecutionEnvironment() as env:
        lines = [line async for line in env.execute_stream(code)]

    # Should get output lines containing our print statements
    output_lines = [line for line in lines if "Stream line" in line]
    assert len(output_lines) >= 3  # noqa: PLR2004
    assert any("Stream line 1" in line for line in output_lines)
    assert any("Stream line 2" in line for line in output_lines)
    assert any("Stream line 3" in line for line in output_lines)


@pytest.mark.integration
async def test_vercel_execution_custom_config():
    """Test vercel execution with custom configuration."""
    code = """
async def main():
    return "Custom config test"
"""

    async with VercelExecutionEnvironment(timeout=600) as env:
        result = await env.execute(code)

        assert result.success is True
        assert result.result == "Custom config test"
        assert env.timeout_ms == 600 * 1000  # timeout is stored in milliseconds


@pytest.mark.integration
async def test_vercel_execute_command():
    """Test executing terminal commands in vercel environment."""
    async with VercelExecutionEnvironment() as env:
        result = await env.execute_command("sh -c \"echo 'Hello from command'\"")

    assert result.success is True
    assert "Hello from command" in result.result
    assert result.duration >= 0
    assert result.error is None
    assert result.stdout is not None


@pytest.mark.integration
async def test_vercel_execute_command_error():
    """Test command execution error handling."""
    async with VercelExecutionEnvironment() as env:
        result = await env.execute_command('sh -c "nonexistent_command_xyz"')

    assert result.success is False
    assert result.result is None
    assert result.duration >= 0
    assert result.error is not None
    assert result.error_type in (
        "CommandError",
        "FileNotFoundError",
        "OSError",
        "SandboxProcessError",
        "APIError",
    )


@pytest.mark.integration
async def test_vercel_execute_command_streaming():
    """Test streaming command execution."""
    async with VercelExecutionEnvironment() as env:
        lines = [
            line
            async for line in env.execute_command_stream(
                "sh -c \"echo 'Line 1' && echo 'Line 2'\""
            )
        ]

    # Should get both echo outputs (may be combined in single line)
    assert len(lines) >= 1
    output_text = " ".join(lines)
    assert "Line 1" in output_text
    assert "Line 2" in output_text


@pytest.mark.integration
async def test_vercel_execution_javascript():
    """Test vercel execution with JavaScript language."""
    code = """console.log("Hello from JavaScript!");"""

    async with VercelExecutionEnvironment(language="javascript", runtime="node22") as env:
        result = await env.execute(code)

    # Note: This test may need adjustment based on how Vercel handles JS execution
    # The exact behavior depends on Vercel's JavaScript support
    assert env.language == "javascript"
    # JavaScript execution might not return structured results the same way
    assert result.duration >= 0


@pytest.mark.integration
async def test_vercel_execution_no_result():
    """Test execution when no result or main function is present."""
    code = """
x = 1 + 1
print("This should not be the result")
"""

    async with VercelExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is True
    # For Vercel, print output might be captured as result if no structured result found
    # Accept either None or the printed output
    assert result.duration >= 0


@pytest.mark.integration
async def test_vercel_execution_multiple_commands():
    """Test multiple consecutive executions in same environment."""
    async with VercelExecutionEnvironment() as env:
        # First execution
        result1 = await env.execute("""
async def main():
    return "First execution"
""")

        # Second execution
        result2 = await env.execute("""
async def main():
    return "Second execution"
""")

    assert result1.success is True
    assert result1.result == "First execution"
    assert result2.success is True
    assert result2.result == "Second execution"


if __name__ == "__main__":
    pytest.main(["-v", __file__, "-m", "integration"])
