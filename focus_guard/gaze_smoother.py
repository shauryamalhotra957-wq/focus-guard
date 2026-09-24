"""
Exponential Moving Average Gaze & Head Pose Smoother.
Stabilizes continuous 3D Euler angles (yaw, pitch, roll) from face mesh models
and filters single-frame tracking glitches before triggering alerts.
"""
from typing import Optional, Tuple

class HeadPoseGazeSmoother:
    def __init__(self, alpha: float = 0.35, max_angle_jump_deg: float = 35.0):
        self.alpha = alpha
        self.max_angle_jump_deg = max_angle_jump_deg
        self.smooth_yaw: Optional[float] = None
        self.smooth_pitch: Optional[float] = None

    def filter(self, raw_yaw: float, raw_pitch: float) -> Tuple[float, float]:
        if self.smooth_yaw is None or self.smooth_pitch is None:
            self.smooth_yaw = raw_yaw
            self.smooth_pitch = raw_pitch
            return self.smooth_yaw, self.smooth_pitch

        # Outlier rejection on sudden unrealistic single-frame discontinuities
        if abs(raw_yaw - self.smooth_yaw) > self.max_angle_jump_deg:
            raw_yaw = self.smooth_yaw
        if abs(raw_pitch - self.smooth_pitch) > self.max_angle_jump_deg:
            raw_pitch = self.smooth_pitch

        self.smooth_yaw = (self.alpha * raw_yaw) + ((1.0 - self.alpha) * self.smooth_yaw)
        self.smooth_pitch = (self.alpha * raw_pitch) + ((1.0 - self.alpha) * self.smooth_pitch)
        return round(self.smooth_yaw, 2), round(self.smooth_pitch, 2)

    def is_distracted(self, yaw_threshold: float = 25.0, pitch_threshold: float = 20.0) -> bool:
        if self.smooth_yaw is None or self.smooth_pitch is None:
            return False
        return abs(self.smooth_yaw) > yaw_threshold or abs(self.smooth_pitch) > pitch_threshold
