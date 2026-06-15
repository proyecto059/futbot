import sys
from pathlib import Path

import cv2
import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "src"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

from capture_attack_geometry import _attack_status, _goal_masks, annotate_attack_geometry, is_better_capture, mask_bbox
from test_vision_operators import bgr_from_hsv


def test_mask_bbox_returns_xywh_for_nonzero_mask():
    mask = np.zeros((80, 100), dtype=np.uint8)
    mask[20:40, 30:70] = 255

    assert mask_bbox(mask) == [30, 20, 40, 20]


def test_mask_bbox_returns_none_for_empty_mask():
    mask = np.zeros((80, 100), dtype=np.uint8)

    assert mask_bbox(mask) is None


def test_goal_masks_use_real_goal_bbox_not_full_width_dark_band():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    frame[:] = bgr_from_hsv(80, 255, 180)
    frame[51:94, 64:320] = bgr_from_hsv(82, 142, 70)
    frame[52:93, 0:64] = bgr_from_hsv(119, 255, 105)

    masks = _goal_masks(frame)

    assert masks["blue_bbox"] is not None
    assert masks["blue_bbox"][0] == 0
    assert masks["blue_bbox"][2] <= 70


def test_annotate_attack_geometry_draws_ball_and_goal_vector():
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    snapshot = {
        "ball": {"cx": 40, "cy": 70, "r": 10, "source": "hsv"},
        "goals": {
            "blue": True,
            "blue_cx": 120,
            "blue_cy": 35,
            "yellow": False,
            "yellow_cx": None,
            "yellow_cy": None,
        },
        "line": {"detected": False},
    }
    masks = {"blue_bbox": [110, 30, 25, 50], "yellow_bbox": None}

    annotated = annotate_attack_geometry(frame, snapshot, masks, target_key="blue")

    assert annotated.shape == frame.shape
    assert int(np.count_nonzero(cv2.absdiff(frame, annotated))) > 0
    assert np.any(np.all(annotated[32:39, 117:124] == np.array([0, 255, 0], dtype=np.uint8), axis=2))


def test_annotate_attack_geometry_draws_behind_ball_route_target():
    frame = np.zeros((240, 320, 3), dtype=np.uint8)
    snapshot = {
        "ball": {"cx": 96, "cy": 85, "r": 13.5, "source": "hsv"},
        "goals": {
            "blue": True,
            "blue_cx": 14.8,
            "blue_cy": 72.8,
            "blue_bbox": [0, 56, 35, 34],
            "yellow": False,
            "yellow_cx": None,
            "yellow_cy": None,
            "yellow_bbox": None,
        },
        "line": {"detected": False},
    }

    annotated = annotate_attack_geometry(frame, snapshot, {}, target_key="blue")

    magenta_pixels = np.all(annotated[87:98, 135:146] == np.array([255, 0, 255], dtype=np.uint8), axis=2)
    cyan_route_pixels = np.all(annotated == np.array([255, 255, 0], dtype=np.uint8), axis=2)
    assert np.any(magenta_pixels)
    assert np.count_nonzero(cyan_route_pixels[130:210, 120:155]) >= 60
    assert np.count_nonzero(cyan_route_pixels[130:210, 170:215]) == 0
    assert np.count_nonzero(cyan_route_pixels[82:96, 96:132]) == 0
    assert np.count_nonzero(cyan_route_pixels[70:88, 35:97]) == 0


def test_attack_status_matches_controller_for_saved_small_ball_route():
    snapshot = {
        "ball": {"cx": 96, "cy": 85, "r": 13.5, "source": "hsv"},
        "goals": {
            "blue": True,
            "blue_cx": 14.8,
            "blue_cy": 72.8,
            "yellow": False,
            "yellow_cx": None,
            "yellow_cy": None,
        },
        "line": {"detected": False},
    }

    assert _attack_status(snapshot, "blue", frame_width=320, frame_height=240) == "ALIGN_ARC"


def test_attack_status_matches_controller_for_goal_aligned_small_ball():
    snapshot = {
        "ball": {"cx": 295, "cy": 112, "r": 15.7, "source": "hsv"},
        "goals": {
            "blue": True,
            "blue_cx": 274.4,
            "blue_cy": 76.9,
            "yellow": False,
            "yellow_cx": None,
            "yellow_cy": None,
        },
        "line": {"detected": False},
    }

    assert _attack_status(snapshot, "blue", frame_width=320, frame_height=240) == "ALIGN_ARC"


def test_annotate_attack_geometry_does_not_draw_false_fallback_goal_bbox():
    frame = np.zeros((120, 160, 3), dtype=np.uint8)
    snapshot = {
        "ball": None,
        "goals": {"blue": True, "blue_bbox": [110, 30, 25, 50], "blue_cx": 120, "yellow": False, "yellow_bbox": None},
        "line": {"detected": False},
    }
    masks = {"blue_bbox": [0, 0, 160, 20], "yellow_bbox": [20, 10, 60, 50]}

    annotated = annotate_attack_geometry(frame, snapshot, masks, target_key="blue")

    yellow_pixels = np.all(annotated[10:60, 20:80] == np.array([0, 255, 255], dtype=np.uint8), axis=2)
    assert not np.any(yellow_pixels)


def test_capture_candidate_with_ball_beats_candidate_without_ball():
    current = {"ball": None, "goals": {"blue": True}}
    candidate = {"ball": {"cx": 40, "cy": 70, "r": 7}, "goals": {"blue": True}}

    assert is_better_capture(candidate, current, target_key="blue") is True


def test_capture_candidate_with_target_goal_beats_other_goal_only():
    current = {"ball": {"cx": 40, "cy": 70, "r": 7}, "goals": {"blue": False, "yellow": True}}
    candidate = {"ball": {"cx": 42, "cy": 70, "r": 7}, "goals": {"blue": True, "yellow": False}}

    assert is_better_capture(candidate, current, target_key="blue") is True
