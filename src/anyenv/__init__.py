"""AnyEnv: A library for environment management and utility functions."""

__version__ = "0.1.0"

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

__all__ = [
    # ThreadGroup
    "ThreadGroup",
    # Download functionality
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
    "post",
    "post_sync",
    "request",
    "request_sync",
    # Async utilities
    "run_sync",
    "run_sync_in_thread",
]
