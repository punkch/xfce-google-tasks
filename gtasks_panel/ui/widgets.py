"""Small parts that the popup and the main window both use."""

import datetime as dt

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gdk, Gtk, Pango  # noqa: E402  (after require_version)

from ..model import Task, due_text, is_overdue

INDENT = 18  # pixels for each sub-task level
OFFLINE_TEXT = "Offline. Showing saved tasks."
ADD_PLACEHOLDER = "New task"

CSS = b"""
.gtasks-overdue { color: #c01c28; }
.gtasks-small { font-size: smaller; }
.gtasks-dim { opacity: 0.5; }
.gtasks-popup { border: 1px solid alpha(currentColor, 0.3); }
"""


def install_css() -> None:
    """Add the style classes this UI uses. Safe to call more than once."""
    screen = Gdk.Screen.get_default()
    if screen is None:
        return
    provider = Gtk.CssProvider()
    provider.load_from_data(CSS)
    Gtk.StyleContext.add_provider_for_screen(
        screen, provider, Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)


def set_margins(widget: Gtk.Widget, size: int) -> None:
    """The same margin on all four sides."""
    widget.set_property("margin", size)


def scrolled(child: Gtk.Widget, shadow: bool = False) -> Gtk.ScrolledWindow:
    """`child` in a box that scrolls up and down, never sideways."""
    scroller = Gtk.ScrolledWindow()
    scroller.set_policy(Gtk.PolicyType.NEVER, Gtk.PolicyType.AUTOMATIC)
    if shadow:
        scroller.set_shadow_type(Gtk.ShadowType.IN)
    scroller.add(child)
    return scroller


def quick_add(entry: Gtk.Entry, store, worker, default_list: str) -> bool:
    """Add the task in the entry. False when there is no list to add to."""
    title = entry.get_text().strip()
    if not title:
        return True
    list_id = store.add_target(default_list)
    if list_id is None:
        return False
    entry.set_text("")
    worker.add(list_id, title)
    return True


def set_strikethrough(label: Gtk.Label, on: bool) -> None:
    """Draw a line through the text, or take it away."""
    attributes = Pango.AttrList()
    if on:
        attributes.insert(Pango.attr_strikethrough_new(True))
    label.set_attributes(attributes)


def clear(container: Gtk.Container) -> None:
    for child in container.get_children():
        container.remove(child)
        child.destroy()


def placeholder_row(text: str) -> Gtk.ListBoxRow:
    """A grey line for a list with nothing in it."""
    row = Gtk.ListBoxRow()
    row.set_selectable(False)
    label = Gtk.Label(label=text, xalign=0.5)
    label.get_style_context().add_class("gtasks-dim")
    label.set_margin_top(16)
    label.set_margin_bottom(16)
    row.add(label)
    return row


class ListRow(Gtk.ListBoxRow):
    """One task list in the sidebar: title and the number of open tasks."""

    def __init__(self, list_id: str | None, title: str, count: int):
        super().__init__()
        self.list_id = list_id
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(10)
        box.set_margin_end(10)
        name = Gtk.Label(label=title, xalign=0.0)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        box.pack_start(name, True, True, 0)
        number = Gtk.Label(label=str(count), xalign=1.0)
        number.get_style_context().add_class("gtasks-dim")
        box.pack_end(number, False, False, 0)
        self.add(box)


class TaskRow(Gtk.ListBoxRow):
    """One task: check button, title, due date. Indented by sub-task level."""

    def __init__(self, task: Task, on_toggle, editable: bool = True,
                 today: dt.date | None = None):
        super().__init__()
        self.task = task
        self._on_toggle = on_toggle

        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        box.set_margin_top(4)
        box.set_margin_bottom(4)
        box.set_margin_start(6 + INDENT * task.depth)
        box.set_margin_end(6)
        self.add(box)

        self.check = Gtk.CheckButton()
        self.check.set_active(task.completed)
        self.check.set_sensitive(editable)
        self.check.set_tooltip_text("Mark done" if not task.completed else "Open again")
        box.pack_start(self.check, False, False, 0)

        self.title = Gtk.Label(label=task.title or "(no title)", xalign=0.0)
        self.title.set_ellipsize(Pango.EllipsizeMode.END)
        set_strikethrough(self.title, task.completed)
        if task.completed:
            self.title.get_style_context().add_class("gtasks-dim")
        box.pack_start(self.title, True, True, 0)

        self.due = None
        text = due_text(task.due, today)
        if text:
            self.due = Gtk.Label(label=text, xalign=1.0)
            self.due.get_style_context().add_class("gtasks-small")
            if is_overdue(task, today):
                self.due.get_style_context().add_class("gtasks-overdue")
            box.pack_end(self.due, False, False, 0)

        # Connect last: set_active above must not look like a user click.
        self.check.connect("toggled", self._toggled)

    def _toggled(self, button: Gtk.CheckButton) -> None:
        self._on_toggle(self.task, button.get_active())
