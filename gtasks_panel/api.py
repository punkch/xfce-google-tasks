"""Google Tasks API v1 calls.

Every function takes the service, so a test gives a fake one. Google
imports stay inside `build_service`: the panel tick never needs them.
"""

import datetime as dt
import time

from .model import (STATUS_DONE, STATUS_OPEN, Task, TaskList, summary,
                    task_from_api, tasklist_from_api)
from .paths import FETCH_DEADLINE, HTTP_TIMEOUT

PAGE_SIZE = 100
TASK_FIELDS = "id,title,notes,due,status,completed,parent,position,updated"
# parent and position are read-only. Use move_task for them.
PATCH_KEYS = ("title", "notes", "due", "status", "completed")


def build_service(creds):
    import httplib2
    from google_auth_httplib2 import AuthorizedHttp
    from googleapiclient.discovery import build

    http = AuthorizedHttp(creds, http=httplib2.Http(timeout=HTTP_TIMEOUT))
    return build("tasks", "v1", http=http, cache_discovery=False)


def iter_items(collection, request):
    """Yield items over all pages of a googleapiclient list request."""
    while request is not None:
        response = request.execute()
        yield from response.get("items", [])
        request = collection.list_next(request, response)


def due_to_api(due: dt.date | None) -> str | None:
    """A due date as the API wants it. None clears the field."""
    return f"{due.isoformat()}T00:00:00.000Z" if due else None


def list_tasklists(service) -> list[dict]:
    """All task lists as API items."""
    collection = service.tasklists()
    return list(iter_items(collection, collection.list(
        maxResults=PAGE_SIZE, fields="items(id,title),nextPageToken")))


def list_tasks(service, list_id: str, show_completed: bool = False) -> list[dict]:
    """All tasks of one list as API items.

    Google also hides completed tasks, so showHidden goes with
    showCompleted.
    """
    collection = service.tasks()
    return list(iter_items(collection, collection.list(
        tasklist=list_id, showCompleted=show_completed, showHidden=show_completed,
        maxResults=PAGE_SIZE, fields=f"items({TASK_FIELDS}),nextPageToken")))


def fetch_lists(service, show_completed: bool = False,
                deadline: float = FETCH_DEADLINE) -> list[TaskList]:
    """Every task list with its tasks. TimeoutError past the deadline."""
    started = time.monotonic()
    lists = []
    for item in list_tasklists(service):
        list_id = item.get("id") or ""
        tasks = [task_from_api(task, list_id)
                 for task in list_tasks(service, list_id, show_completed)]
        if time.monotonic() - started > deadline:
            raise TimeoutError(f"Fetch took longer than {deadline} s")
        lists.append(tasklist_from_api(item, tasks))
    return lists


def fetch_summary(creds, service=None, deadline: float = FETCH_DEADLINE) -> dict:
    """Counts for the panel state file: total, overdue and per list."""
    if service is None:
        service = build_service(creds)
    return summary(fetch_lists(service, deadline=deadline))


def insert_task(service, list_id: str, title: str, notes: str | None = None,
                due: dt.date | None = None) -> Task:
    """Add a task at the top of a list."""
    body = {"title": title}
    if notes:
        body["notes"] = notes
    if due:
        body["due"] = due_to_api(due)
    return task_from_api(service.tasks().insert(tasklist=list_id, body=body).execute(),
                         list_id)


def patch_task(service, list_id: str, task_id: str, **fields) -> Task:
    """Change title, notes, due, status or completed. None clears a field."""
    unknown = set(fields) - set(PATCH_KEYS)
    if unknown:
        raise ValueError(f"Cannot change: {', '.join(sorted(unknown))}")
    body = dict(fields)
    if "due" in body:
        body["due"] = due_to_api(body["due"])
    return task_from_api(
        service.tasks().patch(tasklist=list_id, task=task_id, body=body).execute(),
        list_id)


def complete_task(service, list_id: str, task_id: str) -> Task:
    """Mark a task done. Google sets the completion time."""
    return patch_task(service, list_id, task_id, status=STATUS_DONE)


def uncomplete_task(service, list_id: str, task_id: str) -> Task:
    """Open a task again. Only a null clears the completion time."""
    return patch_task(service, list_id, task_id, status=STATUS_OPEN, completed=None)


def move_task(service, list_id: str, task_id: str,
              destination_list_id: str | None = None) -> Task:
    """Move a task to the top of another list, or to the top of its own."""
    call = {"tasklist": list_id, "task": task_id}
    if destination_list_id and destination_list_id != list_id:
        call["destinationTasklist"] = destination_list_id
    return task_from_api(service.tasks().move(**call).execute(),
                         destination_list_id or list_id)


def delete_task(service, list_id: str, task_id: str) -> None:
    """Delete a task. Google keeps no copy."""
    service.tasks().delete(tasklist=list_id, task=task_id).execute()
