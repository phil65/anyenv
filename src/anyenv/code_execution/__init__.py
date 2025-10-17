"""Code execution environments for remote code execution."""

from typing import Literal, overload

from anyenv.code_execution.base import ExecutionEnvironment

from anyenv.code_execution.daytona_provider import DaytonaExecutionEnvironment
from anyenv.code_execution.docker_provider import DockerExecutionEnvironment
from anyenv.code_execution.local_provider import LocalExecutionEnvironment
from anyenv.code_execution.mcp_python_provider import McpPythonExecutionEnvironment
from anyenv.code_execution.e2b_provider import E2bExecutionEnvironment
from anyenv.code_execution.models import (
    ExecutionResult,
    ServerInfo,
    ToolCallRequest,
    ToolCallResponse,
)

# from anyenv.code_execution.server import fastapi_tool_server
from anyenv.code_execution.subprocess_provider import SubprocessExecutionEnvironment


@overload
def get_environment(
    provider: Literal["local"],
    *,
    timeout: float = 30.0,
) -> LocalExecutionEnvironment: ...


@overload
def get_environment(
    provider: Literal["subprocess"],
    *,
    python_executable: str = "python",
    timeout: float = 30.0,
) -> SubprocessExecutionEnvironment: ...


@overload
def get_environment(
    provider: Literal["docker"],
    *,
    lifespan_handler,  # AbstractAsyncContextManager[ServerInfo]
    image: str = "python:3.13-slim",
    timeout: float = 60.0,
) -> DockerExecutionEnvironment: ...


@overload
def get_environment(
    provider: Literal["mcp"],
    *,
    dependencies: list[str] | None = None,
    allow_networking: bool = True,
    timeout: float = 30.0,
) -> McpPythonExecutionEnvironment: ...


@overload
def get_environment(
    provider: Literal["daytona"],
    *,
    api_url: str | None = None,
    api_key: str | None = None,
    target: str | None = None,
    image: str = "python:3.13-slim",
    timeout: float = 300.0,
    keep_alive: bool = False,
) -> DaytonaExecutionEnvironment: ...


@overload
def get_environment(
    provider: Literal["e2b"],
    *,
    template: str | None = None,
    timeout: float = 300.0,
    keep_alive: bool = False,
) -> E2bExecutionEnvironment: ...


def get_environment(
    provider: Literal["local", "subprocess", "docker", "mcp", "daytona", "e2b"],
    **kwargs,
) -> ExecutionEnvironment:
    """Get an execution environment based on provider name.

    Args:
        provider: The execution environment provider to use
        **kwargs: Keyword arguments to pass to the provider constructor

    Returns:
        An instance of the specified execution environment

    Example:
        ```python
        # Local execution with timeout
        env = get_environment("local", timeout=60.0)

        # Docker with custom image
        env = get_environment("docker", lifespan_handler=handler, image="python:3.11")

        # Daytona with specific config
        env = get_environment("daytona", api_url="https://api.daytona.io", timeout=600.0)

        # E2B with template
        env = get_environment("e2b", template="python", timeout=600.0)
        ```
    """
    match provider:
        case "local":
            return LocalExecutionEnvironment(**kwargs)
        case "subprocess":
            return SubprocessExecutionEnvironment(**kwargs)
        case "docker":
            return DockerExecutionEnvironment(**kwargs)
        case "mcp":
            return McpPythonExecutionEnvironment(**kwargs)
        case "daytona":
            return DaytonaExecutionEnvironment(**kwargs)
        case "e2b":
            return E2bExecutionEnvironment(**kwargs)
        case _:
            error_msg = f"Unknown provider: {provider}"
            raise ValueError(error_msg)


__all__ = [
    "DaytonaExecutionEnvironment",
    "DockerExecutionEnvironment",
    "E2bExecutionEnvironment",
    "ExecutionEnvironment",
    "ExecutionResult",
    "LocalExecutionEnvironment",
    "McpPythonExecutionEnvironment",
    "ServerInfo",
    "SubprocessExecutionEnvironment",
    "ToolCallRequest",
    "ToolCallResponse",
    "get_environment",
    # "fastapi_tool_server",
]
