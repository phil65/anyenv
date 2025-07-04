"""AnyEnv: A library for environment management and utility functions."""

__version__ = "0.4.17"

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
from anyenv.threadgroup.threadgroup import ThreadGroup
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
    "download",
    "download_sync",
    "dump_json",
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
