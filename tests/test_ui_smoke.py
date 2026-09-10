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
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, GLib, Gtk  # noqa: E402

from gtasks_panel.model import Task, TaskList  # noqa: E402
from gtasks_panel.paths import AUTH_NO_TOKEN  # noqa: E402
from gtasks_panel.ui.mainwindow import MainWindow  # noqa: E402
from gtasks_panel.ui.popup import Popup  # noqa: E402
from gtasks_panel.ui.store import TaskStore  # noqa: E402
from gtasks_panel.ui.widgets import (DuePopover, ListRow,  # noqa: E402
                                     TaskRow, confirm)

TODAY = dt.date(2026, 9, 10)


class FakeWorker:
    """Records the jobs the windows post. Nothing reaches Google."""

    def __init__(self):
        self.calls = []

    def complete(self, task):
        self.calls.append(("complete", task.id))

    def uncomplete(self, task):
        self.calls.append(("uncomplete", task.id))

    def add(self, list_id, title, due=None):
        self.calls.append(("add", list_id, title, due))

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

    def add_list(self, title):
        self.calls.append(("add_list", title))

    def rename_list(self, list_, title):
        self.calls.append(("rename_list", list_.id, title))

    def delete_list(self, list_):
        self.calls.append(("delete_list", list_.id))

    def clear_completed(self, list_):
        self.calls.append(("clear_completed", list_.id))

    def complete_all(self, list_):
        self.calls.append(("complete_all", list_.id))


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


def task_row(list_box, task_id):
    """One task row by id. An index would follow the sort order."""
    return next(row for row in task_rows(list_box) if row.task.id == task_id)


def list_row(window, list_id):
    return next(row for row in window.list_box.get_children()
                if isinstance(row, ListRow) and row.list_id == list_id)


def open_list_menu(window, list_id):
    """Open the row menu of one list. Returns its items by label."""
    window._open_list_menu(list_row(window, list_id), None)
    menu = window._row_menu
    menu.popdown()   # a grab in a test would hold the pointer
    return {item.get_label(): item for item in menu.get_children()}


def answer_dialog(response):
    """Push a button of the dialog that `confirm` opens.

    `confirm` runs its own loop, so the answer comes from a timer.
    """
    def push():
        for window in Gtk.Window.list_toplevels():
            if isinstance(window, Gtk.MessageDialog):
                window.response(response)
        return False

    GLib.timeout_add(20, push)


def always_yes(seen):
    """A stand-in for the confirm dialog. It keeps what it was asked."""
    def answer(*args, **_kwargs):
        seen.append(args)
        return True
    return answer


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
    assert worker.calls == [("add", "L2", "New thing", None)]  # default_list = Home
    assert popup.entry.get_text() == ""
    popup.destroy()


def test_a_chosen_list_wins_over_the_default_list(parts):
    store, worker, default_list = parts
    store.set_selected("L1")
    popup = Popup(store, worker, default_list, lambda: None, lambda: None)
    popup.entry.set_text("Another thing")
    popup.entry.emit("activate")
    assert worker.calls == [("add", "L1", "Another thing", None)]
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


# -- the due date popover ---------------------------------------------------


def test_the_due_popover_counts_its_quick_dates_from_today():
    picked = []
    popover = DuePopover(picked.append, today=TODAY)
    popover.tomorrow_button.clicked()
    popover.today_button.clicked()
    popover.clear_button.clicked()
    assert picked == [TODAY + dt.timedelta(days=1), TODAY, None]


def test_the_due_popover_gives_the_day_of_its_calendar():
    picked = []
    popover = DuePopover(picked.append, today=TODAY)
    far = TODAY + dt.timedelta(days=40)   # another month, another length
    popover.select(far)
    popover.set_button.clicked()
    assert picked == [far]


