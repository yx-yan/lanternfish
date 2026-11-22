"""Usage providers. Each one exposes fetch() -> Usage.

fetch() raises ProviderError when it fails (shown in the menu) and NotConfigured when
its credential is not set up (the provider is left out of the menu).
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from . import anthropic_api, claude_sub, codex_sub, deepseek_api, openai_api
from .base import NotConfigured, ProviderError, Usage


@dataclass(frozen=True)
class Provider:
    name: str
    short: str | None                 # menu bar tag; None = menu only
    fetch: Callable[[], Usage]
    key_account: str | None = None    # Keychain account for API keys set from the menu


PROVIDERS: list[Provider] = [
    Provider("Claude", "C", claude_sub.fetch),
    Provider("Codex", "X", codex_sub.fetch),
    Provider("Anthropic API", None, anthropic_api.fetch, anthropic_api.ACCOUNT),
    Provider("OpenAI API", None, openai_api.fetch, openai_api.ACCOUNT),
    Provider("DeepSeek API", None, deepseek_api.fetch, deepseek_api.ACCOUNT),
]


def fetch_all() -> list[Usage]:
    """Fetch every configured provider; a failing one becomes a Usage with .error set."""
    results = []
    for provider in PROVIDERS:
        try:
            results.append(provider.fetch())
        except NotConfigured:
            continue
        except ProviderError as exc:
            results.append(Usage(name=provider.name, short=provider.short, error=str(exc)))
        except Exception as exc:  # unexpected response shape etc.; never crash the app
            results.append(Usage(name=provider.name, short=provider.short,
                                 error=f"unexpected error: {exc.__class__.__name__}"))
    return results
