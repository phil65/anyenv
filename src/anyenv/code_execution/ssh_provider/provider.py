"""SSH execution environment that runs code on remote machines."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Self

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.models import ExecutionResult


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager

    from asyncssh import SSHClientConnection
    from asyncssh.misc import _ACMWrapper

    from anyenv.code_execution.models import Language, ServerInfo


class SshExecutionEnvironment(ExecutionEnvironment):
    """Executes code on remote machines via SSH using asyncssh."""

    def __init__(
        self,
        host: str,
        username: str,
        lifespan_handler: AbstractAsyncContextManager[ServerInfo] | None = None,
        dependencies: list[str] | None = None,
        password: str | None = None,
        private_key_path: str | None = None,
        port: int = 22,
        timeout: float = 60.0,
        language: Language = "python",
        working_directory: str | None = None,
        uv_path: str = "uv",
        node_path: str = "node",
        **ssh_kwargs: Any,
    ):
        """Initialize SSH environment.

        Args:
            host: Remote host to connect to
            username: SSH username
            password: SSH password (if not using key auth)
            dependencies: List of dependencies to install
            lifespan_handler: lifespan handler during execution
            private_key_path: Path to SSH private key file
            port: SSH port
            timeout: Execution timeout in seconds
            language: Programming language to use
            working_directory: Remote working directory (auto-generated if None)
            uv_path: Path to uv executable on remote machine
            node_path: Path to node executable on remote machine
            **ssh_kwargs: Additional arguments passed to asyncssh.connect()
        """
        super().__init__(lifespan_handler=lifespan_handler, dependencies=dependencies)
        self.host = host
        self.username = username
        self.password = password
        self.private_key_path = private_key_path
        self.port = port
        self.timeout = timeout
        self.language = language
        self.working_directory = working_directory
        self.uv_path = uv_path
        self.node_path = node_path
        self.ssh_kwargs = ssh_kwargs

        self._connection_cm: _ACMWrapper | None = None
        self.connection: SSHClientConnection | None = None
        self._remote_work_dir: str | None = None

    async def __aenter__(self) -> Self:
        """Establish SSH connection and set up remote environment."""
        # Start tool server via base class
        await super().__aenter__()

        import asyncssh

        # Build connection arguments
        connect_kwargs = {
            "host": self.host,
            "port": self.port,
            "username": self.username,
            **self.ssh_kwargs,
        }

        # Add authentication
        if self.private_key_path:
            connect_kwargs["client_keys"] = [self.private_key_path]
        elif self.password:
            connect_kwargs["password"] = self.password

        # Create and enter the asyncssh connection context manager
        self._connection_cm = asyncssh.connect(**connect_kwargs)
        self.connection = await self._connection_cm.__aenter__()
        assert self.connection
        # Set up remote working directory
        if self.working_directory:
            self._remote_work_dir = self.working_directory
        else:
            # Create temporary directory
            result = await self.connection.run("mktemp -d")
            if result.returncode != 0:
                stderr = (
                    result.stderr.decode()
                    if isinstance(result.stderr, bytes)
                    else result.stderr
                )
                msg = f"Failed to create remote temp directory: {stderr}"
                raise RuntimeError(msg)
            assert result.stdout
            stdout = (
                result.stdout.decode()
                if isinstance(result.stdout, bytes)
                else result.stdout
            )
            self._remote_work_dir = stdout.strip()

        # Ensure working directory exists
        await self.connection.run(f"mkdir -p {self._remote_work_dir}")

        # Verify required tools are available
        await self._verify_tools()

        # Install dependencies if specified
        if self.dependencies:
            await self._install_dependencies()

        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        """Clean up remote environment and close SSH connection."""
        if self.connection and self._connection_cm:
            # Clean up temporary working directory if we created it
            if not self.working_directory and self._remote_work_dir:
                await self.connection.run(f"rm -rf {self._remote_work_dir}")

            await self._connection_cm.__aexit__(exc_type, exc_val, exc_tb)

        # Cleanup server via base class
        await super().__aexit__(exc_type, exc_val, exc_tb)

    async def _verify_tools(self) -> None:
        """Verify that required tools are available on the remote machine."""
        assert self.connection
        if self.language == "python":
            # Require uv to be available - no fallback to plain python
            uv_result = await self.connection.run(f"which {self.uv_path}")
            if uv_result.returncode != 0:
                msg = f"uv not found at {self.uv_path} on remote machine. Please install."
                raise RuntimeError(msg)
        elif self.language in ("javascript", "typescript"):
            node_result = await self.connection.run(f"which {self.node_path}")
            if node_result.returncode != 0:
                msg = f"Node.js not found at {self.node_path} on remote machine"
                raise RuntimeError(msg)

    async def _install_dependencies(self) -> None:
        """Check dependencies are valid."""
        # For Python, dependencies are handled via uv run --with
        # For JS/TS, we still need to install them in the working directory
        assert self.connection
        if self.language in ("javascript", "typescript") and self.dependencies:
            deps_str = " ".join(self.dependencies)
            cmd = f"cd {self._remote_work_dir} && npm init -y && npm install {deps_str}"
            result = await self.connection.run(cmd)
            if result.returncode != 0:
                stderr = (
                    result.stderr.decode()
                    if isinstance(result.stderr, bytes)
                    else result.stderr
                )
                msg = f"Failed to install Node.js dependencies: {stderr}"
                raise RuntimeError(msg)

    async def execute(self, code: str) -> ExecutionResult:
        """Execute code on the remote machine."""
        if not self.connection:
            msg = "SSH connection not established"
            raise RuntimeError(msg)

        start_time = time.time()

        try:
            if self.language == "python":
                result = await self._execute_python(code)
            elif self.language == "javascript":
                result = await self._execute_javascript(code)
            elif self.language == "typescript":
                result = await self._execute_typescript(code)
            else:
                msg = f"Unsupported language: {self.language}"
                raise ValueError(msg)  # noqa: TRY301

            duration = time.time() - start_time
            success = result.returncode == 0

            # Add tool server URL to code if available
            if self.server_info and self.language == "python":
                code = self._inject_tool_server(code)

            return ExecutionResult(
                result=result.stdout if success else None,
                duration=duration,
                success=success,
                error=result.stderr.decode()
                if isinstance(result.stderr, bytes)
                else result.stderr
                if not success
                else None,
                error_type="RemoteExecutionError" if not success else None,
                stdout=result.stdout.decode()
                if isinstance(result.stdout, bytes)
                else result.stdout,
                stderr=result.stderr.decode()
                if isinstance(result.stderr, bytes)
                else result.stderr,
            )

        except Exception as e:  # noqa: BLE001
            duration = time.time() - start_time
            return ExecutionResult(
                result=None,
                duration=duration,
                success=False,
                error=str(e),
                error_type=type(e).__name__,
            )

    async def _execute_python(self, code: str) -> Any:
        """Execute Python code using uv run --with for dependencies."""
        # Create temporary script file
        script_path = f"{self._remote_work_dir}/script.py"
        assert self.connection
        # Write code to remote file
        await self.connection.run(f"cat > {script_path} << 'EOF'\n{code}\nEOF")

        # Build uv run command with dependencies
        if self.dependencies:
            with_args = " ".join(f"--with {dep}" for dep in self.dependencies)
            cmd = f"cd {self._remote_work_dir} && timeout {self.timeout} {self.uv_path} run {with_args} python {script_path}"  # noqa: E501
            return await self.connection.run(cmd)
        cmd = f"cd {self._remote_work_dir} && timeout {self.timeout} {self.uv_path} run python {script_path}"  # noqa: E501
        return await self.connection.run(cmd)

        return await self.connection.run(cmd)

    async def _execute_javascript(self, code: str) -> Any:
        """Execute JavaScript code using node."""
        script_path = f"{self._remote_work_dir}/script.js"
        assert self.connection
        # Write code to remote file
        await self.connection.run(f"cat > {script_path} << 'EOF'\n{code}\nEOF")

        cmd = f"cd {self._remote_work_dir} && timeout {self.timeout} {self.node_path} {script_path}"  # noqa: E501
        return await self.connection.run(cmd)

    async def _execute_typescript(self, code: str) -> Any:
        """Execute TypeScript code using ts-node or similar."""
        script_path = f"{self._remote_work_dir}/script.ts"
        assert self.connection
        # Write code to remote file
        await self.connection.run(f"cat > {script_path} << 'EOF'\n{code}\nEOF")

        # Try ts-node first, fall back to tsc + node
        ts_node_result = await self.connection.run("which ts-node")
        if ts_node_result.returncode == 0:
            cmd = f"cd {self._remote_work_dir} && timeout {self.timeout} ts-node {script_path}"  # noqa: E501
        else:
            # Compile and run
            cmd = f"cd {self._remote_work_dir} && timeout {self.timeout} npx tsc {script_path} && {self.node_path} script.js"  # noqa: E501

        return await self.connection.run(cmd)

    def _inject_tool_server(self, code: str) -> str:
        """Inject tool server URL into Python code if available."""
        if not self.server_info:
            return code

        injection = f"""