def test_a_popup_row_due_button_sets_today(parts):
    store, worker, default_list = parts
    popup = Popup(store, worker, default_list, lambda: None, lambda: None)
    row = task_row(popup.list_box, "t2")        # this one has no due date
    row.due_button.due_popover.today_button.clicked()
    assert ("patch", "t2", {"due": dt.date.today()}) in worker.calls
    popup.destroy()


def test_a_popup_row_due_button_sets_the_day_of_the_calendar(parts):
    store, worker, default_list = parts
    popup = Popup(store, worker, default_list, lambda: None, lambda: None)
    row = task_row(popup.list_box, "t2")
    far = dt.date.today() + dt.timedelta(days=40)
    row.due_button.due_popover.select(far)
    row.due_button.due_popover.set_button.clicked()
    assert ("patch", "t2", {"due": far}) in worker.calls
    popup.destroy()


def test_a_popup_row_due_button_takes_the_date_away(parts):
    store, worker, default_list = parts
    popup = Popup(store, worker, default_list, lambda: None, lambda: None)
    row = task_row(popup.list_box, "t1")        # this one has a due date
    row.due_button.due_popover.clear_button.clicked()
    assert ("patch", "t1", {"due": None}) in worker.calls
    popup.destroy()


def test_the_popup_quick_add_takes_a_due_date(parts):
    store, worker, default_list = parts
    popup = Popup(store, worker, default_list, lambda: None, lambda: None)
    popup.add_due_button.due_popover.tomorrow_button.clicked()
    due = dt.date.today() + dt.timedelta(days=1)
    assert popup.add_due_button.date == due
    popup.entry.set_text("New thing")
    popup.entry.emit("activate")
    assert worker.calls == [("add", "L2", "New thing", due)]
    assert popup.add_due_button.date is None    # the pick is used up
    popup.destroy()


def test_the_main_window_quick_add_takes_a_due_date(parts):
    store, worker, default_list = parts
    window = MainWindow(store, worker, default_list, lambda: None)
    window.add_due_button.due_popover.today_button.clicked()
    window.add_entry.set_text("Write it down")
    window.add_entry.emit("activate")
    assert ("add", "L2", "Write it down", dt.date.today()) in worker.calls
    assert window.add_due_button.date is None
    window.destroy()


def test_offline_turns_the_popup_due_buttons_off(parts):
    store, worker, default_list = parts
    popup = Popup(store, worker, default_list, lambda: None, lambda: None)
    store.set_offline(True, "no network")
    pump()
    assert task_row(popup.list_box, "t2").due_button.get_sensitive() is False
    assert popup.add_due_button.get_sensitive() is False
    popup.destroy()


# -- the confirm dialog -----------------------------------------------------


def test_the_confirm_dialog_says_yes_on_the_action_button():
    answer_dialog(Gtk.ResponseType.OK)
    assert confirm(None, "Delete list", "Is this what you want?", "Delete") is True


def test_the_confirm_dialog_says_no_on_cancel():
    answer_dialog(Gtk.ResponseType.CANCEL)
    assert confirm(None, "Mark all done", "Is this what you want?",
                   "Mark done", destructive=False) is False


# -- task list actions ------------------------------------------------------


def test_the_new_list_entry_posts_an_add_list_job(parts):
    store, worker, default_list = parts
    window = MainWindow(store, worker, default_list, lambda: None)
    window.show_all()
    # It waits out of sight until the button asks for it.
    assert not window.new_list_entry.get_visible()
    assert window.add_due_button.icon.get_visible()      # no date picked yet
    assert not window.add_due_button.label.get_visible()
    window.new_list_button.emit("clicked")
    assert window.new_list_entry.get_visible()
    window.new_list_entry.set_text("Groceries")
    window.new_list_entry.emit("activate")
    assert worker.calls == [("add_list", "Groceries")]
    assert not window.new_list_entry.get_visible()
    window.destroy()


def test_an_empty_new_list_entry_posts_nothing(parts):
    store, worker, default_list = parts
    window = MainWindow(store, worker, default_list, lambda: None)
    window.new_list_button.emit("clicked")
    window.new_list_entry.emit("activate")
    assert worker.calls == []
    assert not window.new_list_entry.get_visible()
    window.destroy()


