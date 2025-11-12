"""Tests for DaytonaExecutionEnvironment."""

import math
from unittest.mock import AsyncMock, patch

import pytest

from anyenv.code_execution import DaytonaExecutionEnvironment


# Skip entire file if daytona package is not available
daytona = pytest.importorskip("daytona")


# Constants for mock results to avoid long lines
SUCCESS_RESULT = '__RESULT__ {"result": "Hello from Daytona!", "success": true}'
ERROR_RESULT = (
    '__RESULT__ {"success": false, "error": "Daytona test error", "type": "ValueError"}'
)
PI_RESULT = f'__RESULT__ {{"result": {math.pi * 2}, "success": true}}'


class MockSandbox:
    """Mock Daytona sandbox for testing."""

    def __init__(self, sandbox_id: str = "test-sandbox-123"):
        self.id = sandbox_id
        self.name = f"anyenv-exec-{sandbox_id}"
        self.process = AsyncMock()

    async def start(self, timeout: int = 120):
        """Mock start method."""

    async def stop(self):
        """Mock stop method."""

    async def delete(self):
        """Mock delete method."""


@pytest.fixture
def mock_daytona():
    """Mock Daytona SDK."""
    daytona = AsyncMock()
    mock_sandbox = MockSandbox()
    daytona.create.return_value = mock_sandbox
    return daytona


async def test_daytona_execution_basic(mock_daytona):
    """Test basic Daytona execution with successful result."""
    code = """
async def main():
    return "Hello from Daytona!"
"""

    with patch("daytona.AsyncDaytona", return_value=mock_daytona):
        # Setup mock sandbox process
        mock_sandbox = mock_daytona.create.return_value
        mock_sandbox.process.exec.return_value = AsyncMock(
            exit_code=0,
            result=SUCCESS_RESULT,
            stdout=SUCCESS_RESULT,
            stderr="",
        )

        # Test execution
        env = DaytonaExecutionEnvironment(
            api_url="https://api.daytona.com", api_key="test-key"
        )

        async with env:
            result = await env.execute(code)

        assert result.success is True
        assert result.result == "Hello from Daytona!"
        assert result.duration >= 0
        assert result.error is None


async def test_daytona_execution_with_result_variable(mock_daytona):
    """Test Daytona execution using _result variable."""
    code = """
import math
_result = math.pi * 2
"""

    with patch("daytona.AsyncDaytona", return_value=mock_daytona):
        # Setup mock sandbox process
        mock_sandbox = mock_daytona.create.return_value
        mock_sandbox.process.exec.return_value = AsyncMock(
            exit_code=0,
            result=PI_RESULT,
            stdout=PI_RESULT,
            stderr="",
        )

        # Test execution
        env = DaytonaExecutionEnvironment(api_url="https://api.daytona.com")

        async with env:
            result = await env.execute(code)

        assert result.success is True
        assert abs(result.result - (math.pi * 2)) < 0.001  # noqa: PLR2004
        assert result.duration >= 0


async def test_daytona_execution_error_handling(mock_daytona):
    """Test error handling in Daytona execution."""
    code = """
async def main():
    raise ValueError("Daytona test error")
"""

    with patch("daytona.AsyncDaytona", return_value=mock_daytona):
        # Setup mock sandbox process
        mock_sandbox = mock_daytona.create.return_value
        mock_sandbox.process.exec.return_value = AsyncMock(
            exit_code=0,
            result=ERROR_RESULT,
            stdout=ERROR_RESULT,
            stderr="",
        )

        # Test execution
        env = DaytonaExecutionEnvironment(api_url="https://api.daytona.com")

        async with env:
            result = await env.execute(code)

        assert result.success is False
        assert result.result is None
        assert result.error
        assert "Daytona test error" in result.error
        assert result.error_type == "ValueError"


async def test_daytona_execution_command_failure(mock_daytona):
    """Test handling of command execution failure."""
    code = """
print("This will fail")
"""

    with patch("daytona.AsyncDaytona", return_value=mock_daytona):
        # Setup mock sandbox process
        mock_sandbox = mock_daytona.create.return_value
        mock_sandbox.process.exec.return_value = AsyncMock(
            exit_code=1,
            result="Command failed with exit code 1",
            stdout="Command failed with exit code 1",
            stderr="",
        )

        # Test execution
        env = DaytonaExecutionEnvironment(api_url="https://api.daytona.com")

        async with env:
            result = await env.execute(code)

        assert result.success is False
        assert result.result is None
        assert result.error
        assert "Command failed with exit code 1" in result.error
        assert result.error_type == "CommandError"


async def test_daytona_execution_keep_alive(mock_daytona):
    """Test keep_alive functionality."""
    with patch("daytona.AsyncDaytona", return_value=mock_daytona):
        # Setup mock sandbox
        mock_sandbox = mock_daytona.create.return_value
        mock_sandbox.stop = AsyncMock()
        mock_sandbox.delete = AsyncMock()

        # Test with keep_alive=True
        env = DaytonaExecutionEnvironment(
            api_url="https://api.daytona.com", keep_alive=True
        )

        async with env:
            pass  # Just test context manager

        # Should not have called stop/delete for cleanup
        mock_sandbox.stop.assert_not_called()
        mock_sandbox.delete.assert_not_called()


async def test_daytona_execution_custom_configuration(mock_daytona):
    """Test Daytona execution with custom configuration."""
    with patch("daytona.AsyncDaytona", return_value=mock_daytona):
        # Test with custom configuration
        env = DaytonaExecutionEnvironment(
            api_url="https://custom.daytona.com",
            api_key="custom-key",
            timeout=600.0,
        )

        async with env:
            pass

        # Verify sandbox was created
        mock_daytona.create.assert_called_once()
        # Note: image parameter is no longer used in the new SDK


if __name__ == "__main__":
    pytest.main(["-v", __file__])
