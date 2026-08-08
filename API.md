# High Level Objects

## `Hecate`
`Hecate` objects are the first step to standing up a Hecate implant. In simple scenarios, you will only make one, but you can instantiate more and run multiple independent instances simultaneously. If you do, you must take care to not share sources and sinks with other instances of `Hecate`, since you may run into contention issues if one instance is holding write when it is requested by another. They handle monitor communication and deduplication of sources and sinks.

Two file parameters record what happens on a monitor-less standalone device: `logfile=` captures all wire traffic (see the standalone labs), and `errorfile=` captures faults — the same reasons the `status` command reports and the red status LED signals (wiring faults, a read-only filesystem while logging, a runtime error in the poll loop). Each fault is written with a boot-relative timestamp and appended across reboots, so after an unattended run you can plug the device in and read `errorfile` off the drive to see what lit the LED. Both are best-effort: when a USB host is attached the filesystem is read-only to code, so neither file is written and (unlike before) no noise is printed about it.

```
class Hecate:

  def __init__(self, *, buffer=128, monitor=None, logfile=""):
    self._buffer = buffer
    if monitor is None:
      self.monitor = _DummyMonitor()
    else
      self.monitor = monitor
    self.log = os.File("log.txt")
```

## Sources and Sinks
Basically, an object is a Source if it implements a `read(...)` function, and a Sink if it implements a `write(...)` function. Common examples are UART pins (`board.TX`, `board.RX, etc`) but they can be other things, like log files that need to be replayed as a Source, and a Trigger as a Sink that receives messages from a given Source.

### Monitors
A `Monitor` is a special case of a Sink and is intended to be operated by a human being. It can be used for live tailing of specific behaviors on the wire and optionally exposes a simple REPL, allowing a user to interactively inject payloads and alter how bits flow in the system live, without having to reset the device.

By default, it is automatically added as a Sink to all Sources, but specific Sources can be filtered out of a `Monitor`'s feed when writing your harness.

A typical `Monitor` is something like `usb_cdc.data`, from the `usb_cdc` library built into CircuitPython. It exposes `write(...)` like any other Sink, and — if it also exposes `read(...)`/`in_waiting` (as `usb_cdc.data` does) — Hecate reads it for interactive commands (see below).

#### Tagged headers
Every line Hecate writes to the monitor is prefixed with a `<timestamp> [<source>] ` header, so interleaved wires stay disambiguated on a shared terminal:

```
1234.567 [from_keypad] 4821
1234.789 [from_authorizer] OK
1235.010 [hecate] bound: from_keypad rx=U0 tx=U1 | from_authorizer rx=U1 tx=U0
```

The timestamp is `time.monotonic()` (seconds since boot — there is no wall clock on the device). The source is the wire name for passthrough traffic, the wire name (or `payload`) for dropped `Data`, and `hecate` for framework messages. Switching sources mid-line breaks the line so each source keeps its own header. Pass `monitor_headers=False` to `Hecate(...)` for a raw, untagged byte view.

#### Commands
When the monitor port is readable, you can type commands at it (from `picocom`, `screen`, the web console, etc.) — one per line, case-insensitive:

* `status` — report the fault(s) that lit the red status LED (wiring faults, a read-only filesystem during logging on a standalone device, a runtime error in the poll loop, …), or `status: running normally` when there are none. These are the in-RAM faults from the current session; a standalone device with no monitor gets the same list persisted to `errorfile` instead.
* `help` — list the available commands.
* `exit` — leave the monitor session. A CircuitPython device can't hang up the host's terminal, so `exit` prints the detach escape sequences for common terminals (`picocom` `Ctrl-a Ctrl-x`, `screen` `Ctrl-a k`, …) and then goes quiet — it mutes the monitor feed (passthrough and logging keep running untouched) until the host reconnects, at which point the feed resumes automatically. Command replies still print while muted, so an accidental `exit` is recoverable.

### Wires
Wires have exactly one Source, and zero or more Sinks. They are created by calling a method on `hecate` directly to define a connection between a Source and its sinks:

```
h = Hecate()
# one wire for receiving sensor data and sending it to the receiver
sensor = h.wire(rx = board.RX, tx = board.TX1)
# another for the receiver's reply, if any, and sending it back to the sensor
receiver = h.wire(rx = board.RX1, tx = board.TX)
```

Wires are nameless by default, but creating one with `hecate.wire()` returns a reference that you can save to a variable, if you need to mutate the state of that wire later:

```
sensor.remove() # delete the edge between this machine

### Payloads
Payloads have a payload body (can be a file path) and one or more destinations

```

### Triggers
Triggers have conditions (see below) that need to be met for the trigger to evaluate `True`, and a list of callbacks that execute on evaluation to `True`.

```
sensor.trigger(trigger=Trigger(timer=3600), callbacks=[mypayload.drop])
```

#### Match
Matches have a match body and one or more origins. They evaluate to true when one or more of the origins' messages match the body.

```
def pong(match, hecate):
  hecate.downstream.write(b"PONG\r\n")
  hecate.monitor.write(b"Ping Ponged\r\n")

downstream = h.wire(board.RX, board.TX1)
downstream.on_match(b"PING\r\n", callback=pong)
```

#### Timer

```

```

#### Button (hardware interrupt)

#### Action (callbacks)
