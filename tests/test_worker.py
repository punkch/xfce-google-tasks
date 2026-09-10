"""The worker without its thread.

Every job is a function plus two callbacks. The tests take the job the
worker posts and run the callbacks by hand, so nothing reaches Google and
nothing needs a display.
"""

import pytest

pytest.importorskip("gi")

from gtasks_panel.model import Task, TaskList  # noqa: E402
from gtasks_panel.paths import AUTH_NO_TOKEN  # noqa: E402
from gtasks_panel.ui.store import TaskStore  # noqa: E402
from gtasks_panel.ui.worker import AuthNeeded, Job, Worker, error_text  # noqa: E402


class Jobs:
    """Takes the place of `Worker.post` and keeps every job."""

    def __init__(self):
        self.jobs = []

    def __call__(self, function, on_done=None, on_error=None,
                 uses_service=True, quiet=False):
        self.jobs.append(Job(function, on_done, on_error, quiet, uses_service))

    @property
    def last(self) -> Job:
        return self.jobs[-1]


class FakeHttpError(Exception):
    """Looks like googleapiclient.errors.HttpError: response and reason."""

    def __init__(self, message, reason=""):
        super().__init__(message)
        self.resp = object()
        self.reason = reason


def parts():
    store = TaskStore()
    store.set_lists([
        TaskList(id="L1", title="Work", tasks=[
            Task(id="t1", list_id="L1", title="Report", notes="old",
                 position="00001"),
            Task(id="t2", list_id="L1", title="Bank", position="00002"),
        ]),
        TaskList(id="L2", title="Home", tasks=[]),
    ])
    worker = Worker(store)
    jobs = Jobs()
    worker.post = jobs
    return store, worker, jobs


# -- results ---------------------------------------------------------------

def test_an_answer_from_google_is_not_offline():
    store, worker, _jobs = parts()
    worker.on_failed(FakeHttpError("Task not found"))
    assert store.offline is False
    assert store.error == "Task not found"


def test_a_network_error_is_offline():
    store, worker, _jobs = parts()
    worker.on_failed(OSError("Name or service not known"))
    assert store.offline is True
    assert store.error == "Name or service not known"


def test_a_good_job_clears_the_error():
    store, worker, _jobs = parts()
    worker.on_failed(OSError("no network"))
    worker.on_finished([], None, True)
    assert store.offline is False
    assert store.error == ""


def test_a_job_that_never_asked_google_does_not_clear_offline():
    store, worker, _jobs = parts()
    worker.on_failed(OSError("no network"))
    worker.on_finished(None, None, False)
    assert store.offline is True
    assert store.status == ""


def test_a_quiet_job_says_its_error_on_stderr_and_leaves_the_store_alone(capsys):
    store, worker, _jobs = parts()
    worker.on_failed(OSError("cannot write"), None, True)
    assert store.error == "" and store.offline is False
    assert "cannot write" in capsys.readouterr().err


def test_an_http_error_shows_the_reason_google_wrote():
    long_str = FakeHttpError("<HttpError 404 when requesting … >", reason="Not Found")
    assert error_text(long_str) == "Not Found"
    assert error_text(OSError("no route")) == "no route"


def test_a_sign_in_error_sets_the_verdict_and_drops_the_service():
    store, worker, _jobs = parts()
    worker._service = object()
    worker.on_failed(AuthNeeded(AUTH_NO_TOKEN))
    assert store.auth == AUTH_NO_TOKEN
    assert worker._service is None
    assert store.error == ""  # the sign-in page says it, not the error bar


# -- optimistic writes that go wrong ---------------------------------------

def test_complete_goes_back_when_google_says_no():
    store, worker, jobs = parts()
    task = store.find_task("L1", "t1")
    worker.complete(task)
    assert task.completed is True
    worker.on_failed(FakeHttpError("boom"), jobs.last.on_error)
    assert task.completed is False


def test_uncomplete_goes_back_when_google_says_no():
    store, worker, jobs = parts()
    task = store.find_task("L1", "t1")
    task.status = "completed"
    worker.uncomplete(task)
    assert task.completed is False
    worker.on_failed(FakeHttpError("boom"), jobs.last.on_error)
    assert task.completed is True


def test_patch_puts_the_old_fields_back():
    store, worker, jobs = parts()
    task = store.find_task("L1", "t1")
    worker.patch(task, title="New title", notes="new")
    assert (task.title, task.notes) == ("New title", "new")
    worker.on_failed(OSError("down"), jobs.last.on_error)
    assert (task.title, task.notes) == ("Report", "old")


