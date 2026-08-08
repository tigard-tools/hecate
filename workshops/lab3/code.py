import board, usb_cdc
from hecate import Hecate, Trigger


class CodeStorage:
    def __init__(self, capacity=5, terminators=b"\r\n"):
        self._terminators = terminators
        self._capacity = capacity
        self._buf = bytearray()

    def write(self, data):
        # TODO
        # What should Hecate do when it sees a keypad entry?
        # This is before it knows whether it is valid or not
        pass

    def on_authorized(self, hecate, wire):
        # TODO
        # what should Hecate do when it sees an authorized code?
        hecate.mark_captured() # this just flips the light from green to blue, to indicate success
        pass

    def deploy(self, hecate, wire):
        # TODO: replay the most recently harvested code back onto the wire so a
        # button press re-deploys it. (Same wire.inject you used in Lab #2.)
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

storage = CodeStorage()
h.wires["from_keypad"].add_sink(storage)
h.wires["from_authorizer"].on_match(b"AUTHORIZED", callback=storage.on_authorized)
h.wires["from_keypad"].add_trigger(trigger=Trigger(button=board.BTN),
                                   callback=storage.deploy)

h.run()
