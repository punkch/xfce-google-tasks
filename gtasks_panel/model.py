"""Tasks and task lists as plain Python. No Google imports.

The UI, the cache and the panel count all use these types. Google gives a
due date as UTC midnight; only the date part has a meaning.
"""

import datetime as dt
from dataclasses import dataclass, field

CACHE_VERSION = 1

# The two values the Tasks API gives to `status`.
STATUS_OPEN = "needsAction"
STATUS_DONE = "completed"


@dataclass
class Task:
    id: str
    list_id: str
    title: str = ""
    notes: str = ""
    due: dt.date | None = None
    status: str = STATUS_OPEN
    parent: str = ""
    position: str = ""
    updated: str = ""
    depth: int = 0

    @property
    def completed(self) -> bool:
        """True when Google marks the task done. Set `status` to change it."""
        return self.status == STATUS_DONE


@dataclass
class TaskList:
    id: str
    title: str = ""
    tasks: list[Task] = field(default_factory=list)


def parse_due(text: str | None) -> dt.date | None:
    """Date from an API `due` value, or None when it is absent or bad."""
    try:
        return dt.date.fromisoformat((text or "")[:10])
    except ValueError:
        return None


def task_from_api(item: dict, list_id: str) -> Task:
    """Make a Task from one `tasks.get`/`tasks.list` item."""
    return Task(
        id=item.get("id") or "",
        list_id=list_id,
        title=item.get("title") or "",
        notes=item.get("notes") or "",
        due=parse_due(item.get("due")),
        status=item.get("status") or STATUS_OPEN,
        parent=item.get("parent") or "",
        position=item.get("position") or "",
        updated=item.get("updated") or "",
    )


def tasklist_from_api(item: dict, tasks: list[Task]) -> TaskList:
    """Make a TaskList from one `tasklists.list` item and its tasks."""
    return TaskList(id=item.get("id") or "", title=item.get("title") or "?", tasks=tasks)


def open_tasks(tasks: list[Task]) -> list[Task]:
    """The tasks that are not done yet."""
    return [task for task in tasks if not task.completed]


def is_overdue(task: Task, today: dt.date | None = None) -> bool:
    """True when an open task has a due date before today."""
    if task.completed or task.due is None:
        return False
    return task.due < (today or dt.date.today())


def due_text(due: dt.date | None, today: dt.date | None = None) -> str:
    """Short text for a due date. Empty when there is none."""
    if due is None:
        return ""
    today = today or dt.date.today()
    if due == today:
        return "Today"
    if due == today + dt.timedelta(days=1):
        return "Tomorrow"
    if due == today - dt.timedelta(days=1):
        return "Yesterday"
    if due.year == today.year:
        return due.strftime("%-d %b")
    return due.isoformat()


def _root_key(task: Task, today: dt.date) -> tuple:
    return (0 if is_overdue(task, today) else 1, task.due or dt.date.max, task.position)


def ordered(tasks: list[Task], today: dt.date | None = None) -> list[Task]:
    """Sort into display order and set `depth`.

    Top-level tasks come first by overdue, then due date (no date last),
    then API position. Every sub-task follows its parent in position order.
    The returned Task objects are the ones given in.
    """
    today = today or dt.date.today()
    known = {task.id for task in tasks if task.id}
    children: dict[str, list[Task]] = {}
    roots: list[Task] = []
    for task in tasks:
        if task.parent and task.parent in known:
            children.setdefault(task.parent, []).append(task)
        else:
            roots.append(task)
    for group in children.values():
        group.sort(key=lambda task: task.position)
    roots.sort(key=lambda task: _root_key(task, today))

    result: list[Task] = []
    seen: set[int] = set()
    stack = [(task, 0) for task in reversed(roots)]
    while stack:
        task, depth = stack.pop()
        if id(task) in seen:  # a parent loop must not run forever
            continue
        seen.add(id(task))
        task.depth = depth
        result.append(task)
        stack += [(child, depth + 1) for child in reversed(children.get(task.id, []))]

    # A parent loop leaves tasks unvisited. Show them, do not lose them.
    missed = [task for task in tasks if id(task) not in seen]
    for task in missed:
        task.depth = 0
    return result + missed


def summary(lists: list[TaskList], today: dt.date | None = None) -> dict:
    """Counts for the panel: open tasks in total, overdue, and per list."""
    today = today or dt.date.today()
    per_list = []
    total = 0
    overdue = 0
    for task_list in lists:
        still_open = open_tasks(task_list.tasks)
        overdue += sum(1 for task in still_open if is_overdue(task, today))
        total += len(still_open)
        per_list.append([task_list.title, len(still_open)])
    return {"count": total, "overdue": overdue, "lists": per_list}


def task_to_json(task: Task) -> dict:
    """One task as JSON types. `depth` is left out: it is computed."""
    return {
        "id": task.id,
        "list_id": task.list_id,
        "title": task.title,
        "notes": task.notes,
        "due": task.due.isoformat() if task.due else None,
        "status": task.status,
        "parent": task.parent,
        "position": task.position,
        "updated": task.updated,
    }


def task_from_json(data: dict, list_id: str) -> Task:
    """Read back `task_to_json`. The keys are the API keys."""
    return task_from_api(data, data.get("list_id") or list_id)


def lists_to_json(lists: list[TaskList]) -> dict:
    """The whole task tree as a JSON-safe dict for the cache file."""
    return {
        "version": CACHE_VERSION,
        "lists": [{"id": task_list.id, "title": task_list.title,
                   "tasks": [task_to_json(task) for task in task_list.tasks]}
                  for task_list in lists],
    }


def lists_from_json(data: dict | list) -> list[TaskList]:
    """Read back `lists_to_json`. Unknown shapes give an empty list."""
    items = data.get("lists") if isinstance(data, dict) else data
    if not isinstance(items, list):
        return []
    lists = []
    for item in items:
        if not isinstance(item, dict):
            continue
        list_id = item.get("id") or ""
        raw = item.get("tasks")
        tasks = [task_from_json(task, list_id) for task in raw
                 if isinstance(task, dict)] if isinstance(raw, list) else []
        lists.append(TaskList(id=list_id, title=item.get("title") or "?", tasks=tasks))
    return lists
