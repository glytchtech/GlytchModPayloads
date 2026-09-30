"""Explicit WiGLE start gesture; firmware-confirmed status, no radio changes."""
import json
import os
import signal
import subprocess
import threading


def logging_active():
    # Verified on Pager 1.1.2: this boolean is the native WiGLE logging state.
    result = subprocess.run(['curl', '--max-time', '2', '--unix-socket',
                             '/tmp/api.sock', '-fsS',
                             'http://localhost/api/pineap/get_config'],
                            capture_output=True, timeout=3)
    if result.returncode:
        raise RuntimeError('Logging state unavailable')
    value = json.loads(result.stdout).get('logwigle')
    if type(value) is not bool:
        raise ValueError('Unknown logging state')
    return value


def start_logging():
    # The firmware wrapper has no timeout; reap its entire helper group.
    with subprocess.Popen(['/usr/bin/WIGLE_START'], stdin=subprocess.DEVNULL,
                          stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                          start_new_session=True, close_fds=True) as process:
        try:
            if process.wait(timeout=4):
                raise RuntimeError('WIGLE_START failed')
        except BaseException:
            try: os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError: pass
            process.wait()
            raise


class WigleLogger:
    def __init__(self, query=logging_active, start=start_logging):
        self.query, self.command = query, start
        self.status = 'CHECKING'
        self.stop = threading.Event()
        self.request = threading.Event()
        self.thread = None
        self.failed = False

    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def request_start(self):
        self.request.set()

    def update(self):
        requested = self.request.is_set()
        if requested:
            self.request.clear()
            self.failed = False
        try:
            active = self.query()
            # No restart/rotation when logging is already enabled. Fail closed
            # if status cannot be read, rather than blindly creating a log.
            if requested and not active and not self.stop.is_set():
                self.status = 'STARTING'
                self.command()
                if self.stop.is_set(): return
                active = self.query()
                if not active: self.failed = True
            self.status = 'ACTIVE' if active else 'ERROR' if self.failed else 'OFF'
        except (OSError, ValueError, RuntimeError, subprocess.TimeoutExpired):
            self.failed = self.failed or requested
            self.status = 'ERROR' if self.failed else 'UNKNOWN'

    def run(self):
        while not self.stop.is_set():
            self.update()
            # Event wakes quickly for A; polling also detects external stops.
            self.request.wait(1)

    def close(self):
        self.stop.set()
        self.request.set()
        if self.thread: self.thread.join(5)

