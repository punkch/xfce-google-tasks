"""Where the popup goes. Pure geometry, so it needs no display."""

from gtasks_panel.ui.click import GAP, HEIGHT, WIDTH, place

# One 1920x1080 monitor with a 30 pixel panel at the top.
AREA = (0, 30, 1920, 1050)


def at(pointer_x, pointer_y):
    return place(pointer_x, pointer_y, *AREA)


def test_the_popup_hangs_under_a_pointer_in_the_top_half():
    left, top = at(960, 100)
    assert left == 960 - WIDTH // 2
    assert top == 100 + GAP


def test_the_popup_stands_over_a_pointer_in_the_bottom_half():
    _left, top = at(960, 1000)
    assert top == 1000 - HEIGHT - GAP


def test_the_left_edge_holds_the_popup():
    left, _top = at(10, 100)
    assert left == AREA[0]


def test_the_right_edge_holds_the_popup():
    left, _top = at(1910, 100)
    assert left == AREA[0] + AREA[2] - WIDTH


def test_the_top_edge_holds_the_popup():
    # A pointer high in a short work area: the popup must not go over it.
    _left, top = place(500, 35, 0, 30, 1920, 400)
    assert top == 30


def test_the_bottom_edge_holds_the_popup():
    # Just inside the top half, but the popup would hang past the bottom.
    _left, top = at(960, 550)
    assert top == AREA[1] + AREA[3] - HEIGHT


def test_a_work_area_smaller_than_the_popup_starts_at_its_corner():
    left, top = place(100, 100, 0, 0, 200, 200)
    assert (left, top) == (0, 0)