# Tool server configuration injected by anyenv
import os
os.environ['TOOL_SERVER_URL'] = '{self.server_info.url}'
os.environ['TOOL_SERVER_PORT'] = '{self.server_info.port}'

"""
        return injection + code

    async def execute_command(self, command: str) -> ExecutionResult:
        """Execute a shell command on the remote machine."""
        if not self.connection:
            msg = "SSH connection not established"
            raise RuntimeError(msg)

        start_time = time.time()

        try:
            cmd = f"cd {self._remote_work_dir} && timeout {self.timeout} {command}"
            result = await self.connection.run(cmd)

            duration = time.time() - start_time
            success = result.returncode == 0

            return ExecutionResult(
                result=result.stdout if success else None,
                duration=duration,
                success=success,
                error=result.stderr.decode()
                if isinstance(result.stderr, bytes)
                else result.stderr
                if not success
                else None,
                error_type="RemoteCommandError" if not success else None,
                stdout=result.stdout.decode()
                if isinstance(result.stdout, bytes)
                else result.stdout,
                stderr=result.stderr.decode()
                if isinstance(result.stderr, bytes)
                else result.stderr,
            )

        except Exception as e:  # noqa: BLE001
            duration = time.time() - start_time
            return ExecutionResult(
                result=None,
                duration=duration,
                success=False,
                error=str(e),
                error_type=type(e).__name__,
            )

    async def execute_stream(self, code: str) -> AsyncIterator[str]:
        """Execute code and stream output line by line."""
        if not self.connection:
            msg = "SSH connection not established"
            raise RuntimeError(msg)

        if self.language == "python":
            script_path = f"{self._remote_work_dir}/script.py"
            await self.connection.run(f"cat > {script_path} << 'EOF'\n{code}\nEOF")

            # Build uv run command with dependencies
            if self.dependencies:
                with_args = " ".join(f"--with {dep}" for dep in self.dependencies)
                cmd = f"cd {self._remote_work_dir} && {self.uv_path} run {with_args} python {script_path}"  # noqa: E501
            else:
                cmd = f"cd {self._remote_work_dir} && {self.uv_path} run python {script_path}"  # noqa: E501
        else:
            # Similar logic for JS/TS...
            script_path = f"{self._remote_work_dir}/script.{'js' if self.language == 'javascript' else 'ts'}"  # noqa: E501
            await self.connection.run(f"cat > {script_path} << 'EOF'\n{code}\nEOF")
            cmd = f"cd {self._remote_work_dir} && {self.node_path} {script_path}"

        # Stream execution
        async with self.connection.create_process(cmd) as process:
            async for line in process.stdout:
                yield line.rstrip("\n\r")

    async def execute_command_stream(self, command: str) -> AsyncIterator[str]:
        """Execute command and stream output line by line."""
        if not self.connection:
            msg = "SSH connection not established"
            raise RuntimeError(msg)

        cmd = f"cd {self._remote_work_dir} && {command}"
        async with self.connection.create_process(cmd) as process:
            async for line in process.stdout:
                yield line.rstrip("\n\r")
