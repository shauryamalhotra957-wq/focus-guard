from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class DetectedObject:
    label: str
    confidence: float
    box: tuple[int, int, int, int]
    active: bool = False


@dataclass(frozen=True)
class FrameAnalysis:
    objects: tuple[DetectedObject, ...]
    phone_visible: bool
    phone_in_use: bool
    reason: str


class PhoneDetector:
    """YOLO wrapper that only keeps person and cell-phone detections."""

    PHONE_LABELS = {"cell phone", "mobile phone", "phone"}

    def __init__(
        self,
        model_name: str,
        confidence: float,
        ignore_bottom_percent: float,
        require_person: bool,
    ) -> None:
        from ultralytics import YOLO

        self.model = YOLO(model_name)
        self.confidence = confidence
        self.ignore_bottom_fraction = ignore_bottom_percent / 100.0
        self.require_person = require_person

        names = self.model.names
        self.phone_ids = {
            int(class_id)
            for class_id, name in names.items()
            if str(name).strip().lower() in self.PHONE_LABELS
        }
        self.person_ids = {
            int(class_id)
            for class_id, name in names.items()
            if str(name).strip().lower() == "person"
        }
        if not self.phone_ids:
            raise RuntimeError(
                f"Model '{model_name}' does not contain a cell-phone class."
            )

    def analyze(self, frame) -> FrameAnalysis:
        height, width = frame.shape[:2]
        class_filter = sorted(self.phone_ids | self.person_ids)
        results = self.model.predict(
            source=frame,
            classes=class_filter,
            conf=min(0.25, self.confidence),
            imgsz=640,
            verbose=False,
        )

        if not results:
            return FrameAnalysis((), False, False, "No detections")

        result = results[0]
        boxes = result.boxes
        if boxes is None or len(boxes) == 0:
            return FrameAnalysis((), False, False, "No phone visible")

        objects: list[DetectedObject] = []
        for xyxy, confidence, class_id in zip(
            boxes.xyxy.cpu().tolist(),
            boxes.conf.cpu().tolist(),
            boxes.cls.cpu().tolist(),
        ):
            label = str(result.names[int(class_id)]).strip().lower()
            objects.append(
                DetectedObject(
                    label=label,
                    confidence=float(confidence),
                    box=tuple(int(round(value)) for value in xyxy),
                )
            )

        people = [
            obj
            for obj in objects
            if obj.label == "person" and obj.confidence >= 0.25
        ]
        phones = [
            obj
            for obj in objects
            if obj.label in self.PHONE_LABELS
            and obj.confidence >= self.confidence
        ]
        if not phones:
            return FrameAnalysis(tuple(objects), False, False, "No phone visible")

        primary_person = max(people, key=_box_area, default=None)
        active_phone_indexes: set[int] = set()
        ignored_for_desk = False
        ignored_for_person = False

        for phone in phones:
            center_x, center_y = _box_center(phone.box)
            phone_area_ratio = _box_area(phone) / float(width * height)
            in_desk_zone = center_y >= height * (
                1.0 - self.ignore_bottom_fraction
            )
            large_enough = phone_area_ratio >= 0.0005

            near_primary_person = True
            if self.require_person:
                near_primary_person = (
                    primary_person is not None
                    and _point_in_expanded_box(
                        center_x,
                        center_y,
                        primary_person.box,
                        width,
                        height,
                        expansion=0.18,
                    )
                )

            if in_desk_zone:
                ignored_for_desk = True
            elif not near_primary_person:
                ignored_for_person = True
            elif large_enough:
                active_phone_indexes.add(id(phone))

        marked_objects = tuple(
            replace(obj, active=id(obj) in active_phone_indexes)
            if obj.label in self.PHONE_LABELS
            else obj
            for obj in objects
        )
        phone_in_use = bool(active_phone_indexes)

        if phone_in_use:
            reason = "Phone-use evidence"
        elif ignored_for_desk:
            reason = "Phone ignored in the desk zone"
        elif ignored_for_person:
            reason = "Phone is outside the primary person's area"
        else:
            reason = "Phone is too small or far away"

        return FrameAnalysis(
            objects=marked_objects,
            phone_visible=True,
            phone_in_use=phone_in_use,
            reason=reason,
        )


def _box_area(obj: DetectedObject) -> int:
    left, top, right, bottom = obj.box
    return max(0, right - left) * max(0, bottom - top)


def _box_center(box: tuple[int, int, int, int]) -> tuple[float, float]:
    left, top, right, bottom = box
    return ((left + right) / 2.0, (top + bottom) / 2.0)


def _point_in_expanded_box(
    x: float,
    y: float,
    box: tuple[int, int, int, int],
    frame_width: int,
    frame_height: int,
    expansion: float,
) -> bool:
    left, top, right, bottom = box
    expand_x = (right - left) * expansion
    expand_y = (bottom - top) * expansion
    return (
        max(0.0, left - expand_x) <= x <= min(frame_width, right + expand_x)
        and max(0.0, top - expand_y)
        <= y
        <= min(frame_height, bottom + expand_y)
    )


def draw_analysis(frame, analysis: FrameAnalysis, ignore_bottom_percent: float):
    """Draw detections and the ignored desk strip on a BGR OpenCV frame."""
    import cv2

    height, width = frame.shape[:2]
    desk_y = int(height * (1.0 - (ignore_bottom_percent / 100.0)))

    if ignore_bottom_percent > 0:
        overlay = frame.copy()
        cv2.rectangle(
            overlay,
            (0, desk_y),
            (width, height),
            (34, 34, 34),
            thickness=-1,
        )
        cv2.addWeighted(overlay, 0.34, frame, 0.66, 0, frame)
        cv2.line(frame, (0, desk_y), (width, desk_y), (150, 150, 150), 1)
        cv2.putText(
            frame,
            "ignored desk zone",
            (12, min(height - 12, desk_y + 24)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (210, 210, 210),
            1,
            cv2.LINE_AA,
        )

    for obj in analysis.objects:
        if obj.label == "person":
            color = (120, 120, 120)
            thickness = 1
        elif obj.active:
            color = (44, 80, 255)
            thickness = 3
        else:
            color = (245, 180, 40)
            thickness = 2

        left, top, right, bottom = obj.box
        cv2.rectangle(frame, (left, top), (right, bottom), color, thickness)
        if obj.label != "person":
            text = f"{obj.label} {obj.confidence:.0%}"
            cv2.putText(
                frame,
                text,
                (left, max(22, top - 8)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.58,
                color,
                2,
                cv2.LINE_AA,
            )
    return frame
