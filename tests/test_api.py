"""API calls against a fake service that records every request."""

import datetime as dt

import pytest
from conftest import FakeService

from gtasks_panel import api

DUE = dt.date(2026, 9, 11)
DUE_API = "2026-09-11T00:00:00.000Z"


def body_of(collection, name):
    return next(kwargs["body"] for call, kwargs in collection.calls if call == name)


def test_list_tasks_flags_and_fields():
    service = FakeService(tasks={"a": [{"items": []}]})
    api.list_tasks(service, "a")
    api.list_tasks(service, "a", show_completed=True)
    first, second = (kwargs for call, kwargs in service._tasks.calls if call == "list")
    assert (first["showCompleted"], first["showHidden"]) == (False, False)
    assert (second["showCompleted"], second["showHidden"]) == (True, True)
    assert first["fields"] == f"items({api.TASK_FIELDS}),nextPageToken"
    assert "parent" in api.TASK_FIELDS and "notes" in api.TASK_FIELDS


def test_fetch_lists_pages_and_builds_tasks():
    service = FakeService(
        lists=[{"items": [{"id": "a", "title": "Work"}], "nextPageToken": "p2"},
               {"items": [{"id": "b", "title": "Home"}]}],
        tasks={"a": [{"items": [{"id": "1", "title": "Root", "position": "00"}],
                      "nextPageToken": "x"},
                     {"items": [{"id": "2", "title": "Sub", "parent": "1", "due": DUE_API}]}],
               "b": [{"items": []}]},
    )
    lists = api.fetch_lists(service)
    assert [(tl.id, tl.title, len(tl.tasks)) for tl in lists] == [
        ("a", "Work", 2), ("b", "Home", 0)]
    assert lists[0].tasks[1].parent == "1"
    assert lists[0].tasks[1].due == DUE
    assert lists[0].tasks[1].list_id == "a"


def test_fetch_summary_counts_open_tasks():
    service = FakeService(
        lists=[{"items": [{"id": "a", "title": "Work"}]}],
        tasks={"a": [{"items": [{"id": "1"}, {"id": "2", "status": "completed"}]}]},
    )
    assert api.fetch_summary(None, service=service) == {
        "count": 1, "overdue": 0, "lists": [["Work", 1]]}


def test_insert_sends_only_the_fields_given():
    service = FakeService()
    task = api.insert_task(service, "a", "Buy milk")
    assert body_of(service._tasks, "insert") == {"title": "Buy milk"}
    assert (task.title, task.list_id) == ("Buy milk", "a")

    api.insert_task(service, "a", "Pay bill", notes="today", due=DUE)
    assert service._tasks.calls[-1] == ("insert", {
        "tasklist": "a", "body": {"title": "Pay bill", "notes": "today", "due": DUE_API}})


def test_patch_writes_dates_and_clears_them():
    service = FakeService()
    task = api.patch_task(service, "a", "t1", title="New", due=DUE)
    assert service._tasks.calls[-1] == ("patch", {
        "tasklist": "a", "task": "t1", "body": {"title": "New", "due": DUE_API}})
    assert task.id == "t1" and task.due == DUE
    api.patch_task(service, "a", "t1", due=None)
    assert body_of(service._tasks, "patch") == {"title": "New", "due": DUE_API}
    assert service._tasks.calls[-1][1]["body"] == {"due": None}


def test_patch_refuses_read_only_fields():
    service = FakeService()
    with pytest.raises(ValueError):
        api.patch_task(service, "a", "t1", parent="x")
    with pytest.raises(ValueError):
        api.patch_task(service, "a", "t1", position="00")
    assert service._tasks.calls == []


def test_complete_and_uncomplete_round_trip():
    service = FakeService()
    done = api.complete_task(service, "a", "t1")
    assert service._tasks.calls[-1][1]["body"] == {"status": "completed"}
    assert done.completed is True
    open_again = api.uncomplete_task(service, "a", "t1")
    assert service._tasks.calls[-1][1]["body"] == {"status": "needsAction", "completed": None}
    assert open_again.completed is False


def test_move_only_names_another_list():
    service = FakeService()
    api.move_task(service, "a", "t1")
    assert service._tasks.calls[-1] == ("move", {"tasklist": "a", "task": "t1"})
    api.move_task(service, "a", "t1", destination_list_id="a")
    assert "destinationTasklist" not in service._tasks.calls[-1][1]
    task = api.move_task(service, "a", "t1", destination_list_id="b")
    assert service._tasks.calls[-1][1]["destinationTasklist"] == "b"
    assert task.list_id == "b"


