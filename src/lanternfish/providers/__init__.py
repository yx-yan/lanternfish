"""Usage providers. Each one exposes fetch() -> Usage and raises ProviderError on failure."""

from __future__ import annotations

from collections.abc import Callable

from . import claude_sub, codex_sub
from .base import ProviderError, Usage

# (display name, menu bar tag, fetch function), in menu order
PROVIDERS: list[tuple[str, str, Callable[[], Usage]]] = [
    ("Claude", "C", claude_sub.fetch),
    ("Codex", "X", codex_sub.fetch),
]


def fetch_all() -> list[Usage]:
    """Fetch every provider; a failing one becomes a Usage with .error set."""
    results = []
    for name, short, fetch in PROVIDERS:
        try:
            results.append(fetch())
        except ProviderError as exc:
            results.append(Usage(name=name, short=short, error=str(exc)))
        except Exception as exc:  # unexpected response shape etc.; never crash the app
            results.append(Usage(name=name, short=short, error=f"unexpected error: {exc.__class__.__name__}"))
    return results
