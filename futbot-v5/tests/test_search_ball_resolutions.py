import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from search_ball_resolutions import build_summary, fps_from_times, parse_resolutions


def test_parse_resolutions_accepts_comma_separated_sizes():
    assert parse_resolutions("320x240, 424x240,640x480") == [
        (320, 240),
        (424, 240),
        (640, 480),
    ]


def test_parse_resolutions_rejects_invalid_size():
    try:
        parse_resolutions("320x240,bad")
    except ValueError as exc:
        assert "bad" in str(exc)
    else:
        raise AssertionError("expected ValueError")


def test_fps_from_times_uses_elapsed_wall_time():
    assert fps_from_times(frame_count=30, start=10.0, end=11.5) == 20.0


def test_fps_from_times_handles_zero_elapsed():
    assert fps_from_times(frame_count=30, start=10.0, end=10.0) == 0.0


def test_build_summary_counts_balls_goals_lines_and_sources():
    records = [
        {
            "ball": {"source": "hsv", "cx": 10, "cy": 20, "r": 4.0},
            "goals": {"blue": True, "yellow": False},
            "line": {"detected": False},
        },
        {
            "ball": None,
            "goals": {"blue": True, "yellow": True},
            "line": {"detected": True},
        },
    ]

    summary = build_summary(
        mode="pipeline",
        width=320,
        height=240,
        fps=12.5,
        records=records,
    )

    assert summary["mode"] == "pipeline"
    assert summary["width"] == 320
    assert summary["height"] == 240
    assert summary["fps"] == 12.5
    assert summary["frames"] == 2
    assert summary["ball_count"] == 1
    assert summary["blue_goal_count"] == 2
    assert summary["yellow_goal_count"] == 1
    assert summary["line_count"] == 1
    assert summary["sources"] == {"hsv": 1}
