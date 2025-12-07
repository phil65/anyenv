"""SSH execution environment that runs code on remote machines."""

from __future__ import annotations

import time
from typing import TYPE_CHECKING, Any, Self

from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.code_execution.events import (
    OutputEvent,
    ProcessCompletedEvent,
    ProcessErrorEvent,
    ProcessStartedEvent,
)
from anyenv.code_execution.models import ExecutionResult
from anyenv.code_execution.parse_output import wrap_command


if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from contextlib import AbstractAsyncContextManager
    from types import TracebackType

    from asyncssh import SSHClientConnection, SSHCompletedProcess
    from asyncssh.misc import _ACMWrapper
    from upathtools.filesystems.base.wrapper import WrapperFileSystem

    from anyenv.code_execution.events import ExecutionEvent
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
        self._fs: WrapperFileSystem | None = None

    def _ensure_connected(self) -> SSHClientConnection:
        """Validate that SSH connection is established.

        Returns:
            The SSH connection.

        Raises:
            RuntimeError: If not connected via async context manager.
        """
        if self.connection is None:
            msg = "SSH connection not established. Use 'async with' context manager."
            raise RuntimeError(msg)
        return self.connection

    async def run(self, command: str) -> SSHCompletedProcess:
        """Run a command on the remote machine with login shell."""
        connection = self._ensure_connected()
        return await connection.run(wrap_command(command))

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
        # Set up remote working directory
        if self.cwd:
            self._remote_work_dir = self.cwd
        else:
            # Create temporary directory
            result = await self.run("mktemp -d")
            if result.returncode != 0:
                stderr = (
                    result.stderr.decode() if isinstance(result.stderr, bytes) else result.stderr
                )
                msg = f"Failed to create remote temp directory: {stderr}"
                raise RuntimeError(msg)
            assert result.stdout
            stdout = result.stdout.decode() if isinstance(result.stdout, bytes) else result.stdout
            self._remote_work_dir = stdout.strip()

        await self.run(f"mkdir -p {self._remote_work_dir}")
        await self._verify_tools()
        if self.dependencies:  # Install dependencies if specified
            await self._install_dependencies()
        # Create filesystem with proper event loop
        self._fs = await self._create_fs()
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

    async def _create_fs(self) -> WrapperFileSystem:
        """Create SSHFileSystem with proper event loop integration."""
        import asyncio
        from contextlib import AsyncExitStack

        from sshfs import SSHFileSystem  # type: ignore[import-untyped]
        from sshfs.pools import SFTPSoftChannelPool
        from upathtools.filesystems.base.wrapper import WrapperFileSystem

        # SSH filesystem doesnt work with existing connections, so we hack around it.
        loop = asyncio.get_running_loop()
        fs = SSHFileSystem.__new__(SSHFileSystem)
        fs._loop = loop  # noqa: SLF001
        fs._intrans = False  # noqa: SLF001
        fs._transaction = None  # noqa: SLF001
        fs.dircache = {}  # pyright: ignore[reportAttributeAccessIssue]
        fs._stack = AsyncExitStack()  # noqa: SLF001
        fs.active_executors = 0
        fs._client, fs._pool = await fs._connect(  # noqa: SLF001
            self.connect_kwargs["host"],
            SFTPSoftChannelPool,
            max_sftp_channels=8,
            **{k: v for k, v in self.connect_kwargs.items() if k != "host"},
        )
        return WrapperFileSystem(fs)

    def get_fs(self) -> WrapperFileSystem:
        """Return a SSHFileSystem instance for the remote machine."""
        if self._fs is None:
            msg = "Filesystem not available. Use 'async with' context manager first."
            raise RuntimeError(msg)
        return self._fs

    async def _verify_tools(self) -> None:
        """Verify that required tools are available on the remote machine."""
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
        """Install dependencies on the remote machine."""
        # For Python, dependencies are handled via uv run --with
        # For JS/TS, we still need to install them in the working directory
        if self.language in ("javascript", "typescript") and self.dependencies:
            deps_str = " ".join(self.dependencies)
            cmd = f"npm init -y && npm install {deps_str}"
            result = await self.run_in_working_dir(cmd)
            if result.returncode != 0:
                stderr = (
                    result.stderr.decode() if isinstance(result.stderr, bytes) else result.stderr
                )
                msg = f"Failed to install Node.js dependencies: {stderr}"
                raise RuntimeError(msg)

    async def execute(self, code: str) -> ExecutionResult:
        """Execute code on the remote machine."""
        self._ensure_connected()
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

            success = result.returncode == 0
            # Add tool server URL to code if available
            if self.server_info and self.language == "python":
                code = self._inject_tool_server(code)

            return ExecutionResult(
                result=result.stdout if success else None,
                duration=time.time() - start_time,
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
            return ExecutionResult.failed(e, start_time)

    async def run_in_working_dir(self, cmd: str, timeout: bool = False) -> SSHCompletedProcess:
        """Run a command in the working directory."""
        if timeout:
            cmd = f"cd {self._remote_work_dir} && timeout {self.timeout} {cmd}"
        else:
            cmd = f"cd {self._remote_work_dir} && {cmd}"
        return await self.run(cmd)

    async def _execute_python(self, code: str) -> SSHCompletedProcess:
        """Execute Python code using uv run --with for dependencies."""
        self._ensure_connected()
        script_path = f"{self._remote_work_dir}/script.py"
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
        self._ensure_connected()
        script_path = f"{self._remote_work_dir}/script.js"
        await self.write_file(script_path, code)
        return await self.run_in_working_dir(f"node {script_path}", timeout=True)

    async def _execute_typescript(self, code: str) -> Any:
        """Execute TypeScript code using ts-node or similar."""
        self._ensure_connected()
        script_path = f"{self._remote_work_dir}/script.ts"
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
        self._ensure_connected()
        start_time = time.time()

        try:
            result = await self.run_in_working_dir(command, timeout=True)
            success = result.returncode == 0
            stderr = err.decode() if isinstance(err := result.stderr, bytes) else err
            stdout = out.decode() if isinstance(out := result.stdout, bytes) else out
            error = stderr if not success else None
            return ExecutionResult(
                result=result.stdout if success else None,
                duration=time.time() - start_time,
                success=success,
                error=error,
                error_type="RemoteCommandError" if not success else None,
                stdout=stdout,
                stderr=stderr,
            )

        except Exception as e:  # noqa: BLE001
            return ExecutionResult.failed(e, start_time)

    async def stream_code(self, code: str) -> AsyncIterator[ExecutionEvent]:
        """Execute code and stream events over SSH."""
        connection = self._ensure_connected()
        process_id = f"ssh_{id(connection)}"
        yield ProcessStartedEvent(process_id=process_id, command=f"execute({len(code)} chars)")

        try:
            if self.language == "python":
                result = await self._execute_python(code)
            elif self.language == "javascript":
                result = await self._execute_javascript(code)
            elif self.language == "typescript":
                result = await self._execute_typescript(code)
            else:
                msg = f"Unsupported language: {self.language}"
                yield ProcessErrorEvent(process_id=process_id, error=msg, error_type="ValueError")
                return

            stdout = result.stdout.decode() if isinstance(result.stdout, bytes) else result.stdout
            stderr = result.stderr.decode() if isinstance(result.stderr, bytes) else result.stderr

            if stdout:
                yield OutputEvent(process_id=process_id, data=stdout, stream="stdout")
            if stderr:
                yield OutputEvent(process_id=process_id, data=stderr, stream="stderr")

            exit_code = result.returncode or 0
            if exit_code == 0:
                yield ProcessCompletedEvent(process_id=process_id, exit_code=exit_code)
            else:
                yield ProcessErrorEvent(
                    process_id=process_id,
                    error=f"Process exited with code {exit_code}",
                    error_type="ProcessError",
                    exit_code=exit_code,
                )

        except Exception as e:  # noqa: BLE001
            yield ProcessErrorEvent.failed(e, process_id=process_id)

    async def stream_command(self, command: str) -> AsyncIterator[ExecutionEvent]:
        """Execute command and stream events over SSH."""
        connection = self._ensure_connected()
        process_id = f"ssh_cmd_{id(connection)}"
        yield ProcessStartedEvent(process_id=process_id, command=command)
        try:
            cmd = f"cd {self._remote_work_dir} && {command}"
            async with connection.create_process(wrap_command(cmd)) as process:
                async for line in process.stdout:
                    data = line.rstrip("\n\r")
                    yield OutputEvent(process_id=process_id, data=data, stream="stdout")
                async for line in process.stderr:
                    data = line.rstrip("\n\r")
                    yield OutputEvent(process_id=process_id, data=data, stream="stderr")
                code = process.returncode or 0
                if code == 0:
                    yield ProcessCompletedEvent(process_id=process_id, exit_code=code)
                else:
                    yield ProcessErrorEvent(
                        process_id=process_id,
                        error=f"Command exited with code {code}",
                        error_type="CommandError",
                        exit_code=code,
                    )

        except Exception as e:  # noqa: BLE001
            yield ProcessErrorEvent.failed(e, process_id=process_id)


if __name__ == "__main__":

    async def _main() -> None:
        async with SshExecutionEnvironment("91.99.102.138", "root") as sandbox:
            fs = sandbox.get_fs()
            print(await fs._ls("/"))  # noqa: SLF001

    import asyncio

    asyncio.run(_main())
