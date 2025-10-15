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


from anyenv.async_run import run_sync, run_sync_in_thread, gather, run_in_thread
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
from anyenv.calling import ThreadGroup, method_spawner, function_spawner
from anyenv.package_install.functional import install, install_sync
from anyenv.testing import open_in_playground
from anyenv.json_tools import load_json, JsonLoadError, dump_json, JsonDumpError
from anyenv.download.base import HttpBackend, HttpResponse, Session

__all__ = [
    "HttpBackend",
    "HttpError",
    "HttpResponse",
    "JsonDumpError",
    "JsonLoadError",
    "RequestError",
    "ResponseError",
    "Session",
    "ThreadGroup",
    "__version__",
    "download",
    "download_sync",
    "dump_json",
    "function_spawner",
    "gather",
    "get",
    "get_backend",
    "get_bytes",
    "get_bytes_sync",
    "get_json",
    "get_json_sync",
    "get_sync",
    "get_text",
    "get_text_sync",
    "install",
    "install_sync",
    "load_json",
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