def test_move_puts_the_task_back_at_its_old_place():
    store, worker, jobs = parts()
    task = store.find_task("L1", "t2")
    worker.move(task, "L2")
    assert store.find_task("L1", "t2") is None
    worker.on_failed(OSError("down"), jobs.last.on_error)
    assert [t.id for t in store.lists[0].tasks] == ["t1", "t2"]


def test_move_does_not_add_a_second_copy_after_a_load():
    store, worker, jobs = parts()
    task = store.find_task("L1", "t1")
    worker.move(task, "L2")
    store.set_lists([TaskList(id="L1", title="Work", tasks=[task]),
                     TaskList(id="L2", title="Home", tasks=[])])
    moved = Task(id="t1", list_id="L2", title="Report")
    jobs.last.on_done(moved)
    assert [t.id for t in store.lists[0].tasks] == []
    assert [t.id for t in store.lists[1].tasks] == ["t1"]


def test_a_failed_move_after_a_load_does_not_add_a_second_copy():
    store, worker, jobs = parts()
    task = store.find_task("L1", "t1")
    worker.move(task, "L2")
    store.set_lists([TaskList(id="L1", title="Work", tasks=[task]),
                     TaskList(id="L2", title="Home", tasks=[])])
    worker.on_failed(OSError("down"), jobs.last.on_error)
    assert [t.id for t in store.lists[0].tasks] == ["t1"]


def test_delete_puts_the_task_back_at_its_old_place():
    store, worker, jobs = parts()
    task = store.find_task("L1", "t1")
    index = store.remove_task(task)
    worker.delete(task, index)
    worker.on_failed(FakeHttpError("boom"), jobs.last.on_error)
    assert [t.id for t in store.lists[0].tasks] == ["t1", "t2"]


def test_a_failed_delete_after_a_load_does_not_add_a_second_copy():
    store, worker, jobs = parts()
    task = store.find_task("L1", "t1")
    index = store.remove_task(task)
    worker.delete(task, index)
    store.set_lists([TaskList(id="L1", title="Work", tasks=[task]),
                     TaskList(id="L2", title="Home", tasks=[])])
    worker.on_failed(OSError("down"), jobs.last.on_error)
    assert [t.id for t in store.lists[0].tasks] == ["t1"]


# -- load ------------------------------------------------------------------

def test_a_second_load_while_one_runs_is_skipped(mod):
    store, worker, jobs = parts()
    assert worker.reload() is True
    assert worker.reload() is False
    assert len(jobs.jobs) == 1
    jobs.last.on_done([])
    assert worker.reload() is True
    assert len(jobs.jobs) == 2


def test_a_failed_load_lets_the_next_one_through(mod):
    store, worker, jobs = parts()
    worker.reload()
    worker.on_failed(OSError("down"), jobs.last.on_error)
    assert worker.reload() is True


def test_a_load_remembers_whether_it_asked_for_completed_tasks(mod):
    store, worker, jobs = parts()
    worker.reload()
    jobs.last.on_done([])
    assert store.has_completed is False
    store.set_show_completed(True)
    worker.reload()
    jobs.last.on_done([])
    assert store.has_completed is True


def test_a_cache_that_cannot_be_written_is_still_a_good_load(mod, monkeypatch, capsys):
    from gtasks_panel import api, state

    store, worker, jobs = parts()
    monkeypatch.setattr(api, "fetch_lists", lambda service, show_completed=False: [])
    monkeypatch.setattr(state, "save_cache", _raise_oserror)
    worker.reload()
    assert jobs.last.fn(None) == []          # the job did not raise
    assert "Cannot save the task cache" in capsys.readouterr().err


def _raise_oserror(_lists):
    raise OSError("Read-only file system")


# -- the panel item --------------------------------------------------------

def test_a_panel_write_that_lost_the_lock_is_tried_again(mod, monkeypatch):
    store, worker, jobs = parts()
    waits = []
    monkeypatch.setattr("gtasks_panel.ui.worker.GLib.timeout_add_seconds",
                        lambda seconds, fn: waits.append((seconds, fn)) or 1)
    worker._notify_panel()
    assert jobs.last.quiet is True and jobs.last.uses_service is False
    jobs.last.on_done(False)                 # the lock was held
    assert waits and waits[0][0] == 5
    waits[0][1]()                            # the retry runs
    jobs.last.on_done(False)                 # it fails again
    assert len(waits) == 1                   # but it does not go on for ever
