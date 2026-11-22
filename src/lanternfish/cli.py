"""`lanternfish`: print current usage once, for checking without the menu bar."""

from __future__ import annotations

from .format import report
from .providers import fetch_all


def main() -> None:
    print(report(fetch_all()))


if __name__ == "__main__":
    main()
