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
