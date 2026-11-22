"""Menu bar app: shows each provider's usage and refreshes in the background."""

from __future__ import annotations

import threading
from datetime import datetime

import rumps

from .format import MISSING, header_line, title, window_line
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
        self._usages: list[Usage] = [Usage(name=n, short=s) for n, s, _ in PROVIDERS]
        self._updated: datetime | None = None
        self._rendered_minute: datetime | None = None
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
            self.menu.add(rumps.separator)
        updated = self._updated.strftime("%H:%M") if self._updated else "never"
        self.menu["updated"] = rumps.MenuItem(f"Updated {updated}")
        self.menu["refresh"] = rumps.MenuItem("Refresh now", callback=lambda _: self.refresh(), key="r")
        self.menu["quit"] = rumps.MenuItem("Quit Lanternfish", callback=rumps.quit_application, key="q")


def main() -> None:
    LanternfishApp().run()


if __name__ == "__main__":
    main()
