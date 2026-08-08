import time

import busio

try:
    import digitalio
except ImportError:
    digitalio = None


_DEFAULT = object()


class _Copy:
    STATUS_LED_UNAVAILABLE = "status LED unavailable: %s"
    WIRE_SOURCE_NO_UART = "wire '%s': source has no UART"
    WIRE_SINK_NO_UART = "wire '%s': sink has no UART"
    LOG_READONLY = "cannot open log file: %s"
    POLL_ERROR = "runtime error in polling: %s"
    BOUND = "bound: %s\r\n"
    ERRLOG_SESSION = "--- hecate session ---"
    SYNTHETIC_TAG = "*"
    UNKNOWN_CMD = "unknown command '%s', type 'help'\r\n"
    STATUS_HEADER = "status: %d issue(s):\r\n"
    STATUS_ITEM = "  * %s\r\n"
    STATUS_OK = "status: running normally\r\n"
    HELP = ("commands:\r\n"
            " * status  report faults behind a red status LED\r\n"
            " * help    list these commands\r\n"
            " * exit    leave the monitor session (Hecate keeps running)\r\n")
    EXIT = ("monitor closed, detach your terminal:\r\n"
            " * in picocom: Ctrl-a Ctrl-x\r\n"
            " * screen:     Ctrl-a k\r\n"
            " * tio:        Ctrl-t q\r\n"
            " * minicom:    Ctrl-a x\r\n")


def _is_io(obj):
    return hasattr(obj, "read") or hasattr(obj, "write")


def _is_pin(obj):
    return not _is_io(obj) and not isinstance(obj, Data)


def _arity(callback):
    func = getattr(callback, "__func__", None)
    bound = func is not None
    code = getattr(func or callback, "__code__", None)
    if code is None:
        return 2
    n = code.co_argcount
    if bound:
        n -= 1
    return n


def _invoke(callback, hecate, wire):
    n = _arity(callback)
    if n <= 0:
        return callback()
    if n == 1:
        return callback(hecate)
    return callback(hecate, wire)


def _to_bytes(data):
    return data.encode("utf-8") if isinstance(data, str) else data


class _Monitor:
    """The human-facing USB-serial view of everything flowing through Hecate.

    Every write is tagged with a ``<monotonic> [<source>] `` header at the start
    of each line, so interleaved wires stay disambiguated on a shared terminal
    (this mirrors the on-disk log's per-source tagging, plus a boot-relative
    timestamp). Command replies and payload drops are tagged the same way.
    Headers can be turned off (``monitor_headers=False``) for a raw byte view.

    The monitor can also be muted (see the ``exit`` command) so the port goes
    quiet without disturbing passthrough or logging; forced writes (command
    replies) still get through, and reconnecting the host un-mutes it."""

    def __init__(self, sink, headers=True):
        self._sink = sink
        self._headers = headers
        self._last_name = None
        self._at_line_start = True
        self._muted = False

    def _raw(self, data):
        # the one place bytes actually reach the sink; a dead sink never
        # takes down the pump loop
        if self._sink is None or not data:
            return
        try:
            self._sink.write(data)
        except Exception:
            pass

    def write(self, data, name="hecate", force=False, synthetic=False):
        if self._sink is None or not data:
            return
        if self._muted and not force:
            return
        data = _to_bytes(data)
        if not self._headers:
            self._raw(data)
            return
        if synthetic:
            name = name + _Copy.SYNTHETIC_TAG
        now = time.monotonic()
        out = bytearray()
        # a mid-line switch to a different source breaks the line so the new
        # source gets its own header rather than being glued onto the old line
        if not self._at_line_start and name != self._last_name:
            out.append(0x0A)
            self._at_line_start = True
        for byte in data:
            if self._at_line_start:
                out.extend(("%.3f [%s] " % (now, name)).encode("utf-8"))
                self._at_line_start = False
            out.append(byte)
            if byte == 0x0A:            # \n ends the line
                self._at_line_start = True
        self._last_name = name
        self._raw(bytes(out))

    def echo(self, data):
        # reflect the operator's own keystrokes back untagged, ignoring mute, so
        # blind serial terminals (no local echo) still show what's being typed
        data = _to_bytes(data)
        self._raw(data)
        if data:
            # a keystroke interrupts any tagged line in progress; the next
            # tagged write should start fresh with its own header
            self._at_line_start = True

    def mute(self):
        self._muted = True

    def unmute(self):
        self._muted = False
        self._at_line_start = True


