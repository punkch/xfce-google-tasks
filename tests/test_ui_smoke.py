"""GTK smoke tests for the popup and the main window.

They open real windows, so they run only when asked:

    GTASKS_UI_TESTS=1 xvfb-run -a python3 -m pytest tests/test_ui_smoke.py

A DISPLAY gate is not enough: `make deb` runs the test suite with the
desktop DISPLAY set and would put windows on the user's screen.
"""

import datetime as dt
import os

import pytest
from conftest import default_cfg, pump

pytest.importorskip("gi")
if os.environ.get("GTASKS_UI_TESTS") != "1":
    pytest.skip("set GTASKS_UI_TESTS=1 to run the UI tests", allow_module_level=True)

import gi  # noqa: E402

gi.require_version("Gtk", "3.0")

from gi.repository import Gtk  # noqa: E402

from gtasks_panel.model import Task, TaskList  # noqa: E402
from gtasks_panel.paths import AUTH_NO_TOKEN  # noqa: E402
from gtasks_panel.ui.mainwindow import MainWindow  # noqa: E402
from gtasks_panel.ui.popup import Popup  # noqa: E402
from gtasks_panel.ui.store import TaskStore  # noqa: E402
from gtasks_panel.ui.widgets import TaskRow  # noqa: E402

TODAY = dt.date(2026, 9, 10)


class FakeWorker:
    """Records the jobs the windows post. Nothing reaches Google."""

    def __init__(self):
        self.calls = []

    def complete(self, task):
        self.calls.append(("complete", task.id))

    def uncomplete(self, task):
        self.calls.append(("uncomplete", task.id))

    def add(self, list_id, title):
        self.calls.append(("add", list_id, title))

    def patch(self, task, **fields):
        self.calls.append(("patch", task.id, fields))

    def move(self, task, destination_list_id):
        self.calls.append(("move", task.id, destination_list_id))

    def delete(self, task, index=-1):
        self.calls.append(("delete", task.id))

    def reload(self):
        self.calls.append(("reload", None))
        return True

    def reset_service(self):
        self.calls.append(("reset", None))


def two_lists():
    return [
        TaskList(id="L1", title="Work", tasks=[
            Task(id="t1", list_id="L1", title="Write the report",
                 due=TODAY - dt.timedelta(days=1), position="00001"),
            Task(id="t2", list_id="L1", title="Call the bank", position="00002"),
        ]),
        TaskList(id="L2", title="Home", tasks=[
            Task(id="t3", list_id="L2", title="Buy milk", due=TODAY,
                 position="00001"),
        ]),
    ]


@pytest.fixture
def parts(mod):
    """Store, fake worker and the default list, with paths under tmp_path."""
    store = TaskStore()
    store.set_lists(two_lists())
    return store, FakeWorker(), default_cfg(default_list="Home")["default_list"]


def task_rows(list_box):
    return [row for row in list_box.get_children() if isinstance(row, TaskRow)]


def test_the_popup_shows_one_row_for_each_open_task(parts):
    store, worker, default_list = parts
    popup = Popup(store, worker, default_list, lambda: None, lambda: None)
    assert len(task_rows(popup.list_box)) == 3
    popup.destroy()


def test_checking_a_row_posts_a_complete_job(parts):
    store, worker, default_list = parts
    popup = Popup(store, worker, default_list, lambda: None, lambda: None)
    rows = task_rows(popup.list_box)
    rows[0].check.set_active(True)
    assert ("complete", rows[0].task.id) in worker.calls
    popup.destroy()


def test_enter_in_the_quick_add_posts_an_add_job_for_the_default_list(parts):
    store, worker, default_list = parts
    popup = Popup(store, worker, default_list, lambda: None, lambda: None)
    popup.entry.set_text("New thing")
    popup.entry.emit("activate")
    assert worker.calls == [("add", "L2", "New thing")]  # default_list = Home
    assert popup.entry.get_text() == ""
    popup.destroy()


def test_a_chosen_list_wins_over_the_default_list(parts):
    store, worker, default_list = parts
    store.set_selected("L1")
    popup = Popup(store, worker, default_list, lambda: None, lambda: None)
    popup.entry.set_text("Another thing")
    popup.entry.emit("activate")
    assert worker.calls == [("add", "L1", "Another thing")]
    popup.destroy()


def test_the_popup_swaps_to_the_sign_in_page(parts):
    store, worker, default_list = parts
    popup = Popup(store, worker, default_list, lambda: None, lambda: None)
    store.set_auth(AUTH_NO_TOKEN)
    pump()
    assert popup.stack.get_visible_child() is popup.signin_page
    assert popup.signin_page.verdict == AUTH_NO_TOKEN
    popup.destroy()


def test_the_open_window_button_calls_back(parts):
    store, worker, default_list = parts
    opened = []
    popup = Popup(store, worker, default_list, lambda: opened.append(True), lambda: None)
    popup.open_button.clicked()
    assert opened == [True]
    popup.destroy()


def test_the_popup_counts_the_open_and_overdue_tasks(parts):
    store, worker, default_list = parts
    popup = Popup(store, worker, default_list, lambda: None, lambda: None)
    assert popup.status.get_text() == "3 open, 1 overdue"
    popup.destroy()


