import plistlib
from datetime import datetime, timedelta, timezone

from lanternfish import login
from lanternfish.alerts import AlertTracker
from lanternfish.providers.base import Usage, Window

RESET = datetime(2026, 11, 22, 12, tzinfo=timezone.utc)


def usage(percent, resets_at=RESET):
    return [Usage("Claude", "C", windows=[Window("5-hour", percent, resets_at)])]


def titles(tracker, percent, resets_at=RESET):
    return [title for title, _ in tracker.check(usage(percent, resets_at))]


def test_each_level_alerts_once():
    tracker, seen = AlertTracker(), []
    for used in (75, 79, 80, 85, 89, 90, 94, 95, 99, 100, 100):
        seen += titles(tracker, used)
    assert seen == [f"Claude 5-hour: {left}% left" for left in (20, 10, 5, 0)]


def test_skipped_levels_give_one_alert():
    tracker = AlertTracker()
    assert titles(tracker, 96) == ["Claude 5-hour: 4% left"]
    assert titles(tracker, 97) == []
    assert titles(tracker, 100) == ["Claude 5-hour: 0% left"]


def test_reset_alerts_once_then_levels_start_over():
    tracker, later = AlertTracker(), RESET + timedelta(hours=5)
    titles(tracker, 100)
    assert titles(tracker, 0, later) == ["Claude 5-hour: reset, 100% left"]
    assert titles(tracker, 1, later) == []
    assert titles(tracker, 80, later) == ["Claude 5-hour: 20% left"]


def test_reset_is_quiet_if_the_window_never_ran_low():
    tracker = AlertTracker()
    assert titles(tracker, 70) == []
    assert titles(tracker, 0, RESET + timedelta(hours=5)) == []


def test_reset_without_a_reset_time():
    tracker = AlertTracker()
    titles(tracker, 100)
    assert tracker.check(usage(0, None)) == [("Claude 5-hour: reset, 100% left", "Ready to use.")]
    assert titles(tracker, 0, None) == []


def test_new_window_already_low_gives_only_the_low_alert():
    tracker = AlertTracker()
    titles(tracker, 100)
    assert titles(tracker, 85, RESET + timedelta(hours=5)) == ["Claude 5-hour: 15% left"]


def test_jitter_and_small_dips_do_not_alert_again():
    tracker = AlertTracker()
    titles(tracker, 85)
    for seconds in (-1, 0.2, 0.9, 60):
        assert titles(tracker, 86, RESET + timedelta(seconds=seconds)) == []
    assert titles(tracker, 79) == []
    assert titles(tracker, 81) == []
    assert titles(tracker, 86, None) == []


def test_unknown_reset_time_is_filled_in_later():
    tracker = AlertTracker()
    assert len(titles(tracker, 85, None)) == 1
    assert titles(tracker, 86) == []
    assert len(titles(tracker, 0, RESET + timedelta(hours=5))) == 1


def test_alerts_are_remembered_across_restarts(tmp_path):
    path = tmp_path / "Lanternfish" / "alerts.json"
    titles(AlertTracker(path), 85)
    assert titles(AlertTracker(path), 86, RESET + timedelta(seconds=0.5)) == []
    assert len(titles(AlertTracker(path), 91)) == 1
    later = RESET + timedelta(hours=5)
    assert titles(AlertTracker(path), 0, later) == ["Claude 5-hour: reset, 100% left"]
    assert titles(AlertTracker(path), 0, later) == []


def test_damaged_alert_state_is_ignored(tmp_path):
    path = tmp_path / "alerts.json"
    for text in ("{", "[]", '{"a": 3}', '{"a": [20, "soon"]}', '{"a": [33, null]}', '{"a": [20, "2026-11-22"]}'):
        path.write_text(text)
        assert len(titles(AlertTracker(path), 85)) == 1


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
