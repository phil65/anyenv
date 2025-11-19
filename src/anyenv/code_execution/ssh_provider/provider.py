"""SSH execution environment that runs code on remote machines."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Self

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.models import ExecutionResult
from anyenv.code_execution.parse_output import wrap_command


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager
    from types import TracebackType

    from asyncssh import SSHClientConnection, SSHCompletedProcess
    from asyncssh.misc import _ACMWrapper
    from sshfs import SSHFileSystem

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
        cwd: str | None = None,
        **ssh_kwargs: Any,
    ) -> None:
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
            cwd: Remote working directory (auto-generated if None)
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
        self.cwd = cwd
        self.ssh_kwargs = ssh_kwargs

        self._connection_cm: _ACMWrapper[SSHClientConnection] | None = None
        self.connection: SSHClientConnection | None = None
        self._remote_work_dir: str | None = None

    async def run(self, command: str) -> SSHCompletedProcess:
        """Run a command on the remote machine with login shell."""
        if not self.connection:
            msg = "SSH connection not established"
            raise RuntimeError(msg)
        return await self.connection.run(wrap_command(command))

    async def __aenter__(self) -> Self:
        """Establish SSH connection and set up remote environment."""
        # Start tool server via base class
        await super().__aenter__()

        import asyncssh

        # Build connection arguments
        self.connect_kwargs = {
            "host": self.host,
            "port": self.port,
            "username": self.username,
            **self.ssh_kwargs,
        }

        # Add authentication
        if self.private_key_path:
            self.connect_kwargs["client_keys"] = [self.private_key_path]
        elif self.password:
            self.connect_kwargs["password"] = self.password

        # Create and enter the asyncssh connection context manager
        self._connection_cm = asyncssh.connect(**self.connect_kwargs)
        self.connection = await self._connection_cm.__aenter__()
        assert self.connection
        # Set up remote working directory
        if self.cwd:
            self._remote_work_dir = self.cwd
        else:
            # Create temporary directory
            result = await self.run("mktemp -d")
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

        await self.run(f"mkdir -p {self._remote_work_dir}")
        await self._verify_tools()

        # Install dependencies if specified
        if self.dependencies:
            await self._install_dependencies()

        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc_val: BaseException | None,
        exc_tb: TracebackType | None,
    ) -> None:
        """Clean up remote environment and close SSH connection."""
        if self.connection and self._connection_cm:
            # Clean up temporary working directory if we created it
            if not self.cwd and self._remote_work_dir:
                await self.run(f"rm -rf {self._remote_work_dir}")

            await self._connection_cm.__aexit__(exc_type, exc_val, exc_tb)
        await super().__aexit__(exc_type, exc_val, exc_tb)

    def get_fs(self) -> SSHFileSystem:
        """Return a ModalFS instance for the sandbox."""
        from sshfs import SSHFileSystem

        return SSHFileSystem(**self.connect_kwargs)

    async def _verify_tools(self) -> None:
        """Verify that required tools are available on the remote machine."""
        assert self.connection
        if self.language == "python":
            # Require uv to be available - use login shell to load profile
            uv_result = await self.run("which uv")
            if uv_result.returncode != 0:
                msg = "uv not found on remote machine. Please install uv first."
                raise RuntimeError(msg)
        elif self.language in ("javascript", "typescript"):
            node_result = await self.run("which node")
            if node_result.returncode != 0:
                msg = "Node.js not found on remote machine"
                raise RuntimeError(msg)

    async def _install_dependencies(self) -> None:
        """Check dependencies are valid."""
        # For Python, dependencies are handled via uv run --with
        # For JS/TS, we still need to install them in the working directory
        assert self.connection
        if self.language in ("javascript", "typescript") and self.dependencies:
            deps_str = " ".join(self.dependencies)
            cmd = f"npm init -y && npm install {deps_str}"
            result = await self.run_in_working_dir(cmd)
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
                exit_code=result.returncode,
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

    async def run_in_working_dir(
        self,
        cmd: str,
        timeout: bool = False,
    ) -> SSHCompletedProcess:
        """Run a command in the working directory."""
        cmd = f"cd {self._remote_work_dir} && {cmd}"
        if timeout:
            cmd = f"{cmd}timeout {self.timeout} "
        return await self.run(cmd)

    async def _execute_python(self, code: str) -> SSHCompletedProcess:
        """Execute Python code using uv run --with for dependencies."""
        # Create temporary script file
        script_path = f"{self._remote_work_dir}/script.py"
        assert self.connection
        await self.write_file(script_path, code)
        # Build uv run command with dependencies
        if self.dependencies:
            with_args = " ".join(f"--with {dep}" for dep in self.dependencies)
            cmd = f"uv run {with_args} python {script_path}"
        else:
            cmd = f"uv run python {script_path}"
        return await self.run_in_working_dir(cmd, timeout=True)

    async def write_file(self, path: str, content: str) -> None:
        """Write content to a file on the remote server."""
        await self.run(f"cat > {path} << 'EOF'\n{content}\nEOF")

    async def _execute_javascript(self, code: str) -> Any:
        """Execute JavaScript code using node."""
        script_path = f"{self._remote_work_dir}/script.js"
        assert self.connection
        # Write code to remote file
        await self.write_file(script_path, code)
        return await self.run_in_working_dir(f"node {script_path}", timeout=True)

    async def _execute_typescript(self, code: str) -> Any:
        """Execute TypeScript code using ts-node or similar."""
        script_path = f"{self._remote_work_dir}/script.ts"
        assert self.connection
        # Write code to remote file
        await self.write_file(script_path, code)
        # Try ts-node first, fall back to tsc + node
        ts_node_result = await self.run("which ts-node")
        if ts_node_result.returncode == 0:
            cmd = f"ts-node {script_path}"
        else:
            # Compile and run
            cmd = f"npx tsc {script_path} && node script.js"

        return await self.run_in_working_dir(cmd, timeout=True)

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
            result = await self.run_in_working_dir(command, timeout=True)

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
        cwd = self._remote_work_dir
        if not self.connection:
            msg = "SSH connection not established"
            raise RuntimeError(msg)

        if self.language == "python":
            script_path = f"{cwd}/script.py"
            await self.write_file(script_path, code)
            # Build uv run command with dependencies
            if self.dependencies:
                with_args = " ".join(f"--with {dep}" for dep in self.dependencies)
                cmd = f"cd {cwd} && uv run {with_args} python {script_path}"
            else:
                cmd = f"cd {cwd} && uv run python {script_path}"
        else:
            # Similar logic for JS/TS...
            script_path = (
                f"{cwd}/script.{'js' if self.language == 'javascript' else 'ts'}"
            )
            await self.write_file(script_path, code)
            cmd = f"cd {cwd} && node {script_path}"

        # Stream execution - wrap command for login shell
        async with self.connection.create_process(wrap_command(cmd)) as process:
            async for line in process.stdout:
                yield line.rstrip("\n\r")

    async def execute_command_stream(self, command: str) -> AsyncIterator[str]:
        """Execute command and stream output line by line."""
        if not self.connection:
            msg = "SSH connection not established"
            raise RuntimeError(msg)

        cmd = f"cd {self._remote_work_dir} && {command}"
        async with self.connection.create_process(wrap_command(cmd)) as process:
            async for line in process.stdout:
                yield line.rstrip("\n\r")


if __name__ == "__main__":

    async def _main() -> None:
        async with SshExecutionEnvironment("91.99.102.138", "root") as sandbox:
            result = await sandbox.execute_command("ls")
            print(result)

    import asyncio

    asyncio.run(_main())
