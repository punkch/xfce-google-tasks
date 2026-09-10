"""The pure parts of a panel click. No GTK, so a test needs no display.

Genmon runs the click command one time for each click, so a double click
starts two processes. Each one stamps its own start time and hands it to
the first process. Two stamps close together are one double click.

The command line and the place of the popup on screen live here too:
both are pure functions of their input.
"""

import datetime as dt

MIN_THRESHOLD = 0.400  # seconds; process start times are not exact

# Popup size in pixels. `place` needs them, and so does the popup itself.
WIDTH = 380
HEIGHT = 520
GAP = 12  # pixels between the pointer and the popup


def parse_args(args: list[str]) -> tuple[float | None, bool, bool]:
    """Return (clicked_at, quit, window) from our own command line."""
    clicked_at = None
    quit_now = False
    window = False
    rest = list(args)
    while rest:
        arg = rest.pop(0)
        if arg == "--quit":
            quit_now = True
        elif arg == "--window":
            window = True
        elif arg == "--clicked-at":
            clicked_at = _float(rest.pop(0) if rest else None)
        elif arg.startswith("--clicked-at="):
            clicked_at = _float(arg.split("=", 1)[1])
    return clicked_at, quit_now, window


def _float(text) -> float | None:
    try:
        return float(text)
    except (TypeError, ValueError):
        return None


def double_click_threshold(gtk_milliseconds: int | None) -> float:
    """The largest gap that still counts as a double click, in seconds."""
    if not gtk_milliseconds or gtk_milliseconds <= 0:
        gtk_milliseconds = 250
    return max(MIN_THRESHOLD, 2 * gtk_milliseconds / 1000.0)


def classify_click(prev_ts: float | None, ts: float, threshold: float) -> str:
    """Return "double" for the second click of a pair, else "single".

    `prev_ts` is the stamp of the click before, or None for the first one.
    The two stamps come from two processes that race through D-Bus, so the
    second one can arrive first. Only the size of the gap counts.
    """
    if prev_ts is None:
        return "single"
    if abs(ts - prev_ts) < threshold:
        return "double"
    return "single"


def due_shortcuts(today: dt.date) -> dict[str, dt.date]:
    """The quick buttons of the due date popover, in the order they show.

    The dates come from `today`, so a test gives its own day and the
    widget gives the real one.
    """
    return {"Today": today, "Tomorrow": today + dt.timedelta(days=1)}


def clamp(value: int, low: int, high: int) -> int:
    """Keep a number between two bounds. A too small range gives `low`."""
    return max(low, min(value, max(low, high)))


def place(pointer_x: int, pointer_y: int, area_x: int, area_y: int,
          area_w: int, area_h: int, width: int = WIDTH, height: int = HEIGHT,
          gap: int = GAP) -> tuple[int, int]:
    """Top left corner of the popup for a pointer at (pointer_x, pointer_y).

    The popup goes below the pointer in the top half of the work area and
    above it in the bottom half, and it never crosses an edge.
    """
    left = clamp(pointer_x - width // 2, area_x, area_x + area_w - width)
    below = pointer_y - area_y < area_h // 2
    top = pointer_y + gap if below else pointer_y - height - gap
    return left, clamp(top, area_y, area_y + area_h - height)
