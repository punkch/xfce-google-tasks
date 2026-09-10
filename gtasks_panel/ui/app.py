"""The application object. One process serves the popup and the window.

The panel starts `gtasks-window` on every click. The second process hands
its arguments to the first one over DBus and stops. The first one stays
resident (`hold`), so the next click opens the popup at once.
"""

from pathlib import Path
from typing import TYPE_CHECKING

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import Gio, Gtk  # noqa: E402  (after require_version)

from .. import paths  # noqa: E402  (after require_version)
from .click import classify_click, double_click_threshold, parse_args  # noqa: E402
from .store import TaskStore  # noqa: E402  (after require_version)

if TYPE_CHECKING:  # the windows and the worker load in do_startup only
    from .mainwindow import MainWindow
    from .popup import Popup
    from .worker import Worker

APP_ID = "com.belneiski.gtasks"
STOP_WAIT = 3.0  # seconds we give the worker to finish its last job


class GtasksApplication(Gtk.Application):
    """Single instance. Every later start talks to this one."""

    def __init__(self, entry: Path | None = None):
        super().__init__(application_id=APP_ID,
                         flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.cfg: dict = {}
        self.store: "TaskStore | None" = None
        self.worker: "Worker | None" = None
        self._entry = entry
        self._popup: "Popup | None" = None
        self._window: "MainWindow | None" = None
        self._prev_click: float | None = None
        self._threshold = 0.0  # do_startup asks Gtk for the real one
        self._loaded = False

    # -- lifetime ---------------------------------------------------------

    def do_startup(self) -> None:
        Gtk.Application.do_startup(self)
        # Only the first process runs this. A second process forwards its
        # command line over D-Bus and stops, so it must not pay for the
        # windows, the worker or the panel module.
        from .. import panel, state
        from ..config import load_config
        from .widgets import install_css
        from .worker import Worker

        panel.configure(entry=self._entry)
        Gtk.Window.set_default_icon_name(paths.DEFAULTS["icon"])
        install_css()
        self._threshold = double_click_threshold(_gtk_double_click_time())
        self.cfg = load_config()
        self.store = TaskStore()
        self.worker = Worker(self.store)
        for name, handler in (("quit", self._act_quit),
                              ("refresh", self._act_refresh)):
            action = Gio.SimpleAction.new(name, None)
            action.connect("activate", handler)
            self.add_action(action)

        # The cache first: the popup must appear without waiting for Google.
        cached = state.load_cache()
        if cached:
            self.store.set_lists(cached)
        self.worker.start()
        self.hold()  # stay resident after the popup hides

    def do_activate(self) -> None:
        """Nothing to do: every start comes through do_command_line."""

    def do_command_line(self, command_line) -> int:
        clicked_at, quit_now, window = parse_args(command_line.get_arguments()[1:])
        if quit_now:
            # No Google job first: --quit must end at once, even when it
            # is the process that just started.
            self.stop()
            return 0
        self._first_load()
        if window or clicked_at is None:
            self.present_window()
            return 0
        kind = classify_click(self._prev_click, clicked_at, self._threshold)
        self._prev_click = clicked_at
        if kind == "double":
            if self._popup is not None:
                self._popup.hide()
            self.present_window()
        else:
            self.popup.toggle()
        return 0

    def _first_load(self) -> None:
        """Read the tasks from Google. The first command line asks for it."""
        if not self._loaded:
            self._loaded = True
            self.worker.reload()

    def stop(self) -> None:
        """Finish the last write, then end the process."""
        if self._window is not None:
            self._window.flush_edits()
            self._window.flush_delete()
        if self.worker is not None:
            self.worker.stop(STOP_WAIT)
        self.quit()

    # -- windows ----------------------------------------------------------

    @property
    def popup(self) -> "Popup":
        if self._popup is None:
            from .popup import Popup

            self._popup = Popup(self.store, self.worker, self._default_list(),
                                self.open_window, self.reload)
        return self._popup

    @property
    def window(self) -> "MainWindow":
        if self._window is None:
            from .mainwindow import MainWindow

            self._window = MainWindow(self.store, self.worker, self._default_list(),
                                      self.reload, application=self)
        return self._window

    def _default_list(self) -> str:
        """Title of the list a quick-add goes to. Empty means "the first"."""
        return self.cfg.get("default_list", "")

    def present_window(self) -> None:
        window = self.window
        window.show_all()
        window.present()

    def open_window(self) -> None:
        if self._popup is not None:
            self._popup.hide()
        self.present_window()

    def reload(self) -> None:
        """Sign in again if needed, then read every list from Google."""
        self._loaded = True
        self.worker.reset_service()
        self.worker.reload()

    # -- actions ----------------------------------------------------------

    def _act_quit(self, *_args) -> None:
        self.stop()

    def _act_refresh(self, *_args) -> None:
        self.reload()


def _gtk_double_click_time() -> int | None:
    settings = Gtk.Settings.get_default()
    if settings is None:
        return None
    return settings.get_property("gtk-double-click-time")


def run(argv: list[str], entry: Path | None = None) -> int:
    """Start or talk to the application. `argv` starts with the program.

    `entry` is the path of the `gtasks-panel` script beside us. The
    sign-in page starts it as a child process.
    """
    return GtasksApplication(entry).run(argv)
