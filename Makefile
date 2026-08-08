# Hecate — flashing Makefile
#
# Flashes CircuitPython (the tigard-tools fork) + Hecate onto Xiaomao (RP2040)
# boards. The heavy lifting lives in scripts/flash.sh; this file is just the
# friendly entry points. Run `make help`.
#
# Bootloader entry is manual: hold BOOTSEL while plugging a board in.

SHELL       := /bin/bash
FLASH       := scripts/flash.sh

# CircuitPython firmware (tigard-tools fork). Pulled on demand into firmware/
# (git-ignored) and pinned by sha256; or drop your own .uf2 at $(FIRMWARE) to
# vendor it. The build is board-specific: securinghw-xiaomao.
FIRMWARE       ?= firmware/firmware.uf2
CP_UF2_URL     ?= https://github.com/tigard-tools/circuitpython/releases/download/second-try/firmware.uf2
CP_UF2_SHA256  ?= 28be844082ee052c1b63b77d90d885835cf4186f7dd3935cf2284bb3cdf5b806

# Mounting removable drives needs privileges on a box with no automounter.
# Set SUDO= (empty) if you already run as root.
SUDO ?= sudo

export FIRMWARE SUDO

.DEFAULT_GOAL := all
.PHONY: all circuitpy hecate forever firmware list help \
        target_keypad target_authorizer clean

## all: flash CircuitPython then Hecate onto one connected board (default)
all: | $(FIRMWARE)
	@$(FLASH) all

## circuitpy: write CircuitPython onto the board in BOOTSEL mode
circuitpy: | $(FIRMWARE)
	@$(FLASH) circuitpy

## hecate: copy Hecate + lib/ onto the connected CIRCUITPY drive
hecate:
	@$(FLASH) hecate

## forever: flash board after board from a USB hub until Ctrl-C
##          (skips CircuitPython when the board already runs this build)
forever: | $(FIRMWARE)
	@$(FLASH) forever

## list: show detected Xiaomao boards (debugging)
list:
	@$(FLASH) list

## firmware: fetch + verify the CircuitPython .uf2 (cached, offline after first run)
firmware: $(FIRMWARE)
$(FIRMWARE):
	@mkdir -p $(dir $@)
	@echo "Fetching CircuitPython (tigard-tools fork, second-try)…"
	@curl -fL --progress-bar -o $@ "$(CP_UF2_URL)"
	@echo "$(CP_UF2_SHA256)  $@" | sha256sum -c - \
		|| { echo "!! sha256 mismatch — refusing $@"; rm -f $@; exit 1; }
	@echo "firmware ready: $@"

# --- target devices (keypad / authorizer) — DEFERRED ----------------------
# The workshop's target boards (the keypad + the authorizer it talks to) are
# most likely ESP-12F / ESP8266 modules, not yet confirmed. Wiring these up
# needs the FQBN + arduino-cli; left as a TODO so the Xiaomao path can ship.
#   target_keypad     -> target-code/keypadsender.ino  (libs: Keypad, Adafruit_NeoPixel)
#   target_authorizer -> target-code/codechecker.ino
target_keypad target_authorizer:
	@echo "TODO: target flashing not wired up yet (board likely ESP-12F/ESP8266)."
	@echo "      Confirm the FQBN, then build with arduino-cli, e.g.:"
	@echo "        arduino-cli compile --fqbn esp8266:esp8266:generic target-code/keypadsender.ino"
	@exit 2

## clean: remove build scratch (keeps the cached firmware)
clean:
	@rm -rf $${TMPDIR:-/tmp}/hecate-flash 2>/dev/null || true
	@echo "cleaned"

## help: list targets
help:
	@echo "Hecate flashing — targets:"
	@grep -E '^## ' $(MAKEFILE_LIST) | sed 's/^## /  /'
	@echo ""
	@echo "Vars: FIRMWARE=$(FIRMWARE)  SUDO=$(SUDO)"
	@echo "Flow: hold BOOTSEL, plug in a Xiaomao, then 'make all' (or 'make forever' for a hub)."
