import sys
import types

sys.modules.setdefault("busio", types.ModuleType("busio"))
sys.modules.setdefault("digitalio", types.ModuleType("digitalio"))

_results = []


class Capture:
    def __init__(self):
        self.out = bytearray()

    def write(self, data):
        self.out += bytes(data)
        return len(data)


def check(label, cond):
    _results.append(bool(cond))
    print(("PASS" if cond else "FAIL"), label)


def check_eq(label, got, expected):
    ok = got == expected
    _results.append(ok)
    print(("PASS" if ok else "FAIL"), label, "->", repr(got), "expect", repr(expected))


def summary():
    print()
    if all(_results):
        print("all {} tests passed".format(len(_results)))
    else:
        print("{}/{} FAILED".format(_results.count(False), len(_results)))
        sys.exit(1)
