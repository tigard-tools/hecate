"""Pattern-matching tests for hecate.Wire.

Runs on a desktop CPython (no board needed): the CircuitPython-only modules
`busio`/`digitalio` are stubbed before importing hecate. Exercises the real
Wire matcher (on_match / eat / _step / _fire / _flush_safe), not a copy.

    python3 test_pattern_match.py
"""

from test_support import Capture, check_eq, summary
import hecate  # noqa: E402


def _wire():
    w = hecate.Wire(hecate=None, name="w", source=None, sinks=[])
    cap = Capture()
    w._writers = [cap]
    return w, cap


def _run(register, stream):
    """Register handlers on a fresh wire, feed the stream, flush, return bytes."""
    w, cap = _wire()
    fires = register(w)
    w._process(bytes(stream))
    w._flush_safe()
    return bytes(cap.out), fires




# --- documented behaviours --------------------------------------------------

out, _ = _run(lambda w: w.on_match(b"FOO", replace=b"BAR"), b"xxFOOyy")
check_eq("substitute FOO->BAR", out, b"xxBARyy")

out, _ = _run(lambda w: w.eat(b"PING"), b"aPINGb")
check_eq("eat drops match", out, b"ab")

out, _ = _run(lambda w: w.on_match(b"PING"), b"zPINGz")
check_eq("passthrough leaves bytes", out, b"zPINGz")


def _reg_cb(w):
    hits = []
    w.on_match(b"PING", callback=lambda: hits.append(1))
    return hits


out, hits = _run(_reg_cb, b"zPINGz")
check_eq("callback fires once", (out, len(hits)), (b"zPINGz", 1))


def _reg_oneshot(w):
    hits = []
    w.on_match(b"AB", callback=lambda: hits.append(1), one_shot=True)
    return hits


out, hits = _run(_reg_oneshot, b"ABAB")
check_eq("one_shot fires only first time", len(hits), 1)

# --- self-overlapping patterns: the naive matcher missed these --------------

out, _ = _run(lambda w: w.on_match(b"AAB"), b"AAAB")
check_eq("AAB matches inside AAAB", out, b"AAAB")

out, _ = _run(lambda w: w.on_match(b"AAAB"), b"AAAAB")
check_eq("AAAB matches inside AAAAB", out, b"AAAAB")

out, _ = _run(lambda w: w.on_match(b"ABABC"), b"ABABABC")
check_eq("ABABC matches inside ABABABC", out, b"ABABABC")

# a self-overlapping eat must drop exactly the match, keep the overlap prefix
out, _ = _run(lambda w: w.eat(b"AAB"), b"AAAB")
check_eq("eat AAB from AAAB keeps leading A", out, b"A")

# --- validation -------------------------------------------------------------

try:
    _wire()[0].on_match(b"")
    check_eq("empty pattern rejected", "no error", "ValueError")
except ValueError:
    check_eq("empty pattern rejected", "ValueError", "ValueError")

# --- failure table spot checks ----------------------------------------------

check_eq("lps AAB", hecate._kmp_table(b"AAB"), [0, 1, 0])
check_eq("lps ABABC", hecate._kmp_table(b"ABABC"), [0, 0, 1, 2, 0])
check_eq("lps no self-overlap is all zeros", hecate._kmp_table(b"PING"), [0, 0, 0, 0])


summary()
