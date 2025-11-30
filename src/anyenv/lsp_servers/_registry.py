"""Registry for LSP servers."""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from pathlib import Path

    from anyenv.lsp_servers._base import LSPServerInfo


class LSPServerRegistry:
    """Registry for managing LSP server configurations."""

    def __init__(self) -> None:
        self._servers: list[LSPServerInfo] = []

    def register(self, server: LSPServerInfo) -> None:
        """Register an LSP server."""
        self._servers.append(server)

    def register_defaults(self) -> None:
        """Register all default LSP servers."""
        from anyenv.lsp_servers._servers import ALL_SERVERS

        for server in ALL_SERVERS:
            self.register(server)

    def get_by_id(self, server_id: str) -> LSPServerInfo | None:
        """Get server by ID."""
        return next((s for s in self._servers if s.id == server_id), None)

    def get_by_extension(self, extension: str) -> list[LSPServerInfo]:
        """Get all servers that handle a given file extension."""
        return [s for s in self._servers if s.can_handle(extension)]

    def get_for_file(self, path: Path) -> list[LSPServerInfo]:
        """Get all servers that can handle a given file."""
        return self.get_by_extension(path.suffix)

    def get_by_command(self, command: str) -> LSPServerInfo | None:
        """Get server by command name."""
        return next((s for s in self._servers if s.command == command), None)

    def get_installable(self) -> list[LSPServerInfo]:
        """Get all servers that can be auto-installed."""
        return [s for s in self._servers if s.has_auto_install]

    @property
    def all_servers(self) -> list[LSPServerInfo]:
        """Get all registered servers."""
        return list(self._servers)

    def get_supported_extensions(self) -> set[str]:
        """Get all supported file extensions."""
        return {ext for server in self._servers for ext in server.extensions}
