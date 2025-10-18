"""Code execution environments for remote code execution."""

from __future__ import annotations

from typing import Literal, overload, TYPE_CHECKING

from anyenv.code_execution.base import ExecutionEnvironment

from anyenv.code_execution.beam_provider import BeamExecutionEnvironment
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

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager

    from anyenv.code_execution.models import Language


@overload
def get_environment(
    provider: Literal["local"],
    *,
    lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
    timeout: float = 30.0,
) -> LocalExecutionEnvironment: ...


@overload
def get_environment(
    provider: Literal["subprocess"],
    *,
    lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
    executable: str = "python",
    timeout: float = 30.0,
    language: Language = "python",
) -> SubprocessExecutionEnvironment: ...


@overload
def get_environment(
    provider: Literal["docker"],
    *,
    lifespan_handler,  # AbstractAsyncContextManager[ServerInfo]
    image: str = "python:3.13-slim",
    timeout: float = 60.0,
    language: Language = "python",
) -> DockerExecutionEnvironment: ...


@overload
def get_environment(
    provider: Literal["mcp"],
    *,
    lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
    dependencies: list[str] | None = None,
    allow_networking: bool = True,
    timeout: float = 30.0,
) -> McpPythonExecutionEnvironment: ...


@overload
def get_environment(
    provider: Literal["daytona"],
    *,
    lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
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
    lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
    template: str | None = None,
    timeout: float = 300.0,
    keep_alive: bool = False,
    language: Language = "python",
) -> E2bExecutionEnvironment: ...


@overload
def get_environment(
    provider: Literal["beam"],
    *,
    lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
    cpu: float | str = 1.0,
    memory: int | str = 128,
    keep_warm_seconds: int = 600,
    timeout: float = 300.0,
    language: Language = "python",
) -> BeamExecutionEnvironment: ...


def get_environment(  # noqa: PLR0911
    provider: Literal["local", "subprocess", "docker", "mcp", "daytona", "e2b", "beam"],
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

        # E2B with template and language
        env = get_environment("e2b", template="python", timeout=600.0, language="javascript")

        # Beam with custom resources
        env = get_environment("beam", cpu=2.0, memory=512, timeout=600.0)
        ```
    """  # noqa: E501
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
        case "beam":
            return BeamExecutionEnvironment(**kwargs)
        case _:
            error_msg = f"Unknown provider: {provider}"
            raise ValueError(error_msg)


__all__ = [
    "BeamExecutionEnvironment",
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
