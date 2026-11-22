"""API keys stored in the macOS login Keychain under the service "lanternfish"."""

from __future__ import annotations

import subprocess

SERVICE = "lanternfish"


def get(account: str) -> str | None:
    result = subprocess.run(
        ["security", "find-generic-password", "-s", SERVICE, "-a", account, "-w"],
        capture_output=True, text=True, timeout=10,
    )
    value = result.stdout.strip()
    return value if result.returncode == 0 and value else None


def set(account: str, secret: str) -> None:  # noqa: A001 - mirrors get()
    subprocess.run(
        ["security", "add-generic-password", "-U", "-s", SERVICE, "-a", account, "-w", secret],
        capture_output=True, check=True, timeout=10,
    )


def delete(account: str) -> None:
    subprocess.run(
        ["security", "delete-generic-password", "-s", SERVICE, "-a", account],
        capture_output=True, timeout=10,
    )
