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
    from anyenv.code_execution.microsandbox_provider import MicrosandboxExecutionEnvironment
    from anyenv.code_execution.modal_provider import ModalExecutionEnvironment
    from anyenv.code_execution.models import ServerInfo
    from anyenv.code_execution.pyodide_provider import PyodideExecutionEnvironment
    from anyenv.code_execution.srt_provider import SRTExecutionEnvironment
    from anyenv.code_execution.ssh_provider import SshExecutionEnvironment
    from anyenv.code_execution.vercel_provider import VercelExecutionEnvironment


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

    model_config = ConfigDict(json_schema_extra={"x-doc-title": "Local Execution Environment"})

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

    model_config = ConfigDict(json_schema_extra={"x-doc-title": "Docker Execution Environment"})

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

    model_config = ConfigDict(json_schema_extra={"x-doc-title": "E2B Execution Environment"})

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

    model_config = ConfigDict(json_schema_extra={"x-doc-title": "Beam Execution Environment"})

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

    model_config = ConfigDict(json_schema_extra={"x-doc-title": "Daytona Execution Environment"})

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


class SRTExecutionEnvironmentConfig(BaseExecutionEnvironmentConfig):
    """Sandboxed execution environment using Anthropic's sandbox-runtime.

    Executes code locally with OS-level sandboxing for network and filesystem restrictions.
    Requires `srt` CLI: `npm install -g @anthropic-ai/sandbox-runtime`
    """

    model_config = ConfigDict(json_schema_extra={"x-doc-title": "SRT Execution Environment"})

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


class MicrosandboxExecutionEnvironmentConfig(BaseExecutionEnvironmentConfig):
    """Microsandbox execution environment configuration.

    Executes code in lightweight microVMs for strong isolation.
    """

    model_config = ConfigDict(
        json_schema_extra={"x-doc-title": "Microsandbox Execution Environment"}
    )

    type: Literal["microsandbox"] = Field("microsandbox", init=False)

    server_url: str | None = Field(
        default=None,
        title="Server URL",
        examples=["http://localhost:8080"],
    )
    """Microsandbox server URL (uses MSB_SERVER_URL env var if None)."""

    namespace: str = Field(
        default="default",
        title="Namespace",
    )
    """Sandbox namespace."""

    api_key: SecretStr | None = Field(default=None, title="API Key")
    """API key for authentication (uses MSB_API_KEY env var if None)."""

    memory: int = Field(
        default=512,
        ge=128,
        title="Memory (MB)",
    )
    """Memory limit in MB."""

    cpus: float = Field(
        default=1.0,
        ge=0.1,
        title="CPU Cores",
    )
    """CPU limit."""

    language: Language = Field(
        default="python",
        title="Programming Language",
        examples=["python", "javascript", "typescript"],
    )
    """Programming language to use."""

    image: str | None = Field(
        default=None,
        title="Docker Image",
        examples=["python:3.13-slim", "node:20-alpine"],
    )
    """Custom Docker image (uses default for language if None)."""

    def get_provider(
        self, lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None
    ) -> MicrosandboxExecutionEnvironment:
        """Create Microsandbox execution environment instance."""
        from anyenv.code_execution.microsandbox_provider import MicrosandboxExecutionEnvironment

        api_key_str = self.api_key.get_secret_value() if self.api_key else None
        return MicrosandboxExecutionEnvironment(
            lifespan_handler=lifespan_handler,
            dependencies=self.dependencies,
            server_url=self.server_url,
            namespace=self.namespace,
            api_key=api_key_str,
            memory=self.memory,
            cpus=self.cpus,
            timeout=self.timeout,
            language=self.language,
            image=self.image,
        )


