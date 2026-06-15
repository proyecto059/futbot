import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from chase.search_operator import SearchOperator


def forward(v_left, v_right):
    return (v_left - v_right) * 0.5


def turn(v_left, v_right):
    return (v_left + v_right) * 0.5


def test_local_reacquire_turns_toward_last_right_seen_ball():
    direction, v_left, v_right = SearchOperator().local_reacquire_step(
        last_cx=260.0,
        last_r=18.0,
        frame_w=320,
    )

    assert direction == "right"
    assert forward(v_left, v_right) >= 0.0
    assert turn(v_left, v_right) > 0.0


def test_local_reacquire_turns_toward_last_left_seen_ball():
    direction, v_left, v_right = SearchOperator().local_reacquire_step(
        last_cx=60.0,
        last_r=18.0,
        frame_w=320,
    )

    assert direction == "left"
    assert forward(v_left, v_right) >= 0.0
    assert turn(v_left, v_right) < 0.0


def test_local_reacquire_advances_when_far_ball_was_centered():
    direction, v_left, v_right = SearchOperator().local_reacquire_step(
        last_cx=160.0,
        last_r=12.0,
        frame_w=320,
    )

    assert direction == "forward"
    assert forward(v_left, v_right) > 0.0
    assert abs(turn(v_left, v_right)) < 1.0


def test_local_reacquire_scans_when_no_memory():
    direction, v_left, v_right = SearchOperator().local_reacquire_step(
        last_cx=None,
        last_r=0.0,
        frame_w=320,
    )

    assert direction == "scan"
    assert forward(v_left, v_right) == 0.0
    assert turn(v_left, v_right) != 0.0


def test_field_search_alternates_scan_and_forward_steps():
    search = SearchOperator()

    first = search.field_search_step(0)
    second = search.field_search_step(1)
    third = search.field_search_step(2)

    assert first[0] == "scan_left"
    assert second[0] == "forward"
    assert third[0] == "scan_right"
    assert forward(second[1], second[2]) > 0.0


def test_line_aware_field_search_turns_right_away_from_left_line():
    direction, v_left, v_right = SearchOperator().line_aware_field_search_step(
        step_index=1,
        line_cx=70.0,
        frame_w=320,
    )

    assert direction == "line_away_right"
    assert forward(v_left, v_right) <= 20.0
    assert turn(v_left, v_right) > 0.0


def test_line_aware_field_search_turns_left_away_from_right_line():
    direction, v_left, v_right = SearchOperator().line_aware_field_search_step(
        step_index=1,
        line_cx=250.0,
        frame_w=320,
    )

    assert direction == "line_away_left"
    assert forward(v_left, v_right) <= 20.0
    assert turn(v_left, v_right) < 0.0


def test_line_aware_field_search_scans_when_line_side_unknown():
    direction, v_left, v_right = SearchOperator().line_aware_field_search_step(
        step_index=1,
        line_cx=None,
        frame_w=320,
    )

    assert direction == "line_scan"
    assert forward(v_left, v_right) == 0.0
    assert turn(v_left, v_right) != 0.0