_STATUS_GREEN = (0, 255, 0)
_STATUS_YELLOW = (255, 255, 0)
_STATUS_RED = (255, 0, 0)
_STATUS_BLUE = (0, 0, 255)
_STATUS_ACTIVITY_WINDOW = 0.1   # seconds the LED holds yellow after the last byte


class _Status:
    """Drives a single NeoPixel: green while running, yellow on
    passthrough activity, red on a fault. On error, latches to red until reboot
    A disabled instance (status_led off, or no usable pixels) is a
    cheap no-op, so the rest of Hecate can call it unconditionally."""

    def __init__(self, enabled, pixels, power=None):
        self.enabled = bool(enabled) and pixels is not None
        self._pixels = pixels
        self._power = power      # retained so a NeoPixel power pin stays driven
        self._error = False
        self._captured = False
        self._last_activity = None
        self._color = None

    def _set(self, color):
        if not self.enabled or color == self._color:
            return
        self._color = color
        try:
            self._pixels.fill(color)
            show = getattr(self._pixels, "show", None)
            if show is not None:        # honor auto_write=False pixel objects
                show()
        except Exception:
            # a status update must never take down the pump loop
            self.enabled = False

    def set_running(self):
        self.update(None)

    def set_error(self):
        self._error = True
        self._set(_STATUS_RED)

    def set_captured(self):
        self._captured = True
        self._set(_STATUS_BLUE)

    def mark_activity(self, now):
        self._last_activity = now

    def update(self, now):
        if not self.enabled:
            return
        if self._error:
            self._set(_STATUS_RED)
        elif (self._last_activity is not None and now is not None
                and (now - self._last_activity) < _STATUS_ACTIVITY_WINDOW):
            self._set(_STATUS_YELLOW)
        elif self._captured:
            self._set(_STATUS_BLUE)
        else:
            self._set(_STATUS_GREEN)


def _enable_neopixel_power():
    # I think this is required for the NeoPixel to turn on for at least the XiaoMao?
    # Though it is a little unclear to me
    try:
        import board
        if not hasattr(board, "NEOPIXEL_POWER"):
            return None
        import digitalio
        pin = digitalio.DigitalInOut(board.NEOPIXEL_POWER)
        pin.switch_to_output(value=True)
        return pin
    except Exception:
        return None


def _make_status(status_led, status_pixels):
    # returns (status, fault_message_or_None); the caller routes the fault
    # through _fault so it reaches the monitor, the error log, and the LED
    if not status_led:
        return _Status(False, None), None
    pixels = status_pixels
    power = None
    if pixels is None:
        try:
            import board
            import neopixel
            power = _enable_neopixel_power()
            pixels = neopixel.NeoPixel(board.NEOPIXEL, 1, brightness=0.1,
                                       auto_write=True)
        except Exception as exc:
            return _Status(False, None), _Copy.STATUS_LED_UNAVAILABLE % str(exc)
    return _Status(True, pixels, power), None


# supervisor.runtime.usb_connected reads False for the first moments after boot,
# before the host finishes enumerating. Give enumeration this long to settle
# before trusting a "no host -> standalone" reading (see _resolve_log_faults).
_STANDALONE_GRACE = 5.0     # seconds
_CMD_MAX = 64


def _is_standalone():
    # True when running off external power with no USB host attached
    # This is so we can turn status LEDs red when the filesystem
    # is read-only and we try to log, but only when there is no monitor attached
    try:
        import supervisor
        return not supervisor.runtime.usb_connected
    except Exception:
        return False           # can't tell -> assume USB -> don't false-alarm


