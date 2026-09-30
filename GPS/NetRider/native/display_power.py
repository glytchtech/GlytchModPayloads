"""NetRider-only idle settings; no changes to the Pager's system preferences."""
import json
import os
from pathlib import Path
import tempfile

TIMEOUTS = (0, 15, 30, 60, 120, 300, 600, 1800)


def timeout_label(seconds):
    return 'OFF' if not seconds else '%d SEC' % seconds if seconds < 60 else '%d MIN' % (seconds//60)


class DisplaySettings:
    def __init__(self, path):
        self.path = Path(path)
        self.dim_after = self.sleep_after = 0  # Preserve existing always-on behavior.
        try:
            settings = json.loads(self.path.read_text())
            dim, sleep = settings['dim_after'], settings['sleep_after']
            self.validate(dim, sleep)
            self.dim_after, self.sleep_after = dim, sleep
        except (OSError, ValueError, KeyError, TypeError): pass

    @staticmethod
    def validate(dim, sleep):
        if type(dim) is not int or type(sleep) is not int or dim not in TIMEOUTS or sleep not in TIMEOUTS:
            raise ValueError('Invalid display timeout')

    def save(self, dim, sleep):
        self.validate(dim, sleep)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        name = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', dir=self.path.parent, prefix='.display-', delete=False) as f:
                name = f.name
                json.dump({'dim_after': dim, 'sleep_after': sleep}, f)
                f.flush()
                os.fsync(f.fileno())
            os.replace(name, self.path)
        finally:
            if name and os.path.exists(name): os.unlink(name)
        self.dim_after, self.sleep_after = dim, sleep


class IdleTimer:
    def __init__(self, dim=0, sleep=0, now=0):
        self.dim_after, self.sleep_after, self.last_input = dim, sleep, now

    def state(self, now):
        elapsed = max(0, now-self.last_input)
        if self.sleep_after and elapsed >= self.sleep_after: return 'SLEEP'
        if self.dim_after and elapsed >= self.dim_after: return 'DIM'
        return 'AWAKE'

    def activity(self, now):
        self.last_input = now


class DisplayPower:
    """Guardian-owned backlight state. Logging/network workers never count as input."""
    def __init__(self, backlight, settings, now):
        self.backlight, self.settings = backlight, settings
        self.timer = IdleTimer(settings.dim_after, settings.sleep_after, now)
        self.level = backlight.level
        self.mode = 'AWAKE'

    def activity(self, now):
        self.timer.activity(now)
        if self.mode != 'AWAKE': self.backlight.apply(self.level)
        self.mode = 'AWAKE'

    def set_level(self, level, now):
        self.level = self.backlight.apply(level)
        self.timer.activity(now)
        self.mode = 'AWAKE'
        return self.level

    def set_timers(self, dim, sleep, now):
        self.settings.save(dim, sleep)
        self.timer.dim_after, self.timer.sleep_after = dim, sleep
        self.activity(now)

    def tick(self, now):
        mode = self.timer.state(now)
        if mode == 'AWAKE':
            if self.mode != mode: self.backlight.apply(self.level)
        else:
            target = 1 if mode == 'SLEEP' else min(3, self.level)
            # Match stock DISABLE_DISPLAY's low backlight level; the renderer
            # blanks its own frame and stops drawing while asleep. KeepAwake
            # only suppresses the independent system-wide idle policy.
            if self.mode != mode or self.backlight.read() > target:
                self.backlight.idle(target)
        self.mode = mode
        return mode
