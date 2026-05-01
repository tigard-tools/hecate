# Hecate
Hecate: A Trivial UART tool

# Objectives
UART is pervasive. Nearly every piece of hardware can speak it. It can be a treasure trove of access when it's not properly secured, an entrypoint to explore even when it is secured, and often a spot to tap plaintext communications between devices.

Hecate is a CircuitPython framework designed to make it quick and easy to work with UART data streams, both interactively and standalone. Hecate makes it possible to implement a customized UART logger, payload dropper, implant-in-the-middle, and more with little or no code.

# Inspiration
* [Akheron-proxy](https://github.com/rapid7/akheron-proxy) is a python tool for inspecting and manipulating inter-chip UART communications
* [Serberus](https://github.com/google/serberus) is a USB-to-multiple-UART device intended to work with Akheron-proxy and other tools. It was presented at [Crowdsupply's Teardown conference](https://www.youtube.com/watch?v=c6WhOVPHBbU) 
* [Circuitpython-uart-passthrough](https://github.com/scogswell/circuitpython-uart-passthrough) is a bare bones UART passthrough that is the starting point of many customizations that Hecate hopes to make a little more trivial

In Greek mythology, Akheron is the river Charon ferries the dead across and Cerberus is the 3-headed guard dog that guards the underworld. In keeping with the theme, Hecate is a goddess of crossroads. It's typically pronounced "eh-kah-tee" but you're more than welcome to pronounce it like "Tecate".

# Essential Features
* **Passthrough Device:** When not doing anything else, Hecate should be able to sit in the middle of a UART line, passing through all traffic with minimal (sub-millisecond) delays
* **Tap or Tee** In addition to passing through data, Hecate should be able to mirror a copy of that data to an additional UART or to a USB-serial interface.
* **Standalone Logger:** Without any USB host involved, Hecate should be able to log all UART traffic that passes through it to a text file. The text file will be retrievable by plugging the device in over USB and copying it off like a flash drive.
* **Payload Dropper** Without any USB host involved, Hecate should be able to transmit over UART the contents of a text file stored in it's EEPROM.
* **Pattern Detector** Hecate should be able to have basic pattern matching so that when a device transmits a preconfigured UART sequence, it triggers an additional action.
* **Pattern Patcher** Hecate should also be able to match/patch basic sequences to 
* **Triggers** Hecate should be able to do any of these things, triggered or enabled by button presses, timestamps, or other stimuli
* **Alerts** Hecate should be able to fire alerts such as LED output or other UART actions
* **Extensible** Users should be able to implement custom Triggers or Alerts, like temperature sensors or buzzers or wireless actions.

# Installing and Using Hecate
WIP

# Recommended Hardware
[Xiaomao](https://github.com/tigard-tools/xiaomao) is an RP2040-based device that can run CircuitPython, has 2 hardware UARTs, lives under the Tigard-Tools umbrella, and should work well with Hecate. Otherwise, any device that can run CircuitPython and has a UART should work just as well with Hecate.

In order to use Hecate implant-style in a system, you'll need to find a way to get power from the target device. Your implant's power requirements may vary.