def test_renaming_a_list_posts_a_rename_job(parts):
    store, worker, default_list = parts
    window = MainWindow(store, worker, default_list, lambda: None)
    open_list_menu(window, "L1")["Rename"].emit("activate")
    pump()
    assert window._rename_entry is not None
    window._rename_entry.set_text("Office")
    window._rename_entry.emit("activate")
    assert ("rename_list", "L1", "Office") in worker.calls
    pump()
    assert window._editing is None
    assert window._rename_entry is None
    window.destroy()


def test_a_redraw_keeps_the_half_typed_new_title(parts):
    store, worker, default_list = parts
    window = MainWindow(store, worker, default_list, lambda: None)
    open_list_menu(window, "L1")["Rename"].emit("activate")
    pump()
    window._rename_entry.set_text("Off")
    store.notify()          # any other change redraws the sidebar
    pump()
    assert window._rename_entry.get_text() == "Off"
    assert worker.calls == []
    window.destroy()


def test_a_redraw_leaves_the_cursor_where_the_user_put_it(parts):
    store, worker, default_list = parts
    window = MainWindow(store, worker, default_list, lambda: None)
    open_list_menu(window, "L1")["Rename"].emit("activate")
    pump()
    window.title_entry.grab_focus()      # the user went to another field
    store.notify()
    pump()
    assert window.get_focus() is window.title_entry
    assert window._rename_entry is not None   # the rename is still open
    window.destroy()


def test_the_all_lists_row_has_no_menu(parts):
    store, worker, default_list = parts
    window = MainWindow(store, worker, default_list, lambda: None)
    # Every row has the button, so the counts line up. Only a real
    # list can use it.
    assert not list_row(window, None).menu_button.get_sensitive()
    assert list_row(window, "L1").menu_button.get_sensitive()
    window.destroy()


def test_deleting_a_list_asks_first(parts):
    store, worker, default_list = parts
    window = MainWindow(store, worker, default_list, lambda: None)
    seen = []
    window.confirm = always_yes(seen)
    open_list_menu(window, "L1")["Delete list"].emit("activate")
    assert ("delete_list", "L1") in worker.calls
    assert "Delete list “Work” and all its tasks? This cannot be undone." in seen[0]
    window.destroy()


def test_a_no_to_the_dialog_keeps_the_list(parts):
    store, worker, default_list = parts
    window = MainWindow(store, worker, default_list, lambda: None)
    window.confirm = lambda *_args, **_kwargs: False
    open_list_menu(window, "L1")["Delete list"].emit("activate")
    assert worker.calls == []
    window.destroy()


def test_deleting_a_list_sends_a_waiting_task_delete_first(parts):
    """The user said "delete all its tasks", so the waiting one goes too.

    It goes before the list: the worker runs jobs in order. A refused
    list delete then leaves the store as it is, with no task lost.
    """
    store, worker, default_list = parts
    window = MainWindow(store, worker, default_list, lambda: None)
    window.confirm = always_yes([])
    window.task_box.select_row(task_row(window.task_box, "t1"))   # a task of L1
    window.delete_button.emit("clicked")
    pump()
    assert window.undo_bar.get_visible()
    open_list_menu(window, "L1")["Delete list"].emit("activate")
    assert not window.undo_bar.get_visible()
    assert worker.calls == [("delete", "t1"), ("delete_list", "L1")]
    window.destroy()


def test_marking_a_whole_list_done_asks_first(parts):
    store, worker, default_list = parts
    window = MainWindow(store, worker, default_list, lambda: None)
    seen = []
    window.confirm = always_yes(seen)
    open_list_menu(window, "L1")["Mark all done"].emit("activate")
    assert ("complete_all", "L1") in worker.calls
    assert "Mark 2 open tasks in “Work” as done?" in seen[0]
    window.destroy()


