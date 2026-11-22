"""Start at login through a per-user LaunchAgent that opens the installed app."""

from __future__ import annotations

import plistlib
from pathlib import Path

LABEL = "com.yuxuanyan.lanternfish"
APP = "/Applications/Lanternfish.app"
AGENT = Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def app_installed() -> bool:
    return Path(APP).exists()


def enabled(path: Path = AGENT) -> bool:
    return path.exists()


def enable(path: Path = AGENT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as f:
        plistlib.dump({
            "Label": LABEL,
            "ProgramArguments": ["/usr/bin/open", "-a", APP],
            "RunAtLoad": True,
        }, f)


def disable(path: Path = AGENT) -> None:
    path.unlink(missing_ok=True)
