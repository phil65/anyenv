"""Execution environment configuration."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, SecretStr

from anyenv.code_execution.models import Language
from anyenv.code_execution.srt_provider.config import SandboxConfig


if TYPE_CHECKING:
    from contextlib import AbstractAsyncContextManager

    from anyenv.code_execution.beam_provider import BeamExecutionEnvironment
    from anyenv.code_execution.daytona_provider import DaytonaExecutionEnvironment
    from anyenv.code_execution.docker_provider import DockerExecutionEnvironment
    from anyenv.code_execution.e2b_provider import E2bExecutionEnvironment
    from anyenv.code_execution.local_provider import LocalExecutionEnvironment
    from anyenv.code_execution.mcp_python_provider import McpPythonExecutionEnvironment
    from anyenv.code_execution.models import ServerInfo
    from anyenv.code_execution.srt_provider import SRTExecutionEnvironment


class BaseExecutionEnvironmentConfig(BaseModel):
    """Base execution environment configuration."""

    type: str = Field(init=False)
    """Execution environment type."""

    dependencies: list[str] | None = Field(
        default=None,
        title="Dependencies",
        examples=["numpy", "pandas"],
    )
    """List of packages to install (pip for Python, npm for JS/TS)."""

    timeout: float = Field(
        default=60.0,
        gt=0.0,
        title="Execution Timeout",
        examples=[120.0, 300.0],
    )
    """Execution timeout in seconds."""

    model_config = ConfigDict(use_attribute_docstrings=True, extra="forbid")


class LocalExecutionEnvironmentConfig(BaseExecutionEnvironmentConfig):
    """Local execution environment configuration.

    Executes code in the same process. Fastest option but offers no isolation.
    """

    type: Literal["local"] = Field("local", init=False)

    executable: str | None = Field(
        default=None,
        title="Python Executable",
        examples=["/usr/bin/python3", "python3.13", "/opt/conda/bin/python"],
    )
    """Python executable to use (if None, auto-detect based on language)."""

    language: Language = Field(
        default="python",
        title="Programming Language",
        examples=["python", "javascript", "typescript"],
    )
    """Programming language to use."""

    isolated: bool = Field(default=False, title="Isolated Execution")
    """Whether to run code in a subprocess."""

    def get_provider(
        self, lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None
    ) -> LocalExecutionEnvironment:
        """Create local execution environment instance."""
        from anyenv.code_execution.local_provider import LocalExecutionEnvironment

        return LocalExecutionEnvironment(
            lifespan_handler=lifespan_handler,
            dependencies=self.dependencies,
            timeout=self.timeout,
            isolated=self.isolated,
            executable=self.executable,
            language=self.language,
        )


class DockerExecutionEnvironmentConfig(BaseExecutionEnvironmentConfig):
    """Docker execution environment configuration.

    Executes code in Docker containers for strong isolation and reproducible environments.
    """

    type: Literal["docker"] = Field("docker", init=False)

    image: str = Field(
        default="python:3.13-slim",
        title="Docker Image",
        examples=["python:3.13-slim", "node:20-alpine", "ubuntu:22.04"],
    )
    """Docker image to use."""

    language: Language = Field(
        default="python",
        title="Programming Language",
        examples=["python", "javascript", "typescript"],
    )
    """Programming language to use."""

    def get_provider(
        self, lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None
    ) -> DockerExecutionEnvironment:
        """Create Docker execution environment instance."""
        from anyenv.code_execution.docker_provider import DockerExecutionEnvironment

        return DockerExecutionEnvironment(
            lifespan_handler=lifespan_handler,
            dependencies=self.dependencies,
            image=self.image,
            timeout=self.timeout,
            language=self.language,
        )


class E2bExecutionEnvironmentConfig(BaseExecutionEnvironmentConfig):
    """E2B execution environment configuration.

    Executes code in E2B sandboxes for secure, ephemeral execution environments.
    """

    type: Literal["e2b"] = Field("e2b", init=False)

    template: str | None = Field(
        default=None,
        title="E2B Template",
        examples=["python", "nodejs", "custom-template-id"],
    )
    """E2B template to use."""

    keep_alive: bool = Field(default=False, title="Keep Alive")
    """Keep sandbox running after execution."""

    language: Language = Field(
        default="python",
        title="Programming Language",
        examples=["python", "javascript", "typescript"],
    )
    """Programming language to use."""

    def get_provider(
        self, lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None
    ) -> E2bExecutionEnvironment:
        """Create E2B execution environment instance."""
        from anyenv.code_execution.e2b_provider import E2bExecutionEnvironment

        return E2bExecutionEnvironment(
            lifespan_handler=lifespan_handler,
            dependencies=self.dependencies,
            template=self.template,
            timeout=self.timeout,
            keep_alive=self.keep_alive,
            language=self.language,
        )


class BeamExecutionEnvironmentConfig(BaseExecutionEnvironmentConfig):
    """Beam execution environment configuration.

    Executes code in Beam cloud sandboxes for scalable, serverless execution environments.
    """

    type: Literal["beam"] = Field("beam", init=False)

    cpu: float | str = Field(
        default=1.0,
        ge=0.1,
        le=64.0,
        title="CPU Cores",
        examples=[0.5, 1.0, 2.0, "1500m"],
    )
    """CPU cores allocated to the container."""

    memory: int | str = Field(
        default=128,
        title="Memory (MiB)",
        examples=[128, "1Gi"],
    )
    """Memory allocated to the container in MiB."""

    keep_warm_seconds: int = Field(
        default=600,
        title="Keep Warm Duration",
        examples=[300, 600, -1],
    )
    """Seconds to keep sandbox alive, -1 for no timeout."""

    language: Language = Field(
        default="python",
        title="Programming Language",
        examples=["python", "javascript", "typescript"],
    )
    """Programming language to use."""

    def get_provider(
        self, lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None
    ) -> BeamExecutionEnvironment:
        """Create Beam execution environment instance."""
        from anyenv.code_execution.beam_provider import BeamExecutionEnvironment

        return BeamExecutionEnvironment(
            lifespan_handler=lifespan_handler,
            dependencies=self.dependencies,
            cpu=self.cpu,
            memory=self.memory,
            keep_warm_seconds=self.keep_warm_seconds,
            timeout=self.timeout,
            language=self.language,
        )


class DaytonaExecutionEnvironmentConfig(BaseExecutionEnvironmentConfig):
    """Daytona execution environment configuration.

    Executes code in remote Daytona sandboxes for cloud-based development environments.
    """

    type: Literal["daytona"] = Field("daytona", init=False)

    api_url: str | None = Field(
        default=None,
        title="API URL",
        examples=["https://api.daytona.io", "http://localhost:3986"],
    )
    """Daytona API URL (optional, uses env vars if not provided)."""

    api_key: SecretStr | None = Field(default=None, title="API Key")
    """API key for authentication."""

    target: str | None = Field(
        default=None,
        title="Target Configuration",
        examples=["local", "docker", "kubernetes"],
    )
    """Target configuration."""

    image: str = Field(
        default="python:3.13-slim",
        title="Container Image",
        examples=["python:3.13-slim", "node:20-alpine", "ubuntu:22.04"],
    )
    """Container image."""

    keep_alive: bool = Field(default=False, title="Keep Alive")
    """Keep sandbox running after execution."""

    def get_provider(
        self, lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None
    ) -> DaytonaExecutionEnvironment:
        """Create Daytona execution environment instance."""
        from anyenv.code_execution.daytona_provider import DaytonaExecutionEnvironment

        api_key_str = self.api_key.get_secret_value() if self.api_key else None
        return DaytonaExecutionEnvironment(
            lifespan_handler=lifespan_handler,
            dependencies=self.dependencies,
            api_url=self.api_url,
            api_key=api_key_str,
            target=self.target,
            image=self.image,
            timeout=self.timeout,
            keep_alive=self.keep_alive,
        )


class McpPythonExecutionEnvironmentConfig(BaseExecutionEnvironmentConfig):
    """MCP Python execution environment configuration.

    Executes Python code with Model Context Protocol support for AI integrations.
    """

    type: Literal["mcp_python"] = Field("mcp_python", init=False)

    allow_networking: bool = Field(default=True, title="Allow Networking")
    """Allow network access."""

    def get_provider(
        self, lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None
    ) -> McpPythonExecutionEnvironment:
        """Create MCP Python execution environment instance."""
        from anyenv.code_execution.mcp_python_provider import (
            McpPythonExecutionEnvironment,
        )

        return McpPythonExecutionEnvironment(
            lifespan_handler=lifespan_handler,
            dependencies=self.dependencies,
            allow_networking=self.allow_networking,
            timeout=self.timeout,
        )


class SRTExecutionEnvironmentConfig(BaseExecutionEnvironmentConfig):
    """Sandboxed execution environment using Anthropic's sandbox-runtime.

    Executes code locally with OS-level sandboxing for network and filesystem restrictions.
    Requires `srt` CLI: `npm install -g @anthropic-ai/sandbox-runtime`
    """

    type: Literal["srt"] = Field("srt", init=False)

    language: Language = Field(
        default="python",
        title="Programming Language",
        examples=["python", "javascript", "typescript"],
    )
    """Programming language to use."""

    executable: str | None = Field(
        default=None,
        title="Executable",
        examples=["/usr/bin/python3", "python3.13"],
    )
    """Executable to use (auto-detect if None)."""

    sandbox: SandboxConfig = Field(default_factory=SandboxConfig)
    """Sandbox restrictions configuration."""

    def get_provider(
        self, lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None
    ) -> SRTExecutionEnvironment:
        """Create sandboxed execution environment instance."""
        from anyenv.code_execution.srt_provider import SRTExecutionEnvironment

        return SRTExecutionEnvironment(
            sandbox_config=self.sandbox,
            lifespan_handler=lifespan_handler,
            dependencies=self.dependencies,
            timeout=self.timeout,
            executable=self.executable,
            language=self.language,
        )


# Union type for all execution environment configurations
ExecutionEnvironmentConfig = Annotated[
    LocalExecutionEnvironmentConfig
    | DockerExecutionEnvironmentConfig
    | E2bExecutionEnvironmentConfig
    | BeamExecutionEnvironmentConfig
    | DaytonaExecutionEnvironmentConfig
    | McpPythonExecutionEnvironmentConfig
    | SRTExecutionEnvironmentConfig,
    Field(discriminator="type"),
]
