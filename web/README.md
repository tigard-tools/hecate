# Hecate Web Console

A zero-install, browser-based console for the Hecate workshop. It replaces the
`screen`/`picocom` + `nano`/`vim` dance with three panes:

- **Monitor** — a live, read-only tail of what Hecate sees on the wire (the
  `usb_cdc.data` serial port), over the browser's **Web Serial** API.
- **Files** — a simple browser of the `CIRCUITPY` drive.
- **Editor** — a **CodeMirror 6** editor **locked to `code.py`** (Python syntax
  highlighting, line numbers, search, bracket matching), reading and writing the
  file straight on the `CIRCUITPY` drive via the browser's **File System
  Access** API.

Nothing here talks to the network. The only "server" is a static file host; the
browser talks to the board directly.

## Running it

From this directory:

```
python3 -m http.server 8000
```

Then open **http://localhost:8000/** in **Chrome, Edge, or Brave on desktop**.

> **Why only those browsers?** Web Serial and File System Access are
> Chromium-only. Firefox and Safari cannot talk to serial ports or write files
> from a web page, so they will show a compatibility warning and the connect
> buttons will be disabled. This is a browser limitation, not a bug.
>
> Both APIs also require a *secure context*: `http://localhost` (what
> `http.server` gives you) counts as secure, as does any `https://` origin.
> Serving it from a different machine over plain `http://<ip>` will not work —
> run the server on the same laptop the board is plugged into.

## Using it

You connect the two halves independently (each needs one click, because
browsers require a user gesture to grant serial/drive access):

1. **Open CIRCUITPY drive…** → in the picker, select the `CIRCUITPY` volume.
   This grants read/write to `code.py`. The browser remembers the grant, so on
   later visits it's a single "allow" click.
2. **Connect monitor…** → pick the board's serial port. A CircuitPython board
   shows up as **two** ports; the *monitor* is the second one (e.g. `ACM1`, or
   the higher `COM`/`tty` number). If you pick the wrong one you'll see the
   Python REPL instead of UART traffic — just reconnect and choose the other.

When neither half is connected you get a landing page that keeps polling for the
board, so you can plug in at any time.

### Editing `code.py`

Edit in the center pane and press **Save** (or `Ctrl/Cmd+S`). Saving writes the
file to the drive, which makes CircuitPython **auto-reload** the board — the
monitor briefly drops and reconnects on its own. Only `code.py` is editable;
clicking any other file opens it read-only so students can look but not break
things.

### "The drive is read-only" / standalone mode

Editing only works in the **normal** plug-in regime, where the laptop owns the
`CIRCUITPY` drive read/write. If the board is in **standalone mode** — either
self-powered, or plugged in with the button held at power-on so *CircuitPython*
owns the filesystem — the drive is read-only to the laptop and saves will fail
with a clear banner. Re-plug the board normally (don't hold the button) to edit.

The Monitor still works in that state, so you can watch logging behavior even
when you can't edit.

## Files

- `index.html` — markup for the landing page and the three-pane console.
- `style.css` — all styling (dark theme, responsive; tabs on narrow screens).
- `app.js` — all logic: Web Serial monitor (with auto-reconnect across
  soft-reloads), File System Access file browser + `code.py` editor, device
  detection, and the status-polling loop.
- `vendor/codemirror.js` — the CodeMirror 6 editor, pre-bundled into a single
  self-contained ES module. **Checked in on purpose** so the console stays
  no-build, no-CDN, offline-capable — the workshop never runs a bundler.
- `editor-src/` — the source for that bundle (only needed to *rebuild* it).

The **running console** still has no build step, no runtime dependencies, and
no CDN — copy the folder anywhere and serve it with `python3 -m http.server`.

### Rebuilding the editor bundle

Only needed when bumping CodeMirror. Requires Node + npm (once):

```
cd editor-src
npm install
npm run build      # regenerates ../vendor/codemirror.js
```

Optional browser smoke test (needs a local Chromium; override its path with
`CHROMIUM=/path/to/chromium`):

```
npm run smoke      # mounts the bundle + boots index.html headless, checks for errors
```

`node_modules/` and the build tooling are git-ignored; only the built
`vendor/codemirror.js` is committed.
