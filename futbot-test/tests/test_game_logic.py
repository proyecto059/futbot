from game_logic import decide_action, Action


def test_turn_right_when_ball_is_right():
    action = decide_action(ball_x=250, ball_y=120, ball_radius=20)
    assert action == Action.TURN_RIGHT


def test_turn_left_when_ball_is_left():
    action = decide_action(ball_x=50, ball_y=120, ball_radius=20)
    assert action == Action.TURN_LEFT


def test_move_forward_when_centered_and_far():
    action = decide_action(ball_x=160, ball_y=120, ball_radius=10)
    assert action == Action.FORWARD


def test_stop_when_ball_close_and_centered():
    action = decide_action(ball_x=160, ball_y=120, ball_radius=50)
    assert action == Action.STOP


def test_search_when_no_ball():
    action = decide_action(ball_x=None, ball_y=None, ball_radius=None)
    assert action == Action.SEARCH
