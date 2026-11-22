"""Menu bar app: shows each provider's usage and refreshes in the background."""

from __future__ import annotations

import threading
from datetime import datetime

import rumps

from . import keychain, login, single
from .alerts import AlertTracker
from .format import MISSING, header_line, money_line, title, window_line
from .providers import PROVIDERS, fetch_all
from .providers.base import Usage

REFRESH_SECONDS = 5 * 60


class LanternfishApp(rumps.App):
    def __init__(self) -> None:
        # The Quit item is added in _render, because the menu is rebuilt on every refresh.
        super().__init__("Lanternfish", title="…", quit_button=None)
        self._lock = threading.Lock()
        self._pending: list[Usage] | None = None
        self._fetching = False
        # Before the first fetch, show only the subscription rows as placeholders.
        self._usages: list[Usage] = [Usage(name=p.name, short=p.short) for p in PROVIDERS if p.short]
        self._updated: datetime | None = None
        self._rendered_minute: datetime | None = None
        self._alerts = AlertTracker()
        self._render()
        # Main-thread timers: one kicks off fetches, one applies finished results to the UI.
        self._refresh_timer = rumps.Timer(lambda _: self.refresh(), REFRESH_SECONDS)
        self._apply_timer = rumps.Timer(self._apply_pending, 1)
        self._refresh_timer.start()
        self._apply_timer.start()
        self.refresh()

    def refresh(self) -> None:
        with self._lock:
            if self._fetching:
                return
            self._fetching = True
        threading.Thread(target=self._fetch, daemon=True).start()

    def _fetch(self) -> None:
        usages = fetch_all()
        with self._lock:
            self._pending = usages
            self._fetching = False

    def _apply_pending(self, _timer) -> None:
        with self._lock:
            usages, self._pending = self._pending, None
        if usages is not None:
            self._usages = usages
            self._updated = datetime.now()
            for alert_title, message in self._alerts.check(usages):
                notify(alert_title, message)
        # Redraw when new data arrives, and once a minute so the countdowns stay current.
        minute = datetime.now().replace(second=0, microsecond=0)
        if usages is not None or minute != self._rendered_minute:
            self._render()

    def _render(self) -> None:
        self._rendered_minute = datetime.now().replace(second=0, microsecond=0)
        self.title = title(self._usages)
        self.menu.clear()
        # rumps keys menu items by title; use explicit keys so identical lines
        # (e.g. "— network error" for both providers) do not overwrite each other.
        for usage in self._usages:
            self.menu[f"{usage.name}:header"] = rumps.MenuItem(header_line(usage))
            if usage.error:
                self.menu[f"{usage.name}:error"] = rumps.MenuItem(f"    {MISSING} {usage.error}")
            for i, window in enumerate(usage.windows):
                self.menu[f"{usage.name}:{i}"] = rumps.MenuItem(f"    {window_line(window)}")
            for i, value in enumerate(usage.money):
                self.menu[f"{usage.name}:money{i}"] = rumps.MenuItem(f"    {money_line(value)}")
            self.menu.add(rumps.separator)
        updated = self._updated.strftime("%H:%M") if self._updated else "never"
        self.menu["updated"] = rumps.MenuItem(f"Updated {updated}")
        self.menu["refresh"] = rumps.MenuItem("Refresh now", callback=lambda _: self.refresh(), key="r")
        keys = rumps.MenuItem("API Keys")
        for provider in PROVIDERS:
            if provider.key_account:
                mark = "✓ " if keychain.get(provider.key_account) else ""
                keys[provider.key_account] = rumps.MenuItem(
                    f"{mark}{provider.name}…", callback=self._key_prompt(provider.name, provider.key_account))
        self.menu["keys"] = keys
        if login.app_installed():
            start = rumps.MenuItem("Start at Login", callback=self._toggle_login)
            start.state = login.enabled()
            self.menu["login"] = start
        self.menu["quit"] = rumps.MenuItem("Quit Lanternfish", callback=rumps.quit_application, key="q")

    def _key_prompt(self, name: str, account: str):
        def prompt(_item) -> None:
            response = rumps.Window(
                title=f"{name} key",
                message=KEY_HINTS[account] + "\n\nStored in your macOS Keychain. Leave empty to remove it.",
                default_text="", ok="Save", cancel="Cancel", dimensions=(360, 24), secure=True,
            ).run()
            if not response.clicked:
                return
            secret = response.text.strip()
            if secret:
                keychain.set(account, secret)
            else:
                keychain.delete(account)
            self._render()
            self.refresh()
        return prompt

    def _toggle_login(self, item) -> None:
        if login.enabled():
            login.disable()
        else:
            login.enable()
        item.state = login.enabled()


def notify(title: str, message: str) -> None:
    # Notifications need a bundle identifier, which only the installed .app has.
    try:
        rumps.notification("Lanternfish", title, message)
    except Exception as exc:
        print(f"notification failed: {exc}")


KEY_HINTS = {
    "anthropic-admin": "Admin API key (sk-ant-admin…) from Claude Console → Settings → Admin keys.",
    "openai-admin": "Admin key from OpenAI Platform → Organization → Admin keys.",
    "deepseek": "API key from platform.deepseek.com → API keys.",
}


def main() -> None:
    lock = single.acquire()
    if lock is None:
        print("Lanternfish is already running.")
        raise SystemExit(0)
    LanternfishApp().run()


if __name__ == "__main__":
    main()
