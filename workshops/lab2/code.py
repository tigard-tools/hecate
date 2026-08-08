import board, usb_cdc
from hecate import Hecate, Trigger


class CodeReplay:
    def __init__(self, terminators=b"\r\n"):
        self._terminators = terminators
        self._buf = bytearray()
        self.last_code = None

    def write(self, data):
        # TODO
        # What should Hecate do when it sees a keypad entry?
        pass

    def replay(self, hecate, wire):
        # TODO: replay the most recent code you've seen back onto the wire so a
        # button press re-sends it
        pass


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
