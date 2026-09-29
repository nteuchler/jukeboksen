"""Monotonic coin-survival countdown, independent of web polling and hardware."""
from __future__ import annotations

import math
import time


class SurvivalTimer:
    WARNINGS = (600, 300, 60, 30, 10)

    def __init__(self, sounds, rgb, clock=time.monotonic):
        self.sounds = sounds
        self.rgb = rgb
        self.clock = clock
        self.minutes = 30
        self.deadline = None
        self.expired = False
        self.error = None
        self._previous_remaining = 0
        self._next_alarm = 0
        self._next_update = 0

    def configure(self, minutes):
        if isinstance(minutes, bool) or not isinstance(minutes, int) or not 1 <= minutes <= 180:
            raise ValueError('Duration must be a whole number from 1 to 180 minutes')
        self.minutes = minutes
        if self.deadline is not None:
            self.start()

    def start(self):
        self.sounds.stop()
        self.error = None
        self.expired = False
        self.deadline = self.clock() + self.minutes * 60
        self._previous_remaining = self.minutes * 60
        self._next_alarm = self.deadline
        self._next_update = 0
        self.rgb.set_countdown(1.0)

    def stop(self):
        self.deadline = None
        self.expired = False
        self.sounds.stop()

    def coin(self):
        if self.deadline is not None:
            self.start()
            try:
                self.sounds.play('coin')
            except Exception as error:
                self.error = str(error)

    def poll(self):
        if self.deadline is None:
            return
        now = self.clock()
        if now < self._next_update:
            return
        self._next_update = now + .1
        remaining = max(0.0, self.deadline - now)
        self.expired = remaining == 0
        try:
            self.rgb.set_countdown(remaining / (self.minutes * 60))
        except Exception as error:
            self.error = str(error)
        try:
            if self.expired:
                if now >= self._next_alarm:
                    self._next_alarm = now + 15
                    self.sounds.play('expired')
            else:
                crossed = [n for n in self.WARNINGS if remaining <= n < self._previous_remaining]
                if crossed:
                    # After a scheduling delay announce only the most urgent warning.
                    self.sounds.play(str(min(crossed)))
        except Exception as error:
            self.error = str(error)
        self._previous_remaining = remaining

    def status(self):
        remaining = max(0.0, self.deadline - self.clock()) if self.deadline is not None else 0
        return {
            'minutes': self.minutes,
            'active': self.deadline is not None,
            'expired': self.deadline is not None and remaining == 0,
            'remaining_seconds': math.ceil(remaining),
            'fraction': remaining / (self.minutes * 60),
            'error': self.error or getattr(self.sounds, 'error', None),
        }
