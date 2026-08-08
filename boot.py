import board
import digitalio
import storage
import usb_cdc

usb_cdc.enable(console=True, data=True)

# switch is connected to the up direction on the d-pad
switch = digitalio.DigitalInOut(board.BTN)
switch.direction = digitalio.Direction.INPUT
switch.pull = digitalio.Pull.UP
# usb power is connected to the output of the usb 3.3v regulator
usb_power = digitalio.DigitalInOut(board.VBUS_DET)
usb_power.direction = digitalio.Direction.INPUT
usb_power.pull = digitalio.Pull.DOWN

#led = digitalio.DigitalInOut(board.LED)
#led.direction = digitalio.Direction.OUTPUT

#while true:
#    led.value=usb_power.value ^ switch.value

# true: usb write
# false: circuitpython write

# button\usb power | detected=true | detected=false
# pressed = true   | code r/w      | usb r/w
# pressed = false  | usb r/w       | code r/w
storage.remount("/", not usb_power.value ^ switch.value)
