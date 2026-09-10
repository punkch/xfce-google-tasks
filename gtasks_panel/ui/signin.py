"""The sign-in page. Shown when there is no usable Google token.

The OAuth flow starts a local web server and waits for the browser. That
would block the worker thread, so it runs as a child process:
`gtasks-panel --auth`. We only watch for the process to end.
"""

import subprocess
import sys
import tempfile

import gi

gi.require_version("Gtk", "3.0")

from gi.repository import GLib, Gtk, Pango  # noqa: E402  (after require_version)

from .. import panel, paths  # noqa: E402  (after require_version)
from .widgets import set_margins  # noqa: E402  (after require_version)

POLL_MS = 500
NARROW = 34   # characters per line in the popup
WIDE = 60     # characters per line in the main window
KILL_WAIT = 2  # seconds we give the sign-in child to end by itself
ERROR_CHARS = 80  # of the child's last stderr line

STEPS = (
    "1. In Google Cloud Console make an OAuth client of type "
    "\"Desktop app\".",
    "2. Download its JSON file.",
    "3. Save the file at the path above, then click Try again.",
)


class SignInView(Gtk.Box):
    """Tells the user what is missing and starts the sign-in."""

    def __init__(self, verdict: str, store, on_done, compact: bool = False):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=10)
        self.verdict = verdict
        self.store = store
        self.on_done = on_done
        self.width = NARROW if compact else WIDE
        self._process: subprocess.Popen | None = None
        self._errors = None
        self._poll_id = 0
        set_margins(self, 12)
        self.set_valign(Gtk.Align.CENTER)
        # Centre the column. Without it the text stretches over the
        # whole window and the popup grows past its 380 pixels.
        self.set_halign(Gtk.Align.CENTER)

        icon = Gtk.Image.new_from_icon_name(paths.DEFAULTS["icon"], Gtk.IconSize.DIALOG)
        self.pack_start(icon, False, False, 0)

        self.pack_start(self._heading(verdict, self.width), False, False, 0)
        if verdict == paths.AUTH_NO_SECRET:
            self._add_secret_help()
        self.status = Gtk.Label(label="", xalign=0.5, wrap=True)
        self.status.set_max_width_chars(self.width)
        self.status.get_style_context().add_class("gtasks-small")
        self.pack_start(self.status, False, False, 0)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=6)
        buttons.set_halign(Gtk.Align.CENTER)
        label = "Try again" if verdict == paths.AUTH_NO_SECRET else "Sign in"
        self.button = Gtk.Button(label=label)
        self.button.get_style_context().add_class("suggested-action")
        self.button.connect("clicked", self._start)
        buttons.pack_start(self.button, False, False, 0)
        self.cancel = Gtk.Button(label="Cancel")
        self.cancel.set_no_show_all(True)
        self.cancel.connect("clicked", self._cancel)
        buttons.pack_start(self.cancel, False, False, 0)
        self.pack_start(buttons, False, False, 0)

        self.connect("destroy", self._stop_polling)

    # -- layout -----------------------------------------------------------

    @staticmethod
    def _heading(verdict: str, width: int) -> Gtk.Label:
        text = {
            paths.AUTH_NO_SECRET: "No OAuth client file yet",
            paths.AUTH_NO_TOKEN: "Sign in with Google to see your tasks",
            paths.AUTH_REAUTH: "The sign-in expired. Sign in again.",
        }.get(verdict, "Sign in with Google to see your tasks")
        label = Gtk.Label(xalign=0.5, wrap=True)
        label.set_max_width_chars(width)
        label.set_markup(f"<b>{GLib.markup_escape_text(text)}</b>")
        return label

    def _add_secret_help(self) -> None:
        path = Gtk.Label(label=str(paths.USER_SECRET_PATH), xalign=0.0, wrap=True,
                         selectable=True)
        # A path has no spaces to break at, so break it anywhere.
        path.set_line_wrap_mode(Pango.WrapMode.CHAR)
        path.set_max_width_chars(self.width)
        path.select_region(0, 0)  # do not open with the whole line marked
        path.get_style_context().add_class("gtasks-small")
        self.pack_start(path, False, False, 0)
        for step in STEPS:
            line = Gtk.Label(label=step, xalign=0.0, wrap=True)
            line.set_max_width_chars(self.width)
            line.get_style_context().add_class("gtasks-small")
            self.pack_start(line, False, False, 0)

    # -- the child process ------------------------------------------------

    def _start(self, _button) -> None:
        if self.verdict == paths.AUTH_NO_SECRET and not paths.SECRET_PATH.is_file():
            self.status.set_text("The file is still not there.")
            return
        # A file, not a pipe: nobody reads the pipe until the child ends,
        # and a full pipe would stop the child for good.
        self._errors = tempfile.TemporaryFile(mode="w+", encoding="utf-8")
        try:
            self._process = subprocess.Popen(
                [sys.executable, str(panel.entry_path()), "--auth"],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=self._errors)
        except OSError as exc:
            self._close_errors()
            self.status.set_text(f"Cannot start gtasks-panel --auth: {exc}")
            return
        self.button.set_sensitive(False)
        self.cancel.show()
        self.status.set_text("A browser window opens. Finish the sign-in there.")
        self._poll_id = GLib.timeout_add(POLL_MS, self._poll)

    def _poll(self) -> bool:
        if self._process is None or self._process.poll() is None:
            return True
        code = self._process.returncode
        self._process = None
        self._poll_id = 0
        self.button.set_sensitive(True)
        self.cancel.hide()
        if code == 0:
            self._close_errors()
            self.status.set_text("Signed in. Loading your tasks…")
            # Say it here: a load that fails would else leave both windows
            # on this page with "Loading your tasks…" and no way forward.
            self.store.set_auth(paths.AUTH_OK)
            self.on_done()
        else:
            reason = self._last_error_line()
            self.status.set_text(
                f"The sign-in did not finish. {reason}" if reason
                else "The sign-in did not finish. Try again.")
        return False

    def _last_error_line(self) -> str:
        """The last thing the child said, cut to one short line."""
        if self._errors is None:
            return ""
        try:
            self._errors.seek(0)
            lines = self._errors.read().splitlines()
        except OSError:
            lines = []
        finally:
            self._close_errors()
        last = next((line.strip() for line in reversed(lines) if line.strip()), "")
        last = " ".join(last.split())
        return last if len(last) <= ERROR_CHARS else last[:ERROR_CHARS - 1] + "…"

    def _close_errors(self) -> None:
        if self._errors is not None:
            self._errors.close()
            self._errors = None

    def _cancel(self, _button) -> None:
        if self._process is not None:
            self._process.terminate()

    def _stop_polling(self, _widget) -> None:
        if self._poll_id:
            GLib.source_remove(self._poll_id)
            self._poll_id = 0
        if self._process is not None:
            self._end_process(self._process)
            self._process = None
        self._close_errors()

    @staticmethod
    def _end_process(process: subprocess.Popen) -> None:
        """Stop the child and reap it, so no zombie stays behind."""
        process.terminate()
        try:
            process.wait(timeout=KILL_WAIT)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()


class SignInPage(Gtk.Box):
    """The sign-in page of a window. It rebuilds only on a new verdict."""

    def __init__(self, store, on_done, compact: bool = False):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.store = store
        self.on_done = on_done
        self.compact = compact
        self.verdict: str | None = None

    def reset(self) -> None:
        """Forget the last verdict, so the next sign-in starts with a fresh page."""
        self.verdict = None

    def show_for(self, verdict: str) -> None:
        """Fill the page for this verdict. The same verdict changes nothing."""
        if verdict == self.verdict:
            return
        self.verdict = verdict
        for child in self.get_children():
            self.remove(child)
            child.destroy()
        self.pack_start(SignInView(verdict, self.store, self.on_done, self.compact),
                        True, True, 0)
        self.show_all()
