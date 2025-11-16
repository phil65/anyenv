"""Code execution environments for remote code execution."""

from __future__ import annotations

from typing import Any, Literal, overload, TYPE_CHECKING, assert_never

from anyenv.code_execution.base import ExecutionEnvironment

from anyenv.code_execution.beam_provider import BeamExecutionEnvironment
from anyenv.code_execution.daytona_provider import DaytonaExecutionEnvironment
from anyenv.code_execution.docker_provider import DockerExecutionEnvironment
from anyenv.code_execution.local_provider import LocalExecutionEnvironment
from anyenv.code_execution.mcp_python_provider import McpPythonExecutionEnvironment
from anyenv.code_execution.e2b_provider import E2bExecutionEnvironment
from anyenv.code_execution.microsandbox_provider import MicrosandboxExecutionEnvironment
from anyenv.code_execution.modal_provider import ModalExecutionEnvironment
from anyenv.code_execution.vercel_provider import (
    DEFAULT_TIMEOUT_SECONDS,
    VercelExecutionEnvironment,
    VercelRuntime,
)
from anyenv.code_execution.models import ExecutionResult, ServerInfo
from anyenv.code_execution.remote_callable import (
    create_remote_callable,
    infer_package_dependencies,
)

# from anyenv.code_execution.server import fastapi_tool_server

from anyenv.code_execution.ssh_provider import SshExecutionEnvironment

if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager

    from anyenv.code_execution.models import Language


ExecutionEnvironmentStr = Literal[
    "local",
    "docker",
    "ssh",
    "mcp",
    "daytona",
    "e2b",
    "beam",
    "vercel",
    "microsandbox",
    "modal",
]


@overload
def get_environment(
    provider: Literal["local"],
    *,
    lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
    timeout: float = 30.0,
    isolated: bool = False,
    executable: str | None = None,
    language: Language = "python",
) -> LocalExecutionEnvironment: ...


@overload
def get_environment(
    provider: Literal["docker"],
    *,
    lifespan_handler: AbstractAsyncContextManager[ServerInfo],
    image: str = "python:3.13-slim",
    timeout: float = 60.0,
    language: Language = "python",
) -> DockerExecutionEnvironment: ...


@overload
def get_environment(
    provider: Literal["ssh"],
    *,
    host: str,
    username: str,
    lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
    dependencies: list[str] | None = None,
    password: str | None = None,
    private_key_path: str | None = None,
    port: int = 22,
    timeout: float = 60.0,
    language: Language = "python",
    cwd: str | None = None,
    **ssh_kwargs: Any,
) -> SshExecutionEnvironment: ...


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


@overload
def get_environment(
    provider: Literal["vercel"],
    *,
    lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
    runtime: VercelRuntime | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
    resources: dict[str, Any] | None = None,
    ports: list[int] | None = None,
    language: Language = "python",
    token: str | None = None,
    project_id: str | None = None,
    team_id: str | None = None,
) -> VercelExecutionEnvironment: ...


@overload
def get_environment(
    provider: Literal["microsandbox"],
    *,
    lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
    server_url: str | None = None,
    namespace: str = "default",
    api_key: str | None = None,
    memory: int = 512,
    cpus: float = 1.0,
    timeout: float = 180.0,
    language: Language = "python",
    image: str | None = None,
) -> MicrosandboxExecutionEnvironment: ...


@overload
def get_environment(
    provider: Literal["modal"],
    *,
    lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
    app_name: str | None = None,
    image: Any | None = None,
    volumes: dict[str, Any] | None = None,
    secrets: list[Any] | None = None,
    cpu: float | None = None,
    memory: int | None = None,
    gpu: str | None = None,
    timeout: int = 300,
    idle_timeout: int | None = None,
    workdir: str = "/tmp",
    language: Language = "python",
) -> ModalExecutionEnvironment: ...


def get_environment(  # noqa: PLR0911
    provider: ExecutionEnvironmentStr,
    **kwargs: Any,
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

        # SSH with password auth
        env = get_environment("ssh", host="remote.server.com", username="user", password="pass")

        # SSH with key auth
        env = get_environment("ssh", host="remote.server.com", username="user",
                            private_key_path="~/.ssh/id_rsa", timeout=120.0)

        # Daytona with specific config
        env = get_environment("daytona", api_url="https://api.daytona.io", timeout=600.0)

        # E2B with template and language
        env = get_environment("e2b", template="python", timeout=600.0, language="javascript")

        # Beam with custom resources
        env = get_environment("beam", cpu=2.0, memory=512, timeout=600.0)

        # Vercel with custom runtime
        env = get_environment("vercel", runtime="node22", timeout=600.0)

        # Microsandbox with custom resources
        env = get_environment("microsandbox", memory=1024, cpus=2.0, language="javascript")

        # Modal with GPU and volumes
        env = get_environment("modal", gpu="T4", memory=2048, app_name="my-app")
        ```
    """  # noqa: E501
    match provider:
        case "local":
            return LocalExecutionEnvironment(**kwargs)
        case "docker":
            return DockerExecutionEnvironment(**kwargs)
        case "ssh":
            return SshExecutionEnvironment(**kwargs)
        case "mcp":
            return McpPythonExecutionEnvironment(**kwargs)
        case "daytona":
            return DaytonaExecutionEnvironment(**kwargs)
        case "e2b":
            return E2bExecutionEnvironment(**kwargs)
        case "beam":
            return BeamExecutionEnvironment(**kwargs)
        case "vercel":
            return VercelExecutionEnvironment(**kwargs)
        case "microsandbox":
            return MicrosandboxExecutionEnvironment(**kwargs)
        case "modal":
            return ModalExecutionEnvironment(**kwargs)
        case _ as unreachable:
            assert_never(unreachable)


__all__ = [
    "BeamExecutionEnvironment",
    "DaytonaExecutionEnvironment",
    "DockerExecutionEnvironment",
    "E2bExecutionEnvironment",
    "ExecutionEnvironment",
    "ExecutionResult",
    "LocalExecutionEnvironment",
    "McpPythonExecutionEnvironment",
    "MicrosandboxExecutionEnvironment",
    "ModalExecutionEnvironment",
    "ServerInfo",
    "SshExecutionEnvironment",
    "VercelExecutionEnvironment",
    "VercelRuntime",
    "create_remote_callable",
    "get_environment",
    "infer_package_dependencies",
    # "fastapi_tool_server",
]
