"""The worker without its thread.

Every job is a function plus two callbacks. The tests take the job the
worker posts and run the callbacks by hand, so nothing reaches Google and
nothing needs a display.
"""

import pytest

pytest.importorskip("gi")

from gtasks_panel.model import Task, TaskList  # noqa: E402
from gtasks_panel.paths import AUTH_NO_TOKEN  # noqa: E402
from gtasks_panel.ui.store import ALL_LISTS, TaskStore  # noqa: E402
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


# -- a due date on a new task ----------------------------------------------

def test_add_sends_the_due_date_when_there_is_one():
    import datetime as dt

    from conftest import FakeService

    store, worker, jobs = parts()
    worker.add("L1", "No date")
    service = FakeService()
    jobs.last.fn(service)
    assert service._tasks.calls[-1][1]["body"] == {"title": "No date"}

    worker.add("L1", "Pay bill", due=dt.date(2026, 9, 11))
    jobs.last.fn(service)
    assert service._tasks.calls[-1][1]["body"] == {
        "title": "Pay bill", "due": "2026-09-11T00:00:00.000Z"}


# -- task list jobs --------------------------------------------------------

def test_add_list_adds_it_and_chooses_it():
    store, worker, jobs = parts()
    worker.add_list("Holiday")
    assert store.find_list("L3") is None          # nothing before Google answers
    jobs.last.on_done(TaskList(id="L3", title="Holiday", tasks=[]))
    assert [item.id for item in store.lists] == ["L1", "L2", "L3"]
    assert store.selected_list_id == "L3"


def test_rename_list_shows_the_new_title_at_once():
    store, worker, jobs = parts()
    worker.rename_list(store.lists[0], "Office")
    assert store.lists[0].title == "Office"
    jobs.last.on_done(TaskList(id="L1", title="Office", tasks=[]))
    assert store.lists[0].title == "Office"
    assert [t.id for t in store.lists[0].tasks] == ["t1", "t2"]   # tasks stay


def test_rename_list_puts_the_old_title_back_when_google_says_no():
    store, worker, jobs = parts()
    worker.rename_list(store.lists[0], "Office")
    worker.on_failed(FakeHttpError("boom"), jobs.last.on_error)
    assert store.lists[0].title == "Work"


def test_delete_list_waits_for_google():
    store, worker, jobs = parts()
    store.set_selected("L1")
    worker.delete_list(store.lists[0])
    assert store.find_list("L1") is not None      # the row stays for now
    jobs.last.on_done(None)
    assert [item.id for item in store.lists] == ["L2"]
    assert store.selected_list_id is ALL_LISTS    # All lists again
    assert len(jobs.jobs) == 2                    # the panel job followed


def test_a_failed_delete_list_leaves_the_list_where_it_is():
    store, worker, jobs = parts()
    worker.delete_list(store.lists[0])
    worker.on_failed(FakeHttpError("Cannot delete the default list"),
                     jobs.last.on_error)
    assert [item.id for item in store.lists] == ["L1", "L2"]
    assert store.error == "Cannot delete the default list"


def test_clear_completed_takes_the_deleted_tasks_out():
    store, worker, jobs = parts()
    worker.clear_completed(store.lists[0])
    jobs.last.on_done(["t1"])
    assert [t.id for t in store.lists[0].tasks] == ["t2"]
    assert len(jobs.jobs) == 2                    # the panel job followed


def test_clear_completed_reads_the_list_again_after_an_error(mod):
    store, worker, jobs = parts()
    worker.clear_completed(store.lists[0])
    worker.on_failed(OSError("down"), jobs.last.on_error)
    assert store.status == "Loading…"             # the reload started
    assert len(jobs.jobs) == 2


def test_complete_all_sends_the_open_tasks_of_the_store_only():
    """The whole way through: the job runs against a fake service."""
    from conftest import FakeService

    store, worker, jobs = parts()
    store.lists[0].tasks.append(Task(id="t9", list_id="L1", title="Old",
                                     status="completed"))
    worker.complete_all(store.lists[0])
    service = FakeService()
    written = jobs.last.fn(service)
    assert [kwargs["task"] for call, kwargs in service._tasks.calls if call == "patch"] \
        == ["t1", "t2"]                           # the done one is left alone
    assert service._tasks.calls[-1][1]["body"] == {"status": "completed"}
    assert [task.id for task in written] == ["t1", "t2"]


def test_clear_completed_deletes_the_done_tasks_google_names():
    """The whole way through: the job asks Google, then deletes."""
    from conftest import FakeService

    store, worker, jobs = parts()
    service = FakeService(tasks={"L1": [{"items": [
        {"id": "t1", "title": "Report"},
        {"id": "t2", "title": "Bank", "status": "completed"},
    ]}]})
    worker.clear_completed(store.lists[0])
    assert jobs.last.fn(service) == ["t2"]
    assert [kwargs["task"] for call, kwargs in service._tasks.calls if call == "delete"] \
        == ["t2"]


def test_complete_all_marks_the_open_tasks_the_worker_saw():
    store, worker, jobs = parts()
    worker.complete_all(store.lists[0])
    fresh = [Task(id="t1", list_id="L1", title="Report", status="completed"),
             Task(id="t2", list_id="L1", title="Bank", status="completed")]
    jobs.last.on_done(fresh)
    assert [t.completed for t in store.lists[0].tasks] == [True, True]
    assert len(jobs.jobs) == 2


def test_complete_all_reads_the_list_again_after_an_error(mod):
    store, worker, jobs = parts()
    worker.complete_all(store.lists[0])
    worker.on_failed(FakeHttpError("boom"), jobs.last.on_error)
    assert store.status == "Loading…"
    assert len(jobs.jobs) == 2


def test_a_long_job_counts_its_work_out_in_the_status_line(monkeypatch):
    """The progress callback must not stay in the GLib idle queue.

    GLib runs an idle callback again while it answers True, and
    `set_status` answers True when the text changed. So the text would
    come back after the job cleared it.
    """
    from gtasks_panel import api

    store, worker, jobs = parts()
    idles = []
    kept = []
    # The store uses the same GLib, so take its keyword argument too.
    monkeypatch.setattr("gtasks_panel.ui.worker.GLib.idle_add",
                        lambda fn, *args, **kwargs: idles.append((fn, args)) or 1)
    monkeypatch.setattr(api, "clear_completed",
                        lambda service, list_id, progress=None: kept.append(progress))
    monkeypatch.setattr(api, "complete_all",
                        lambda service, list_id, tasks, progress=None: kept.append(progress))

    worker.clear_completed(store.lists[0])
    jobs.last.fn(None)                            # the job keeps its progress callback
    kept[-1](2, 5)                                # the worker thread reports
    function, args = idles[-1]
    assert args == ("Deleting 2 of 5…",)
    assert function(*args) is False               # GLib drops it after one run
    assert store.status == "Deleting 2 of 5…"

    worker.complete_all(store.lists[0])
    jobs.last.fn(None)
    kept[-1](1, 2)
    function, args = idles[-1]
    assert args == ("Marking 1 of 2 done…",)
    assert function(*args) is False
    assert store.status == "Marking 1 of 2 done…"


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
