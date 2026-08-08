# Welcome to Hecate: A Trivial UART tool!
# Hecate is a CircuitPython framework for working with UART datastreams.
# Details are available at https://tigard-tools.org/hecate

# This file is the code.py file that gets run when your hardware powers up.
# It's also the instruction guide for the Workshop on using Hecate.

# Read through this file, and be sure to follow the instructions

# Hecate uses a few libraries. We'll import them here, then import Hecate itself
import board, usb_cdc
from hecate import Hecate, Data, Trigger

# Here, we create the Hecate object that we'll interact with throughout the workshop
h = Hecate(
  status_led=True,
  buffer=128, # this holds temporary uart data until we're ready to process it
  monitor=usb_cdc.data, # this gives us a second usb-serial port we can spit out monitor data to
  uarts=[(board.TX, board.RX), (board.TX1, board.RX1)], # tells Hecate what hardware peripherals we have
  logfile="hecate.log", # Hecate will log intercepted traffic here in standalone mode
  errorfile="errors.log" # If Hecate runs into errors in standalone mode, it will log them here
)


# -----
# Example: Full Duplex Monitoring
# Let's set up Hecate in the middle of the UART link.
# We're going to tell Hecate to pass through everything from RX to TX1, and everything from RX1 to TX.
# -----

h.wire("from_pin", board.RX) # with just a pogo pin probe
#h.wire("from_authorizer", board.RX, board.TX1) # authorizer listens to keypad
#h.wire("from_keypad", board.RX1, board.TX) # keypad talks to authorizer

# This is the command that sets Hecate off on its task. Don't remove it or else Hecate won't run.

h.run()