def test_delete_calls_the_api_and_returns_nothing():
    service = FakeService()
    assert api.delete_task(service, "a", "t1") is None
    assert service._tasks.calls[-1] == ("delete", {"tasklist": "a", "task": "t1"})


def test_due_to_api():
    assert api.due_to_api(DUE) == DUE_API
    assert api.due_to_api(None) is None


# -- task lists ------------------------------------------------------------

def test_insert_tasklist_sends_the_title_only():
    service = FakeService()
    made = api.insert_tasklist(service, "Holiday")
    assert service._lists.calls[-1] == ("insert", {"body": {"title": "Holiday"}})
    assert (made.title, made.tasks) == ("Holiday", [])
    assert made.id == "new-id"


def test_rename_tasklist_patches_the_title_and_keeps_the_id():
    service = FakeService()
    renamed = api.rename_tasklist(service, "L1", "Work again")
    assert service._lists.calls[-1] == ("patch", {
        "tasklist": "L1", "body": {"title": "Work again"}})
    assert (renamed.id, renamed.title) == ("L1", "Work again")


def test_delete_tasklist_calls_the_api_and_returns_nothing():
    service = FakeService()
    assert api.delete_tasklist(service, "L1") is None
    assert service._lists.calls[-1] == ("delete", {"tasklist": "L1"})


# -- clear completed -------------------------------------------------------

def done_and_open_tasks():
    return FakeService(tasks={"L1": [{"items": [
        {"id": "t1", "title": "Open"},
        {"id": "t2", "title": "Old", "status": "completed"},
        {"id": "t3", "title": "Older", "status": "completed"},
    ]}]})


def test_clear_completed_asks_for_the_done_tasks_and_deletes_them():
    service = done_and_open_tasks()
    steps = []
    ids = api.clear_completed(service, "L1",
                              lambda index, total: steps.append((index, total)))
    assert ids == ["t2", "t3"]
    assert steps == [(1, 2), (2, 2)]
    asked = next(kwargs for call, kwargs in service._tasks.calls if call == "list")
    assert asked["showCompleted"] is True and asked["showHidden"] is True
    assert [kwargs["task"] for call, kwargs in service._tasks.calls if call == "delete"] \
        == ["t2", "t3"]


def test_clear_completed_works_without_a_progress_callback():
    service = done_and_open_tasks()
    assert api.clear_completed(service, "L1") == ["t2", "t3"]


def test_clear_completed_stops_at_the_first_error(monkeypatch):
    service = done_and_open_tasks()
    steps = []
    monkeypatch.setattr(api, "delete_task", _fails_on_call(2))
    with pytest.raises(RuntimeError):
        api.clear_completed(service, "L1", lambda index, total: steps.append(index))
    assert steps == [1]     # nothing partial comes back, only the first tick ran


# -- mark all done ---------------------------------------------------------

def open_and_done_tasks():
    from gtasks_panel.model import Task

    return [Task(id="t1", list_id="L1", title="Open"),
            Task(id="t2", list_id="L1", title="Done", status="completed"),
            Task(id="t3", list_id="L1", title="Also open")]


def test_complete_all_patches_the_open_tasks_only():
    service = FakeService()
    steps = []
    written = api.complete_all(service, "L1", open_and_done_tasks(),
                               lambda index, total: steps.append((index, total)))
    assert [task.id for task in written] == ["t1", "t3"]
    assert all(task.completed for task in written)
    assert steps == [(1, 2), (2, 2)]
    assert [kwargs["task"] for call, kwargs in service._tasks.calls if call == "patch"] \
        == ["t1", "t3"]
    assert body_of(service._tasks, "patch") == {"status": "completed"}


def test_complete_all_with_nothing_open_asks_google_nothing():
    from gtasks_panel.model import Task

    service = FakeService()
    assert api.complete_all(service, "L1", [Task(id="t2", list_id="L1",
                                                 status="completed")]) == []
    assert service._tasks.calls == []


def test_complete_all_stops_at_the_first_error(monkeypatch):
    service = FakeService()
    steps = []
    monkeypatch.setattr(api, "complete_task", _fails_on_call(2))
    with pytest.raises(RuntimeError):
        api.complete_all(service, "L1", open_and_done_tasks(),
                         lambda index, total: steps.append(index))
    assert steps == [1]


def _fails_on_call(number):
    """A stand-in that raises on call `number`. It counts its own calls."""
    calls = []

    def call(*args, **kwargs):
        calls.append(1)
        if len(calls) >= number:
            raise RuntimeError("Google said no")
        return None

    return call
