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
h = Hecate(                                                                                             status_led=True,
  buffer=128, # this holds temporary uart data until we're ready to process it
  monitor=usb_cdc.data, # this gives us a second usb-serial port we can spit out monitor data to
  logfile="log.txt", # this is where we'll log everything that happens
  uarts=[(board.TX, board.RX), (board.TX1, board.RX1)] # tells Hecate what hardware peripherals we have
)


# LAB #1: Monitoring UART
# We've got two devices that are communicating via UART, and we'd like to see what they're saying.
# With a single line of code, we'll set up Hecate to listen on an RX pin (a source).
# Uncomment the following line of code and save:

h.wire("from_authorizer", board.RX)

# 1. Connect the Xiaomao to your computer via USB.
# 2. Open up a terminal and connect to /dev/ttyACM1 to see the output
# 3. Connect the black ground wire from Xiaomao to your target.
# 4. Touch the white RX wire on your Xiaomao to the WHITE wire on your target system. Try pressing some buttons. What do you see?
# 5. Move the white RX wire on your Xiaomao to the GREEN wire on the target system and press some buttons. What do you see now?

# LAB #2: Full Duplex Monitoring
# It'd be much easier if we could see everything happening without having to move a wire around.
# Let's set up Hecate in the middle of the UART link. First we'll do some wiring, then we'll do some coding.

# Right now your board has green and white wires connecting UART between the two components.
# We want to intercept those wires with your XiaoMao board
# 1. Disconnect the bottom end of the green and white wires on your target system
# 2. Connect those now-loose ends to your XiaoMao's TX1 and RX1 pins. It should be Red-Black-Green-White-blank-blank-White-Green
# 3. Connect the green and white wires from your XiaoMao to the tx and rx pins you just vacated on your target

# Now, for the code. We're going to tell Hecate to pass through everything from RX to TX1, and everything from RX1 to TX.
# Uncomment the following lines of code and save:

h.wires["from_authorizer"].add_sink(board.TX1)
h.wire("from_keypad", board.RX1, board.TX)

# 1. Interact with your target system. Does it work normally, like it did before? If not, double check your wiring, then ask for some help.
# 2. Connect to your /dev/ttyACM1 monitor, and interact with the system. What do you see?
# 3. How does this protocol work? What happens when you press a button? What is the response you get?


# Lab #3: Standalone Logging
# So, we no longer have to poke around with a loose wire, but we still have to attached a computer to see what's happening.
# Let's use Hecate in standalone mode. We'll set it up to log UART data to a file that we can later retrieve.
# First, we'll do the coding, THEN we'll adjust the hardware wiring.

# The following code will log all the data to a file we can retrieve later.
# Uncomment the following lines of code and save:

#h.wires["from_keypad"].add_logfile("keypad.log")
#h.wires["from_authorizer"].add_logfile("authorizer.log")

# Now, we need to disconnect XiaoMao from USB and connect it directly to the target system
# 1. Disconnect your Xiaomao USB cable
# 2. Remove the red jumper from your Xiaomao board
# 3. Connect the red wire from your Xiaomao to the Target board
# 4. Interact with your target board.
# 5. Remove the red wire, and reconnect via USB
# 6. Look at the CIRCUITPY drive that shows up. Do you see your log files? What do they contain?
# 7. Now, reconnect your XiaoMao to the target system, and trick an instructor into unlocking your target
# 8. What's the password? Can you unlock the target now?


# Lab #4: Sending Data
# We know the magic message to drop in order to unlock the system. Lets use Hecate to do it!

# The following code will drop the contents of a text file onto a TX pin after a certain amount of time.
# Uncomment the following lines of code and save:

#data = Data(b"1234") # or Data("data.bin") for a file on disk
#timer = Trigger(timer=10)
#h.wires["from_keypad"].add_trigger(trigger=timer, callbacks=[data.drop])

# 1. Enter the secret pin above, or put the data you want into data.bin on the CIRCUITPY drive
# 2. Interact with your target. Does it work as expected?
# 3. Wait for the timeout. What happens?

# Lab #5: Pattern Matching
# WIP for defcon

# This is the command that sets Hecate off on its task. Call it once you've done all your configuring.
h.run()
