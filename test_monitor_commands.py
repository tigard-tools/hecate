"""Tests for the monitor's tagged headers and the status/help/exit commands.

Runs on desktop CPython (no board): the CircuitPython-only modules busio and
digitalio are stubbed before importing hecate, so we exercise the real _Monitor
and Hecate command path, not a copy.

    python3 test_monitor_commands.py
"""

import re
import sys
import types

from test_support import Capture, check, summary

import hecate  # noqa: E402


class FakeCDC:
    """Stand-in for usb_cdc.data: a bidirectional byte port."""

    def __init__(self, connected=True):
        self.out = bytearray()
        self._in = bytearray()
        self.connected = connected

    def write(self, data):
        self.out += bytes(data)
        return len(data)

    @property
    def in_waiting(self):
        return len(self._in)

    def read(self, n):
        chunk = bytes(self._in[:n])
        del self._in[:n]
        return chunk

    def feed(self, text):
        self._in += text.encode("utf-8") if isinstance(text, str) else text

    def take(self):
        s = bytes(self.out)
        self.out = bytearray()
        return s


HEADER = re.compile(rb"^\d+\.\d{3} \[[^\]]+\] ")


# --- headers ---------------------------------------------------------------

cdc = FakeCDC()
mon = hecate._Monitor(cdc)
mon.write(b"hello\r\n", "from_keypad")
out = cdc.take()
check("line carries a <timestamp> [name] header", HEADER.match(out) is not None)
check("header names the source wire", b"[from_keypad] hello\r\n" in out)

# a same-source continuation that did not end in newline keeps one header
cdc = FakeCDC()
mon = hecate._Monitor(cdc)
mon.write(b"ab", "w")
mon.write(b"cd\n", "w")
out = cdc.take()
check("mid-line same-source continuation is not re-headered",
      out.count(b"[w] ") == 1 and out.endswith(b"abcd\n"))

# a mid-line switch to a new source breaks the line and re-headers
cdc = FakeCDC()
mon = hecate._Monitor(cdc)
mon.write(b"ab", "w1")       # no trailing newline
mon.write(b"cd\n", "w2")
out = cdc.take()
check("source switch mid-line inserts a break + new header",
      b"[w1] ab" in out and b"[w2] cd" in out and out.count(b"\n") == 2)

# each new line gets its own header
cdc = FakeCDC()
mon = hecate._Monitor(cdc)
mon.write(b"one\ntwo\n", "w")
out = cdc.take()
check("every line is headered", out.count(b"[w] ") == 2)

# headers can be disabled for a raw byte view
cdc = FakeCDC()
mon = hecate._Monitor(cdc, headers=False)
mon.write(b"raw\n", "w")
check("headers=False writes raw bytes", cdc.take() == b"raw\n")


# --- command dispatch ------------------------------------------------------

def new_hecate(connected=True):
    cdc = FakeCDC(connected=connected)
    h = hecate.Hecate(monitor=cdc)
    return h, cdc


h, cdc = new_hecate()
cdc.feed("help\r\n")
h._poll_commands(0.0)
out = cdc.take()
check("help lists status/help/exit",
      b"status" in out and b"help" in out and b"exit" in out)

# status with no faults
h, cdc = new_hecate()
cdc.feed("status\n")
h._poll_commands(0.0)
check("status reports running normally when clean",
      b"status: running normally" in cdc.take())

# status surfaces recorded faults
h, cdc = new_hecate()
h._fault("wire 'x': source pin has no UART (wiring fault)")
cdc.take()  # discard the live fault announcement
cdc.feed("status\n")
h._poll_commands(0.0)
out = cdc.take()
check("status lists recorded faults",
      b"issue(s)" in out and b"source pin has no UART" in out)

# unknown command
h, cdc = new_hecate()
cdc.feed("frobnicate\n")
h._poll_commands(0.0)
check("unknown command is reported", b"unknown command 'frobnicate'" in cdc.take())

# case-insensitive + whitespace tolerant
h, cdc = new_hecate()
cdc.feed("  HELP  \n")
h._poll_commands(0.0)
check("commands are case/space insensitive", b"commands:" in cdc.take())

# backspace editing: "helXbp" with a backspace before 'p' -> not "help"; build "help"
h, cdc = new_hecate()
cdc.feed("helx\x08p\n")   # type helx, backspace the x, type p -> help
h._poll_commands(0.0)
check("backspace edits the command buffer", b"commands:" in cdc.take())

# CRLF line ending fires exactly once (no phantom blank-line command)
h, cdc = new_hecate()
cdc.feed("status\r\n")
h._poll_commands(0.0)
check("CRLF fires the command once",
      cdc.take().count(b"status: running normally") == 1)


# --- exit / mute / reconnect ----------------------------------------------

h, cdc = new_hecate()
cdc.feed("exit\n")
h._poll_commands(0.0)
out = cdc.take()
check("exit prints detach instructions", b"picocom" in out and b"screen" in out)
check("exit mutes the monitor", h.monitor._muted is True)

# muted: ordinary passthrough output is suppressed
h.monitor.write(b"passthrough\n", "wire")
check("muted monitor drops passthrough output", cdc.take() == b"")

# muted: command replies still get through (forced), so exit is recoverable
cdc.feed("status\n")
h._poll_commands(0.0)
check("commands still answer while muted",
      b"status: running normally" in cdc.take())

# reconnecting the host un-mutes
cdc.connected = False
h._check_monitor_connection()
cdc.connected = True
h._check_monitor_connection()
check("host reconnect un-mutes the monitor", h.monitor._muted is False)
h.monitor.write(b"back\n", "wire")
check("output resumes after reconnect", b"back" in cdc.take())


