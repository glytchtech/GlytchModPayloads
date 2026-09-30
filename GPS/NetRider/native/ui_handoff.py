"""Firmware 1.1.2+ display/input handoff; no native-UI process signals.

Only the independent guardian executes these calls. Hak5's wrappers can
partially succeed and have no transport timeout, so an attempted takeover
always creates a release obligation, including on nonzero exit or timeout.
"""
import os
from pathlib import Path
import signal
import stat
import subprocess
import time


class UIHandoffError(RuntimeError):
    pass


class UIHandoff:
    COMMAND_TIMEOUT = 2.0
    RELEASE_ATTEMPTS = 3
    SETTLE_SECONDS = .25  # Queued API events; this is not a state-query barrier.

    def __init__(self, command_dir="/usr/bin", socket_path="/tmp/api.sock"):
        self.takeover_command = str(Path(command_dir)/"UI_TAKEOVER")
        self.release_command = str(Path(command_dir)/"UI_RELEASE")
        self.socket_path = Path(socket_path)
        self.attempted = False
        self.released = False

    def preflight(self):
        # Never execute --help: these wrappers ignore arguments and act anyway.
        for command in (self.takeover_command, self.release_command):
            if not Path(command).is_file() or not os.access(command, os.X_OK):
                raise UIHandoffError("Pager firmware 1.1.2+ UI_TAKEOVER/UI_RELEASE required")
        try:
            active_socket = stat.S_ISSOCK(self.socket_path.stat().st_mode)
        except OSError:
            active_socket = False
        if not active_socket:
            raise UIHandoffError("Pineapple UI API socket unavailable")

    def _run(self, command):
        # A new helper group contains bash/curl/jq. close_fds prevents it from
        # keeping the watchdog pipes or display/audio locks open.
        process = subprocess.Popen([command], stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                   start_new_session=True, close_fds=True)
        try:
            status = process.wait(timeout=self.COMMAND_TIMEOUT)
        except BaseException:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            process.wait()
            raise
        if status:
            raise UIHandoffError(Path(command).name + " failed; handoff may be partial")

    def takeover(self):
        if self.attempted:
            raise UIHandoffError("Repeated takeover refused")
        self.attempted = True  # Before exec: timeout/failure may still change UI.
        self._run(self.takeover_command)
        time.sleep(self.SETTLE_SECONDS)

    def release(self):
        if not self.attempted or self.released:
            return
        for attempt in range(self.RELEASE_ATTEMPTS):
            try:
                self._run(self.release_command)
                time.sleep(self.SETTLE_SECONDS)
                self.released = True  # Before guardian acknowledgment can fail.
                return
            except (OSError, subprocess.TimeoutExpired, UIHandoffError):
                if attempt+1 < self.RELEASE_ATTEMPTS:
                    time.sleep(.15)
        raise UIHandoffError("UI_RELEASE failed; manual recovery required")
