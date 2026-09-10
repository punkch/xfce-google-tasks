"""What the two windows show. No Gtk, so a test needs no display.

One object holds the task lists, the view options and the connection
state. Both windows register a callback and redraw when it runs. GLib
gives the change notice, and GLib runs without a display.
"""

import datetime as dt

from gi.repository import GLib

from ..model import Task, TaskList, open_tasks, ordered
from ..paths import AUTH_OK

ALL_LISTS = None  # value of `selected_list_id` for "All lists"
ALL_LISTS_TITLE = "All lists"


class TaskStore:
    """Shared data of the popup and the main window."""

    def __init__(self, show_completed: bool = False):
        self.lists: list[TaskList] = []
        self.show_completed = show_completed
        self.has_completed = False   # the lists hold the completed tasks too
        self.offline = False
        self.error = ""
        self.status = ""
        self.auth = AUTH_OK
        self.selected_list_id = ALL_LISTS
        self._listeners: list = []
        self._pending = False

    # -- change notice ----------------------------------------------------

    def subscribe(self, callback) -> None:
        """Call `callback(store)` after every change."""
        self._listeners.append(callback)

    def notify(self) -> None:
        """Ask for one redraw. Many changes together give one redraw.

        One user action changes the store several times, and every window
        rebuilds all of its rows on a change. So the calls are collected
        and run one time, before the next frame.
        """
        if self._pending:
            return
        self._pending = True
        GLib.idle_add(self._deliver, priority=GLib.PRIORITY_DEFAULT)

    def _deliver(self) -> bool:
        self._pending = False
        for callback in list(self._listeners):
            callback(self)
        return False

    # -- whole-model changes ----------------------------------------------

    def update(self, **fields) -> bool:
        """Set fields and redraw one time. False when nothing changed."""
        changed = [key for key, value in fields.items() if getattr(self, key) != value]
        if not changed:
            return False
        for key in changed:
            setattr(self, key, fields[key])
        self.notify()
        return True

    def set_lists(self, lists: list[TaskList]) -> None:
        self.lists = list(lists)
        if self.selected_list_id is not ALL_LISTS and not self.find_list(self.selected_list_id):
            self.selected_list_id = ALL_LISTS
        self.notify()

    def snapshot(self) -> list[TaskList]:
        """A copy the worker thread can read while the user keeps clicking."""
        return [TaskList(id=item.id, title=item.title, tasks=list(item.tasks))
                for item in self.lists]

    def set_offline(self, offline: bool, error: str = "") -> bool:
        return self.update(offline=offline, error=error)

    def set_status(self, status: str) -> bool:
        return self.update(status=status)

    def set_auth(self, verdict: str) -> bool:
        return self.update(auth=verdict)

    def set_show_completed(self, show: bool) -> bool:
        return self.update(show_completed=show)

    def set_selected(self, list_id: str | None) -> bool:
        return self.update(selected_list_id=list_id)

    @property
    def needs_signin(self) -> bool:
        return self.auth != AUTH_OK

    # -- reading ----------------------------------------------------------

    def find_list(self, list_id: str | None) -> TaskList | None:
        return next((item for item in self.lists if item.id == list_id), None)

    def list_title(self, list_id: str | None) -> str:
        found = self.find_list(list_id)
        return found.title if found else ALL_LISTS_TITLE

    def open_count(self, list_id: str) -> int:
        found = self.find_list(list_id)
        return len(open_tasks(found.tasks)) if found else 0

    def visible_tasks(self, list_id: str | None = ALL_LISTS, *,
                      open_only: bool = False,
                      today: dt.date | None = None) -> list[Task]:
        """Tasks in display order for one list, or for every list."""
        today = today or dt.date.today()
        chosen = self.lists if list_id is ALL_LISTS else [self.find_list(list_id)]
        result: list[Task] = []
        for task_list in chosen:
            if task_list is None:
                continue
            # Order first: a sub-task of a completed task keeps its indent.
            tasks = ordered(task_list.tasks, today)
            if open_only or not self.show_completed:
                tasks = open_tasks(tasks)
            result += tasks
        return result

    def add_target(self, default_title: str = "") -> str | None:
        """Id of the list a new task goes to: chosen, config, then first."""
        if self.selected_list_id is not ALL_LISTS and self.find_list(self.selected_list_id):
            return self.selected_list_id
        by_title = next((item for item in self.lists if item.title == default_title), None)
        if by_title:
            return by_title.id
        return self.lists[0].id if self.lists else None

    # -- single task changes ----------------------------------------------

    def add_task(self, task: Task, index: int | None = None) -> None:
        target = self.find_list(task.list_id)
        if target is None:
            return
        target.tasks.insert(len(target.tasks) if index is None else index, task)
        self.notify()

    def remove_task(self, task: Task) -> int:
        """Take the task out. Returns the index it had, or -1."""
        source = self.find_list(task.list_id)
        if source is None:
            return -1
        found = next((i for i, item in enumerate(source.tasks) if item.id == task.id), -1)
        if found >= 0:
            source.tasks.pop(found)
            self.notify()
        return found

    def replace_task(self, task: Task) -> None:
        """Copy fresh field values from Google onto the task we show."""
        target = self.find_list(task.list_id)
        if target is None:
            return
        for index, item in enumerate(target.tasks):
            if item.id == task.id:
                task.depth = item.depth
                target.tasks[index] = task
                break
        else:
            target.tasks.append(task)
        self.notify()

    def find_task(self, list_id: str, task_id: str) -> Task | None:
        found = self.find_list(list_id)
        if found is None:
            return None
        return next((task for task in found.tasks if task.id == task_id), None)