def _kmp_table(pattern):
    # Failure table: lps[i] = length of the longest proper prefix of
    # pattern[:i+1] that is also a suffix of it. Computed once per pattern so
    # a broken match backs off without re-examining bytes already seen.
    lps = [0] * len(pattern)
    k = 0
    for i in range(1, len(pattern)):
        while k > 0 and pattern[i] != pattern[k]:
            k = lps[k - 1]
        if pattern[i] == pattern[k]:
            k += 1
        lps[i] = k
    return lps


class _Handler:

    def __init__(self, pattern, replace, callback, one_shot):
        self.pattern = pattern
        self.replace = replace
        self.callback = callback
        self.one_shot = one_shot
        self.pos = 0
        self.fired = False
        self.lps = _kmp_table(pattern)


class Data:

    def __init__(self, body, destinations=None):
        self._body = body
        self._destinations = list(destinations) if destinations else []

    def _resolve(self):
        if isinstance(self._body, (bytes, bytearray)):
            return bytes(self._body)
        with open(self._body, "rb") as handle:
            return handle.read()

    def drop(self, hecate, wire=None):
        data = self._resolve()
        if wire is not None:
            wire.write(data)
        for sink in self._destinations:
            sink.write(data)
        hecate.monitor.write(data, wire.name if wire is not None else "payload",
                             synthetic=True)
        hecate._log_global(wire.name if wire is not None else "payload", data,
                           synthetic=True)


class Trigger:

    def __init__(self, *parts, timer=None, match=None, button=None, count=None):
        self.timer = timer
        self.match = bytes(match) if match is not None else None
        self.button = button
        self.count = count

        self._stages = [_as_trigger(p) for p in parts]

        self._fires = 0
        self._done = False

        self._armed_at = None
        self._match_pos = 0
        self._stage_i = 0
        self._dio = None
        self._btn_prev = True

    def _arm(self, now):
        self._armed_at = now
        self._match_pos = 0
        self._stage_i = 0
        for stage in self._stages:
            stage._arm(now)

    def _eval(self, data, now):
        if self._stages:
            return self._eval_sequence(data, now)
        if self.match is not None:
            return self._eval_match(data)
        if self.button is not None:
            return self._eval_button()
        if self.timer is not None:
            if self._armed_at is None:
                self._armed_at = now
            return (now - self._armed_at) >= self.timer
        return True

    def _eval_sequence(self, data, now):
        if self._stage_i >= len(self._stages):
            return True
        stage = self._stages[self._stage_i]
        if stage._eval(data, now):
            self._stage_i += 1
            if self._stage_i < len(self._stages):
                self._stages[self._stage_i]._arm(now)
                return False
            return True
        return False

    def _eval_match(self, data):
        for byte in data:
            if byte == self.match[self._match_pos]:
                self._match_pos += 1
                if self._match_pos == len(self.match):
                    self._match_pos = 0
                    return True
            else:
                self._match_pos = 1 if byte == self.match[0] else 0
        return False

    def _eval_button(self):
        if digitalio is None:
            return False
        if self._dio is None:
            self._dio = digitalio.DigitalInOut(self.button)
            self._dio.switch_to_input(pull=digitalio.Pull.UP)
            self._btn_prev = self._dio.value
        pressed = not self._dio.value
        edge = pressed and self._btn_prev
        self._btn_prev = self._dio.value
        return edge

    def update(self, data, now):
        if self._done:
            return False
        if not self._eval(data, now):
            return False

        self._fires += 1
        limit = self.count
        if (limit is None and not self._stages and self.match is None
                and self.button is None and self.timer is None):
            limit = 1
        if limit is not None and self._fires >= limit:
            self._done = True
        else:
            self._arm(now)
        return True


def _as_trigger(spec):
    if isinstance(spec, Trigger):
        return spec
    if spec is True:
        return Trigger()
    if isinstance(spec, (tuple, list)):
        return Trigger(*[_as_trigger(s) for s in spec])
    raise TypeError("trigger must be a Trigger, True, or a tuple of triggers")


def _register_trigger(store, trigger, callbacks, callback, count):
    cbs = list(callbacks) if callbacks else []
    if callback is not None:
        cbs.append(callback)
    trig = _as_trigger(trigger)
    if count is not None:
        trig.count = count
    store.append((trig, cbs))
    return trig


