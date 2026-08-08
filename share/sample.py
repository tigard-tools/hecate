import board, usb_cdc, neopixel 
from hecate import Hecate                                                       

pixels = neopixel.NeoPixel(board.NEOPIXEL, 2, brightness=0.1, auto_write=True)
pixels.fill((255, 255, 255))

h = Hecate(                                                                                             
  buffer=128,
  monitor=usb_cdc.data,
  logfile="log.txt",
)

def pingpong(hecate):
  hecate.wires["downstream"].write(b"PONG\r\n")
  hecate.wires["monitor"].write(b"Ping Ponged\r\n")

# Note to Joe: we thought we'd leave these unnamed by default last we talked,
# but the callback pattern has no good way of referring to its write destinations
# unless we put them all on the hecate context and make them accessible
# so the `upstream = h.wire(board.RX, board.TX1)` pattern is probably no good

# Also, we previously wanted to be able to do stuff like
# `hecate.downstream`, but probably safer to put wires in a hecate.wires array

# simple tee
h.wire("upstream", board.RX, board.TX1)
h.wire("downwstream", board.RX1, board.TX)

# adding pingpong to simple tee
h.wires["downstream"].on_match(b"PING\r\n", callback=pingpong)

# writing a payload on a simple timer
# TODO: Payload is kind of a heavy abstraction for what it buys us, maybe Payloads are just callbacks
payload = Payload("payload.bin")
timer = Trigger(timer=3600)
h.wires["downstream"].add_trigger(trigger=timer, callbacks=[payload.drop]


# alternative approaches
h.wires["downstream"].add_trigger(trigger=Trigger(timer=3600), callbacks=[payload.drop])
h.wires["downstream"].add_trigger(trigger=True, callbacks=[payload.drop]) # if no trigger, fires on first check (implied trigger=True)

# write a payload on a pattern match
match = Trigger(match=b"PING\r\n")

# or button presses
button = Trigger(button=board.BTN)

# compose more complex triggers from multiple simple ones
# triggers block evaluation of later triggers
# so this waits for a match, then counts down 3600s after the match
complex_trigger = (match, timer)

def flash_lights()
  pixels.fill(...)
  async.wait(30)
  pixels.fill(...)

h.add_trigger(trigger=(match, timer), count=5, callbacks=[
    h.wires["upstream"].enable_logging,
    payload.drop,
    flash_lights,
    ]
)

h.wires["upstream"].add_callback(trigger=complex_trigger, callback=payload.drop)
h.wires["upstream"].add_payload(payload, trigger=complex_trigger)

# buttons and other hardware interrupts 

# you can also make triggers one-shots or run a limited number of times
oneshot = Trigger(match, timer, count=1)

# filtering messages
h.wires["downstream"].eat(b"PING\r\n")

# multiple outputs, only one jumper (octojumper case)
h.wire("alice_mux", payload, [board.TX, board.TX1])

# this can be blocking or non-blocking, depending on asyncio stuff
h.run() 
