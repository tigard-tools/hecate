import board, usb_cdc
from hecate import Hecate, Trigger


class CodeReplay:
    def __init__(self, terminators=b"\r\n"):
        self._terminators = terminators
        self._buf = bytearray()
        self.last_code = None

    def write(self, data):
        for byte in data:
            # step through each byte in the data we received
            self._buf.append(byte)
            if byte in self._terminators:
                # if the byte is a line terminator, it's a new message
                frame = bytes(self._buf)
                self._buf = bytearray()
                if any(b not in self._terminators for b in frame):
                    # if we got real data, then we save it to replay
                    self.last_code = frame

    def replay(self, hecate, wire):
        if self.last_code:
            wire.inject(self.last_code)


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

replay = CodeReplay()
h.wires["from_keypad"].add_sink(replay)
h.wires["from_keypad"].add_trigger(trigger=Trigger(button=board.BTN),
                                   callback=replay.replay)

h.run()
