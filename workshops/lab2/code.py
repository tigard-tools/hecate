import board, usb_cdc
from hecate import Hecate, Trigger


class CodeReplay:
    def __init__(self, terminators=b"\r\n"):
        # We are setting up some internal state for CodeReplay here
        # terminators is a list of bytes that signal the beginning or end of a message
        self._terminators = terminators
        # buf is the buffer where we'll store the code we want to replay
        self._buf = bytearray()
        # and finally, last_code is where we'll store the code we've seen most recently
        self.last_code = None

    def write(self, data):
        # TODO
        # What should Hecate do when it sees a keypad entry?
        pass

    def replay(self, hecate, wire):
        if self.last_code:
            # When we call replay on a specific wire, we'll take our most recent code
            # and send it in UART along that wire
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
