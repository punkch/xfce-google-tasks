"""Pure model: order, tree depth, overdue, summary, cache JSON."""

import datetime as dt
import json

from gtasks_panel import model

TODAY = dt.date(2026, 9, 10)


def task(task_id, **kwargs):
    return model.Task(id=task_id, list_id=kwargs.pop("list_id", "L"), **kwargs)


def test_task_from_api_reads_every_field():
    item = {"id": "1", "title": "Pay bill", "notes": "n", "due": "2026-09-11T00:00:00.000Z",
            "status": "needsAction", "parent": "0", "position": "007", "updated": "u"}
    result = model.task_from_api(item, "L")
    assert result.due == dt.date(2026, 9, 11)
    assert (result.list_id, result.parent, result.position) == ("L", "0", "007")
    assert result.completed is False
    assert model.task_from_api({"id": "2", "status": "completed"}, "L").completed is True
    assert model.task_from_api({"id": "3", "due": "rubbish"}, "L").due is None


def test_overdue_only_for_open_tasks_with_a_past_date():
    assert model.is_overdue(task("a", due=TODAY - dt.timedelta(days=1)), TODAY)
    assert not model.is_overdue(task("b", due=TODAY), TODAY)
    assert not model.is_overdue(task("c"), TODAY)
    done = task("d", due=TODAY - dt.timedelta(days=1), status="completed")
    assert not model.is_overdue(done, TODAY)


def test_order_is_overdue_then_due_then_position():
    late = task("late", due=TODAY - dt.timedelta(days=2), position="09")
    soon = task("soon", due=TODAY + dt.timedelta(days=1), position="08")
    none_a = task("none_a", position="01")
    none_b = task("none_b", position="00")
    result = model.ordered([none_a, soon, none_b, late], TODAY)
    assert [t.id for t in result] == ["late", "soon", "none_b", "none_a"]


def test_children_follow_their_parent_with_depth():
    root = task("r", position="00")
    child_b = task("cb", parent="r", position="02")
    child_a = task("ca", parent="r", position="01")
    grandchild = task("g", parent="ca", position="00")
    other = task("o", position="01")
    result = model.ordered([grandchild, other, child_b, root, child_a], TODAY)
    assert [t.id for t in result] == ["r", "ca", "g", "cb", "o"]
    assert [t.depth for t in result] == [0, 1, 2, 1, 0]


def test_orphan_is_a_root_and_a_loop_keeps_every_task():
    orphan = task("x", parent="gone", position="00")
    assert [t.id for t in model.ordered([orphan], TODAY)] == ["x"]
    loop_a = task("a", parent="b")
    loop_b = task("b", parent="a")
    assert len(model.ordered([loop_a, loop_b], TODAY)) == 2


def test_summary_counts_open_tasks_only():
    lists = [
        model.TaskList("1", "Work", [
            task("a", due=TODAY - dt.timedelta(days=1)),
            task("b", status="completed"),
            task("c"),
        ]),
        model.TaskList("2", "Home", []),
    ]
    assert model.summary(lists, TODAY) == {
        "count": 2, "overdue": 1, "lists": [["Work", 2], ["Home", 0]]}


def test_cache_json_round_trip():
    lists = [model.TaskList("1", "Work", [
        task("a", title="Pay", due=TODAY, notes="soon", parent="", position="00"),
        task("b", title="Done", status="completed"),
    ])]
    data = json.loads(json.dumps(model.lists_to_json(lists)))
    back = model.lists_from_json(data)
    assert [(l.id, l.title) for l in back] == [("1", "Work")]
    assert back[0].tasks[0].due == TODAY
    assert back[0].tasks[0].title == "Pay"
    assert back[0].tasks[1].completed is True
    assert model.summary(back, TODAY) == model.summary(lists, TODAY)


def test_lists_from_json_survives_rubbish():
    assert model.lists_from_json({"lists": "no"}) == []
    assert model.lists_from_json({}) == []
    assert model.lists_from_json({"lists": [{"id": "1", "tasks": "no"}]})[0].tasks == []


def test_json_has_no_completed_key_and_reads_the_status():
    data = model.task_to_json(task("a", status="completed"))
    assert "completed" not in data
    assert model.task_from_json(data, "L").completed is True
    # An old cache with the key still reads: the status decides.
    assert model.task_from_json({"id": "a", "completed": True}, "L").completed is False
    assert model.task_from_json({"id": "a", "list_id": "X"}, "L").list_id == "X"


def test_open_tasks_leaves_out_the_done_ones():
    tasks = [task("a"), task("b", status="completed"), task("c")]
    assert [t.id for t in model.open_tasks(tasks)] == ["a", "c"]


def test_due_text_names_the_days_around_today():
    assert model.due_text(None, TODAY) == ""
    assert model.due_text(TODAY, TODAY) == "Today"
    assert model.due_text(TODAY + dt.timedelta(days=1), TODAY) == "Tomorrow"
    assert model.due_text(TODAY - dt.timedelta(days=1), TODAY) == "Yesterday"


def test_due_text_drops_the_year_only_inside_this_year():
    assert model.due_text(dt.date(2026, 9, 25), TODAY) == "25 Sep"
    assert model.due_text(dt.date(2027, 1, 3), TODAY) == "2027-01-03"
    assert model.due_text(dt.date(2025, 12, 31), TODAY) == "2025-12-31"
