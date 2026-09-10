"""The small window that a single click on the panel item opens.

It shows the open tasks, lets you tick them off and add one. It is not a
menu: it is a toplevel without a frame, put under the pointer.
"""

import datetime as dt

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gdk, Gtk, Pango  # noqa: E402  (after require_version)

from ..model import summary  # noqa: E402  (after require_version)
from .click import HEIGHT, WIDTH, place  # noqa: E402  (after require_version)
from .signin import SignInPage  # noqa: E402  (after require_version)
from .store import ALL_LISTS  # noqa: E402  (after require_version)
from .widgets import (ADD_PLACEHOLDER, OFFLINE_TEXT, TaskRow,  # noqa: E402
                      clear, placeholder_row, quick_add, scrolled, set_margins)


class Popup(Gtk.Window):
    """Open tasks, a check button for each, and a quick-add field."""

    def __init__(self, store, worker, default_list: str, on_open_window, on_reload):
        super().__init__(type=Gtk.WindowType.TOPLEVEL)
        self.store = store
        self.worker = worker
        self.default_list = default_list
        self.on_open_window = on_open_window
        self.on_reload = on_reload
        self._chooser_key = None

        self.set_title("Google Tasks")
        self.set_decorated(False)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_keep_above(True)
        self.set_resizable(False)
        self.set_default_size(WIDTH, HEIGHT)
        # A window that cannot be resized ignores the default size.
        self.set_size_request(WIDTH, HEIGHT)
        # A window with no frame needs an edge of its own, or it runs
        # into the wallpaper behind it.
        self.get_style_context().add_class("gtasks-popup")

        self.add(self._build())
        self.connect("key-press-event", self._on_key)
        self.connect("focus-out-event", self._on_focus_out)
        self.connect("delete-event", lambda *_args: self.hide_on_delete())
        store.subscribe(self.refresh)
        self.refresh()

    # -- layout -----------------------------------------------------------

    def _build(self) -> Gtk.Box:
        outer = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        set_margins(outer, 8)

        self.chooser = Gtk.MenuButton()
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.chooser_label = Gtk.Label(label=self.store.list_title(ALL_LISTS),
                                       xalign=0.0)
        self.chooser_label.set_ellipsize(Pango.EllipsizeMode.END)
        row.pack_start(self.chooser_label, True, True, 0)
        row.pack_end(Gtk.Image.new_from_icon_name("pan-down-symbolic",
                                                  Gtk.IconSize.BUTTON), False, False, 0)
        self.chooser.add(row)
        self.chooser_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=2)
        set_margins(self.chooser_box, 6)
        popover = Gtk.Popover()
        popover.add(self.chooser_box)
        self.chooser.set_popover(popover)
        outer.pack_start(self.chooser, False, False, 0)

        self.entry = Gtk.Entry(placeholder_text=ADD_PLACEHOLDER)
        self.entry.set_icon_from_icon_name(Gtk.EntryIconPosition.SECONDARY,
                                           "list-add-symbolic")
        self.entry.connect("activate", self._add_task)
        self.entry.connect("icon-press", lambda *_args: self._add_task(self.entry))
        outer.pack_start(self.entry, False, False, 0)

        self.stack = Gtk.Stack()
        self.list_box = Gtk.ListBox()
        self.list_box.set_selection_mode(Gtk.SelectionMode.NONE)
        self.list_box.set_header_func(self._list_header)
        self.tasks_page = scrolled(self.list_box)
        self.stack.add_named(self.tasks_page, "tasks")
        self.signin_page = SignInPage(self.store, self.on_reload, compact=True)
        self.stack.add_named(self.signin_page, "signin")
        outer.pack_start(self.stack, True, True, 0)

        bottom = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        self.status = Gtk.Label(label="", xalign=0.0)
        self.status.set_ellipsize(Pango.EllipsizeMode.END)
        self.status.get_style_context().add_class("gtasks-small")
        bottom.pack_start(self.status, True, True, 0)
        self.open_button = Gtk.Button(label="Open window")
        self.open_button.connect("clicked", lambda *_args: self.on_open_window())
        bottom.pack_end(self.open_button, False, False, 0)
        outer.pack_end(bottom, False, False, 0)
        return outer

    # -- showing and hiding -----------------------------------------------

    def show_at_pointer(self) -> None:
        """Put the popup under the pointer, inside the monitor work area."""
        spot = _pointer_position()
        if spot is None:
            self.show_all()
            return
        pointer_x, pointer_y = spot
        monitor = Gdk.Display.get_default().get_monitor_at_point(pointer_x, pointer_y)
        area = monitor.get_workarea() if monitor else None
        if area is not None:
            self.move(*place(pointer_x, pointer_y,
                             area.x, area.y, area.width, area.height))
        self.show_all()
        self.present()
        self.entry.grab_focus()

    def toggle(self) -> None:
        if self.get_visible():
            self.hide()
        else:
            self.show_at_pointer()

    def _on_key(self, _widget, event) -> bool:
        if event.keyval == Gdk.KEY_Escape:
            self.hide()
            return True
        return False

    def _on_focus_out(self, _widget, _event) -> bool:
        self.hide()
        return False

    # -- redraw -----------------------------------------------------------

    def refresh(self, _store=None) -> None:
        store = self.store
        if store.needs_signin:
            self.signin_page.show_for(store.auth)
            self.stack.set_visible_child(self.signin_page)
            self.entry.set_sensitive(False)
            self.chooser.set_sensitive(False)
            self.status.set_text("")
            return
        self.stack.set_visible_child(self.tasks_page)
        self.signin_page.reset()
        writable = not store.offline
        # Offline the text stays readable, it only cannot be changed.
        self.entry.set_sensitive(True)
        self.entry.set_editable(writable)
        self.entry.set_icon_sensitive(Gtk.EntryIconPosition.SECONDARY, writable)
        self.chooser.set_sensitive(True)
        self._refresh_chooser()
        self._refresh_tasks(writable)
        self.status.set_text(_status_text(store))

    def _refresh_chooser(self) -> None:
        store = self.store
        self.chooser_label.set_text(store.list_title(store.selected_list_id))
        key = [(item.id, item.title) for item in store.lists]
        if key == self._chooser_key:
            # The same lists, but the main window can change the choice.
            for button in self.chooser_box.get_children():
                button.set_active(button.list_id == store.selected_list_id)
            return
        self._chooser_key = key
        clear(self.chooser_box)
        group = None
        for list_id, title in [(ALL_LISTS, store.list_title(ALL_LISTS))] + key:
            button = Gtk.RadioButton.new_with_label_from_widget(group, title)
            group = group or button
            button.list_id = list_id
            button.set_active(list_id == store.selected_list_id)
            button.connect("toggled", self._choose_list, list_id)
            self.chooser_box.pack_start(button, False, False, 0)
        self.chooser_box.show_all()

    def _refresh_tasks(self, writable: bool) -> None:
        clear(self.list_box)
        today = dt.date.today()
        tasks = self.store.visible_tasks(self.store.selected_list_id,
                                         open_only=True, today=today)
        for task in tasks:
            self.list_box.add(TaskRow(task, self._toggle_task, editable=writable,
                                      today=today))
        if not tasks:
            self.list_box.add(placeholder_row("No open tasks."))
        self.list_box.show_all()
        self.list_box.invalidate_headers()

    def _list_header(self, row, before) -> None:
        """With "All lists" chosen, name the list above its first task."""
        if self.store.selected_list_id is not ALL_LISTS or not isinstance(row, TaskRow):
            row.set_header(None)
            return
        if isinstance(before, TaskRow) and before.task.list_id == row.task.list_id:
            row.set_header(None)
            return
        label = Gtk.Label(label=self.store.list_title(row.task.list_id), xalign=0.0)
        style = label.get_style_context()
        style.add_class("gtasks-small")
        style.add_class("gtasks-dim")
        label.set_margin_top(6)
        label.set_margin_bottom(2)
        label.set_margin_start(6)
        label.show()
        row.set_header(label)

    # -- actions ----------------------------------------------------------

    def _choose_list(self, button, list_id) -> None:
        if button.get_active() and self.store.selected_list_id != list_id:
            self.store.set_selected(list_id)

    def _toggle_task(self, task, done: bool) -> None:
        if done:
            self.worker.complete(task)
        else:
            self.worker.uncomplete(task)

    def _add_task(self, entry: Gtk.Entry) -> None:
        if not quick_add(entry, self.store, self.worker, self.default_list):
            self.status.set_text("No task list to add to.")


def _pointer_position() -> tuple[int, int] | None:
    """Where the mouse is now, or None when there is nobody to ask."""
    display = Gdk.Display.get_default()
    seat = display.get_default_seat() if display is not None else None
    pointer = seat.get_pointer() if seat is not None else None
    if pointer is None:
        return None
    _screen, pointer_x, pointer_y = pointer.get_position()
    return pointer_x, pointer_y


def _status_text(store) -> str:
    """The line at the bottom: the state, or the counts when all is well."""
    if store.offline:
        return OFFLINE_TEXT
    if store.error or store.status:
        return store.error or store.status
    counts = summary(store.lists)
    text = f"{counts['count']} open"
    if counts["overdue"]:
        text += f", {counts['overdue']} overdue"
    return text
