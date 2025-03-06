"""Functional API for package installation."""

from __future__ import annotations

import importlib.util
import sys
from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from anyenv.package_install.base import PackageInstaller


def _is_pyodide() -> bool:
    """Check if running in a Pyodide environment."""
    return sys.platform == "emscripten"


async def install(
    package_name: str,
    version: str | None = None,
    upgrade: bool = False,
) -> None:
    """Install a package using the appropriate installer for the current environment.

    Args:
        package_name: Name of the package to install.
        version: Optional version specifier.
        upgrade: Whether to upgrade an existing package.

    Raises:
        ImportError: If no suitable installer is available.
    """
    # Format version string if needed
    if version and version[0] not in ("=", "<", ">", "!"):
        version = "==" + version

    # Choose installer based on environment
    if _is_pyodide() and importlib.util.find_spec("micropip"):
        from anyenv.package_install.micropip_install import MicropipInstaller

        installer: PackageInstaller = MicropipInstaller()
        await installer.install(package_name, version, upgrade)
        return

    # Default to pip if available
    if importlib.util.find_spec("pip"):
        from anyenv.package_install.pip_install import PipInstaller

        installer = PipInstaller()
        await installer.install(package_name, version, upgrade)
        return

    msg = (
        "No suitable package installer found. "
        "Please install either pip or run in a Pyodide environment."
    )
    raise ImportError(msg)


def install_sync(
    package_name: str,
    version: str | None = None,
    upgrade: bool = False,
) -> None:
    """Synchronous version of install."""
    from anyenv.async_run import run_sync

    return run_sync(install(package_name=package_name, version=version, upgrade=upgrade))
