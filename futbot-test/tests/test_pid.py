from motor_control import PIDController


def test_pid_output_positive_for_positive_error():
    pid = PIDController(kp=1.0, ki=0.0, kd=0.0)
    out = pid.update(error=10.0, dt=0.02)
    assert out > 0


def test_pid_output_zero_for_zero_error():
    pid = PIDController(kp=1.0, ki=0.1, kd=0.1)
    # Warm up with zero error
    for _ in range(20):
        pid.update(error=0.0, dt=0.02)
    assert abs(pid.update(error=0.0, dt=0.02)) < 0.01


def test_pid_clamps_to_max():
    pid = PIDController(kp=100.0, ki=0.0, kd=0.0, max_output=80.0)
    out = pid.update(error=50.0, dt=0.02)
    assert out <= 80.0


def test_pid_reset_clears_integral():
    pid = PIDController(kp=0.0, ki=10.0, kd=0.0, max_output=100.0)
    for _ in range(10):
        pid.update(error=5.0, dt=0.02)
    pid.reset()
    out = pid.update(error=0.0, dt=0.02)
    assert abs(out) < 0.01
