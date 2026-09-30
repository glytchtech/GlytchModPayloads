"""Native NetRider launcher with an independent firmware-UI recovery guardian."""
import argparse
import fcntl
import os
from pathlib import Path
import select
import signal
import stat
import sys
import time

from hardware import Framebuffer, Keys, identity, native_ui, process_state, signal_exact
from ui_handoff import UIHandoff
from data import Telemetry, Roads
from view import MapCanvas, MapView
from controls import ATap
from logging_control import WigleLogger
from brightness import Backlight, BrightnessMenu, KeepAwake
from navigation import Navigation
from display_power import DisplaySettings, DisplayPower, IdleTimer

ROOT = Path(__file__).resolve().parent


def lock_display():
    handles = []
    # Also respect PagerScribe's existing lock so the two apps cannot overlap.
    for path in ('/tmp/netrider-display.lock', '/tmp/pagerscribe-display.lock'):
        fd = os.open(path, os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW, 0o600)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_uid != os.geteuid() or info.st_nlink != 1:
            os.close(fd)
            raise RuntimeError('Unsafe display lock')
        try: fcntl.flock(fd, fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:
            os.close(fd)
            raise RuntimeError('NetRider or PagerScribe already owns the display')
        handles.append(fd)
    return handles


def guardian(read_fd, reply_fd, owner, settings):
    os.setsid()
    for sig in (signal.SIGHUP, signal.SIGINT, signal.SIGTERM): signal.signal(sig, signal.SIG_IGN)
    ui = UIHandoff()
    backlight = None
    awake = None
    power = None
    def restore_light():
        try:
            if backlight: backlight.restore()
        except OSError as error:
            print('NetRider backlight restore: '+str(error), flush=True)
    buffer = b''
    last = time.monotonic()
    try:
        while True:
            ready, _, _ = select.select([read_fd], [], [], .5)
            if ready:
                packet = os.read(read_fd, 4096)
                if not packet: break
                buffer += packet
                while b'\n' in buffer:
                    command, buffer = buffer.split(b'\n', 1)
                    if command == b'TAKE':
                        backlight = Backlight()
                        ui.takeover()
                        awake = KeepAwake()
                        awake.tick(time.monotonic())
                        backlight.apply(backlight.level)
                        power = DisplayPower(backlight, settings, time.monotonic())
                        os.write(reply_fd, b'READY\n')
                    elif command.startswith(b'ACT '):
                        power.activity(float(command.split()[1]))
                    elif command.startswith(b'TIMERS '):
                        try:
                            _, dim, sleep = command.split()
                            power.set_timers(int(dim), int(sleep), time.monotonic())
                            os.write(reply_fd, b'TIMERS OK\n')
                        except (OSError, ValueError, RuntimeError):
                            os.write(reply_fd, b'TIMERS ERROR\n')
                    elif command == b'LIGHT?' or command.startswith(b'LIGHT '):
                        try:
                            if command != b'LIGHT?':
                                power.set_level(int(command.split()[1]), time.monotonic())
                            os.write(reply_fd, ('LIGHT %d\n' % power.level).encode())
                        except (OSError, ValueError, RuntimeError):
                            os.write(reply_fd, b'LIGHT ERROR\n')
                    elif command == b'RELEASE':
                        restore_light()
                        ui.release()
                        print('NetRider UI_RELEASE completed.', flush=True)
                        os.write(reply_fd, b'RELEASED\n')
                        return 0
                    last = time.monotonic()
            # A cold vector-tile redraw can take several seconds on the MIPS CPU.
            if time.monotonic()-last > 20:
                print('NetRider renderer heartbeat timed out.', flush=True)
                break
            if awake: awake.tick(time.monotonic())
            if power: power.tick(time.monotonic())
    except Exception as error:
        print('NetRider guardian: '+str(error), flush=True)
    # Stop every renderer thread before returning display/input to firmware.
    signal_exact(owner, signal.SIGKILL)
    deadline = time.monotonic()+2
    while identity(owner[0]) == owner and process_state(owner[0]) not in ('Z', None) and time.monotonic()<deadline:
        time.sleep(.05)
    if identity(owner[0]) == owner and process_state(owner[0]) not in ('Z', None):
        print('Renderer did not stop; UI release deferred.', flush=True)
        return 1
    restore_light()
    try:
        ui.release()
        print('NetRider UI_RELEASE completed (recovery).', flush=True)
        return 0
    except Exception as error:
        print('NetRider UI_RELEASE failed: '+str(error), flush=True)
        return 1


def request(write_fd, read_fd, command, expected=None):
    os.write(write_fd, command+b'\n')
    ready, _, _ = select.select([read_fd], [], [], 10)
    response = os.read(read_fd, 64).strip() if ready else b''
    if not response or (expected is not None and response != expected):
        raise RuntimeError('Display guardian did not acknowledge '+command.decode())
    return response


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--check', action='store_true', help='Read-only display and firmware preflight')
    parser.add_argument('--duration', type=float, default=0, help='Return to firmware after N seconds')
    parser.add_argument('--offline', action='store_true', help='Use cached roads only; no map network requests')
    parser.add_argument('--snapshot', help='Write one raw rendered map frame for display verification')
    args = parser.parse_args()
    os.umask(0o077)
    version = Path('/etc/pineapplepager/version').read_text().splitlines()[0]
    parts = tuple(int(v) for v in version.split('.')[:3])
    if parts < (1,1,2): raise RuntimeError('Pager firmware 1.1.2 or later required')
    ui = UIHandoff(); ui.preflight()
    native = native_ui()
    key_path = Keys.discover()
    fb = Framebuffer()
    canvas = MapCanvas(str(ROOT/'assets'), physical_layout=True)
    if args.check:
        fb.close()
        print('NetRider native preflight OK: firmware '+version+', 480x222 RGB565, GPIO keys, UI commands and assets.')
        return
    locks = lock_display()
    settings = DisplaySettings(ROOT.parent/'display-settings.json')
    stop = False
    def halt(*_):
        nonlocal stop
        stop = True
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP): signal.signal(sig, halt)
    read_fd, write_fd = os.pipe()
    reply_read, reply_write = os.pipe()
    owner = identity(os.getpid())
    child = os.fork()
    if child == 0:
        os.close(write_fd); os.close(reply_read); fb.close()
        os._exit(guardian(read_fd, reply_write, owner, settings))
    os.close(read_fd); os.close(reply_write)
    keys = None
    telemetry, roads = Telemetry(), Roads(ROOT.parent/'cache/roads')
    logger, taps, power_taps = WigleLogger(), ATap(), ATap()
    idle = IdleTimer(settings.dim_after, settings.sleep_after, time.monotonic())
    def light(level=None):
        command = b'LIGHT?' if level is None else ('LIGHT %d' % level).encode()
        answer = request(write_fd, reply_read, command)
        if not answer.startswith(b'LIGHT '): raise RuntimeError('Invalid backlight response')
        return int(answer.split()[1])
    def timers(dim, sleep):
        request(write_fd, reply_read, ('TIMERS %d %d' % (dim, sleep)).encode(), b'TIMERS OK')
        idle.dim_after, idle.sleep_after = dim, sleep
        idle.activity(time.monotonic())
    brightness = BrightnessMenu(light, light, timers, settings.dim_after, settings.sleep_after)
    brightness_background = None
    navigation = None
    try:
        request(write_fd, reply_read, b'TAKE', b'READY')
        if stop: return
        keys = Keys(key_path)
        telemetry.start()
        logger.start()
        roads.offline = args.offline
        view = MapView()
        navigation = Navigation(canvas, roads=roads)
        start = last_beat = last_frame = time.monotonic()
        idle.activity(start)
        os.write(write_fd, ('ACT %.6f\n' % start).encode())
        sleep_blanked = False
        snapshot_done = False
        displayed_result = None
        print('NetRider native active; renderer PID %d, guardian PID %d.' % (os.getpid(), child), flush=True)
        while not stop:
            now = time.monotonic()
            if args.duration and now-start >= args.duration: break
            if now-last_beat > .25:
                os.write(write_fd, b'.\n'); last_beat = now
                if identity(native[0]) != native or process_state(native[0]) in ('T','t','Z',None):
                    raise RuntimeError('Native Pager UI restarted or stopped')
            pressed = keys.poll()
            if pressed:
                wake_only = idle.state(now) == 'SLEEP'
                idle.activity(now)
                os.write(write_fd, ('ACT %.6f\n' % now).encode())
                if wake_only:
                    # Consume the entire wake gesture, including queued double
                    # taps, so it cannot exit, move the map, or start logging.
                    pressed = []
                    taps.reset()
                    power_taps.reset()
                    last_frame = 0
            for key in pressed:
                pressed_at = getattr(key, 'when', now)
                if key == Keys.POWER:
                    if power_taps.press(pressed_at) == 'start':
                        taps.reset()
                        brightness.toggle()
                        if brightness.visible: brightness_background = canvas.pixels[:]
                        last_frame = 0
                elif brightness.visible:
                    brightness.input(key, Keys)
                    taps.reset()
                    last_frame = 0
                elif key == Keys.BACK: stop = True
                elif now-start >= 3.2:
                    if key == Keys.ENTER:
                        action = taps.press(pressed_at)
                        if action == 'start': logger.request_start()
                        elif action == 'mode': view.input(Keys.ENTER, Keys)
                    else:
                        view.input(key, Keys)
                        last_frame = 0
            # Expire single taps only after processing queued, timestamped input.
            if not brightness.visible and taps.tick(now) == 'mode':
                view.input(Keys.ENTER, Keys)
                last_frame = 0
            power_taps.tick(now)  # Single Power is intentionally inert during takeover.
            if stop: break
            if idle.state(now) == 'SLEEP':
                if not sleep_blanked:
                    canvas.clear()
                    fb.write(canvas.physical())
                    sleep_blanked = True
                time.sleep(.025)
                continue
            if sleep_blanked:
                sleep_blanked = False
                last_frame = 0
            if not brightness.visible and navigation.result is not displayed_result:
                displayed_result = navigation.result
                last_frame = 0
            # Gestures and completed maps invalidate immediately; idle frames
            # only animate the position marker, leaving CPU for maps/telemetry.
            interval = .12 if now-start < 3.2 else .4
            if now-last_frame >= interval:
                if brightness.visible:
                    # Do not make brightness input wait for a cold tile redraw.
                    canvas.pixels = brightness_background[:]
                    canvas.brightness_menu(brightness.level, brightness.error, brightness.selected,
                                           brightness.dim_after, brightness.sleep_after)
                elif now-start < 3.2: canvas.boot(now-start)
                else: navigation.draw(canvas, view, dict(telemetry.snapshot, logging=logger.status), roads, now)
                raw = canvas.physical()
                fb.write(raw)
                if args.snapshot and not snapshot_done and now-start > 5:
                    Path(args.snapshot).write_bytes(raw)
                    snapshot_done = True
                last_frame = now
            time.sleep(.025)
    finally:
        telemetry.stop.set(); roads.stop.set()
        if keys: keys.close()
        fb.close()
        if navigation: navigation.close()
        # No framebuffer writes or EVIOCGRAB after this point.
        try: request(write_fd, reply_read, b'RELEASE', b'RELEASED')
        finally:
            os.close(write_fd); os.close(reply_read)
        os.waitpid(child, 0)
        logger.close()
        for fd in locks: os.close(fd)


if __name__ == '__main__':
    try: main()
    except Exception as error:
        print('NetRider native: '+str(error), file=sys.stderr, flush=True)
        sys.exit(1)
