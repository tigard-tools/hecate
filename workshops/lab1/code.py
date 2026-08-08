import board, usb_cdc
from hecate import Hecate


# -----
# Lab #1: Full-Duplex Monitoring
# Before we change anything, let's make sure Hecate is sitting transparently
# in the middle of the link and everything still works like normal.
#
# The two wires below pass every byte straight through: the authorizer hears
# the keypad, and the keypad hears the authorizer, exactly as if Hecate
# weren't there.
#
# You shouldn't need to modify this file at all to get things working.
# This lab is all about making sure that you can
# -----

h = Hecate(
    status_led=True,
    buffer=128,
    monitor=usb_cdc.data,
    uarts=[(board.TX, board.RX), (board.TX1, board.RX1)],
    logfile="hecate.log",
    errorfile="errors.log",
)

h.wire("from_authorizer", board.RX, board.TX1)  # authorizer listens to keypad
h.wire("from_keypad", board.RX1, board.TX)      # keypad talks to authorizer

# -----
# 1. Interact with your target system. Does it work normally, like it did
#    before? If not, check your wiring and ask an assistant for help.
# 2. Connect to your /dev/ttyACM1 monitor and interact with the system again.
#    What do you see flowing across the wire?
#      Hint: Use screen /dev/ttyACM1 or similar
# 3. How does this keypad work? What happens when you press a key? When you
#    hit ENT? What response comes back?
#      Hint: Try entering 1337
# -----

h.run()
