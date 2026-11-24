"""Menu bar app: shows each provider's usage and refreshes in the background."""

from __future__ import annotations

import threading
import time
from datetime import datetime

import rumps

from . import hotkey, keychain, login, single
from .alerts import STATE_FILE, AlertTracker
from .format import HOTKEY, title, updated_line
from .panel import UsagePanel
from .views import usage_rows
from .providers import PROVIDERS, fetch_all, token_renewed
from .providers.base import Usage
from .retry import RetrySchedule

REFRESH_SECONDS = 5 * 60
CONTROL_OPTION_MASK = (1 << 18) | (1 << 19)   # NSEventModifierFlagControl | Option


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
        self._alerts = AlertTracker(path=STATE_FILE)
        self._retry = RetrySchedule()
        self._panel = UsagePanel()
        self._hotkey = hotkey.register(hotkey.KEY_L, hotkey.CONTROL | hotkey.OPTION, self._toggle_panel)
        self._render()
        # Main-thread timers: one kicks off fetches, one applies finished results to the UI.
        self._refresh_timer = rumps.Timer(lambda _: self.refresh(), REFRESH_SECONDS)
        self._apply_timer = rumps.Timer(self._apply_pending, 1)
        self._refresh_timer.start()
        self._apply_timer.start()
        self.refresh()

    def refresh(self) -> None:
        self._start(self._fetch)

    def _start(self, work) -> None:
        """Run work on a background thread unless a fetch or token check is already running."""
        with self._lock:
            if self._fetching:
                return
            self._fetching = True
        threading.Thread(target=work, daemon=True).start()

    def _fetch(self) -> None:
        usages = fetch_all()
        with self._lock:
            self._pending = usages
            self._fetching = False

    def _check_token(self) -> None:
        try:
            renewed = token_renewed(self._usages)
        except Exception as exc:
            print(f"token check failed: {exc.__class__.__name__}")
            renewed = False
        if renewed:
            self._fetch()
        else:
            with self._lock:
                self._fetching = False

    def _apply_pending(self, _timer) -> None:
        with self._lock:
            usages, self._pending = self._pending, None
        if usages is not None:
            self._usages = usages
            self._updated = datetime.now()
            self._retry.update(usages, time.monotonic())
            for alert_title, message in self._alerts.check(usages):
                notify(alert_title, message)
        # Redraw when new data arrives, and once a minute so the countdowns stay current.
        minute = datetime.now().replace(second=0, microsecond=0)
        if usages is not None or minute != self._rendered_minute:
            self._render()
        if self._fetching:
            return  # keep a due retry for the next tick instead of dropping it
        now = time.monotonic()
        if self._retry.network_due(now):
            self.refresh()
        elif self._retry.token_due(now):
            self._start(self._check_token)

    def _render(self) -> None:
        self._rendered_minute = datetime.now().replace(second=0, microsecond=0)
        self.title = title(self._usages)
        self.menu.clear()
        # rumps keys menu items by title; use explicit keys so identical lines
        # (e.g. "— network error" for both providers) do not overwrite each other.
        for key, text, view in usage_rows(self._usages):
            self._row(key, text, view)
        self.menu.add(rumps.separator)
        self.menu["updated"] = rumps.MenuItem(updated_line(self._updated))
        if self._hotkey:
            show = rumps.MenuItem("Show Panel", callback=lambda _: self._toggle_panel())
            # Display-only shortcut hint; the real hotkey is registered system-wide.
            show._menuitem.setKeyEquivalent_("l")
            show._menuitem.setKeyEquivalentModifierMask_(CONTROL_OPTION_MASK)
            self.menu["panel"] = show
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
        if self._panel.visible:
            self._panel.update(self._usages, self._panel_footer())

    def _toggle_panel(self) -> None:
        self._panel.toggle(self._usages, self._panel_footer())

    def _panel_footer(self) -> str:
        return f"{updated_line(self._updated)}  ·  {HOTKEY} to close"

    def _row(self, key: str, text: str, view) -> None:
        """An info row drawn by a custom view; the plain text stays as the item's title."""
        item = rumps.MenuItem(text)
        item._menuitem.setView_(view)
        self.menu[key] = item

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
