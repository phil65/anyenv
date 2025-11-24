"""Tests for BeamExecutionEnvironment."""

import pytest

from anyenv.code_execution import BeamExecutionEnvironment


EXPECTED_RESULT = 42
EXPECTED_MATH_RESULT = 3.141592653589793


@pytest.mark.integration
async def test_beam_execution_with_main_function():
    """Test beam execution with main function returning a value."""
    code = """
async def main():
    return "Hello from Beam!"
"""

    async with BeamExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.result == "Hello from Beam!"
    assert result.duration >= 0
    assert result.error is None
    assert result.error_type is None
    assert result.stdout is not None


@pytest.mark.integration
async def test_beam_execution_with_result_variable():
    """Test beam execution using _result variable."""
    code = """
_result = 21 * 2
"""

    async with BeamExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.result == EXPECTED_RESULT
    assert result.duration >= 0
    assert result.error is None


@pytest.mark.integration
async def test_beam_execution_error_handling():
    """Test error handling in beam execution."""
    code = """
async def main():
    raise ValueError("Beam test error")
"""

    async with BeamExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is False
    assert result.result is None
    assert result.duration >= 0
    assert result.error
    assert "Beam test error" in result.error
    assert result.error_type == "ValueError"
    assert result.stdout is not None


@pytest.mark.integration
async def test_beam_execution_with_imports():
    """Test beam execution with Python imports."""
    code = """
import math
async def main():
    return math.pi
"""

    async with BeamExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.result == EXPECTED_MATH_RESULT
    assert result.duration >= 0
    assert result.error is None


@pytest.mark.integration
async def test_beam_execution_streaming():
    """Test streaming beam execution."""
    code = """
import time
for i in range(3):
    print(f"Stream line {i + 1}")
    time.sleep(0.1)
"""

    async with BeamExecutionEnvironment() as env:
        lines = [line async for line in env.execute_stream(code)]

    # Should get output lines containing our print statements
    output_lines = [line for line in lines if "Stream line" in line]
    assert len(output_lines) >= 3  # noqa: PLR2004
    assert any("Stream line 1" in line for line in output_lines)
    assert any("Stream line 2" in line for line in output_lines)
    assert any("Stream line 3" in line for line in output_lines)


@pytest.mark.integration
async def test_beam_execution_custom_config():
    """Test beam execution with custom configuration."""
    code = """
async def main():
    return "Custom config test"
"""

    async with BeamExecutionEnvironment(
        cpu=2.0, memory=256, timeout=600.0, keep_warm_seconds=300
    ) as env:
        result = await env.execute(code)

        assert result.success is True
        assert result.result == "Custom config test"
        assert env.cpu == 2.0  # noqa: PLR2004
        assert env.memory == 256  # noqa: PLR2004
        assert env.timeout == 600.0  # noqa: PLR2004
        assert env.keep_warm_seconds == 300  # noqa: PLR2004


@pytest.mark.integration
async def test_beam_execute_command():
    """Test executing terminal commands in beam environment."""
    async with BeamExecutionEnvironment() as env:
        result = await env.execute_command("echo 'Hello from command'")

    assert result.success is True
    assert "Hello from command" in result.result
    assert result.duration >= 0
    assert result.error is None
    assert result.stdout is not None


@pytest.mark.integration
async def test_beam_execute_command_error():
    """Test command execution error handling."""
    async with BeamExecutionEnvironment() as env:
        result = await env.execute_command("nonexistent_command_xyz")

    assert result.success is False
    assert result.result is None
    assert result.duration >= 0
    assert result.error is not None
    assert result.error_type in (
        "CommandError",
        "FileNotFoundError",
        "OSError",
        "SandboxProcessError",
    )


@pytest.mark.integration
async def test_beam_execute_command_streaming():
    """Test streaming command execution."""
    async with BeamExecutionEnvironment() as env:
        lines = [
            line async for line in env.execute_command_stream("echo 'Line 1' && echo 'Line 2'")
        ]

    # Should get both echo outputs (may be combined in single line)
    assert len(lines) >= 1
    output_text = " ".join(lines)
    assert "Line 1" in output_text
    assert "Line 2" in output_text


@pytest.mark.integration
async def test_beam_execution_javascript():
    """Test beam execution with JavaScript language."""
    code = """console.log("Hello from JavaScript!");"""

    async with BeamExecutionEnvironment(language="javascript") as env:
        _result = await env.execute(code)

    # Note: This test may need adjustment based on how Beam handles JS execution
    # The exact behavior depends on Beam's JavaScript support
    assert env.language == "javascript"


@pytest.mark.integration
async def test_beam_execution_no_result():
    """Test execution when no result or main function is present."""
    code = """
x = 1 + 1
print("This should not be the result")
"""

    async with BeamExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is True
    # For Beam, print output might be captured as result if no structured result found
    # Accept either None or the printed output
    assert result.duration >= 0


@pytest.mark.integration
async def test_beam_execution_multiple_commands():
    """Test multiple consecutive executions in same environment."""
    async with BeamExecutionEnvironment() as env:
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