def test_a_list_with_nothing_open_says_so(parts):
    store, worker, default_list = parts
    store.set_lists([TaskList(id="L3", title="Empty", tasks=[])])
    window = MainWindow(store, worker, default_list, lambda: None)
    window.confirm = always_yes([])
    open_list_menu(window, "L3")["Mark all done"].emit("activate")
    assert worker.calls == []
    pump()
    assert window.status.get_text() == "Nothing to do."
    window.destroy()


def test_clearing_the_completed_tasks_asks_first(parts):
    store, worker, default_list = parts
    window = MainWindow(store, worker, default_list, lambda: None)
    seen = []
    window.confirm = always_yes(seen)
    open_list_menu(window, "L1")["Clear completed"].emit("activate")
    assert ("clear_completed", "L1") in worker.calls
    assert ("Delete all completed tasks in “Work”? This cannot be undone."
            in seen[0])
    window.destroy()


def test_offline_turns_the_list_menu_off(parts):
    store, worker, default_list = parts
    window = MainWindow(store, worker, default_list, lambda: None)
    store.set_offline(True, "no network")
    pump()
    items = open_list_menu(window, "L1")
    assert sorted(items) == ["Clear completed", "Delete list", "Mark all done",
                             "Rename"]
    assert not any(item.get_sensitive() for item in items.values())
    assert window.new_list_button.get_sensitive() is False
    assert window.add_due_button.get_sensitive() is False
    window.destroy()


# -- review batch of 2026-09-10 ---------------------------------------------

def test_the_menu_button_of_a_list_row_opens_the_menu(parts):
    store, worker, default_list = parts
    window = MainWindow(store, worker, default_list, lambda: None)
    list_row(window, "L1").menu_button.clicked()
    menu = window._row_menu
    assert menu is not None
    menu.popdown()
    labels = [item.get_label() for item in menu.get_children()]
    assert labels == ["Rename", "Mark all done", "Clear completed", "Delete list"]
    window.destroy()


def test_escape_cancels_a_rename(parts):
    store, worker, default_list = parts
    window = MainWindow(store, worker, default_list, lambda: None)
    open_list_menu(window, "L1")["Rename"].emit("activate")
    pump()
    entry = window._rename_entry
    assert entry is not None
    entry.set_text("Something else")
    event = Gdk.Event.new(Gdk.EventType.KEY_PRESS)
    event.keyval = Gdk.KEY_Escape
    assert window._on_rename_key(entry, event) is True
    pump()
    assert worker.calls == []
    assert isinstance(list_row(window, "L1"), ListRow)
    window.destroy()


def test_a_hidden_popup_redraws_when_it_shows(parts):
    store, worker, default_list = parts
    popup = Popup(store, worker, default_list, lambda: None, lambda: None)
    popup.show_all()
    popup.hide()
    store.set_lists([TaskList(id="L9", title="Only", tasks=[
        Task(id="x1", list_id="L9", title="One task", position="00001")])])
    pump()
    assert len(task_rows(popup.list_box)) == 3    # no redraw while hidden
    popup.show_at_pointer()
    assert [row.task.id for row in task_rows(popup.list_box)] == ["x1"]
    popup.destroy()


def test_the_window_says_when_there_is_no_list_to_add_to(parts):
    store, worker, default_list = parts
    store.set_lists([])
    window = MainWindow(store, worker, default_list, lambda: None)
    window.add_entry.set_text("Lost task")
    window.add_entry.emit("activate")
    pump()
    assert worker.calls == []
    assert window.status.get_text() == "No task list to add to."
    window.destroy()


def test_the_due_button_makes_its_calendar_on_first_use(parts):
    store, worker, default_list = parts
    popup = Popup(store, worker, default_list, lambda: None, lambda: None)
    row = task_rows(popup.list_box)[0]
    assert row.due_button._popover is None
    popover = row.due_button.due_popover
    assert popover.title_label.get_text() == row.task.title
    assert row.due_button.due_popover is popover
    popup.destroy()