class Wire:

    def __init__(self, hecate, name, source, sinks):
        self._h = hecate
        self.name = name
        self._source = source
        self._sinks = list(sinks)
        self._handlers = []
        self._triggers = []
        self._logfiles = []
        self.logging = True
        self._buf = bytearray()

        self._reader = None
        self._writers = []
        self._removed = False
        self._src_armed = False

    def add_sink(self, sink):
        self._sinks.append(sink)
        if self._reader is not None or self._writers:
            self._writers.append(self._h._resolve_sink(sink))
        return self

    def add_logfile(self, path):
        handle = self._h._open_log(path)
        if handle is not None:
            self._logfiles.append(handle)
        return self

    def enable_logging(self, hecate=None, wire=None):
        self.logging = True

    def disable_logging(self, hecate=None, wire=None):
        self.logging = False

    def on_match(self, pattern, *, replace=_DEFAULT, callback=None,
                 one_shot=False):
        if not isinstance(pattern, (bytes, bytearray)) or len(pattern) == 0:
            raise ValueError("pattern must be non-empty bytes")
        handler = _Handler(bytes(pattern), replace, callback, one_shot)
        self._handlers.append(handler)
        return handler

    def eat(self, pattern):
        return self.on_match(pattern, replace=None)

    def add_trigger(self, trigger=True, callbacks=None, callback=None,
                    count=None):
        return _register_trigger(self._triggers, trigger, callbacks,
                                 callback, count)

    def add_callback(self, trigger=True, callback=None):
        return self.add_trigger(trigger=trigger, callback=callback)

    def add_data(self, data, trigger=True):
        return self.add_trigger(trigger=trigger, callback=data.drop)

    def remove(self):
        self._removed = True
        for handle in self._logfiles:
            try:
                handle.close()
            except OSError:
                pass
        self._logfiles = []
        self._h.wires.pop(self.name, None)

    def write(self, data):
        for writer in self._writers:
            writer.write(data)

    def inject(self, data):
        self.write(data)
        self._h.monitor.write(data, self.name, synthetic=True)
        self._h._log_global(self.name, data, synthetic=True)

    def _log(self, data):
        if not self.logging or not data:
            return
        for handle in self._logfiles:
            try:
                handle.write(data)
                handle.flush()
            except OSError:
                pass
        self._h._log_global(self.name, data)

    def _process(self, data):
        for byte in data:
            self._step(byte)

    def _step(self, byte):
        self._buf.append(byte)
        for handler in self._handlers:
            if handler.one_shot and handler.fired:
                continue
            pos = handler.pos
            while pos > 0 and byte != handler.pattern[pos]:
                pos = handler.lps[pos - 1]
            if byte == handler.pattern[pos]:
                pos += 1
            handler.pos = pos
            if pos == len(handler.pattern):
                self._fire(handler)
                return
        self._flush_safe()

    def _fire(self, handler):
        plen = len(handler.pattern)
        match_bytes = bytes(self._buf[-plen:])
        prefix = bytes(self._buf[:-plen])
        if prefix:
            self.write(prefix)
        if handler.replace is _DEFAULT:
            self.write(match_bytes)
        elif handler.replace is not None:
            self.write(handler.replace)
        self._buf = bytearray()
        for other in self._handlers:
            other.pos = 0
        handler.fired = True
        if handler.callback is not None:
            _invoke(handler.callback, self._h, self)

    def _flush_safe(self):
        max_partial = max((h.pos for h in self._handlers), default=0)
        count = len(self._buf) - max_partial
        if count > 0:
            self.write(bytes(self._buf[:count]))
            self._buf = self._buf[count:]


