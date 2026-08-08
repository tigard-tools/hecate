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
# LAB #1: Full Duplex Monitoring
# Let's set up Hecate in the middle of the UART link.
# We're going to tell Hecate to pass through everything from RX to TX1, and everything from RX1 to TX.
# -----

h.wire("from_authorizer", board.RX, board.TX1) # authorizer listens to keypad
h.wire("from_keypad", board.RX1, board.TX) # keypad talks to authorizer

# -----
# 1. Interact with your target system. Does it work normally, like it did before? If not, wiring, then ask for some help.
# 2. Connect to your /dev/ttyACM1 monitor, and interact with the system. What do you see?
# 3. How does this protocol work? What happens when you press a button? What happens when you hit ENT? What is the response you get?
# -----

# -----
# Lab #2: Standalone Mode (or Implant Mode)
# We still have to attache a computer to see what's happening.
# Let's use Hecate in standalone mode. We'll set it up to log UART data to a file that we can later retrieve.

# In order to log to a file, unplug the Xiaomao and plug its USB-C cable into the keypad instead
# Xiaomao will get its power from the keypad parasitically and switch to logging instead of serial monitor.
# Once you're logging, raise your hand and ask for one of the assistants to type in the secret pin
# -----

# -----
# Lab #3: Sending a Payload
# Once someone has type the secret pin, you can switch the USB-C cable back from the keypad to Xiaomao.
# We know the secret pin to drop in order to unlock the system. Lets use Hecate to do it!
# The following code will drop a message onto a TX pin after a certain amount of time (3 seconds by default)
# Uncomment the following lines of code and save
# -----

#data = Data(b"SECRET PIN HERE")
#timer = Trigger(timer=3, count=1)
#h.wires["from_keypad"].add_trigger(trigger=timer, callbacks=[data.drop])

# -----
# 1. Enter the secret pin above (where it says SECRET PIN HERE)
# 2. Interact with your target. Does it work as expected?
# 3. Wait for the timeout. What happens?

# You can also trigger this payload autonomously in standalone mode.
# Unplug the Xiaomao from the USB and plug the keypad in like in Lab #2.
# Does your payload still trigger?
# -----

# -----
# (Bonus) Lab #4: More Complex Callbacks
# Hecate can use whatever other input devices that are normally available on the board.
# Xiaomao has a button, available as board.BTN. Rather than fire on a timer,
# we can fire a payload on a button press instead.
# Uncomment the following lines of code and save.
# -----

#data = Data(b"SECRET PIN HERE")
#button = Trigger(button=board.BTN)
#h.wires["from_keypad"].add_trigger(trigger=button, callbacks=[data.drop])

# -----
# 1. Enter the secret pin above (where it says SECRET PIN HERE)
# 2. Interact with your target, then press the button on the Xiaomao. Does the payload drop?
# 3. Press it again. Because there's no count=1 this time, the button fires the payload every press.
# -----

# This is the command that sets Hecate off on its task. Don't remove it or else Hecate won't run.
h.run()
