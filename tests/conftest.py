"""Pytest fixtures and utilities."""

import importlib.util

import pytest


FLAVOURS = [
    pytest.param(
        name,
        marks=pytest.mark.skipif(
            not (importlib.util.find_spec(name) and importlib.util.find_spec("hishel")),
            reason=f"{name} not installed",
        ),
    )
    for name in ("httpx2", "httpx")
]


@pytest.fixture(params=FLAVOURS)
def httpx_flavour(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """Run a test once per installed httpx flavour (httpx2, legacy httpx)."""
    from anyenv.download.httpx_backend import module

    monkeypatch.setattr(module, "HTTPX_MODULE_NAMES", (request.param,))
    return request.param
