import plistlib
from datetime import datetime, timedelta, timezone

from lanternfish import login
from lanternfish.alerts import AlertTracker
from lanternfish.providers.base import Usage, Window

RESET = datetime(2026, 11, 22, 12, tzinfo=timezone.utc)


def usage(percent, resets_at=RESET):
    return [Usage("Claude", "C", windows=[Window("5-hour", percent, resets_at)])]


def test_alert_fires_once_per_window():
    tracker = AlertTracker()
    assert tracker.check(usage(79)) == []
    first = tracker.check(usage(81))
    assert len(first) == 1 and first[0][0] == "Claude 5-hour at 81%"
    assert tracker.check(usage(95)) == []  # same window, already told


def test_alert_fires_again_after_reset():
    tracker = AlertTracker()
    tracker.check(usage(90))
    assert len(tracker.check(usage(85, RESET + timedelta(hours=5)))) == 1


def test_errors_and_money_rows_never_alert():
    assert AlertTracker().check([Usage("Codex", "X", error="network error")]) == []


def test_login_agent_round_trip(tmp_path):
    path = tmp_path / "LaunchAgents" / "agent.plist"
    assert not login.enabled(path)
    login.enable(path)
    agent = plistlib.loads(path.read_bytes())
    assert agent["RunAtLoad"] is True
    assert agent["ProgramArguments"] == ["/usr/bin/open", "-a", "/Applications/Lanternfish.app"]
    login.disable(path)
    assert not login.enabled(path)
    login.disable(path)  # already gone is fine


def test_single_instance_lock(tmp_path):
    import os

    from lanternfish import single

    path = tmp_path / "app.lock"
    first = single.acquire(path)
    assert first is not None
    assert single.acquire(path) is None  # a second launch is refused
    os.close(first)                       # the first instance exits
    again = single.acquire(path)
    assert again is not None
    os.close(again)
