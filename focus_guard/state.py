from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class Phase(str, Enum):
    FOCUSED = "Focused"
    SUSPECTED = "Phone detected"
    ALERT = "Put the phone down"
    COOLDOWN = "Cooldown"
    WAITING_FOR_CLEAR = "Waiting for phone to leave"
    SNOOZED = "Snoozed"


@dataclass(frozen=True)
class PolicyConfig:
    trigger_seconds: float = 6.0
    clear_seconds: float = 3.0
    cooldown_seconds: float = 60.0
    evidence_decay: float = 2.0
    max_step_seconds: float = 1.0

    def __post_init__(self) -> None:
        if self.trigger_seconds <= 0:
            raise ValueError("trigger_seconds must be positive")
        if self.clear_seconds <= 0:
            raise ValueError("clear_seconds must be positive")
        if self.cooldown_seconds < 0:
            raise ValueError("cooldown_seconds cannot be negative")
        if self.evidence_decay <= 0:
            raise ValueError("evidence_decay must be positive")
        if self.max_step_seconds <= 0:
            raise ValueError("max_step_seconds must be positive")


@dataclass(frozen=True)
class PolicySnapshot:
    phase: Phase
    phone_in_use: bool
    evidence_seconds: float
    progress: float
    triggered: bool = False
    cleared: bool = False
    cooldown_remaining: float = 0.0
    snooze_remaining: float = 0.0


class FocusPolicy:
    """Turns noisy phone detections into a one-alert-per-episode policy."""

    def __init__(self, config: PolicyConfig) -> None:
        self.config = config
        self._last_time: float | None = None
        self._evidence_seconds = 0.0
        self._alerting = False
        self._clear_started_at: float | None = None
        self._cooldown_until = 0.0
        self._snooze_until = 0.0
        self._needs_clear = False

    def update(self, phone_in_use: bool, now: float) -> PolicySnapshot:
        dt = self._elapsed(now)

        if now < self._snooze_until:
            was_alerting = self._alerting
            self._alerting = False
            self._evidence_seconds = 0.0
            self._clear_started_at = None
            self._needs_clear = False
            return self._snapshot(
                Phase.SNOOZED,
                phone_in_use,
                cleared=was_alerting,
                snooze_remaining=self._snooze_until - now,
            )

        if self._alerting:
            if phone_in_use:
                self._clear_started_at = None
                return self._snapshot(Phase.ALERT, phone_in_use)

            if self._clear_started_at is None:
                self._clear_started_at = now

            if now - self._clear_started_at >= self.config.clear_seconds:
                self._alerting = False
                self._clear_started_at = None
                self._evidence_seconds = 0.0
                self._cooldown_until = now + self.config.cooldown_seconds
                self._needs_clear = True
                return self._snapshot(
                    Phase.COOLDOWN,
                    phone_in_use,
                    cleared=True,
                    cooldown_remaining=self.config.cooldown_seconds,
                )

            return self._snapshot(Phase.ALERT, phone_in_use)

        if now < self._cooldown_until:
            self._evidence_seconds = 0.0
            return self._snapshot(
                Phase.COOLDOWN,
                phone_in_use,
                cooldown_remaining=self._cooldown_until - now,
            )

        if self._needs_clear:
            if phone_in_use:
                self._clear_started_at = None
            else:
                if self._clear_started_at is None:
                    self._clear_started_at = now
                elif now - self._clear_started_at >= self.config.clear_seconds:
                    self._needs_clear = False
                    self._clear_started_at = None

            return self._snapshot(
                Phase.WAITING_FOR_CLEAR,
                phone_in_use,
                cooldown_remaining=0.0,
            )

        if phone_in_use:
            self._evidence_seconds += dt
        else:
            self._evidence_seconds = max(
                0.0,
                self._evidence_seconds - (dt * self.config.evidence_decay),
            )

        if self._evidence_seconds >= self.config.trigger_seconds:
            self._evidence_seconds = self.config.trigger_seconds
            self._alerting = True
            self._clear_started_at = None
            return self._snapshot(
                Phase.ALERT,
                phone_in_use,
                triggered=True,
            )

        phase = (
            Phase.SUSPECTED
            if self._evidence_seconds > 0.0
            else Phase.FOCUSED
        )
        return self._snapshot(phase, phone_in_use)

    def dismiss(self, now: float) -> None:
        """Stop an alert, then require the phone to disappear before re-arming."""
        self._last_time = now
        self._alerting = False
        self._evidence_seconds = 0.0
        self._clear_started_at = None
        self._cooldown_until = now + self.config.cooldown_seconds
        self._needs_clear = True

    def snooze(self, now: float, seconds: float) -> None:
        self._last_time = now
        self._snooze_until = now + max(0.0, seconds)
        self._alerting = False
        self._evidence_seconds = 0.0
        self._clear_started_at = None
        self._needs_clear = False

    def _elapsed(self, now: float) -> float:
        if self._last_time is None:
            self._last_time = now
            return 0.0

        elapsed = max(0.0, now - self._last_time)
        self._last_time = now
        return min(elapsed, self.config.max_step_seconds)

    def _snapshot(
        self,
        phase: Phase,
        phone_in_use: bool,
        *,
        triggered: bool = False,
        cleared: bool = False,
        cooldown_remaining: float = 0.0,
        snooze_remaining: float = 0.0,
    ) -> PolicySnapshot:
        return PolicySnapshot(
            phase=phase,
            phone_in_use=phone_in_use,
            evidence_seconds=self._evidence_seconds,
            progress=min(
                1.0, self._evidence_seconds / self.config.trigger_seconds
            ),
            triggered=triggered,
            cleared=cleared,
            cooldown_remaining=max(0.0, cooldown_remaining),
            snooze_remaining=max(0.0, snooze_remaining),
        )
