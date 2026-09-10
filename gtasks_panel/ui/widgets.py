"""Small parts that the popup and the main window both use."""

import datetime as dt

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")

from gi.repository import Gdk, GLib, Gtk, Pango  # noqa: E402  (after require_version)

from ..model import Task, due_text, is_overdue
from .click import due_shortcuts

INDENT = 24  # pixels for each sub-task level: one check button plus its gap
OFFLINE_TEXT = "Offline. Showing saved tasks."
NO_LIST_TEXT = "No task list to add to."
ADD_PLACEHOLDER = "New task"
DUE_ICON = "x-office-calendar-symbolic"   # shown when a task has no due date
MENU_ICON = "view-more-symbolic"          # the "…" button of a list row

# A selected row is white on blue, so the fixed overdue red must change
# with it. The popup border is opaque: alpha() needs a compositor, and
# without one it comes out black.
CSS = b"""
.gtasks-overdue { color: #c01c28; }
row:selected .gtasks-overdue { color: #ffd6d9; }
.gtasks-small { font-size: smaller; }
.gtasks-dim { opacity: 0.5; }
.gtasks-header { color: shade(@theme_fg_color, 1.35); font-weight: bold; }
.gtasks-popup { border: 1px solid shade(@theme_bg_color, 0.85); }
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


def quick_add(entry: Gtk.Entry, store, worker, default_list: str,
              due: dt.date | None = None) -> bool:
    """Add the task in the entry. False when there is no list to add to."""
    title = entry.get_text().strip()
    if not title:
        return True
    list_id = store.add_target(default_list)
    if list_id is None:
        return False
    entry.set_text("")
    worker.add(list_id, title, due=due)
    return True


def add_from_entry(entry: Gtk.Entry, due_button: "DueButton", store, worker,
                   default_list: str) -> bool:
    """Quick-add with the due date on the button. False: no list to add to.

    The date is used up when the job is posted, so the next task starts
    with none. A failed add is rare, and a lost date is cheap.
    """
    had_text = bool(entry.get_text().strip())
    if not quick_add(entry, store, worker, default_list, due=due_button.date):
        return False
    if had_text:
        due_button.show_date(None)
    return True


def confirm(parent, title: str, text: str, action_label: str,
            destructive: bool = True) -> bool:
    """Ask the user before we do something that we cannot undo.

    True when the user chose the action. The dialog is modal: it stops
    the window below it until the user answers.
    """
    dialog = Gtk.MessageDialog(transient_for=parent, modal=True,
                               message_type=Gtk.MessageType.QUESTION,
                               buttons=Gtk.ButtonsType.NONE, text=title)
    dialog.format_secondary_text(text)
    dialog.add_button("Cancel", Gtk.ResponseType.CANCEL)
    button = dialog.add_button(action_label, Gtk.ResponseType.OK)
    if destructive:
        button.get_style_context().add_class("destructive-action")
    # Cancel is the safe answer, so Enter and Escape both give it.
    dialog.set_default_response(Gtk.ResponseType.CANCEL)
    answer = dialog.run()
    dialog.destroy()
    return answer == Gtk.ResponseType.OK


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


class DuePopover(Gtk.Popover):
    """A calendar and quick buttons to pick a due date.

    `on_pick(date)` gets the new date, or None for "no due date". The
    popover closes itself before it calls back, so the user does not see
    it stay open on top of the change.

    `today` is the day the quick buttons count from. A test gives its own
    day; the windows give the real one.
    """

    def __init__(self, on_pick, today: dt.date | None = None, title: str = ""):
        super().__init__()
        self._on_pick = on_pick
        self.today = today
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
        set_margins(box, 6)

        # The popover covers the row it changes, so it names the task.
        self.title_label = Gtk.Label(label=title, xalign=0.0)
        self.title_label.set_ellipsize(Pango.EllipsizeMode.END)
        self.title_label.set_max_width_chars(30)
        self.title_label.get_style_context().add_class("gtasks-small")
        self.title_label.set_no_show_all(True)
        self.title_label.set_visible(bool(title))
        box.pack_start(self.title_label, False, False, 0)

        self.calendar = Gtk.Calendar()
        self.calendar.connect("day-selected-double-click",
                              lambda *_args: self.pick(self.date()))
        box.pack_start(self.calendar, True, True, 0)

        shortcuts = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6,
                            homogeneous=True)
        made = {}
        for name in due_shortcuts(self._today()):
            button = Gtk.Button(label=name)
            button.connect("clicked", self._shortcut, name)
            shortcuts.pack_start(button, True, True, 0)
            made[name] = button
        self.today_button = made["Today"]
        self.tomorrow_button = made["Tomorrow"]
        box.pack_start(shortcuts, False, False, 0)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6,
                          homogeneous=True)
        self.clear_button = Gtk.Button(label="Clear")
        self.clear_button.connect("clicked", lambda *_args: self.pick(None))
        buttons.pack_start(self.clear_button, True, True, 0)
        self.set_button = Gtk.Button(label="Set")
        self.set_button.connect("clicked", lambda *_args: self.pick(self.date()))
        buttons.pack_start(self.set_button, True, True, 0)
        box.pack_start(buttons, False, False, 0)

        self.add(box)
        box.show_all()

    def _today(self) -> dt.date:
        return self.today or dt.date.today()

    def _shortcut(self, _button, name: str) -> None:
        # The date comes from the day of the click, not the day the
        # window opened: a window can stay open over midnight.
        self.pick(due_shortcuts(self._today())[name])

    def date(self) -> dt.date:
        """The day the calendar shows. Gtk months start at 0."""
        year, month, day = self.calendar.get_date()
        return dt.date(year, month + 1, day)

    def select(self, date: dt.date | None) -> None:
        """Put the calendar on a day. None puts it on today."""
        date = date or self._today()
        self.calendar.select_month(date.month - 1, date.year)
        self.calendar.select_day(date.day)

    def pick(self, date: dt.date | None) -> None:
        """Close the popover and give the date to the callback."""
        self.popdown()
        self._on_pick(date)


class DueButton(Gtk.Button):
    """A flat button that opens a `DuePopover`.

    It shows the due date when there is one, and a calendar icon when
    there is none. `date` is the date it shows. The popover, with its
    calendar, is made on the first click: a list redraws every row on
    each change, and a calendar per row would make that slow.
    """

    def __init__(self, on_pick, today: dt.date | None = None,
                 tooltip: str = "Due date", title: str = ""):
        super().__init__()
        self._on_pick = on_pick
        self._today = today
        self._title = title
        self._popover: DuePopover | None = None
        self.date: dt.date | None = None
        self.get_style_context().add_class("flat")
        self.set_tooltip_text(tooltip)
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=4)
        self.icon = Gtk.Image.new_from_icon_name(DUE_ICON, Gtk.IconSize.BUTTON)
        self.label = Gtk.Label()
        self.label.get_style_context().add_class("gtasks-small")
        # Only one of the two shows at a time, so `show_all` must not
        # bring the other one back.
        for child in (self.icon, self.label):
            child.set_no_show_all(True)
            box.pack_start(child, False, False, 0)
        self.add(box)
        box.show_all()
        self.connect("clicked", self._open)
        self.show_date(None, today)

    @property
    def due_popover(self) -> DuePopover:
        """The popover. Made on first use."""
        if self._popover is None:
            self._popover = DuePopover(self._on_pick, today=self._today,
                                       title=self._title)
            self._popover.set_relative_to(self)
            self._popover.select(self.date)
        return self._popover

    def _open(self, _button) -> None:
        self.due_popover.select(self.date)
        self.due_popover.popup()

    def show_date(self, date: dt.date | None, today: dt.date | None = None,
                  overdue: bool = False) -> None:
        """Put a date on the button. The calendar follows on the next open."""
        self.date = date
        text = due_text(date, today or self._today)
        self.label.set_text(text)
        self.label.set_visible(bool(text))
        self.icon.set_visible(not text)
        style = self.label.get_style_context()
        if overdue and text:
            style.add_class("gtasks-overdue")
        else:
            style.remove_class("gtasks-overdue")


class ListRow(Gtk.ListBoxRow):
    """One task list in the sidebar: title and the number of open tasks.

    With `on_menu` the row gets a "…" button and a right-click handler.
    Both call `on_menu(row, event)`, where `event` is the click event or
    None. The "All lists" row has no menu, so it passes `on_menu=None`.
    """

    def __init__(self, list_id: str | None, title: str, count: int,
                 on_menu=None):
        super().__init__()
        self.list_id = list_id
        self._on_menu = on_menu
        self._hovered = False
        box = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        box.set_margin_top(6)
        box.set_margin_bottom(6)
        box.set_margin_start(10)
        box.set_margin_end(10)
        name = Gtk.Label(label=title, xalign=0.0)
        name.set_ellipsize(Pango.EllipsizeMode.END)
        box.pack_start(name, True, True, 0)

        # Every row gets the button, so the counts line up in one column.
        # A row without a menu keeps it empty and out of the focus chain.
        self.menu_button = Gtk.Button.new_from_icon_name(MENU_ICON, Gtk.IconSize.BUTTON)
        self.menu_button.set_relief(Gtk.ReliefStyle.NONE)
        self.menu_button.set_opacity(0)   # it comes with the pointer
        box.pack_end(self.menu_button, False, False, 0)
        if on_menu is not None:
            self.menu_button.set_tooltip_text("List actions")
            self.menu_button.connect("clicked", lambda *_args: on_menu(self, None))
            for signal in ("focus-in-event", "focus-out-event"):
                self.menu_button.connect(signal, self._on_focus_change)
                self.connect(signal, self._on_focus_change)
        else:
            self.menu_button.set_sensitive(False)
            self.menu_button.set_can_focus(False)

        number = Gtk.Label(label=str(count), xalign=1.0)
        number.get_style_context().add_class("gtasks-dim")
        box.pack_end(number, False, False, 0)

        if on_menu is None:
            self.add(box)
            return
        # A ListBoxRow has no window of its own, so it gets no pointer
        # and no button events. An event box with no window of its own
        # gets them and does not change how the row looks.
        events = Gtk.EventBox()
        events.set_visible_window(False)
        events.add_events(Gdk.EventMask.ENTER_NOTIFY_MASK
                          | Gdk.EventMask.LEAVE_NOTIFY_MASK
                          | Gdk.EventMask.BUTTON_PRESS_MASK)
        events.add(box)
        events.connect("enter-notify-event", self._on_enter)
        events.connect("leave-notify-event", self._on_leave)
        events.connect("button-press-event", self._on_press)
        self.connect("popup-menu", self._on_popup_menu)
        self.add(events)

    def _show_menu_button(self) -> None:
        focused = self.has_focus() or self.menu_button.has_focus()
        self.menu_button.set_opacity(1.0 if self._hovered or focused else 0.0)

    def _on_focus_change(self, _widget, _event) -> bool:
        # The focus moves before the signal ends. Look after it has.
        GLib.idle_add(self._show_menu_button)
        return False

    def _on_enter(self, _widget, _event) -> bool:
        self._hovered = True
        self._show_menu_button()
        return False

    def _on_leave(self, _widget, event) -> bool:
        # A move onto a child is still inside the row.
        if event.detail == Gdk.NotifyType.INFERIOR:
            return False
        self._hovered = False
        self._show_menu_button()
        return False

    def _on_press(self, _widget, event) -> bool:
        if event.button != 3:
            return False
        self._on_menu(self, event)
        return True

    def _on_popup_menu(self, _widget) -> bool:
        """The Menu key: the same menu without a pointer."""
        self._on_menu(self, None)
        return True


class TaskRow(Gtk.ListBoxRow):
    """One task: check button, title, due date. Indented by sub-task level.

    With `due_picker` the due date becomes a button that opens a
    calendar. A pick calls `on_due(task, date)`, with None for "no due
    date".
    """

    def __init__(self, task: Task, on_toggle, editable: bool = True,
                 today: dt.date | None = None, due_picker: bool = False,
                 on_due=None):
        super().__init__()
        self.task = task
        self._on_toggle = on_toggle
        self._on_due = on_due

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
        self.due_button = None
        if due_picker:
            self.due_button = DueButton(self._picked, today=today,
                                        title=task.title or "(no title)")
            self.due_button.show_date(task.due, today, is_overdue(task, today))
            self.due_button.set_sensitive(editable)
            box.pack_end(self.due_button, False, False, 0)
        elif text := due_text(task.due, today):
            self.due = Gtk.Label(label=text, xalign=1.0)
            self.due.get_style_context().add_class("gtasks-small")
            if is_overdue(task, today):
                self.due.get_style_context().add_class("gtasks-overdue")
            box.pack_end(self.due, False, False, 0)

        # Connect last: set_active above must not look like a user click.
        self.check.connect("toggled", self._toggled)

    def _toggled(self, button: Gtk.CheckButton) -> None:
        self._on_toggle(self.task, button.get_active())

    def _picked(self, date: dt.date | None) -> None:
        if self._on_due is not None:
            self._on_due(self.task, date)
