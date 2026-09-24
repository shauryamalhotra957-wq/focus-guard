import pytest
from focus_guard.gaze_smoother import HeadPoseGazeSmoother

def test_smoother_initialization():
    smoother = HeadPoseGazeSmoother(alpha=0.5)
    yaw, pitch = smoother.filter(10.0, -5.0)
    assert yaw == 10.0
    assert pitch == -5.0
    assert smoother.is_distracted() is False

def test_smoother_exponential_decay():
    smoother = HeadPoseGazeSmoother(alpha=0.5)
    smoother.filter(0.0, 0.0)
    yaw, pitch = smoother.filter(20.0, 10.0)
    assert yaw == 10.0
    assert pitch == 5.0

def test_smoother_outlier_rejection():
    smoother = HeadPoseGazeSmoother(alpha=0.5, max_angle_jump_deg=30.0)
    smoother.filter(0.0, 0.0)
    # 80 deg jump is rejected
    yaw, pitch = smoother.filter(80.0, 0.0)
    assert yaw == 0.0

def test_distraction_flag():
    smoother = HeadPoseGazeSmoother(alpha=1.0)
    smoother.filter(30.0, 0.0)
    assert smoother.is_distracted(yaw_threshold=25.0) is True
