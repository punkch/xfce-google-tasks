"""One background thread for every Google call.

The GTK main loop must never wait for the network. The windows post a job
here and get the answer back with `GLib.idle_add`, which runs it on the
GTK thread again. There is one thread only: `httplib2.Http` and the
credential refresh are not thread safe.
"""

import queue
import sys
import threading
from typing import Callable, NamedTuple

from gi.repository import GLib

from .. import api, auth, panel, state
from ..model import STATUS_DONE, STATUS_OPEN, Task, TaskList
from ..paths import AUTH_OK, AUTH_REAUTH

PANEL_RETRY_SECONDS = 5  # wait for a --fetch to let go of the state file lock


class AuthNeeded(Exception):
    """No usable sign-in. `verdict` is one of the AUTH_* names."""

    def __init__(self, verdict: str):
        super().__init__(verdict)
        self.verdict = verdict


class Job(NamedTuple):
    """One piece of work for the thread. `fn(service)` runs there."""

    fn: Callable
    on_done: Callable | None = None
    on_error: Callable | None = None
    quiet: bool = False
    uses_service: bool = True


class Worker:
    """Job queue with a thread behind it. Post from the GTK thread only."""

    def __init__(self, store):
        self.store = store
        self._jobs: queue.Queue = queue.Queue()
        self._service = None
        self._thread: threading.Thread | None = None
        self._load_pending = False

    # -- thread -----------------------------------------------------------

    def start(self) -> None:
        if self._thread is None:
            self._thread = threading.Thread(target=self._run, name="gtasks-worker",
                                            daemon=True)
            self._thread.start()

    def stop(self, timeout: float | None = None) -> None:
        """Ask the thread to end. Wait for the job it runs now, if asked."""
        self._jobs.put(None)
        if timeout and self._thread is not None:
            self._thread.join(timeout)

    def post(self, function, on_done=None, on_error=None,
             uses_service: bool = True, quiet: bool = False) -> None:
        """Queue one job. `function(service)` runs in the worker thread."""
        self._jobs.put(Job(function, on_done, on_error, quiet, uses_service))

    def reset_service(self) -> None:
        """Forget the service. The next job signs in again."""
        self.post(self._clear_service, uses_service=False, quiet=True)

    def _clear_service(self, _service=None) -> None:
        self._service = None

    def _run(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            try:
                result = job.fn(self._service_now() if job.uses_service else None)
            except Exception as exc:  # a job must never kill the thread
                GLib.idle_add(self.on_failed, exc, job.on_error, job.quiet)
                continue
            GLib.idle_add(self.on_finished, result, job.on_done, job.uses_service,
                          job.quiet)

    def _service_now(self):
        if self._service is None:
            creds, verdict = auth.load_credentials()
            if verdict != AUTH_OK:
                raise AuthNeeded(verdict)
            self._service = api.build_service(creds)
        return self._service

    # -- results, back on the GTK thread ----------------------------------

    def on_finished(self, result, on_done, used_service: bool,
                    quiet: bool = False) -> bool:
        """A job came back with an answer. Runs on the GTK thread."""
        if not quiet:
            fields = {"status": ""}
            if used_service:  # a job that talked to Google proves all of these
                fields.update(offline=False, error="", auth=AUTH_OK)
            self.store.update(**fields)
        if on_done:
            on_done(result)
        return False

    def on_failed(self, exc, on_error=None, quiet: bool = False) -> bool:
        """A job raised. Runs on the GTK thread."""
        verdict = self._auth_verdict(exc)
        if verdict:
            self._clear_service()
            self.store.update(auth=verdict)
        elif quiet:
            # No window shows a quiet job, so the error would be lost.
            print(error_text(exc), file=sys.stderr)
        else:
            self.store.update(error=error_text(exc), offline=not _from_google(exc),
                              status="")
        if on_error:
            on_error(exc)
        return False

    @staticmethod
    def _auth_verdict(exc) -> str | None:
        if isinstance(exc, AuthNeeded):
            return exc.verdict
        return AUTH_REAUTH if auth.needs_reauth(exc) else None

    # -- jobs -------------------------------------------------------------

    def reload(self) -> bool:
        """Read every list from Google and save the cache.

        False when a load is already on its way: a second one would ask
        Google the same question and answer it with the same lists.
        """
        if self._load_pending:
            return False
        self._load_pending = True
        show = self.store.show_completed
        self.store.set_status("Loading…")

        def job(service) -> list[TaskList]:
            lists = api.fetch_lists(service, show_completed=show)
            try:
                state.save_cache(lists)
            except OSError as exc:  # a cache we cannot write is still a good fetch
                print(f"Cannot save the task cache: {exc}", file=sys.stderr)
            return lists

        def done(lists: list[TaskList]) -> None:
            self._load_pending = False
            self.store.has_completed = show
            self.store.set_lists(lists)

        def failed(_exc) -> None:
            self._load_pending = False

        self.post(job, done, failed)
        return True

    def complete(self, task: Task) -> None:
        self.set_done(task, True)
        self.post(lambda service: api.complete_task(service, task.list_id, task.id),
                  self._written, lambda _exc: self.set_done(task, False))

    def uncomplete(self, task: Task) -> None:
        self.set_done(task, False)
        self.post(lambda service: api.uncomplete_task(service, task.list_id, task.id),
                  self._written, lambda _exc: self.set_done(task, True))

    def add(self, list_id: str, title: str) -> None:
        def done(task: Task) -> None:
            self.store.add_task(task, 0)
            self._notify_panel()

        self.post(lambda service: api.insert_task(service, list_id, title), done)

    def patch(self, task: Task, **fields) -> None:
        """Change title, notes or due. The view shows it before Google does."""
        old = {key: getattr(task, key) for key in fields}
        for key, value in fields.items():
            setattr(task, key, value)
        self.store.notify()

        def failed(_exc) -> None:
            for key, value in old.items():
                setattr(task, key, value)

        self.post(lambda service: api.patch_task(service, task.list_id, task.id, **fields),
                  self._written, failed)

    def move(self, task: Task, destination_list_id: str) -> None:
        index = self.store.remove_task(task)

        def done(moved: Task) -> None:
            # A load can put the task back while we wait for the answer.
            self.store.remove_task(task)
            self.store.add_task(moved, 0)
            self._notify_panel()

        def failed(_exc) -> None:
            if self.store.find_task(task.list_id, task.id) is None:
                self.store.add_task(task, max(index, 0))

        self.post(lambda service: api.move_task(service, task.list_id, task.id,
                                                destination_list_id),
                  done, failed)

    def delete(self, task: Task, index: int = -1) -> None:
        """Delete for good. The window already took the row out of the view."""
        def failed(_exc) -> None:
            if self.store.find_task(task.list_id, task.id) is None:
                self.store.add_task(task, max(index, 0))

        self.post(lambda service: api.delete_task(service, task.list_id, task.id),
                  self._written, failed)

    # -- helpers ----------------------------------------------------------

    def set_done(self, task: Task, done: bool) -> None:
        """Show a task as done, or open again, before Google answers."""
        task.status = STATUS_DONE if done else STATUS_OPEN
        self.store.notify()

    def _written(self, result) -> None:
        if isinstance(result, Task):
            self.store.replace_task(result)
        self._notify_panel()

    def _notify_panel(self, retry: bool = True) -> None:
        """Save the new counts and make the panel item redraw itself."""
        snapshot = self.store.snapshot()

        def done(written: bool) -> None:
            if not written and retry:
                # A --fetch holds the lock and writes older counts than
                # ours. Come back when it is done.
                GLib.timeout_add_seconds(PANEL_RETRY_SECONDS, self._retry_panel)

        self.post(lambda _service: panel.notify_summary(snapshot), done,
                  uses_service=False, quiet=True)

    def _retry_panel(self) -> bool:
        self._notify_panel(retry=False)
        return False


def _from_google(exc: BaseException) -> bool:
    """True when Google answered with an error. Then we are not offline.

    A googleapiclient HttpError carries the response. A DNS, socket or
    timeout error carries nothing.
    """
    return hasattr(exc, "resp")


def error_text(exc: BaseException) -> str:
    """Short text for the user.

    A googleapiclient HttpError says `<HttpError 404 when requesting …>`
    in `str()`, which helps nobody. It also carries `reason`, which is
    the message Google wrote.
    """
    reason = getattr(exc, "reason", None)
    if _from_google(exc) and isinstance(reason, str) and reason.strip():
        return reason.strip()
    return state.error_text(exc)