class ModalExecutionEnvironmentConfig(BaseExecutionEnvironmentConfig):
    """Modal execution environment configuration.

    Executes code in Modal serverless sandboxes for scalable cloud execution.
    """

    model_config = ConfigDict(json_schema_extra={"x-doc-title": "Modal Execution Environment"})

    type: Literal["modal"] = Field("modal", init=False)

    app_name: str | None = Field(
        default=None,
        title="App Name",
        examples=["my-app", "anyenv-execution"],
    )
    """Modal app name (creates if missing)."""

    cpu: float | None = Field(
        default=None,
        ge=0.1,
        title="CPU Cores",
    )
    """CPU allocation in cores."""

    memory: int | None = Field(
        default=None,
        ge=128,
        title="Memory (MB)",
    )
    """Memory allocation in MB."""

    gpu: str | None = Field(
        default=None,
        title="GPU Type",
        examples=["T4", "A100", "A10G"],
    )
    """GPU type."""

    idle_timeout: int | None = Field(
        default=None,
        title="Idle Timeout (seconds)",
    )
    """Idle timeout in seconds."""

    workdir: str = Field(
        default="/tmp",
        title="Working Directory",
    )
    """Working directory in sandbox."""

    language: Language = Field(
        default="python",
        title="Programming Language",
        examples=["python", "javascript", "typescript"],
    )
    """Programming language to use."""

    def get_provider(
        self, lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None
    ) -> ModalExecutionEnvironment:
        """Create Modal execution environment instance."""
        from anyenv.code_execution.modal_provider import ModalExecutionEnvironment

        return ModalExecutionEnvironment(
            lifespan_handler=lifespan_handler,
            dependencies=self.dependencies,
            app_name=self.app_name,
            cpu=self.cpu,
            memory=self.memory,
            gpu=self.gpu,
            timeout=int(self.timeout),
            idle_timeout=self.idle_timeout,
            workdir=self.workdir,
            language=self.language,
        )


class SshExecutionEnvironmentConfig(BaseExecutionEnvironmentConfig):
    """SSH execution environment configuration.

    Executes code on a remote machine via SSH connection.
    """

    model_config = ConfigDict(json_schema_extra={"x-doc-title": "SSH Execution Environment"})

    type: Literal["ssh"] = Field("ssh", init=False)

    host: str = Field(
        title="Host",
        examples=["192.168.1.100", "example.com"],
    )
    """Remote host to connect to."""

    username: str = Field(
        title="Username",
        examples=["ubuntu", "root"],
    )
    """SSH username."""

    password: SecretStr | None = Field(default=None, title="Password")
    """SSH password (if not using key auth)."""

    private_key_path: str | None = Field(
        default=None,
        title="Private Key Path",
        examples=["~/.ssh/id_rsa", "/path/to/key"],
    )
    """Path to SSH private key file."""

    port: int = Field(
        default=22,
        ge=1,
        le=65535,
        title="SSH Port",
    )
    """SSH port."""

    language: Language = Field(
        default="python",
        title="Programming Language",
        examples=["python", "javascript", "typescript"],
    )
    """Programming language to use."""

    cwd: str | None = Field(
        default=None,
        title="Working Directory",
        examples=["/tmp", "~/workspace"],
    )
    """Remote working directory (auto-generated if None)."""

    def get_provider(
        self, lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None
    ) -> SshExecutionEnvironment:
        """Create SSH execution environment instance."""
        from anyenv.code_execution.ssh_provider import SshExecutionEnvironment

        password_str = self.password.get_secret_value() if self.password else None
        return SshExecutionEnvironment(
            host=self.host,
            username=self.username,
            lifespan_handler=lifespan_handler,
            dependencies=self.dependencies,
            password=password_str,
            private_key_path=self.private_key_path,
            port=self.port,
            timeout=self.timeout,
            language=self.language,
            cwd=self.cwd,
        )


