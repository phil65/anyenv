"""Configuration for sandbox restrictions."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class SandboxConfig(BaseModel):
    """Configuration for sandbox-runtime restrictions."""

    # Network settings
    allowed_domains: list[str] = Field(
        default_factory=list,
        title="Allowed Domains",
        examples=[["github.com", "*.github.com", "pypi.org"]],
    )
    """Domains that can be accessed. Empty = no network access."""

    denied_domains: list[str] = Field(
        default_factory=list,
        title="Denied Domains",
        examples=[["malicious.com"]],
    )
    """Domains explicitly blocked (checked before allowed_domains)."""

    allow_unix_sockets: list[str] = Field(
        default_factory=list,
        title="Allowed Unix Sockets",
        examples=[["/var/run/docker.sock"]],
    )
    """Specific Unix socket paths to allow (e.g., Docker socket)."""

    allow_all_unix_sockets: bool = Field(default=False, title="Allow All Unix Sockets")
    """Allow all Unix sockets (less secure)."""

    allow_local_binding: bool = Field(default=False, title="Allow Local Binding")
    """Allow binding to localhost ports."""

    # Filesystem read settings (deny-only pattern)
    deny_read: list[str] = Field(
        default_factory=lambda: ["~/.ssh", "~/.aws", "~/.gnupg"],
        title="Deny Read Paths",
        examples=[["~/.ssh", "~/.aws"]],
    )
    """Paths blocked from reading. Empty = full read access."""

    # Filesystem write settings (allow-only pattern)
    allow_write: list[str] = Field(
        default_factory=lambda: ["."],
        title="Allow Write Paths",
        examples=[["."], [".", "/tmp"]],
    )
    """Paths where writes are permitted. Empty = no write access."""

    deny_write: list[str] = Field(
        default_factory=list,
        title="Deny Write Paths",
        examples=[[".env", "secrets/"]],
    )
    """Paths denied within allowed write paths."""

    def to_srt_settings(self) -> dict[str, dict[str, Any]]:
        """Convert to srt-settings.json format."""
        return {
            "network": {
                "allowedDomains": self.allowed_domains,
                "deniedDomains": self.denied_domains,
                "allowUnixSockets": self.allow_unix_sockets,
                "allowAllUnixSockets": self.allow_all_unix_sockets,
                "allowLocalBinding": self.allow_local_binding,
            },
            "filesystem": {
                "denyRead": self.deny_read,
                "allowWrite": self.allow_write,
                "denyWrite": self.deny_write,
            },
        }