def test_the_popup_names_each_list_above_its_tasks(parts):
    store, worker, default_list = parts
    popup = Popup(store, worker, default_list, lambda: None, lambda: None)
    headers = [row.get_header().get_text() for row in task_rows(popup.list_box)
               if row.get_header() is not None]
    assert headers == ["Work", "Home"]
    store.set_selected("L1")
    pump()
    assert all(row.get_header() is None for row in task_rows(popup.list_box))
    popup.destroy()


def test_offline_keeps_the_quick_add_readable(parts):
    store, worker, default_list = parts
    popup = Popup(store, worker, default_list, lambda: None, lambda: None)
    store.set_offline(True, "no network")
    pump()
    assert popup.entry.get_sensitive() is True
    assert popup.entry.get_editable() is False
    popup.destroy()


def test_the_main_window_sidebar_has_a_row_for_each_list(parts):
    store, worker, default_list = parts
    window = MainWindow(store, worker, default_list, lambda: None)
    titles = [row.list_id for row in window.list_box.get_children()]
    assert titles == [None, "L1", "L2"]  # None is the "All lists" row
    assert len(task_rows(window.task_box)) == 3
    window.destroy()


def test_the_main_window_detail_pane_patches_the_title(parts):
    store, worker, default_list = parts
    window = MainWindow(store, worker, default_list, lambda: None)
    row = task_rows(window.task_box)[0]
    window.task_box.select_row(row)
    window.title_entry.set_text("A new title")
    window.title_entry.emit("activate")
    assert ("patch", row.task.id, {"title": "A new title"}) in worker.calls
    window.destroy()


def test_offline_keeps_the_task_text_readable(parts):
    store, worker, default_list = parts
    window = MainWindow(store, worker, default_list, lambda: None)
    store.set_offline(True, "no network")
    pump()
    assert window.title_entry.get_sensitive() is True
    assert window.title_entry.get_editable() is False
    assert window.notes_view.get_editable() is False
    assert window.delete_button.get_sensitive() is False
    window.destroy()


def test_show_completed_off_asks_google_for_nothing(parts):
    store, worker, default_list = parts
    window = MainWindow(store, worker, default_list, lambda: None)
    window.completed_toggle.set_active(True)
    assert ("reload", None) in worker.calls   # the completed tasks are not here yet
    worker.calls.clear()
    store.has_completed = True
    window.completed_toggle.set_active(False)
    window.completed_toggle.set_active(True)
    assert worker.calls == []                 # already read: no second query
    window.destroy()


def test_deleting_a_task_waits_behind_the_undo_bar(parts):
    store, worker, default_list = parts
    window = MainWindow(store, worker, default_list, lambda: None)
    row = task_rows(window.task_box)[0]
    window.task_box.select_row(row)
    window.delete_button.emit("clicked")
    pump()
    assert worker.calls == []  # nothing sent yet
    assert window.undo_bar.get_visible()
    assert len(task_rows(window.task_box)) == 2
    window.flush_delete()
    assert ("delete", row.task.id) in worker.calls
    window.destroy()


def test_undo_puts_the_task_back(parts):
    store, worker, default_list = parts
    window = MainWindow(store, worker, default_list, lambda: None)
    row = task_rows(window.task_box)[0]
    window.task_box.select_row(row)
    window.delete_button.emit("clicked")
    pump()
    window.undo_bar.emit("response", Gtk.ResponseType.OK)
    pump()
    assert worker.calls == []
    assert len(task_rows(window.task_box)) == 3
    window.destroy()


def test_closing_the_undo_bar_sends_the_delete(parts):
    store, worker, default_list = parts
    window = MainWindow(store, worker, default_list, lambda: None)
    row = task_rows(window.task_box)[0]
    window.task_box.select_row(row)
    window.delete_button.emit("clicked")
    pump()
    window.undo_bar.emit("response", Gtk.ResponseType.CLOSE)
    assert ("delete", row.task.id) in worker.calls
    assert not window.undo_bar.get_visible()
    window.destroy()


def test_closing_the_window_keeps_the_waiting_delete(parts):
    store, worker, default_list = parts
    window = MainWindow(store, worker, default_list, lambda: None)
    row = task_rows(window.task_box)[0]
    window.task_box.select_row(row)
    window.delete_button.emit("clicked")
    pump()
    window._on_delete()
    assert window._pending_delete is not None
    assert worker.calls == []          # closing is not "delete it now"
    window.flush_delete()
    assert ("delete", row.task.id) in worker.calls
    window.destroy()


def test_the_detail_pane_follows_the_next_task_after_a_delete(parts):
    store, worker, default_list = parts
    window = MainWindow(store, worker, default_list, lambda: None)
    rows = task_rows(window.task_box)
    window.task_box.select_row(rows[0])
    gone = rows[0].task
    window.delete_button.emit("clicked")
    pump()
    assert window.detail_task is not None and window.detail_task.id != gone.id
    assert window.title_entry.get_text() == window.detail_task.title
    window.title_entry.set_text("Renamed")
    window.title_entry.emit("activate")
    assert ("patch", window.detail_task.id, {"title": "Renamed"}) in worker.calls
    window.destroy()


def test_the_popup_chooser_follows_the_window(parts):
    store, worker, default_list = parts
    popup = Popup(store, worker, default_list, lambda: None, lambda: None)
    store.set_selected("L2")
    pump()
    active = [button.list_id for button in popup.chooser_box.get_children()
              if button.get_active()]
    assert active == ["L2"]
    popup.destroy()
