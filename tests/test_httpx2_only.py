"""anyenv must work with only httpx2 installed (legacy httpx not importable)."""

import importlib.util
import os
import subprocess
import sys
import textwrap

import pytest


pytestmark = pytest.mark.skipif(
    not importlib.util.find_spec("httpx2"), reason="httpx2 not installed"
)

_SCRIPT = textwrap.dedent(
    """
    import importlib.abc
    import sys
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer


    class BlockHttpx(importlib.abc.MetaPathFinder):
        def find_spec(self, name, path=None, target=None):
            if name.partition(".")[0] in {"httpx", "httpcore"}:
                raise ModuleNotFoundError(f"No module named {name!r} (blocked)")
            return None


    sys.meta_path.insert(0, BlockHttpx())

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = b'{"ok": true}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}/json"

    import anyenv
    import anyenv.text_sharing
    from anyenv.download import httpx_backend
    from anyenv.download.session import CacheSettings, create_client
    from anyenv.text_sharing.opencode import OpenCodeSharer

    assert create_client(CacheSettings.create(False))[1].__name__ == "httpx2"
    assert anyenv.get_json_sync(url) == {"ok": True}
    assert anyenv.get_json_sync(url, cache=True) == {"ok": True}
    assert anyenv.get_bytes_sync(url) == b'{"ok": true}'
    assert httpx_backend.JSTransport.__mro__[1].__module__.startswith("httpx2")
    assert OpenCodeSharer()._httpx.__name__ == "httpx2"  # noqa: SLF001
    assert "httpx" not in sys.modules
    server.shutdown()
    print("OK")
    """
)


def test_works_without_legacy_httpx(tmp_path) -> None:
    """Import anyenv and download with httpx blocked via a meta path finder."""
    proc = subprocess.run(
        [sys.executable, "-c", _SCRIPT],
        capture_output=True,
        text=True,
        timeout=60,
        cwd=tmp_path,
        # Keep the inherited env (Windows sockets need SYSTEMROOT); isolate the cache dirs.
        env={**os.environ, "XDG_CACHE_HOME": str(tmp_path), "LOCALAPPDATA": str(tmp_path)},
    )
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip() == "OK"


def test_js_transport_and_client_follow_flavour(httpx_flavour: str) -> None:
    """JSTransport and clients are built on the selected httpx flavour."""
    from anyenv.download.httpx_backend import get_js_transport_class
    from anyenv.download.session import CacheSettings, create_client

    mod = importlib.import_module(httpx_flavour)
    assert issubclass(get_js_transport_class(httpx_flavour), mod.AsyncBaseTransport)
    client, client_mod = create_client(CacheSettings.create(False))
    assert client_mod is mod
    assert isinstance(client, mod.AsyncClient)
