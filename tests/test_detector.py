from __future__ import annotations

import unittest

from focus_guard.detector import PhoneDetector


class FakeTensor:
    def __init__(self, values) -> None:
        self.values = values

    def cpu(self) -> "FakeTensor":
        return self

    def tolist(self):
        return self.values


class FakeBoxes:
    def __init__(self, boxes, confidences, classes) -> None:
        self.xyxy = FakeTensor(boxes)
        self.conf = FakeTensor(confidences)
        self.cls = FakeTensor(classes)

    def __len__(self) -> int:
        return len(self.xyxy.values)


class FakeResult:
    names = {0: "person", 67: "cell phone"}

    def __init__(self, boxes) -> None:
        self.boxes = boxes


class FakeModel:
    def __init__(self, result: FakeResult) -> None:
        self.result = result

    def predict(self, **_kwargs):
        return [self.result]


class FakeFrame:
    shape = (720, 1280, 3)


def make_detector(boxes, confidences, classes, *, require_person=True):
    detector = PhoneDetector.__new__(PhoneDetector)
    detector.model = FakeModel(
        FakeResult(FakeBoxes(boxes, confidences, classes))
    )
    detector.confidence = 0.45
    detector.ignore_bottom_fraction = 0.18
    detector.require_person = require_person
    detector.phone_ids = {67}
    detector.person_ids = {0}
    return detector


class PhoneDetectorTests(unittest.TestCase):
    def test_constructor_rejects_invalid_confidence_before_model_load(self) -> None:
        with self.assertRaisesRegex(ValueError, "confidence must be greater"):
            PhoneDetector("unused.pt", 0.0, 18.0, True)

    def test_constructor_rejects_invalid_desk_zone_percentage(self) -> None:
        with self.assertRaisesRegex(ValueError, "ignore_bottom_percent"):
            PhoneDetector("unused.pt", 0.45, 100.0, True)

    def test_phone_near_primary_person_is_active(self) -> None:
        detector = make_detector(
            boxes=[
                [200, 40, 1040, 700],
                [560, 260, 650, 430],
            ],
            confidences=[0.91, 0.82],
            classes=[0, 67],
        )

        analysis = detector.analyze(FakeFrame())

        self.assertTrue(analysis.phone_visible)
        self.assertTrue(analysis.phone_in_use)
        phone = next(obj for obj in analysis.objects if obj.label == "cell phone")
        self.assertTrue(phone.active)

    def test_phone_in_bottom_desk_strip_is_ignored(self) -> None:
        detector = make_detector(
            boxes=[
                [200, 40, 1040, 710],
                [560, 610, 660, 700],
            ],
            confidences=[0.91, 0.82],
            classes=[0, 67],
        )

        analysis = detector.analyze(FakeFrame())

        self.assertTrue(analysis.phone_visible)
        self.assertFalse(analysis.phone_in_use)
        self.assertIn("desk zone", analysis.reason)

    def test_person_requirement_rejects_background_phone(self) -> None:
        detector = make_detector(
            boxes=[[920, 200, 1010, 370]],
            confidences=[0.82],
            classes=[67],
            require_person=True,
        )

        analysis = detector.analyze(FakeFrame())

        self.assertFalse(analysis.phone_in_use)
        self.assertIn("primary person", analysis.reason)

    def test_person_requirement_can_be_disabled(self) -> None:
        detector = make_detector(
            boxes=[[600, 200, 690, 370]],
            confidences=[0.82],
            classes=[67],
            require_person=False,
        )

        analysis = detector.analyze(FakeFrame())

        self.assertTrue(analysis.phone_in_use)


if __name__ == "__main__":
    unittest.main()