# --- write-only monitor is safe -------------------------------------------

h = hecate.Hecate(monitor=Capture())
h._poll_commands(0.0)  # must not raise despite no read/in_waiting
check("write-only monitor: command polling is a no-op", True)


# --- startup clears stale monitor buffers (fragments across a soft-reload) --

class ResettableCDC(FakeCDC):
    def __init__(self):
        super().__init__()
        self.reset_in = 0
        self.reset_out = 0

    def reset_input_buffer(self):
        self.reset_in += 1

    def reset_output_buffer(self):
        self.reset_out += 1


rcdc = ResettableCDC()
hecate.Hecate(monitor=rcdc)
check("startup resets the monitor input/output buffers",
      rcdc.reset_in == 1 and rcdc.reset_out == 1)


# --- error log (faults persisted for a monitor-less standalone device) -----

import os          # noqa: E402
import tempfile    # noqa: E402

errpath = os.path.join(tempfile.mkdtemp(), "errors.log")

# no monitor at all: a standalone device still records faults to the file
h = hecate.Hecate(monitor=None, errorfile=errpath)
h._fault("wire 'from_keypad': source pin has no UART (wiring fault)")
h._fault("cannot open log file 'keypad.log' (filesystem read-only?)")
with open(errpath, "rb") as fh:
    body = fh.read()
check("errorfile captures faults with no monitor attached",
      b"source pin has no UART" in body
      and b"cannot open log file 'keypad.log'" in body)
check("errorfile stamps each fault with a monotonic time",
      re.search(rb"^\d+\.\d{3} wire 'from_keypad'", body, re.M) is not None)
check("errorfile marks the session boundary", b"--- hecate session ---" in body)

# a repeated fault is not written twice within a session
before = open(errpath, "rb").read()
h._fault("wire 'from_keypad': source pin has no UART (wiring fault)")
check("repeated fault is not re-logged in the same session",
      open(errpath, "rb").read() == before)

# a fresh session appends (append mode preserves history across reboots)
h2 = hecate.Hecate(monitor=None, errorfile=errpath)
h2._fault("runtime error in poll (boom)")
body2 = open(errpath, "rb").read()
check("a new session appends rather than truncating",
      b"source pin has no UART" in body2 and b"runtime error in poll (boom)" in body2
      and body2.count(b"--- hecate session ---") == 2)

# an unopenable errorfile is silently tolerated (no crash, faults still work)
h3 = hecate.Hecate(monitor=Capture(),
                   errorfile="/nonexistent-dir-xyz/errors.log")
h3._fault("some fault")
check("unopenable errorfile degrades gracefully",
      "some fault" in h3._faults)

# the error log is opened only per fault (open-append-close), never held open
open_calls = {"count": 0}
_builtin_open = open


def _counting_open(path, *a, **k):
    if path == errpath:
        open_calls["count"] += 1
    return _builtin_open(path, *a, **k)


import builtins  # noqa: E402

builtins.open = _counting_open
try:
    h4 = hecate.Hecate(monitor=None, errorfile=errpath)
    check("errorfile is not opened at construction", open_calls["count"] == 0)
    h4._fault("first fault")
    h4._fault("second fault")
    check("each fault opens and closes the errorfile once",
          open_calls["count"] == 2)
finally:
    builtins.open = _builtin_open


# --- read-only log + standalone detection (the early-boot false fault) -----

# Drive _is_standalone() by faking supervisor.runtime.usb_connected.
class _Runtime:
    usb_connected = True


fake_supervisor = types.ModuleType("supervisor")
fake_supervisor.runtime = _Runtime()
sys.modules["supervisor"] = fake_supervisor

BAD_LOG = "/nonexistent-dir-xyz/hecate.log"   # open('ab') raises OSError

# A log that can't be opened must NOT fault during __init__ (usb_connected is
# unreliable that early); the decision is deferred to the poll loop.
_Runtime.usb_connected = False                # early boot: host not enumerated yet
h = hecate.Hecate(monitor=FakeCDC(), logfile=BAD_LOG)
check("read-only log does not fault at construction",
      h._faults == [] and h._log_ro_paths == [BAD_LOG])

# The user's bug: usb_connected reads False at boot, then the host enumerates.
h._resolve_log_faults(1.0)                     # still early, still hostless
check("deferred while enumeration is still pending", h._faults == [])
_Runtime.usb_connected = True                  # host shows up
h._resolve_log_faults(2.0)
check("USB host appearing clears the log fault silently",
      h._faults == [] and h._log_ro_paths == [])

# Steady-state USB (the reported case): plugged in, host present -> never faults.
_Runtime.usb_connected = True
h = hecate.Hecate(monitor=FakeCDC(), logfile=BAD_LOG)
h._resolve_log_faults(10.0)
check("plugged-in board never reports a read-only-log fault", h._faults == [])

# Genuinely standalone: no host through the whole grace window -> real fault.
_Runtime.usb_connected = False
h = hecate.Hecate(monitor=None, logfile=BAD_LOG)
h._resolve_log_faults(1.0)                     # before grace: hold off
check("standalone holds off until the grace window elapses", h._faults == [])
h._resolve_log_faults(hecate._STANDALONE_GRACE + 0.1)
check("standalone past grace does fault (red LED is the only signal)",
      any("cannot open log file" in f for f in h._faults))

del sys.modules["supervisor"]


summary()
