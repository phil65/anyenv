"""Micropip package installer implementation for Pyodide environments."""

from __future__ import annotations

import importlib
import importlib.metadata

from anyenv.package_install.base import PackageInstaller


class MicropipInstaller(PackageInstaller):
    """Package installer using micropip in Pyodide environments."""

    def __init__(self) -> None:
        """Initialize the micropip installer.

        Raises:
            ImportError: If micropip is not available.
        """
        try:
            import micropip  # type: ignore

            self._micropip = micropip
        except ImportError:
            msg = (
                "micropip is not available. "
                "This installer only works in Pyodide environments."
            )
            raise ImportError(msg)  # noqa: B904

    async def install(
        self,
        package_name: str,
        version: str | None = None,
        upgrade: bool = False,
    ) -> None:
        """Install a package using micropip.

        Args:
            package_name: Name of the package to install.
            version: Optional version specifier.
            upgrade: Whether to upgrade an existing package.
        """
        # Check if the package is already installed
        try:
            importlib.metadata.distribution(package_name)
            if upgrade:
                # Uninstall the package first if upgrading
                self._micropip.uninstall(package_name)
            else:
                # Package already installed and not upgrading, so nothing to do
                return
        except importlib.metadata.PackageNotFoundError:
            pass  # Package not installed, continue with installation

        # Format the package name with version if specified
        if version:
            if version[0] not in ("=", "<", ">", "!"):
                version = "==" + version
            package_spec = f"{package_name}{version}"
        else:
            package_spec = package_name

        # Install the package
        print(f"Installing {package_spec} with micropip...")
        await self._micropip.install(package_spec)
        print(f"Successfully installed {package_spec}")
