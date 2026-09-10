"""The full window: lists on the left, tasks in the middle, details right."""

import datetime as dt
from typing import NamedTuple

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gio, GLib, Gtk  # noqa: E402  (after require_version)

from .. import state  # noqa: E402  (after require_version)
from ..model import Task, due_text, summary  # noqa: E402  (after require_version)
from .signin import SignInPage  # noqa: E402  (after require_version)
from .store import ALL_LISTS  # noqa: E402  (after require_version)
from .widgets import (ADD_PLACEHOLDER, OFFLINE_TEXT, ListRow,  # noqa: E402
                      TaskRow, clear, placeholder_row, quick_add, scrolled,
                      set_margins)

DEFAULT_WIDTH = 960
DEFAULT_HEIGHT = 600
SAVE_DELAY_MS = 500     # wait for the drag to stop before saving the size
UNDO_SECONDS = 8        # a deleted task can come back for this long


class PendingDelete(NamedTuple):
    """A task waiting behind the undo bar, and the timer that ends the wait."""

    task: Task
    index: int
    source: int


class MainWindow(Gtk.ApplicationWindow):
    """Read and change every task. One window for the whole application."""

    def __init__(self, store, worker, default_list: str, on_reload, **kwargs):
        super().__init__(title="Google Tasks", **kwargs)
        self.store = store
        self.worker = worker
        self.default_list = default_list
        self.on_reload = on_reload
        self.detail_task: Task | None = None
        self._loading = False        # widgets are being filled: ignore signals
        self._rebuilding = False     # rows are being rebuilt: ignore selection
        self._save_id = 0
        self._pending_delete: PendingDelete | None = None
        self._move_key: list | None = None

        saved = state.load_window_state()
        # The size we start with is also the size on the disk. Keep it, so
        # that a window that is not resized does not write the file again.
        self._saved_size: tuple[int, int] = (
            _int(saved.get("width"), DEFAULT_WIDTH),
            _int(saved.get("height"), DEFAULT_HEIGHT))
        self.set_default_size(*self._saved_size)
        self.add(self._build())
        self.connect("configure-event", self._on_configure)
        self.connect("delete-event", self._on_delete)
        store.subscribe(self.refresh)
        self.refresh()

    # -- layout -----------------------------------------------------------

    def _build(self) -> Gtk.Box:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL)

        self.offline_bar = Gtk.InfoBar(message_type=Gtk.MessageType.WARNING)
        self.offline_bar.set_no_show_all(True)
        self.offline_label = Gtk.Label(label=OFFLINE_TEXT, xalign=0.0)
        self.offline_bar.get_content_area().add(self.offline_label)
        # A bar with no_show_all keeps its own flag, but the parts inside it
        # need their own show(), or an open bar comes up empty.
        self.offline_bar.get_content_area().show_all()
        outer.pack_start(self.offline_bar, False, False, 0)

        self.undo_bar = Gtk.InfoBar(message_type=Gtk.MessageType.INFO)
        self.undo_bar.set_no_show_all(True)
        self.undo_bar.set_show_close_button(True)
        self.undo_bar.get_content_area().add(Gtk.Label(label="Task deleted.", xalign=0.0))
        self.undo_bar.add_button("Undo", Gtk.ResponseType.OK).show()
        self.undo_bar.get_content_area().show_all()
        self.undo_bar.connect("response", self._on_undo_response)
        outer.pack_start(self.undo_bar, False, False, 0)

        self.stack = Gtk.Stack()
        self.tasks_page = self._build_panes()
        self.stack.add_named(self.tasks_page, "tasks")
        self.signin_page = SignInPage(self.store, self.on_reload)
        self.stack.add_named(self.signin_page, "signin")
        outer.pack_start(self.stack, True, True, 0)
        return outer

    def _build_panes(self) -> Gtk.Paned:
        outer = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        outer.set_position(220)
        outer.pack1(self._build_sidebar(), False, False)

        inner = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        inner.set_position(420)
        inner.pack1(self._build_centre(), True, False)
        inner.pack2(self._build_detail(), False, False)
        outer.pack2(inner, True, False)
        return outer

    def _build_sidebar(self) -> Gtk.ScrolledWindow:
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list_box.connect("row-selected", self._on_list_selected)
        return scrolled(self.list_box)

    def _build_centre(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        for side in ("set_margin_top", "set_margin_start", "set_margin_end"):
            getattr(bar, side)(6)

        self.add_entry = Gtk.Entry(placeholder_text=ADD_PLACEHOLDER)
        self.add_entry.connect("activate", self._add_task)
        bar.pack_start(self.add_entry, True, True, 0)
        self.add_button = Gtk.Button(label="Add")
        self.add_button.connect("clicked", lambda *_args: self._add_task(self.add_entry))
        bar.pack_start(self.add_button, False, False, 0)

        self.completed_toggle = Gtk.ToggleButton(label="Show completed")
        self.completed_toggle.connect("toggled", self._on_show_completed)
        bar.pack_start(self.completed_toggle, False, False, 0)

        refresh = Gtk.Button.new_from_icon_name("view-refresh-symbolic",
                                                Gtk.IconSize.BUTTON)
        refresh.set_tooltip_text("Refresh")
        refresh.set_action_name("app.refresh")
        bar.pack_start(refresh, False, False, 0)

        menu = Gio.Menu()
        menu.append("Refresh", "app.refresh")
        menu.append("Quit", "app.quit")
        menu_button = Gtk.MenuButton()
        menu_button.add(Gtk.Image.new_from_icon_name("open-menu-symbolic",
                                                     Gtk.IconSize.BUTTON))
        menu_button.set_menu_model(menu)
        bar.pack_start(menu_button, False, False, 0)
        box.pack_start(bar, False, False, 0)

        self.task_box = Gtk.ListBox()
        self.task_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.task_box.connect("row-selected", self._on_task_selected)
        box.pack_start(scrolled(self.task_box), True, True, 0)
        return box

    def _build_detail(self) -> Gtk.Stack:
        self.detail_stack = Gtk.Stack()
        self.empty_detail = Gtk.Label(label="Select a task.")
        self.empty_detail.get_style_context().add_class("gtasks-dim")
        self.detail_stack.add_named(self.empty_detail, "empty")

        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8)
        set_margins(box, 10)

        self.title_entry = Gtk.Entry()
        self.title_entry.connect("activate", lambda *_args: self._save_title())
        self.title_entry.connect("focus-out-event", self._on_title_focus_out)
        box.pack_start(self.title_entry, False, False, 0)

        due_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        due_row.pack_start(Gtk.Label(label="Due", xalign=0.0), False, False, 0)
        self.due_button = Gtk.MenuButton(label="None")
        self.due_button.set_popover(self._build_calendar())
        due_row.pack_start(self.due_button, False, False, 0)
        box.pack_start(due_row, False, False, 0)

        notes_label = Gtk.Label(label="Notes", xalign=0.0)
        notes_label.get_style_context().add_class("gtasks-small")
        box.pack_start(notes_label, False, False, 0)
        self.notes_view = Gtk.TextView()
        self.notes_view.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.notes_view.connect("focus-out-event", self._on_notes_focus_out)
        box.pack_start(scrolled(self.notes_view, shadow=True), True, True, 0)

        move_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        move_row.pack_start(Gtk.Label(label="Move to", xalign=0.0), False, False, 0)
        self.move_combo = Gtk.ComboBoxText()
        self.move_combo.connect("changed", self._on_move)
        move_row.pack_start(self.move_combo, True, True, 0)
        box.pack_start(move_row, False, False, 0)

        # A button as wide as the pane looks like the main action. It is not.
        delete_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.delete_button = Gtk.Button(label="Delete")
        self.delete_button.get_style_context().add_class("destructive-action")
        self.delete_button.connect("clicked", self._delete_task)
        delete_row.pack_end(self.delete_button, False, False, 0)
        box.pack_start(delete_row, False, False, 0)

        self.detail_page = box
        self.detail_stack.add_named(box, "task")
        return self.detail_stack

    def _build_calendar(self) -> Gtk.Popover:
        popover = Gtk.Popover()
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        set_margins(box, 6)
        self.calendar = Gtk.Calendar()
        self.calendar.connect("day-selected-double-click",
                              lambda *_args: self._set_due(self._calendar_date()))
        box.pack_start(self.calendar, True, True, 0)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        clear_button = Gtk.Button(label="Clear")
        clear_button.connect("clicked", lambda *_args: self._clear_due())
        buttons.pack_start(clear_button, True, True, 0)
        set_button = Gtk.Button(label="Set")
        set_button.connect("clicked", lambda *_args: self._set_due(self._calendar_date()))
        buttons.pack_start(set_button, True, True, 0)
        box.pack_start(buttons, False, False, 0)
        popover.add(box)
        box.show_all()
        return popover

    # -- redraw -----------------------------------------------------------

    def refresh(self, _store=None) -> None:
        store = self.store
        if store.needs_signin:
            self.signin_page.show_for(store.auth)
            self.stack.set_visible_child(self.signin_page)
            return
        self.stack.set_visible_child(self.tasks_page)
        self.signin_page.reset()
        writable = not store.offline
        today = dt.date.today()
        self._refresh_offline_bar()
        self.add_entry.set_editable(writable)
        self.add_button.set_sensitive(writable)
        if self.completed_toggle.get_active() != store.show_completed:
            self._loading = True
            self.completed_toggle.set_active(store.show_completed)
            self._loading = False
        # Offline the task text stays readable. Only the writing stops.
        self.title_entry.set_editable(writable)
        self.notes_view.set_editable(writable)
        for widget in (self.due_button, self.move_combo, self.delete_button):
            widget.set_sensitive(writable)
        self._rebuild_sidebar()
        self._rebuild_tasks(writable, today)
        self._refresh_detail(today)

    def _refresh_offline_bar(self) -> None:
        """One bar for two conditions: no network, or Google said no."""
        store = self.store
        self.offline_bar.set_visible(store.offline or bool(store.error))
        if store.offline:
            self.offline_bar.set_message_type(Gtk.MessageType.WARNING)
            self.offline_label.set_text(f"{OFFLINE_TEXT} {store.error}".strip())
        else:
            self.offline_bar.set_message_type(Gtk.MessageType.ERROR)
            self.offline_label.set_text(store.error)

    def _rebuild_sidebar(self) -> None:
        store = self.store
        self._rebuilding = True
        clear(self.list_box)
        counts = summary(store.lists)
        rows = [(ALL_LISTS, store.list_title(ALL_LISTS), counts["count"])]
        rows += [(item.id, item.title, count)
                 for item, (_title, count) in zip(store.lists, counts["lists"])]
        chosen = None
        for list_id, title, count in rows:
            row = ListRow(list_id, title, count)
            self.list_box.add(row)
            if list_id == store.selected_list_id:
                chosen = row
        self.list_box.show_all()
        if chosen is not None:
            self.list_box.select_row(chosen)
        self._rebuilding = False

    def _rebuild_tasks(self, writable: bool, today: dt.date) -> None:
        self._rebuilding = True
        clear(self.task_box)
        selected_id = self.detail_task.id if self.detail_task else None
        rows = []
        for task in self.store.visible_tasks(self.store.selected_list_id, today=today):
            row = TaskRow(task, self._toggle_task, editable=writable, today=today)
            self.task_box.add(row)
            rows.append(row)
        if not rows:
            self.task_box.add(placeholder_row("No tasks in this list."))
        self.task_box.show_all()
        # Keep the row that was open. Without one, show the first task:
        # an empty detail pane beside a full list helps nobody.
        chosen = next((row for row in rows if row.task.id == selected_id), None)
        chosen = chosen or (rows[0] if rows else None)
        if chosen is not None:
            self.task_box.select_row(chosen)
        self.detail_task = chosen.task if chosen else None
        self._rebuilding = False

    def _refresh_detail(self, today: dt.date | None = None,
                        force: bool = False) -> None:
        task = self.detail_task
        if task is None:
            self.detail_stack.set_visible_child(self.empty_detail)
            return
        self.detail_stack.set_visible_child(self.detail_page)
        self._loading = True
        # Never write over a field the user is typing in. A refresh can
        # arrive at any time, and a half-typed title must survive it.
        if (force or not self.title_entry.has_focus()) \
                and self.title_entry.get_text() != task.title:
            self.title_entry.set_text(task.title)
        buffer = self.notes_view.get_buffer()
        if (force or not self.notes_view.has_focus()) \
                and _buffer_text(buffer) != task.notes:
            buffer.set_text(task.notes)
        self.due_button.set_label(due_text(task.due, today) or "None")
        if task.due:
            self.calendar.select_month(task.due.month - 1, task.due.year)
            self.calendar.select_day(task.due.day)
        # Rebuilding the combo makes it drop its list. Only do it when
        # the task lists really changed.
        key = [(item.id, item.title) for item in self.store.lists]
        if key != self._move_key:
            self._move_key = key
            self.move_combo.remove_all()
            for list_id, title in key:
                self.move_combo.append(list_id, title)
        self.move_combo.set_active_id(task.list_id)
        self._loading = False

    # -- actions ----------------------------------------------------------

    def _on_list_selected(self, _box, row) -> None:
        if self._rebuilding or row is None:
            return
        self.flush_edits()
        self.detail_task = None
        self.store.set_selected(row.list_id)

    def _on_task_selected(self, _box, row) -> None:
        if self._rebuilding:
            return
        self.flush_edits()
        self.detail_task = row.task if row is not None else None
        self._refresh_detail(force=True)

    def _toggle_task(self, task: Task, done: bool) -> None:
        if done:
            self.worker.complete(task)
        else:
            self.worker.uncomplete(task)

    def _add_task(self, entry: Gtk.Entry) -> None:
        quick_add(entry, self.store, self.worker, self.default_list)

    def _on_title_focus_out(self, *_args) -> bool:
        self._save_title()
        return False

    def _on_notes_focus_out(self, *_args) -> bool:
        self._save_notes()
        return False

    def _save_title(self) -> None:
        task = self.detail_task
        if self._loading or task is None:
            return
        title = self.title_entry.get_text().strip()
        if title and title != task.title:
            self.worker.patch(task, title=title)

    def _save_notes(self) -> None:
        task = self.detail_task
        if self._loading or task is None:
            return
        notes = _buffer_text(self.notes_view.get_buffer())
        if notes != task.notes:
            self.worker.patch(task, notes=notes)

    def _calendar_date(self) -> dt.date:
        year, month, day = self.calendar.get_date()
        return dt.date(year, month + 1, day)  # Gtk months start at 0

    def _set_due(self, date: dt.date | None) -> None:
        task = self.detail_task
        if self._loading or task is None:
            return
        if date != task.due:
            self.worker.patch(task, due=date)
        self.due_button.get_popover().popdown()

    def _clear_due(self) -> None:
        self._set_due(None)

    def _on_move(self, combo: Gtk.ComboBoxText) -> None:
        task = self.detail_task
        if self._loading or task is None:
            return
        target = combo.get_active_id()
        if target and target != task.list_id:
            self.detail_task = None
            self.worker.move(task, target)

    def _on_show_completed(self, button: Gtk.ToggleButton) -> None:
        if self._loading:
            return
        show = button.get_active()
        self.store.set_show_completed(show)
        # Hiding them needs no new data, and the completed tasks are read
        # one time only.
        if show and not self.store.has_completed:
            self.worker.reload()

    # -- delayed delete ---------------------------------------------------

    def _delete_task(self, *_args) -> None:
        task = self.detail_task
        if task is None:
            return
        self.flush_delete()
        # Before the removal: taking the row out picks a new detail task,
        # and a later None would wipe the pane while it shows that one.
        self.detail_task = None
        index = self.store.remove_task(task)
        source = GLib.timeout_add_seconds(UNDO_SECONDS, self._undo_timeout)
        self._pending_delete = PendingDelete(task, index, source)
        self.undo_bar.set_visible(True)

    def _take_pending(self) -> tuple[Task | None, int]:
        """Stop the timer, hide the bar and hand back the waiting task."""
        pending = self._pending_delete
        if pending is None:
            return None, -1
        self._pending_delete = None
        if pending.source:
            GLib.source_remove(pending.source)
        self.undo_bar.set_visible(False)
        return pending.task, pending.index

    def _undo_timeout(self) -> bool:
        """The undo time is over. Forget the timer: it ends by itself."""
        if self._pending_delete is not None:
            self._pending_delete = self._pending_delete._replace(source=0)
        self._delete_now()
        return False

    def _delete_now(self) -> bool:
        task, index = self._take_pending()
        if task is not None:
            # A load may have put the task back while the bar was open.
            self.store.remove_task(task)
            self.worker.delete(task, index)
        return False

    def _on_undo_response(self, _bar, response: int) -> None:
        if response == Gtk.ResponseType.OK:
            self._undo_delete()
        else:
            self.flush_delete()

    def _undo_delete(self) -> None:
        task, index = self._take_pending()
        if task is not None and self.store.find_task(task.list_id, task.id) is None:
            self.store.add_task(task, max(index, 0))

    def flush_delete(self) -> None:
        """Do a waiting delete now. Called before we quit."""
        self._delete_now()

    def flush_edits(self) -> None:
        """Save the detail pane before the view changes under it."""
        self._save_title()
        self._save_notes()

    # -- size and closing -------------------------------------------------

    def _on_configure(self, *_args) -> bool:
        if self._save_id:
            GLib.source_remove(self._save_id)
        self._save_id = GLib.timeout_add(SAVE_DELAY_MS, self._save_size)
        return False

    def _save_size(self) -> bool:
        self._save_id = 0
        if self.is_maximized():
            return False
        size = self.get_size()
        if size == self._saved_size:
            return False
        try:
            state.save_window_state({"width": size[0], "height": size[1]})
        except OSError:
            return False  # a size we cannot save is not worth a crash
        self._saved_size = size
        return False

    def _on_delete(self, *_args) -> bool:
        self.flush_edits()
        # The undo bar keeps its task: closing the window is not the same
        # as saying "delete it now".
        if self._save_id:
            GLib.source_remove(self._save_id)
            self._save_id = 0
        self._save_size()
        self.hide()  # the next double click shows it again
        return True


def _int(value, fallback: int) -> int:
    try:
        return max(320, int(value))
    except (TypeError, ValueError):
        return fallback


def _buffer_text(buffer: Gtk.TextBuffer) -> str:
    return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
