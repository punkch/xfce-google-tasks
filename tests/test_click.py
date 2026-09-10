"""One click or two, and the command line. The pure part: no GTK."""

import datetime as dt
import os
import subprocess
import sys

from conftest import ROOT, WINDOW_ENTRY

from gtasks_panel.ui.click import (classify_click, double_click_threshold,
                                   due_shortcuts, parse_args)


def test_the_first_click_is_single():
    assert classify_click(None, 100.0, 0.4) == "single"


def test_two_clicks_109_ms_apart_are_a_double():
    # Measured on the real panel: genmon ran the command twice, 109 ms apart.
    assert classify_click(100.0, 100.109, 0.4) == "double"


def test_a_gap_at_the_threshold_is_a_new_single_click():
    assert classify_click(100.0, 100.4, 0.4) == "single"


def test_a_long_gap_is_a_new_single_click():
    assert classify_click(100.0, 102.0, 0.4) == "single"


def test_the_second_stamp_may_arrive_first():
    # Two processes race through D-Bus. A small gap is a double click
    # whichever way round the two stamps come in.
    assert classify_click(100.109, 100.0, 0.4) == "double"
    assert classify_click(102.0, 100.0, 0.4) == "single"


def test_the_threshold_is_never_below_400_ms():
    assert double_click_threshold(100) == 0.4
    assert double_click_threshold(None) == 0.5
    assert double_click_threshold(0) == 0.5


def test_the_threshold_is_twice_the_gtk_time():
    assert double_click_threshold(250) == 0.5
    assert double_click_threshold(400) == 0.8


def test_parse_args_reads_the_click_time_in_both_spellings():
    assert parse_args(["--clicked-at=1.5"]) == (1.5, False, False)
    assert parse_args(["--clicked-at", "1.5"]) == (1.5, False, False)


def test_parse_args_survives_a_bad_click_time():
    assert parse_args(["--clicked-at"]) == (None, False, False)
    assert parse_args(["--clicked-at=later"]) == (None, False, False)
    assert parse_args([]) == (None, False, False)


def test_parse_args_reads_the_two_switches():
    assert parse_args(["--window"]) == (None, False, True)
    assert parse_args(["--quit"]) == (None, True, False)
    assert parse_args(["--quit", "--window"]) == (None, True, True)
    assert parse_args(["--nonsense"]) == (None, False, False)


def test_due_shortcuts_names_today_and_tomorrow():
    today = dt.date(2026, 9, 10)
    assert due_shortcuts(today) == {"Today": today, "Tomorrow": dt.date(2026, 9, 11)}
    assert list(due_shortcuts(today)) == ["Today", "Tomorrow"]   # button order


def test_due_shortcuts_crosses_the_end_of_a_month():
    assert due_shortcuts(dt.date(2026, 9, 30))["Tomorrow"] == dt.date(2026, 10, 1)
    assert due_shortcuts(dt.date(2026, 12, 31))["Tomorrow"] == dt.date(2027, 1, 1)


def _run_entry(*args):
    """Run bin/gtasks-window with no display and no GTK modules."""
    env = {**os.environ, "GTK_MODULES": "", "PYTHONPATH": str(ROOT)}
    env.pop("DISPLAY", None)
    env.pop("WAYLAND_DISPLAY", None)
    return subprocess.run([sys.executable, str(WINDOW_ENTRY), *args],
                          capture_output=True, text=True, env=env, timeout=30)


def test_the_window_entry_answers_help_without_gtk():
    done = _run_entry("--help")
    assert done.returncode == 0
    assert "--version" in done.stdout and "--quit" in done.stdout


def test_the_window_entry_answers_version_without_gtk():
    done = _run_entry("--version")
    assert done.returncode == 0
    assert done.stdout.startswith("gtasks-window ")
