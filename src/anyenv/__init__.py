"""AnyEnv: main package.

Compatibility layer for some basic operations to allow painless operation in PyOdide
and Python pre-releases.
"""

from __future__ import annotations

from importlib.metadata import version

__version__ = version("anyenv")
__title__ = "AnyEnv"

__author__ = "Philipp Temminghoff"
__author_email__ = "philipptemminghoff@googlemail.com"
__copyright__ = "Copyright (c) 2025 Philipp Temminghoff"
__license__ = "MIT"
__url__ = "https://github.com/phil65/anyenv"


from anyenv.async_run import (
    run_sync,
    run_sync_in_thread,
    gather,
    run_in_thread,
    call_and_gather,
)
from anyenv.download.functional import (
    download,
    download_sync,
    get,
    get_backend,
    get_bytes,
    get_bytes_sync,
    get_json,
    get_json_sync,
    get_sync,
    get_text,
    get_text_sync,
    post,
    post_sync,
    request,
    request_sync,
    post_json,
    post_json_sync,
)
from anyenv.download.exceptions import RequestError, ResponseError, HttpError
from anyenv.calling import (
    ThreadGroup,
    method_spawner,
    function_spawner,
    MultiEventHandler,
)
from anyenv.package_install.functional import install, install_sync
from anyenv.testing import open_in_playground
from anyenv.json_tools import load_json, JsonLoadError, dump_json, JsonDumpError
from anyenv.toml_tools import load_toml, TomlLoadError, dump_toml, TomlDumpError
from anyenv.download.base import HttpBackend, HttpResponse, Session
from anyenv.code_execution import get_environment
from anyenv.code_execution.remote_callable import create_remote_callable
from anyenv.code_execution.base import ExecutionEnvironment
from anyenv.os_commands import get_os_command_provider
from anyenv.process_manager import ProcessManager, ProcessOutput, RunningProcess
from anyenv.processes import create_process, create_shell_process

__all__ = [
    "ExecutionEnvironment",
    "HttpBackend",
    "HttpError",
    "HttpResponse",
    "JsonDumpError",
    "JsonLoadError",
    "MultiEventHandler",
    "ProcessManager",
    "ProcessOutput",
    "RequestError",
    "ResponseError",
    "RunningProcess",
    "Session",
    "ThreadGroup",
    "TomlDumpError",
    "TomlLoadError",
    "__version__",
    "call_and_gather",
    "create_process",
    "create_remote_callable",
    "create_shell_process",
    "download",
    "download_sync",
    "dump_json",
    "dump_toml",
    "function_spawner",
    "gather",
    "get",
    "get_backend",
    "get_bytes",
    "get_bytes_sync",
    "get_environment",
    "get_json",
    "get_json_sync",
    "get_os_command_provider",
    "get_sync",
    "get_text",
    "get_text_sync",
    "install",
    "install_sync",
    "load_json",
    "load_toml",
    "method_spawner",
    "open_in_playground",
    "post",
    "post_json",
    "post_json_sync",
    "post_sync",
    "request",
    "request_sync",
    "run_in_thread",
    "run_sync",
    "run_sync_in_thread",
]
