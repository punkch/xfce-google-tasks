"""The full window: lists on the left, tasks in the middle, details right."""

import datetime as dt
from typing import NamedTuple

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, Gio, GLib, Gtk, Pango  # noqa: E402  (after require_version)

from .. import state  # noqa: E402  (after require_version)
from ..model import Task, TaskList, is_overdue, summary  # noqa: E402
from .signin import SignInPage  # noqa: E402  (after require_version)
from .store import ALL_LISTS  # noqa: E402  (after require_version)
from .widgets import (ADD_PLACEHOLDER, NO_LIST_TEXT, OFFLINE_TEXT,  # noqa: E402
                      DueButton, ListRow, TaskRow, add_from_entry, clear,
                      confirm, placeholder_row, scrolled, set_margins)

DEFAULT_WIDTH = 960
DEFAULT_HEIGHT = 600
SAVE_DELAY_MS = 500     # wait for the drag to stop before saving the size
UNDO_SECONDS = 8        # a deleted task can come back for this long
NEW_LIST_PLACEHOLDER = "List title"


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
        self._editing: tuple[str, str] | None = None   # list id and new title
        self._rename_entry: Gtk.Entry | None = None
        self._rename_fresh = False                # the rename only started
        self._row_menu: Gtk.Menu | None = None
        # An attribute, so that a test can answer the dialog without one.
        self.confirm = confirm

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

    def _build_sidebar(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.SINGLE)
        self.list_box.connect("row-selected", self._on_list_selected)
        box.pack_start(scrolled(self.list_box), True, True, 0)

        # The entry stays out of the ListBox: a refresh empties the box
        # and would take a half-typed title with it.
        self.new_list_entry = Gtk.Entry(placeholder_text=NEW_LIST_PLACEHOLDER)
        self.new_list_entry.set_no_show_all(True)
        for side in ("margin_start", "margin_end", "margin_top", "margin_bottom"):
            self.new_list_entry.set_property(side, 6)
        self.new_list_entry.connect("activate", self._new_list_done)
        self.new_list_entry.connect("key-press-event", self._on_new_list_key)
        box.pack_start(self.new_list_entry, False, False, 0)

        self.new_list_button = Gtk.Button()
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        row.pack_start(Gtk.Image.new_from_icon_name("list-add-symbolic",
                                                    Gtk.IconSize.BUTTON),
                       False, False, 0)
        row.pack_start(Gtk.Label(label="New list", xalign=0.0), True, True, 0)
        self.new_list_button.add(row)
        self.new_list_button.set_relief(Gtk.ReliefStyle.NONE)
        self.new_list_button.connect("clicked", self._show_new_list)
        box.pack_start(self.new_list_button, False, False, 0)
        return box

    def _build_centre(self) -> Gtk.Box:
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        bar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        for side in ("set_margin_top", "set_margin_start", "set_margin_end"):
            getattr(bar, side)(6)

        self.add_entry = Gtk.Entry(placeholder_text=ADD_PLACEHOLDER)
        self.add_entry.connect("activate", self._add_task)
        bar.pack_start(self.add_entry, True, True, 0)
        self.add_due_button = DueButton(self._pick_add_due,
                                        tooltip="Due date of the new task")
        bar.pack_start(self.add_due_button, False, False, 0)
        self.add_button = Gtk.Button(label="Add")
        self.add_button.connect("clicked", lambda *_args: self._add_task(self.add_entry))
        bar.pack_start(self.add_button, False, False, 0)

        # A check button: a filled toggle looks like the main action.
        self.completed_toggle = Gtk.CheckButton(label="Show completed")
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

        # Progress of a long job, "Nothing to do." and the like.
        self.status = Gtk.Label(label="", xalign=0.0)
        self.status.set_ellipsize(Pango.EllipsizeMode.END)
        self.status.get_style_context().add_class("gtasks-small")
        for side in ("margin_start", "margin_end", "margin_bottom"):
            self.status.set_property(side, 6)
        box.pack_end(self.status, False, False, 0)
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
        self.due_button = DueButton(self._set_due, tooltip="Due date of this task")
        self.due_button.set_relief(Gtk.ReliefStyle.NORMAL)
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
        self.add_due_button.set_sensitive(writable)
        self.new_list_button.set_sensitive(writable)
        self.new_list_entry.set_editable(writable)
        if self.completed_toggle.get_active() != store.show_completed:
            self._loading = True
            self.completed_toggle.set_active(store.show_completed)
            self._loading = False
        # Offline the task text stays readable. Only the writing stops.
        self.title_entry.set_editable(writable)
        self.notes_view.set_editable(writable)
        for widget in (self.due_button, self.move_combo, self.delete_button):
            widget.set_sensitive(writable)
        self.status.set_text(store.status)
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
        # Take the cursor back only when it was in the entry we destroy.
        # A redraw must not pull the user out of another field.
        refocus = self._rename_fresh or (self._rename_entry is not None
                                         and self.get_focus() is self._rename_entry)
        self._rename_entry = None
        # The list under rename can be gone: another window deleted it.
        if self._editing and store.find_list(self._editing[0]) is None:
            self._editing = None
            self._rename_fresh = False
        clear(self.list_box)
        counts = summary(store.lists)
        rows = [(ALL_LISTS, store.list_title(ALL_LISTS), counts["count"])]
        rows += [(item.id, item.title, count)
                 for item, (_title, count) in zip(store.lists, counts["lists"])]
        chosen = None
        for list_id, title, count in rows:
            if self._editing and self._editing[0] == list_id:
                row = self._rename_row(list_id, self._editing[1])
            else:
                # Only a real task list has actions. "All lists" has none.
                row = ListRow(list_id, title, count,
                              on_menu=None if list_id is ALL_LISTS else self._open_list_menu)
            self.list_box.add(row)
            if list_id == store.selected_list_id:
                chosen = row
        self.list_box.show_all()
        if chosen is not None:
            self.list_box.select_row(chosen)
        if refocus:
            self._focus_rename_entry()
        self._rebuilding = False

    def _rename_row(self, list_id: str, text: str) -> Gtk.ListBoxRow:
        """The sidebar row of a list that the user renames now."""
        row = Gtk.ListBoxRow()
        row.list_id = list_id
        # A click on it must not change the chosen list under the entry.
        row.set_selectable(False)
        entry = Gtk.Entry()
        entry.set_text(text)
        entry.set_margin_top(2)
        entry.set_margin_bottom(2)
        entry.set_margin_start(6)
        entry.set_margin_end(6)
        # Connect after set_text, or the line above looks like typing.
        entry.connect("changed", self._on_rename_changed)
        entry.connect("activate", self._rename_done)
        entry.connect("key-press-event", self._on_rename_key)
        row.add(entry)
        self._rename_entry = entry
        return row

    def _focus_rename_entry(self) -> None:
        """Put the cursor back in the entry that the rebuild made again."""
        if self._rename_entry is None:
            return
        self._rename_entry.grab_focus()
        if self._rename_fresh:
            self._rename_fresh = False   # the old title stays selected
        else:
            # grab_focus selects every character. In the middle of a
            # rename that would let the next key wipe the title.
            self._rename_entry.set_position(-1)

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
        self.due_button.show_date(task.due, today, is_overdue(task, today))
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
        if not add_from_entry(entry, self.add_due_button, self.store, self.worker,
                              self.default_list):
            self.store.set_status(NO_LIST_TEXT)

    def _pick_add_due(self, date: dt.date | None) -> None:
        """The due date the next new task gets. The button keeps it."""
        self.add_due_button.show_date(date)

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

    def _set_due(self, date: dt.date | None) -> None:
        task = self.detail_task
        if self._loading or task is None:
            return
        if date != task.due:
            self.worker.patch(task, due=date)

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

    # -- task list actions ------------------------------------------------

    def _show_new_list(self, *_args) -> None:
        """The New list button: show the entry and put the cursor in it."""
        self.new_list_entry.set_text("")
        # The button goes: the entry is the button now.
        self.new_list_button.set_visible(False)
        self.new_list_entry.set_visible(True)
        self.new_list_entry.grab_focus()

    def _hide_new_list(self) -> None:
        self.new_list_entry.set_text("")
        self.new_list_entry.set_visible(False)
        self.new_list_button.set_visible(True)

    def _new_list_done(self, entry: Gtk.Entry) -> None:
        title = entry.get_text().strip()
        self._hide_new_list()
        if title:
            self.worker.add_list(title)

    def _on_new_list_key(self, _entry, event) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self._hide_new_list()
            return True
        return False

    def _open_list_menu(self, row, event=None) -> None:
        """The row menu of one task list, from the button or a right click."""
        list_ = self.store.find_list(row.list_id)
        if list_ is None:
            return
        if self._row_menu is not None:
            self._row_menu.destroy()
        menu = self._row_menu = self._build_list_menu(list_)
        menu.attach_to_widget(row)
        if event is not None:
            menu.popup_at_pointer(event)
        else:
            under = row.menu_button if row.menu_button is not None else row
            menu.popup_at_widget(under, Gdk.Gravity.SOUTH_WEST,
                                 Gdk.Gravity.NORTH_WEST, Gtk.get_current_event())

    def _build_list_menu(self, list_: TaskList) -> Gtk.Menu:
        """Rename, Mark all done, Clear completed, Delete list."""
        menu = Gtk.Menu()
        writable = not self.store.offline
        actions = (("Rename", self._start_rename),
                   ("Mark all done", self._complete_all),
                   ("Clear completed", self._clear_completed),
                   ("Delete list", self._delete_list))
        for label, handler in actions:
            item = Gtk.MenuItem(label=label)
            item.set_sensitive(writable)   # offline nothing can be written
            item.connect("activate", handler, list_)
            menu.append(item)
        menu.show_all()
        return menu

    def _current(self, list_: TaskList) -> TaskList:
        """The list as the store holds it now. A reload can replace the object
        while the menu is open."""
        return self.store.find_list(list_.id) or list_

    def _start_rename(self, _item, list_: TaskList) -> None:
        list_ = self._current(list_)
        self._editing = (list_.id, list_.title)
        self._rename_fresh = True
        # The redraw makes the row again, this time as an entry.
        self.store.notify()

    def _on_rename_changed(self, entry: Gtk.Entry) -> None:
        """Keep the text the user types, so a redraw cannot lose it."""
        if self._editing:
            self._editing = (self._editing[0], entry.get_text())

    def _rename_done(self, entry: Gtk.Entry) -> None:
        editing, self._editing = self._editing, None
        title = entry.get_text().strip()
        list_ = self.store.find_list(editing[0]) if editing else None
        if list_ is not None and title and title != list_.title:
            self.worker.rename_list(list_, title)
        self.store.notify()

    def _on_rename_key(self, _entry, event) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self._editing = None
            self.store.notify()
            return True
        return False

    def _complete_all(self, _item, list_: TaskList) -> None:
        list_ = self._current(list_)
        count = self.store.open_count(list_.id)
        if not count:
            self.store.set_status("Nothing to do.")
            return
        tasks = "task" if count == 1 else "tasks"
        if self.confirm(self, "Mark all done",
                        f"Mark {count} open {tasks} in “{list_.title}” as done?",
                        "Mark done", destructive=False):
            self.worker.complete_all(list_)

    def _clear_completed(self, _item, list_: TaskList) -> None:
        list_ = self._current(list_)
        # The window holds the completed tasks only with Show completed
        # on, so the question has no count. The job reads them itself.
        if self.confirm(self, "Clear completed",
                        f"Delete all completed tasks in “{list_.title}”? "
                        "This cannot be undone.", "Delete"):
            self.worker.clear_completed(list_)

    def _delete_list(self, _item, list_: TaskList) -> None:
        list_ = self._current(list_)
        if not self.confirm(self, "Delete list",
                            f"Delete list “{list_.title}” and all its tasks? "
                            "This cannot be undone.", "Delete"):
            return
        # A task of this list can wait behind the undo bar. The user just
        # said "delete all its tasks", so send that delete now. The jobs
        # run in order, so it lands before the list goes.
        pending = self._pending_delete
        if pending is not None and pending.task.list_id == list_.id:
            self._delete_now()
        self.worker.delete_list(list_)

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
        if self._row_menu is not None:
            self._row_menu.destroy()
            self._row_menu = None
        self.hide()  # the next double click shows it again
        return True


def _int(value, fallback: int) -> int:
    try:
        return max(320, int(value))
    except (TypeError, ValueError):
        return fallback


def _buffer_text(buffer: Gtk.TextBuffer) -> str:
    return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), False)
