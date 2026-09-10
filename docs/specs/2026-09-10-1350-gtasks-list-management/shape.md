# gtasks-panel 0.3.0: list management and popup due dates — Shaping Notes

## Scope

0.2.0 shows lists but cannot change them. 0.3.0 adds:

- New list, Rename list, Delete list, Clear completed, Mark all done in
  the full window.
- A due date picker on each task row in the popup.
- A due date picker in the quick-add field (popup and full window).

## User answers (2026-09-10)

- List actions: "New list, Rename list, Delete list, Clear completed,
  may be also mark all tasks in the list as completed."
- Placement: row menu (right click, or a "…" button that shows when the
  mouse is over the row).
- Popup due date: both per row and in quick-add.

## Decisions

- Delete list, Clear completed and Mark all done ask first with a modal
  dialog. `tasks.delete` has no undo. Mark all done is N calls, so it
  asks too.
- Clear completed deletes each completed task with `tasks.delete`. It
  does not call `tasks.clear`.
- The calendar popover moves out of `mainwindow.py` into a shared
  `DuePopover` widget with Today, Tomorrow, Clear and Set.
- The store keeps the selection on "All lists" when the selected list is
  deleted.
- The All lists row has no menu.
- Menu items and due pickers are insensitive offline.
- Version 0.3.0. No new dependencies.

## Out of scope

Reorder lists, list colours, undo for list actions, moving all tasks
between lists.

## Context

- **Visuals:** None. Xvfb screenshots are made during verification.
- **References:** see `references.md`.
- **Product alignment:** N/A. No `docs/product/` folder.

## Skills & Conventions Applied

- Global user rules: ASD-STE100, conventional commits after
  confirmation, no attribution trailers, keep `CLAUDE.md` current.
- Delivery workflow: Workflow tool with three agents (opus, opus,
  sonnet), then the code-review skill with five agents, then
  interface-craft on screenshots.

## As built (2026-09-10)

- `DueButton` is a flat `Gtk.Button`; its `DuePopover` is made on the
  first click and names the task it changes. `add_from_entry()` in
  `widgets.py` is the one quick-add path for both windows.
- The main window has a status line under the task list. "Show
  completed" is a check button. Every sidebar row has the "…" button
  (empty on "All lists"), so the counts line up.
- Delete list sends a waiting task delete first, then the list delete.
- `replace_task` never appends: a task behind the undo bar stays out.
- The popup skips redraws while hidden and redraws when it shows.
- Review of 2026-09-10 (five code lenses, one UX critique): 20 items
  applied. Left as recommendations: batch HTTP for Mark all done and
  Clear completed; a `Rename` NamedTuple for the rename state; a shared
  composite action for the apt-get install lines in the workflows;
  tests that reach private window attributes.
