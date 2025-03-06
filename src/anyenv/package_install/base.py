"""Base class for package installation."""

from __future__ import annotations

import abc


class PackageInstaller(abc.ABC):
    """Base class for package installer implementations."""

    @abc.abstractmethod
    async def install(
        self,
        package_name: str,
        version: str | None = None,
        upgrade: bool = False,
    ) -> None:
        """Install a package.

        Args:
            package_name: Name of the package to install.
            version: Optional version specifier. If provided without a comparison
                     operator, '==' will be used.
            upgrade: Whether to upgrade an existing package.
        """
        raise NotImplementedError

    def install_sync(
        self,
        package_name: str,
        version: str | None = None,
        upgrade: bool = False,
    ) -> None:
        """Synchronous version of install."""
        from anyenv.async_run import run_sync

        return run_sync(
            self.install(
                package_name=package_name,
                version=version,
                upgrade=upgrade,
            )
        )
