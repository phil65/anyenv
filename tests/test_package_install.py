import importlib.machinery
import sys
import types
from typing import TYPE_CHECKING

import anyenv


if TYPE_CHECKING:
    import pytest


async def test_install_uses_micropip_under_pyodide(monkeypatch: pytest.MonkeyPatch) -> None:
    """Under Pyodide (sys.platform == 'emscripten'), install() delegates to micropip."""
    installed: list[str] = []
    uninstalled: list[str] = []

    async def fake_install(spec: str) -> None:
        installed.append(spec)

    micropip = types.ModuleType("micropip")
    micropip.__spec__ = importlib.machinery.ModuleSpec("micropip", None)
    micropip.install = fake_install  # type: ignore[attr-defined]
    micropip.uninstall = uninstalled.append  # type: ignore[attr-defined]

    monkeypatch.setitem(sys.modules, "micropip", micropip)
    monkeypatch.setattr(sys, "platform", "emscripten")

    # Package not yet installed
    await anyenv.install("definitely-not-installed-pkg", version="1.2.3")
    assert installed == ["definitely-not-installed-pkg==1.2.3"]
    assert uninstalled == []

    # Upgrade an already-installed package (anyenv itself is installed)
    await anyenv.install("anyenv", upgrade=True)
    assert uninstalled == ["anyenv"]
    assert installed[-1] == "anyenv"
