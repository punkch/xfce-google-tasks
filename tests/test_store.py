"""The shared data of the two windows. GLib only, so no display is needed."""

import datetime as dt

import pytest
from conftest import pump

pytest.importorskip("gi")

from gtasks_panel.model import Task, TaskList  # noqa: E402
from gtasks_panel.paths import AUTH_OK, AUTH_REAUTH  # noqa: E402
from gtasks_panel.ui.store import ALL_LISTS, TaskStore  # noqa: E402

TODAY = dt.date(2026, 9, 10)


def two_lists():
    return [
        TaskList(id="L1", title="Work", tasks=[
            Task(id="t1", list_id="L1", title="Report", position="00001"),
            Task(id="t2", list_id="L1", title="Bank", position="00002"),
            Task(id="t3", list_id="L1", title="Old", status="completed",
                 position="00003"),
        ]),
        TaskList(id="L2", title="Home", tasks=[
            Task(id="h1", list_id="L2", title="Milk", position="00001"),
        ]),
    ]


def filled():
    store = TaskStore()
    store.set_lists(two_lists())
    return store


# -- change notice ---------------------------------------------------------

def test_many_changes_give_one_redraw():
    store = filled()
    seen = []
    store.subscribe(lambda _store: seen.append(1))
    store.set_status("Loading…")
    store.set_selected("L1")
    store.notify()
    assert seen == []  # nothing before the main loop runs
    pump()
    assert seen == [1]


def test_update_says_when_nothing_changed():
    store = filled()
    assert store.update(offline=True, error="down") is True
    assert store.update(offline=True, error="down") is False
    assert store.update(auth=AUTH_REAUTH) is True
    assert store.needs_signin is True
    assert store.update(auth=AUTH_OK) is True
    assert store.needs_signin is False


# -- whole-model changes ---------------------------------------------------

def test_set_lists_forgets_a_list_that_is_gone():
    store = filled()
    store.set_selected("L2")
    store.set_lists([TaskList(id="L1", title="Work", tasks=[])])
    assert store.selected_list_id is ALL_LISTS
    store.set_lists(two_lists())
    store.set_selected("L2")
    store.set_lists(two_lists())
    assert store.selected_list_id == "L2"  # still there, so it stays


def test_snapshot_copies_the_task_lists():
    """The worker thread reads the copy while the user keeps clicking."""
    store = filled()
    copy = store.snapshot()
    store.remove_task(store.lists[0].tasks[0])
    assert [t.id for t in copy[0].tasks] == ["t1", "t2", "t3"]
    assert len(store.lists[0].tasks) == 2


# -- reading ---------------------------------------------------------------

def test_add_target_takes_the_chosen_list_first():
    store = filled()
    store.set_selected("L1")
    assert store.add_target("Home") == "L1"
    store.set_selected(ALL_LISTS)
    assert store.add_target("Home") == "L2"     # then the configured title
    assert store.add_target("Gone") == "L1"     # then the first list
    assert TaskStore().add_target("Home") is None


def test_visible_tasks_follows_show_completed_and_open_only():
    store = filled()
    assert [t.id for t in store.visible_tasks("L1", today=TODAY)] == ["t1", "t2"]
    store.set_show_completed(True)
    assert [t.id for t in store.visible_tasks("L1", today=TODAY)] == ["t1", "t2", "t3"]
    assert [t.id for t in store.visible_tasks("L1", open_only=True, today=TODAY)] \
        == ["t1", "t2"]
    assert len(store.visible_tasks(ALL_LISTS, open_only=True, today=TODAY)) == 3
    assert store.visible_tasks("gone", today=TODAY) == []


def test_open_count_and_list_title():
    store = filled()
    assert store.open_count("L1") == 2
    assert store.open_count("gone") == 0
    assert store.list_title("L2") == "Home"
    assert store.list_title(ALL_LISTS) == "All lists"


# -- single task changes ---------------------------------------------------

def test_remove_task_gives_back_the_index_it_had():
    store = filled()
    task = store.lists[0].tasks[1]
    assert store.remove_task(task) == 1
    assert store.remove_task(task) == -1          # gone: no second removal
    assert store.remove_task(Task(id="x", list_id="gone")) == -1
    store.add_task(task, 1)
    assert [t.id for t in store.lists[0].tasks] == ["t1", "t2", "t3"]
    store.add_task(Task(id="y", list_id="gone"))  # an unknown list is no crash
    assert store.find_task("L1", "t2") is task


def test_replace_task_keeps_the_place_and_the_depth():
    store = filled()
    store.lists[0].tasks[1].depth = 1
    fresh = Task(id="t2", list_id="L1", title="Bank, called", position="00002")
    store.replace_task(fresh)
    assert store.lists[0].tasks[1] is fresh
    assert fresh.depth == 1
    store.replace_task(Task(id="new", list_id="L1"))
    assert store.lists[0].tasks[-1].id == "new"


# -- a load that arrives in the middle of a change (A1) --------------------

def test_a_load_during_a_move_does_not_leave_two_copies():
    """The move takes the task out, then a load puts the old lists back."""
    store = filled()
    task = store.lists[0].tasks[0]
    store.remove_task(task)
    store.set_lists(two_lists())                  # the answer of a load
    assert store.find_task("L1", "t1") is not None

    # What the worker does when the move comes back: take it out again,
    # then add the task Google gave us.
    store.remove_task(task)
    moved = Task(id="t1", list_id="L2", title="Report")
    store.add_task(moved, 0)
    assert [t.id for t in store.lists[0].tasks] == ["t2", "t3"]
    assert [t.id for t in store.lists[1].tasks] == ["t1", "h1"]


def test_a_load_during_a_delete_does_not_resurrect_the_task_twice():
    store = filled()
    task = store.lists[0].tasks[0]
    index = store.remove_task(task)
    store.set_lists(two_lists())                  # the answer of a load
    # Undo now: the task is back already, so a second copy must not appear.
    if store.find_task(task.list_id, task.id) is None:
        store.add_task(task, max(index, 0))
    assert [t.id for t in store.lists[0].tasks] == ["t1", "t2", "t3"]
