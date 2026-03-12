from enum import Enum, auto
from config import FRAME_CENTER_X, DEAD_ZONE_X, CLOSE_RADIUS


class Action(Enum):
    FORWARD = auto()
    TURN_LEFT = auto()
    TURN_RIGHT = auto()
    STOP = auto()
    SEARCH = auto()


def decide_action(
    ball_x: int | None,
    ball_y: int | None,
    ball_radius: int | None,
) -> Action:
    """
    Pure function: maps ball position to robot action.
    No side effects — easy to test.
    """
    if ball_x is None or ball_y is None or ball_radius is None:
        return Action.SEARCH

    if ball_radius >= CLOSE_RADIUS:
        return Action.STOP

    error_x = ball_x - FRAME_CENTER_X
    if error_x > DEAD_ZONE_X:
        return Action.TURN_RIGHT
    if error_x < -DEAD_ZONE_X:
        return Action.TURN_LEFT

    return Action.FORWARD
