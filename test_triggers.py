"""Trigger + Data.drop coverage for hecate (desktop CPython).

The CircuitPython-only modules busio/digitalio are stubbed before importing
hecate, so this exercises the real Trigger/Wire/Hecate/Data classes.

    python3 test_triggers.py
"""

from test_support import Capture, check, summary
import hecate  # noqa: E402


class FakeUART:
    def __init__(self):
        self._buf = bytearray()

    def feed(self, b):
        self._buf += b

    @property
    def in_waiting(self):
        return len(self._buf)

    def read(self, n):
        chunk = bytes(self._buf[:n])
        del self._buf[:n]
        return chunk

    def write(self, d):
        return len(d)


# --- Trigger condition semantics -------------------------------------------

check("match fires on a substring",
      hecate.Trigger(match=b"AB").update(b"xAB", 0.0) is True)
check("match does not fire without the pattern",
      hecate.Trigger(match=b"AB").update(b"xx", 0.0) is False)

tc = hecate.Trigger(match=b"A", count=2)
check("count=2 fires exactly twice then stops",
      (tc.update(b"A", 0.0), tc.update(b"A", 0.0), tc.update(b"A", 0.0))
      == (True, True, False))

tt = hecate.Trigger(timer=5)
check("timer holds off before elapsing", tt.update(b"", 0.0) is False)
check("timer fires once elapsed", tt.update(b"", 5.0) is True)


# --- Wire.add_trigger fires end-to-end through poll ------------------------

h = hecate.Hecate(monitor=Capture())
u = FakeUART()
w = h.wire("w", u)
hits = []
w.add_trigger(trigger=hecate.Trigger(match=b"GO"),
              callback=lambda he, wi: hits.append((he, wi)))
h._bind()
u.feed(b"..GO..")
h.poll()
check("wire trigger fires through poll with (hecate, wire)",
      len(hits) == 1 and hits[0][0] is h and hits[0][1] is w)


# --- Hecate.add_trigger (global) fires through poll ------------------------

h2 = hecate.Hecate(monitor=Capture())
ghits = []
h2.add_trigger(trigger=hecate.Trigger(timer=0), callback=lambda: ghits.append(1))
h2.poll()
check("global trigger fires through poll", len(ghits) >= 1)


# --- add_trigger registration (guards the Wire/Hecate merge) ---------------

h3 = hecate.Hecate(monitor=Capture())
trg = hecate.Trigger(match=b"Z")
ret = h3.add_trigger(trigger=trg, callback=lambda: None, count=3)
check("add_trigger returns the trigger, applies count, registers one entry",
      ret is trg and trg.count == 3
      and len(h3._triggers) == 1 and len(h3._triggers[0][1]) == 1)

wr = h3.wire("wr", FakeUART())
wtrg = wr.add_trigger(trigger=hecate.Trigger(match=b"Q"), callbacks=[lambda: None])
check("Wire.add_trigger registers on the wire",
      wtrg in [t for t, _ in wr._triggers] and len(wr._triggers) == 1)


# --- Data.drop fans out to wire, extra destinations, and the monitor -------

h4 = hecate.Hecate(monitor=Capture())
dest = Capture()
wire_cap = Capture()


class WireStub:
    name = "pay"

    def write(self, d):
        wire_cap.out += bytes(d)


hecate.Data(b"PAYLOAD", destinations=[dest]).drop(h4, WireStub())
check("Data.drop writes to wire, destinations, and monitor",
      bytes(wire_cap.out) == b"PAYLOAD" and bytes(dest.out) == b"PAYLOAD"
      and b"PAYLOAD" in bytes(h4.monitor._sink.out))

# Data.drop tags its payload synthetic (*) so injected bytes are distinguishable
# from real wire traffic in the monitor stream.
check("Data.drop tags the payload source synthetic",
      b"[pay" + hecate._Copy.SYNTHETIC_TAG.encode("utf-8") + b"] "
      in bytes(h4.monitor._sink.out))


# --- Wire.inject writes to the wire and tags monitor + log synthetic ---------

import os        # noqa: E402
import tempfile  # noqa: E402


class RecordIO:
    def __init__(self):
        self.out = bytearray()

    def write(self, d):
        self.out += bytes(d)
        return len(d)


logpath = tempfile.mktemp(suffix=".log")
h5 = hecate.Hecate(monitor=Capture(), logfile=logpath)
sink = RecordIO()
w5 = h5.wire("inj", FakeUART(), sink)
h5._bind()
w5.inject(b"CODE\r\n")

tag = hecate._Copy.SYNTHETIC_TAG.encode("utf-8")
check("Wire.inject writes the bytes onto the wire",
      bytes(sink.out) == b"CODE\r\n")
check("Wire.inject tags the source synthetic in the monitor",
      b"[inj" + tag + b"] " in bytes(h5.monitor._sink.out)
      and b"CODE\r\n" in bytes(h5.monitor._sink.out))

with open(logpath, "rb") as fh:
    logged = fh.read()
os.remove(logpath)
check("Wire.inject tags the source synthetic in the global log",
      b"[inj" + tag + b"] " in logged and b"CODE\r\n" in logged)


# --- mark_captured latches the status LED blue ------------------------------

class FakePixels:
    def __init__(self):
        self.color = None

    def fill(self, c):
        self.color = c


st = hecate._Status(True, FakePixels())
st.set_captured()
check("set_captured turns the status LED blue",
      st._pixels.color == hecate._STATUS_BLUE)

# activity still wins briefly, then it settles back to blue (not green) because
# capture is latched until reboot.
st.mark_activity(10.0)
st.update(10.0)
check("passthrough activity still shows yellow over a latched capture",
      st._pixels.color == hecate._STATUS_YELLOW)
st.update(11.0)
check("after activity, a captured device settles back to blue not green",
      st._pixels.color == hecate._STATUS_BLUE)

h6 = hecate.Hecate(monitor=Capture())
fp = FakePixels()
h6._status = hecate._Status(True, fp)
h6.mark_captured()
check("Hecate.mark_captured drives the status LED blue",
      fp.color == hecate._STATUS_BLUE)


summary()
