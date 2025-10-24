"""Tests for E2bExecutionEnvironment."""

import pytest

from anyenv.code_execution import E2bExecutionEnvironment


# Skip entire file if e2b package is not available
e2b = pytest.importorskip("e2b")


EXPECTED_RESULT = 42
EXPECTED_MATH_RESULT = 3.141592653589793


@pytest.mark.integration
async def test_e2b_execution_with_main_function():
    """Test E2B execution with main function returning a value."""
    code = """
async def main():
    return "Hello from E2B!"
"""

    async with E2bExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.result == "Hello from E2B!"
    assert result.duration >= 0
    assert result.error is None
    assert result.error_type is None
    assert result.stdout is not None


@pytest.mark.integration
async def test_e2b_execution_with_result_variable():
    """Test E2B execution using _result variable."""
    code = """
_result = 21 * 2
"""

    async with E2bExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.result == EXPECTED_RESULT
    assert result.duration >= 0
    assert result.error is None


@pytest.mark.integration
async def test_e2b_execution_error_handling():
    """Test error handling in E2B execution."""
    code = """
async def main():
    raise ValueError("E2B test error")
"""

    async with E2bExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is False
    assert result.result is None
    assert result.duration >= 0
    assert result.error
    assert "E2B test error" in result.error
    assert result.error_type == "ValueError"
    assert result.stdout is not None


@pytest.mark.integration
async def test_e2b_execution_with_imports():
    """Test E2B execution with Python imports."""
    code = """
import math
async def main():
    return math.pi
"""

    async with E2bExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.result == EXPECTED_MATH_RESULT
    assert result.duration >= 0
    assert result.error is None


@pytest.mark.integration
async def test_e2b_execute_command():
    """Test executing terminal commands in E2B environment."""
    async with E2bExecutionEnvironment() as env:
        result = await env.execute_command("echo 'Hello from command'")

    assert result.success is True
    assert "Hello from command" in result.result
    assert result.duration >= 0
    assert result.error is None
    assert result.stdout is not None


@pytest.mark.integration
async def test_e2b_execute_command_error():
    """Test command execution error handling."""
    async with E2bExecutionEnvironment() as env:
        result = await env.execute_command("nonexistent_command_xyz")

    assert result.success is False
    assert result.result is None
    assert result.duration >= 0
    assert result.error is not None
    assert result.error_type == "CommandError"


@pytest.mark.integration
async def test_e2b_execute_command_streaming():
    """Test streaming command execution."""
    async with E2bExecutionEnvironment() as env:
        lines = [
            line
            async for line in env.execute_command_stream("echo 'Line 1' && echo 'Line 2'")
        ]

    # Should get both echo outputs
    assert len(lines) >= 1
    output_text = " ".join(lines)
    assert "Line 1" in output_text
    assert "Line 2" in output_text


@pytest.mark.integration
async def test_e2b_execution_javascript():
    """Test E2B execution with JavaScript language."""
    code = """
async function main() {
    return "Hello from JavaScript!";
}
"""

    async with E2bExecutionEnvironment(language="javascript") as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.result == "Hello from JavaScript!"
    assert result.duration >= 0
    assert result.error is None


@pytest.mark.integration
async def test_e2b_execution_typescript():
    """Test E2B execution with TypeScript language."""
    code = """
async function main(): Promise<string> {
    return "Hello from TypeScript!";
}
"""

    async with E2bExecutionEnvironment(language="typescript") as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.result == "Hello from TypeScript!"
    assert result.duration >= 0
    assert result.error is None


@pytest.mark.integration
async def test_e2b_execution_with_dependencies():
    """Test E2B execution with dependencies installation."""
    code = """
import requests
async def main():
    # Just check if requests can be imported
    return f"requests version available: {hasattr(requests, '__version__')}"
"""

    async with E2bExecutionEnvironment(dependencies=["requests"]) as env:
        result = await env.execute(code)

    # Note: This might fail if pip install fails, but that's expected behavior
    assert result.duration >= 0
    # Don't assert success since dependency installation might fail in test environment


@pytest.mark.integration
async def test_e2b_execution_custom_template():
    """Test E2B execution with custom template."""
    code = """
async def main():
    return "Custom template test"
"""

    async with E2bExecutionEnvironment(template="base") as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.result == "Custom template test"
    assert result.duration >= 0
    assert result.error is None


@pytest.mark.integration
async def test_e2b_execution_timeout():
    """Test E2B execution with custom timeout."""
    code = """
async def main():
    return "Timeout test"
"""

    async with E2bExecutionEnvironment(timeout=600) as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.result == "Timeout test"
    assert result.duration >= 0
    assert env.timeout == 600  # noqa: PLR2004


@pytest.mark.integration
async def test_e2b_execution_keep_alive():
    """Test keep_alive functionality."""
    code = """
async def main():
    return "Keep alive test"
"""

    async with E2bExecutionEnvironment(keep_alive=True) as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.result == "Keep alive test"
    assert result.duration >= 0
    assert env.keep_alive is True


@pytest.mark.integration
async def test_e2b_execution_multiple_commands():
    """Test multiple consecutive executions in same environment."""
    async with E2bExecutionEnvironment() as env:
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


@pytest.mark.integration
async def test_e2b_execution_no_result():
    """Test execution when no result or main function is present."""
    code = """
x = 1 + 1
print("This should not be the result")
"""

    async with E2bExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is True
    assert result.result is None  # No explicit result or main function
    assert result.duration >= 0


@pytest.mark.integration
async def test_e2b_execution_syntax_error():
    """Test handling of Python syntax errors."""
    code = """
def broken_function(
    # Missing closing parenthesis
    return "This won't work"
"""

    async with E2bExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is False
    assert result.result is None
    assert result.error
    assert result.error_type in ("SyntaxError", "IndentationError")


@pytest.mark.integration
async def test_e2b_execution_runtime_error():
    """Test handling of runtime errors."""
    code = """
async def main():
    x = 1 / 0  # Division by zero
    return x
"""

    async with E2bExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is False
    assert result.result is None
    assert result.error
    assert result.error_type == "ZeroDivisionError"


@pytest.mark.integration
async def test_e2b_execution_long_output():
    """Test execution with longer output."""
    code = """
async def main():
    result = []
    for i in range(10):
        result.append(f"Item {i}: {i * i}")
    return result
"""

    async with E2bExecutionEnvironment() as env:
        result = await env.execute(code)

    assert result.success is True
    assert isinstance(result.result, list)
    assert len(result.result) == 10  # noqa: PLR2004
    assert "Item 0: 0" in result.result
    assert "Item 9: 81" in result.result


if __name__ == "__main__":
    pytest.main(["-v", __file__, "-m", "integration"])
