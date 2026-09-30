"""Pager 1.1.2 backlight control, isolated from persistent system preferences.

The stock UI writes backlight_pwm/brightness and clamps normal levels to 2..16.
ENABLE_DISPLAY cannot be used here: it also overwrites the framebuffer.
"""
from pathlib import Path
import json
import subprocess
from display_power import TIMEOUTS


def configured_level():
    try:
        result = subprocess.run(['uci', '-q', 'get', 'system.@pager[0].lcd_brightness'],
                                capture_output=True, timeout=2)
        return max(2, min(16, int(result.stdout)))
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return 14  # Same fallback as the stock 1.1.2 GetDisplayBrightnessConfig.


def wake_display():
    # Native 1.1.2 API resets idle timers and wakes a sleeping/dimmed display.
    # Unlike ENABLE_DISPLAY it does not write an image into the framebuffer.
    result = subprocess.run(['curl', '--max-time', '2', '--unix-socket', '/tmp/api.sock',
                             '-fsS', '-X', 'POST', 'http://localhost/api/pager/display/wake'],
                            capture_output=True, timeout=3)
    if result.returncode or json.loads(result.stdout).get('success') is not True:
        raise RuntimeError('Could not keep the Pager display awake')


class KeepAwake:
    def __init__(self, wake=wake_display):
        self.wake = wake
        self.next = 0

    def tick(self, now):
        if now >= self.next:
            self.wake()
            self.next = now+5


class Backlight:
    def __init__(self, root='/sys/class/backlight/backlight_pwm', configured=configured_level):
        self.root = Path(root)
        self.maximum = min(16, int((self.root/'max_brightness').read_text()))
        if self.maximum < 2:
            raise RuntimeError('Unsupported backlight range')
        self.saved_level = int((self.root/'brightness').read_text())
        self.saved_power = int((self.root/'bl_power').read_text())
        self.level = max(2, min(self.maximum, configured()))
        self.restore_level = self.level
        self.touched = False

    def apply(self, level):
        level = max(2, min(self.maximum, int(level)))
        self.touched = True  # Partial writes must still be restored.
        (self.root/'bl_power').write_text('0\n')
        (self.root/'brightness').write_text(str(level)+'\n')
        actual = int((self.root/'brightness').read_text())
        if actual != level:
            raise RuntimeError('Backlight did not accept brightness')
        self.level = actual
        return actual

    def restore(self):
        if not self.touched: return
        # No periodic brightness writes: leave firmware thermal protection intact.
        # WakeScreen cleared firmware's asleep/dimmed flags. Return to its
        # configured awake level, not a stale pre-launch dim/sleep value.
        (self.root/'brightness').write_text(str(self.restore_level)+'\n')
        (self.root/'bl_power').write_text('0\n')
        self.touched = False

    def read(self):
        self.level = int((self.root/'brightness').read_text())
        return self.level

    def idle(self, level):
        self.touched = True
        (self.root/'bl_power').write_text('0\n')
        (self.root/'brightness').write_text(str(max(1, min(self.maximum, level)))+'\n')


class BrightnessMenu:
    def __init__(self, read, apply, timers=None, dim_after=0, sleep_after=0):
        self.read, self.apply = read, apply
        self.timers = timers
        self.dim_after, self.sleep_after = dim_after, sleep_after
        self.selected = 0
        self.visible = False
        self.level = 14
        self.error = False

    def toggle(self):
        self.visible = not self.visible
        if self.visible:
            try:
                self.level = self.read()
                self.error = False
            except (OSError, ValueError, RuntimeError): self.error = True

    def input(self, code, keys):
        if code in (keys.ENTER, keys.BACK):
            self.visible = False
        elif code in (keys.UP, keys.DOWN):
            self.selected = (self.selected + (1 if code == keys.DOWN else -1)) % 3
        elif code in (keys.RIGHT, keys.LEFT):
            delta = 1 if code == keys.RIGHT else -1
            try:
                if self.selected == 0:
                    self.level = self.apply(max(2, min(16, self.level+delta)))
                else:
                    values = [self.dim_after, self.sleep_after]
                    index = self.selected-1
                    choice = max(0, min(len(TIMEOUTS)-1, TIMEOUTS.index(values[index])+delta))
                    values[index] = TIMEOUTS[choice]
                    if self.timers is None: raise RuntimeError('Timers unavailable')
                    self.timers(*values)
                    self.dim_after, self.sleep_after = values
                self.error = False
            except (OSError, ValueError, RuntimeError): self.error = True
