"""Pip package installer implementation."""

from __future__ import annotations

import importlib
import importlib.metadata
import sys

from anyenv.package_install.base import PackageInstaller


class PipInstaller(PackageInstaller):
    """Package installer using pip."""

    async def install(
        self,
        package_name: str,
        version: str | None = None,
        upgrade: bool = False,
    ) -> None:
        """Install a package using pip.

        Args:
            package_name: Name of the package to install.
            version: Optional version specifier.
            upgrade: Whether to upgrade an existing package.
        """
        # Format the package name with version if specified
        if version:
            if version[0] not in ("=", "<", ">", "!"):
                version = "==" + version
            package_spec = f"{package_name}{version}"
        else:
            package_spec = package_name

        # Build the command
        args = ["install", package_spec]
        if upgrade:
            args.append("--upgrade")

        # Run pip in a separate process to avoid blocking the event loop
        cmd = [sys.executable, "-m", "pip", *args]
        print(f"Running: {' '.join(cmd)}")

        # Use anyio's run_process
        import subprocess

        import anyio

        try:
            # When check=True, run_process raises CalledProcessError on non-zero exit
            process = await anyio.run_process(cmd, check=True)
            # Output is available in process.stdout
            print(process.stdout.decode())
            # Reload the package if it was upgraded
            if upgrade:
                self._reload_package(package_name)

        except subprocess.CalledProcessError as e:
            error_msg = e.stderr.decode() if e.stderr else str(e)
            msg = f"Pip installation failed: {error_msg}"
            raise RuntimeError(msg) from e

    def _reload_package(self, package_name: str) -> None:
        """Attempt to reload a package's modules after installation."""
        try:
            dist = importlib.metadata.distribution(package_name)
            if top_level_content := dist.read_text("top_level.txt"):
                top_level_modules = top_level_content.splitlines()
                for mod in top_level_modules:
                    if mod not in sys.modules:
                        continue
                    try:
                        importlib.reload(sys.modules[mod])
                    except Exception as e:  # noqa: BLE001
                        print(f"Warning: Failed to reload module {mod}: {e}")
        except Exception as e:  # noqa: BLE001
            print(f"Warning: Failed to reload package {package_name}: {e}")
