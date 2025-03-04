"""AnyEnv: A library for environment management and utility functions."""

__version__ = "0.2.0"

from anyenv.async_run import run_sync, run_sync_in_thread
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
)
from anyenv.threadgroup.threadgroup import ThreadGroup
from anyenv.package_install.functional import install, install_sync
from anyenv.testing import open_in_playground

__all__ = [
    "ThreadGroup",
    "download",
    "download_sync",
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
    "open_in_playground",
    "post",
    "post_sync",
    "request",
    "request_sync",
    "run_sync",
    "run_sync_in_thread",
]
