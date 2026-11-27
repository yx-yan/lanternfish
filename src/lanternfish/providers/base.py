"""Shared types and HTTP helper for usage providers."""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime

USER_AGENT = "lanternfish/0.1"
TIMEOUT_SECONDS = 15


class ProviderError(Exception):
    """A provider could not produce usage; the message is shown in the menu."""


class NetworkError(ProviderError):
    """The endpoint could not be reached; worth retrying soon."""


class TokenExpired(ProviderError):
    """The stored token has expired; worth retrying once its owner renews it."""


class NotConfigured(Exception):
    """The provider has no credential set up; it is left out of the menu entirely."""


@dataclass
class Window:
    label: str                     # "5-hour", "Weekly"
    used_percent: float
    resets_at: datetime | None     # timezone-aware


@dataclass
class Money:
    label: str                     # "This month", "Balance"
    amount: float
    currency: str                  # ISO code, e.g. "USD", "CNY"


@dataclass
class Usage:
    name: str                      # "Claude", "Codex", "Anthropic API"
    short: str | None              # tag for the menu bar title; None keeps it out of the title
    windows: list[Window] = field(default_factory=list)
    money: list[Money] = field(default_factory=list)
    plan: str | None = None
    error: str | None = None
    network_error: bool = False
    token_expired: bool = False

    @property
    def primary(self) -> Window | None:
        return self.windows[0] if self.windows else None


def get_json(url: str, headers: dict[str, str]) -> dict:
    """GET a JSON endpoint, turning network and HTTP failures into ProviderError."""
    return _send(urllib.request.Request(url, headers={"User-Agent": USER_AGENT, **headers}))


def post_json(url: str, body: dict, headers: dict[str, str]) -> dict:
    """POST a JSON body to a JSON endpoint, with the same error handling as get_json."""
    return _send(urllib.request.Request(url, data=json.dumps(body).encode(), headers={
        "User-Agent": USER_AGENT, "Content-Type": "application/json", **headers}))


def _send(request: urllib.request.Request) -> dict:
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        if exc.code in (401, 403):
            raise ProviderError(f"auth rejected (HTTP {exc.code})") from exc
        raise ProviderError(f"HTTP {exc.code}") from exc
    except (urllib.error.URLError, TimeoutError) as exc:
        raise NetworkError("network error") from exc
    except json.JSONDecodeError as exc:
        raise ProviderError("bad response") from exc
