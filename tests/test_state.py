from __future__ import annotations

import unittest

from focus_guard.state import FocusPolicy, Phase, PolicyConfig


class FocusPolicyTests(unittest.TestCase):
    def make_policy(self) -> FocusPolicy:
        return FocusPolicy(
            PolicyConfig(
                trigger_seconds=3.0,
                clear_seconds=2.0,
                cooldown_seconds=5.0,
                evidence_decay=2.0,
                max_step_seconds=1.0,
            )
        )

    def test_sustained_detection_triggers_once(self) -> None:
        policy = self.make_policy()
        policy.update(True, 0.0)
        policy.update(True, 1.0)
        policy.update(True, 2.0)
        triggered = policy.update(True, 3.0)
        still_alerting = policy.update(True, 4.0)

        self.assertEqual(triggered.phase, Phase.ALERT)
        self.assertTrue(triggered.triggered)
        self.assertEqual(still_alerting.phase, Phase.ALERT)
        self.assertFalse(still_alerting.triggered)

    def test_brief_phone_sighting_decays_instead_of_triggering(self) -> None:
        policy = self.make_policy()
        policy.update(False, 0.0)
        partial = policy.update(True, 1.0)
        cleared = policy.update(False, 2.0)

        self.assertEqual(partial.phase, Phase.SUSPECTED)
        self.assertEqual(cleared.phase, Phase.FOCUSED)
        self.assertEqual(cleared.evidence_seconds, 0.0)

    def test_alert_clears_only_after_phone_is_absent(self) -> None:
        policy = self.make_policy()
        for second in range(4):
            snapshot = policy.update(True, float(second))
        self.assertEqual(snapshot.phase, Phase.ALERT)

        policy.update(False, 4.0)
        not_clear_yet = policy.update(False, 5.0)
        cleared = policy.update(False, 6.0)

        self.assertEqual(not_clear_yet.phase, Phase.ALERT)
        self.assertTrue(cleared.cleared)
        self.assertEqual(cleared.phase, Phase.COOLDOWN)

    def test_cooldown_does_not_retrigger_until_phone_leaves(self) -> None:
        policy = self.make_policy()
        for second in range(4):
            policy.update(True, float(second))
        policy.update(False, 4.0)
        policy.update(False, 6.0)

        still_present = policy.update(True, 11.0)
        self.assertEqual(still_present.phase, Phase.WAITING_FOR_CLEAR)
        self.assertFalse(still_present.triggered)

        policy.update(False, 12.0)
        cleared = policy.update(False, 14.0)
        self.assertEqual(cleared.phase, Phase.FOCUSED)
        self.assertFalse(cleared.phone_in_use)

    def test_cooldown_blocks_a_new_alert(self) -> None:
        policy = self.make_policy()
        for second in range(4):
            policy.update(True, float(second))
        policy.update(False, 4.0)
        policy.update(False, 6.0)

        during_cooldown = policy.update(True, 8.0)
        self.assertEqual(during_cooldown.phase, Phase.COOLDOWN)
        self.assertFalse(during_cooldown.triggered)

    def test_manual_dismiss_requires_phone_to_leave(self) -> None:
        policy = self.make_policy()
        for second in range(4):
            policy.update(True, float(second))
        policy.dismiss(4.0)

        still_present = policy.update(True, 20.0)
        self.assertEqual(still_present.phase, Phase.WAITING_FOR_CLEAR)

        policy.update(False, 21.0)
        policy.update(False, 22.0)
        clear = policy.update(False, 23.0)
        self.assertEqual(clear.phase, Phase.WAITING_FOR_CLEAR)

        armed = policy.update(False, 24.0)
        self.assertEqual(armed.phase, Phase.FOCUSED)

    def test_snooze_prevents_evidence_accumulation(self) -> None:
        policy = self.make_policy()
        policy.update(False, 0.0)
        policy.snooze(1.0, 10.0)

        snoozed = policy.update(True, 5.0)
        after_snooze = policy.update(True, 12.0)

        self.assertEqual(snoozed.phase, Phase.SNOOZED)
        self.assertEqual(snoozed.evidence_seconds, 0.0)
        self.assertEqual(after_snooze.phase, Phase.SUSPECTED)
        self.assertFalse(after_snooze.triggered)


if __name__ == "__main__":
    unittest.main()