class VercelExecutionEnvironmentConfig(BaseExecutionEnvironmentConfig):
    """Vercel execution environment configuration.

    Executes code in Vercel cloud sandboxes for serverless execution.
    """

    model_config = ConfigDict(json_schema_extra={"x-doc-title": "Vercel Execution Environment"})

    type: Literal["vercel"] = Field("vercel", init=False)

    runtime: (
        Literal["node22", "python3.13", "v0-next-shadcn", "cua-ubuntu-xfce", "walleye-python"]
        | None
    ) = Field(
        default=None,
        title="Runtime",
    )
    """Vercel runtime to use."""

    resources: dict[str, int | str] | None = Field(
        default=None,
        title="Resources",
    )
    """Resource configuration for the sandbox."""

    ports: list[int] = Field(
        default=[3000],
        title="Ports",
    )
    """List of ports to expose."""

    language: Language = Field(
        default="python",
        title="Programming Language",
        examples=["python", "javascript", "typescript"],
    )
    """Programming language to use."""

    token: SecretStr | None = Field(default=None, title="API Token")
    """Vercel API token (uses environment if None)."""

    project_id: str | None = Field(
        default=None,
        title="Project ID",
    )
    """Vercel project ID (uses environment if None)."""

    team_id: str | None = Field(
        default=None,
        title="Team ID",
    )
    """Vercel team ID (uses environment if None)."""

    def get_provider(
        self, lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None
    ) -> VercelExecutionEnvironment:
        """Create Vercel execution environment instance."""
        from anyenv.code_execution.vercel_provider import VercelExecutionEnvironment

        token_str = self.token.get_secret_value() if self.token else None
        return VercelExecutionEnvironment(
            lifespan_handler=lifespan_handler,
            dependencies=self.dependencies,
            runtime=self.runtime,
            timeout=int(self.timeout),
            resources=self.resources,
            ports=self.ports,
            language=self.language,
            token=token_str,
            project_id=self.project_id,
            team_id=self.team_id,
        )


class PyodideExecutionEnvironmentConfig(BaseExecutionEnvironmentConfig):
    """Pyodide execution environment configuration.

    Executes Python code in WASM via Deno for sandboxed browser-like execution.
    """

    model_config = ConfigDict(json_schema_extra={"x-doc-title": "Pyodide Execution Environment"})

    type: Literal["pyodide"] = Field("pyodide", init=False)

    startup_timeout: float = Field(
        default=60.0,
        gt=0.0,
        title="Startup Timeout",
    )
    """Timeout for Pyodide initialization in seconds."""

    allow_net: bool | list[str] = Field(
        default=True,
        title="Network Access",
    )
    """Network access (True=all, list=specific hosts, False=none)."""

    allow_read: bool | list[str] = Field(
        default=False,
        title="File Read Access",
    )
    """File read access."""

    allow_write: bool | list[str] = Field(
        default=False,
        title="File Write Access",
    )
    """File write access."""

    allow_env: bool | list[str] = Field(
        default=False,
        title="Environment Variable Access",
    )
    """Environment variable access."""

    allow_run: bool | list[str] = Field(
        default=False,
        title="Subprocess Execution",
    )
    """Subprocess execution (limited in WASM)."""

    allow_ffi: bool | list[str] = Field(
        default=False,
        title="FFI Access",
    )
    """Foreign function interface access."""

    deno_executable: str | None = Field(
        default=None,
        title="Deno Executable",
        examples=["deno", "/usr/local/bin/deno"],
    )
    """Path to deno executable (auto-detected if None)."""

    def get_provider(
        self, lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None
    ) -> PyodideExecutionEnvironment:
        """Create Pyodide execution environment instance."""
        from anyenv.code_execution.pyodide_provider import PyodideExecutionEnvironment

        return PyodideExecutionEnvironment(
            lifespan_handler=lifespan_handler,
            dependencies=self.dependencies,
            timeout=self.timeout,
            startup_timeout=self.startup_timeout,
            allow_net=self.allow_net,
            allow_read=self.allow_read,
            allow_write=self.allow_write,
            allow_env=self.allow_env,
            allow_run=self.allow_run,
            allow_ffi=self.allow_ffi,
            deno_executable=self.deno_executable,
        )


# Union type for all execution environment configurations
ExecutionEnvironmentConfig = Annotated[
    LocalExecutionEnvironmentConfig
    | DockerExecutionEnvironmentConfig
    | E2bExecutionEnvironmentConfig
    | BeamExecutionEnvironmentConfig
    | DaytonaExecutionEnvironmentConfig
    | SRTExecutionEnvironmentConfig
    | MicrosandboxExecutionEnvironmentConfig
    | ModalExecutionEnvironmentConfig
    | SshExecutionEnvironmentConfig
    | VercelExecutionEnvironmentConfig
    | PyodideExecutionEnvironmentConfig,
    # | ACPExecutionEnvironmentConfig,
    Field(discriminator="type"),
]