class Hecate:

    def __init__(self, *, buffer=128, monitor=None, logfile="", errorfile="",
                 baudrate=9600, uarts=None, status_led=False, status_pixels=None,
                 monitor_headers=True):
        self._buffer = buffer
        self._baudrate = baudrate
        self._monitor_io = monitor          # raw port: also read for commands
        for _reset in ("reset_input_buffer", "reset_output_buffer"):
            _fn = getattr(monitor, _reset, None)
            if _fn is not None:
                try:
                    _fn()
                except Exception:
                    pass
        self.monitor = _Monitor(monitor, headers=monitor_headers)
        self.wires = {}
        self.wires["monitor"] = self.monitor

        self._faults = []                   # reasons behind a red status LED
        self._cmd_buf = bytearray()         # accrues a monitor command line
        self._mon_connected = bool(getattr(monitor, "connected", False))
        self._log_ro_paths = []             # logs that wouldn't open (read-only FS);
                                            # faulted only if we settle as standalone

        # The error log persists faults on a standalone device with no monitor
        # attached (it can write files in standalone mode; a red LED alone can't
        # say what broke). Written open-append-close per fault in _write_errlog
        # so the log is never the second file held open at once.
        self._errlog_path = errorfile
        self._errlog_started = False

        self._status, status_fault = _make_status(status_led, status_pixels)
        if status_fault:
            self._fault(status_fault)
        self._log = self._open_log(logfile) if logfile else None
        self._log_last_name = None
        self._log_line_start = True
        self._uart_decls = uarts
        self._pin_uart = {}
        self._bound = False
        self._triggers = []

    def wire(self, name, source, *sinks):
        if len(sinks) == 1 and isinstance(sinks[0], (tuple, list)):
            sinks = tuple(sinks[0])
        w = Wire(self, name, source, sinks)
        self.wires[name] = w
        if self._bound:
            self._bind_wire(w)
        return w

    def add_trigger(self, trigger=True, callbacks=None, callback=None,
                    count=None):
        return _register_trigger(self._triggers, trigger, callbacks,
                                 callback, count)

    def mark_captured(self):
        self._status.set_captured()

    def _pumpable_wires(self):
        return [w for w in self.wires.values()
                if isinstance(w, Wire) and not w._removed]

    def _bind(self):
        self._allocate_uarts()
        for w in self._pumpable_wires():
            self._bind_wire(w)
        self._bound = True
        self._report_binding()

    def _allocate_uarts(self):
        if self._uart_decls:
            self._allocate_declared()
        else:
            self._allocate_by_trial()

    def _allocate_declared(self):
        for decl in self._uart_decls:
            tx, rx = decl
            uart = self._make_uart(tx=tx, rx=rx)
            if tx is not None:
                self._pin_uart[tx] = uart
            if rx is not None:
                self._pin_uart[rx] = uart

    def _allocate_by_trial(self):
        rx_pins, tx_pins = [], []
        for w in self._pumpable_wires():
            if _is_pin(w._source) and w._source not in rx_pins:
                rx_pins.append(w._source)
            for sink in w._sinks:
                if _is_pin(sink) and sink not in tx_pins:
                    tx_pins.append(sink)

        unpaired_tx = list(tx_pins)
        for rx in rx_pins:
            if rx in self._pin_uart:
                continue
            paired = False
            for tx in list(unpaired_tx):
                uart = self._try_uart(tx, rx)
                if uart is not None:
                    self._pin_uart[rx] = uart
                    self._pin_uart[tx] = uart
                    unpaired_tx.remove(tx)
                    paired = True
                    break
            if not paired:
                uart = self._try_uart(None, rx)
                if uart is not None:
                    self._pin_uart[rx] = uart
        for tx in unpaired_tx:
            if tx not in self._pin_uart:
                uart = self._try_uart(tx, None)
                if uart is not None:
                    self._pin_uart[tx] = uart

    def _try_uart(self, tx, rx):
        try:
            return self._make_uart(tx=tx, rx=rx)
        except (ValueError, RuntimeError):
            return None

    def _make_uart(self, *, tx, rx):
        return busio.UART(tx, rx, baudrate=self._baudrate, timeout=0,
                          receiver_buffer_size=self._buffer)

    def _resolve_source(self, source):
        if isinstance(source, Data):
            return None
        if _is_io(source):
            return source
        return self._pin_uart.get(source)

    def _resolve_sink(self, sink):
        if _is_io(sink):
            return sink
        return self._pin_uart.get(sink)

    def _bind_wire(self, w):
        w._reader = self._resolve_source(w._source)
        w._writers = [self._resolve_sink(s) for s in w._sinks]
        w._writers = [s for s in w._writers if s is not None]
        if isinstance(w._source, Data) and not w._src_armed:
            w._src_armed = True
            w.add_trigger(trigger=True, callback=w._source.drop, count=1)
        # A declared pin that failed to allocate a UART is a wiring fault.
        # Data sources (reader is intentionally None) and sink-less monitor
        # wires are not faults.
        if _is_pin(w._source) and w._reader is None:
            self._fault(_Copy.WIRE_SOURCE_NO_UART % w.name)
        for s in w._sinks:
            if _is_pin(s) and self._resolve_sink(s) is None:
                self._fault(_Copy.WIRE_SINK_NO_UART % w.name)

    def _report_binding(self):
        ids = []

        def uid(uart):
            for i, other in enumerate(ids):
                if other is uart:
                    return "U%d" % i
            ids.append(uart)
            return "U%d" % (len(ids) - 1)

        parts = []
        for w in self._pumpable_wires():
            if isinstance(w._source, Data):
                rx = "pay"
            elif not _is_pin(w._source):
                rx = "ext"
            elif w._reader is not None:
                rx = uid(w._reader)
            else:
                rx = "NONE"
            txs = []
            for s in w._sinks:
                if not _is_pin(s):
                    txs.append("ext")
                    continue
                writer = self._resolve_sink(s)
                txs.append(uid(writer) if writer is not None else "NONE")
            parts.append("%s rx=%s tx=%s" % (w.name, rx, "/".join(txs) or "-"))
        self.monitor.write(_Copy.BOUND % " | ".join(parts))

    def _fault(self, message):
        # record a red-LED reason, announce it on the monitor, persist it to the
        # error log (the only trace on a standalone device), and latch the LED
        # red. `status` reads back the recorded reasons.
        new = message not in self._faults
        if new:
            self._faults.append(message)
        self.monitor.write(message + "\r\n")
        if new:
            self._write_errlog(message)
        self._status.set_error()

    def _open_log(self, path):
        try:
            return open(path, "ab")
        except OSError:
            # A read-only FS with a USB host attached is the unsurprising normal
            # case, so we stay quiet about it; only a standalone device that
            # still can't write is a real fault. But this runs during __init__,
            # when usb_connected is not yet reliable, so we defer the standalone
            # decision to the poll loop instead of judging it here.
            self._log_ro_paths.append(path)
            return None

    def _resolve_log_faults(self, now):
        # Decide, once USB has had time to enumerate, whether a log that
        # wouldn't open is an actual fault. If a host is present it's the
        # unsurprising read-only case -> drop it silently. If we're still
        # hostless after the grace window -> genuinely standalone -> fault.
        if not self._log_ro_paths:
            return
        if not _is_standalone():
            self._log_ro_paths = []
        elif now >= _STANDALONE_GRACE:
            for path in self._log_ro_paths:
                self._fault(_Copy.LOG_READONLY % path)
            self._log_ro_paths = []

    def _write_errlog(self, message):
        # Open-append-close per fault: a read-only FS (USB host attached) is the
        # normal case and fails silently here; append mode keeps faults across
        # reboots. Only new (deduped) faults reach this, so the churn is tiny and
        # the log stays the sole persistently open file.
        if not self._errlog_path:
            return
        try:
            with open(self._errlog_path, "ab") as errlog:
                if not self._errlog_started:
                    # monotonic restarts each boot; mark the session boundary so
                    # appended-across-reboots faults stay legible
                    errlog.write((_Copy.ERRLOG_SESSION + "\n").encode("utf-8"))
                    self._errlog_started = True
                errlog.write(("%.3f %s\n" % (time.monotonic(), message))
                             .encode("utf-8"))
        except OSError:
            pass

    def _log_global(self, name, data, synthetic=False):
        if self._log is None or not data:
            return
        if synthetic:
            name = name + _Copy.SYNTHETIC_TAG
        try:
            if name != self._log_last_name:
                if not self._log_line_start:
                    self._log.write(b"\n")
                self._log.write(b"[" + name.encode("utf-8") + b"] ")
                self._log_last_name = name
            self._log.write(data)
            self._log_line_start = data.endswith(b"\n")
            self._log.flush()
        except OSError:
            pass

    def run(self):
        if not self._bound:
            self._bind()
        self._status.set_running()
        reported = set()
        while True:
            try:
                self.poll()
            except Exception as exc:
                msg = _Copy.POLL_ERROR % str(exc)
                if msg not in reported:
                    reported.add(msg)
                    self._fault(msg)
                self._status.set_error()

    def poll(self):
        now = time.monotonic()
        for w in self._pumpable_wires():
            data = self._pump(w)
            if data:
                self._status.mark_activity(now)
            self._run_triggers(w._triggers, data, w, now)
        self._run_triggers(self._triggers, b"", None, now)
        self._poll_commands(now)
        self._check_monitor_connection()
        self._resolve_log_faults(now)
        self._status.update(now)

    def _poll_commands(self, now):
        # read operator input off the monitor port and dispatch whole lines as
        # commands. A monitor with no readable side (write-only sink) is a no-op.
        io = self._monitor_io
        reader = getattr(io, "read", None)
        if reader is None:
            return
        n = getattr(io, "in_waiting", 0)
        if not n:
            return
        data = reader(n)
        if not data:
            return
        for byte in data:
            if byte in (0x0A, 0x0D):            # \n or \r ends the line
                line = bytes(self._cmd_buf)
                self._cmd_buf = bytearray()
                if line.strip():                # ignore blank lines / CRLF pairs
                    self.monitor.echo(b"\r\n")
                    self._dispatch_command(line, now)
            elif byte in (0x08, 0x7F):          # backspace / delete
                if self._cmd_buf:
                    # CircuitPython bytearray has no .pop(); slice off the last byte
                    self._cmd_buf = self._cmd_buf[:-1]
                    self.monitor.echo(b"\x08 \x08")
            elif 0x20 <= byte <= 0x7E:          # printable ASCII
                if len(self._cmd_buf) < _CMD_MAX:
                    self._cmd_buf.append(byte)
                    self.monitor.echo(bytes((byte,)))
            # other control bytes are ignored

    def _reply(self, text):
        self.monitor.write(text, "hecate", True)

    def _dispatch_command(self, line, now):
        cmd = line.strip().lower()
        if cmd == b"help":
            self._cmd_help()
        elif cmd == b"status":
            self._cmd_status()
        elif cmd == b"exit":
            self._cmd_exit()
        else:
            self._reply(_Copy.UNKNOWN_CMD % cmd.decode("utf-8"))

    def _cmd_help(self):
        self._reply(_Copy.HELP)

    def _cmd_status(self):
        if self._faults:
            self._reply(_Copy.STATUS_HEADER % len(self._faults))
            for fault in self._faults:
                self._reply(_Copy.STATUS_ITEM % fault)
        else:
            self._reply(_Copy.STATUS_OK)

    def _cmd_exit(self):
        # a device can't hang up the host's terminal, so the honest best is to
        # tell the user how to detach and then go quiet (auto-resumes on
        # reconnect). Passthrough and logging are untouched.
        self._reply(_Copy.EXIT)
        self.monitor.mute()

    def _check_monitor_connection(self):
        # when the host detaches and a fresh terminal reconnects, un-mute so the
        # new session sees output even if the previous one ran `exit`
        connected = getattr(self._monitor_io, "connected", None)
        if connected is None:
            return
        if connected and not self._mon_connected:
            self.monitor.unmute()
        self._mon_connected = connected

    def _pump(self, w):
        if w._reader is None:
            return b""
        n = getattr(w._reader, "in_waiting", 0)
        if not n:
            return b""
        data = w._reader.read(n)
        if not data:
            return b""
        w._process(data) # transmit data before writing to the monitor or log
        self.monitor.write(data, w.name)
        w._log(data)
        return data

    def _run_triggers(self, triggers, data, wire, now):
        for trig, cbs in triggers:
            if trig.update(data, now):
                for cb in cbs:
                    _invoke(cb, self, wire)
