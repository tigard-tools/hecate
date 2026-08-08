// Hecate Web Console
// A fully static, offline-capable console for the Hecate UART workshop.
//
//   * Editor + file browser  -> File System Access API on the mounted CIRCUITPY drive.
//     Editing only works in the normal plug-in regime (host owns the drive, BTN not
//     held at boot). When the board owns the filesystem (standalone / BTN held) the
//     drive is read-only and the editor drops to read-only automatically.
//   * Monitor -> Web Serial API, read-only live tail of the usb_cdc.data port.
//
// Both APIs are Chromium-desktop only. Nothing here talks to the network; serve it
// with `python3 -m http.server` and open it in Chrome/Edge/Brave.
//
// The code editor is CodeMirror 6, bundled offline into ./vendor/codemirror.js
// (rebuild from editor-src/ — see web/README.md).

import {
  EditorView, EditorState, Compartment,
  basicSetup, keymap, placeholder, indentWithTab, python, oneDark,
} from "./vendor/codemirror.js";

const EDITABLE_FILE = "code.py"; // the editor is locked to this one file
const MONITOR_BAUD = 115200; // nominal; USB-CDC ignores it but open() requires a value
const MONITOR_CAP = 200_000; // max characters retained in the monitor view
const POLL_MS = 2500;

// --------------------------------------------------------------------------
// tiny DOM helpers
// --------------------------------------------------------------------------
const $ = (sel) => document.querySelector(sel);
const el = {
  landing: $("#landing"),
  console: $("#console"),
  chipDrive: $("#chip-drive"),
  chipMonitor: $("#chip-monitor"),
  chipDriveDot: $("#chip-drive .dot"),
  chipMonitorDot: $("#chip-monitor .dot"),
  chipDriveLabel: $("#chip-drive .chip-label"),
  chipMonitorLabel: $("#chip-monitor .chip-label"),
  chipConsole: $("#chip-console"),
  chipConsoleDot: $("#chip-console .dot"),
  btnOpenDrive: $("#btn-open-drive"),
  btnConnectMonitor: $("#btn-connect-monitor"),
  driveHint: $("#drive-hint"),
  monitorHint: $("#monitor-hint"),
  landingCompat: $("#landing-compat"),
  // files
  breadcrumb: $("#breadcrumb"),
  filelist: $("#filelist"),
  driveInfo: $("#drive-info"),
  btnRefreshFiles: $("#btn-refresh-files"),
  // editor
  editor: $("#editor"),                 // CodeMirror mount point (a <div>)
  editorFilename: $("#editor-filename"),
  editorBadge: $("#editor-badge"),
  editorBanner: $("#editor-banner"),
  editorStatus: $("#editor-status"),
  dirtyDot: $("#dirty-dot"),
  btnSave: $("#btn-save"),
  btnRevert: $("#btn-revert"),
  btnEditCodepy: $("#btn-edit-codepy"),
  // monitor
  monitorOut: $("#monitor-out"),
  monitorStatus: $("#monitor-status"),
  monitorBadge: $("#monitor-badge"),
  autoscroll: $("#autoscroll"),
  btnClearMonitor: $("#btn-clear-monitor"),
  btnReconnectMonitor: $("#btn-reconnect-monitor"),
  toast: $("#toast"),
};

// --------------------------------------------------------------------------
// state
// --------------------------------------------------------------------------
const state = {
  drive: {
    root: null, // FileSystemDirectoryHandle of CIRCUITPY
    cwd: null, // handle of the folder currently shown
    path: [], // breadcrumb path relative to root
    connected: false,
    writable: false, // whether code.py is writable (false => standalone / read-only)
    board: "", // parsed from boot_out.txt
  },
  editor: {
    fileHandle: null, // handle of the file currently in the editor
    name: EDITABLE_FILE,
    baseline: "", // last-saved contents, for dirty tracking
    readOnly: true,
  },
  monitor: {
    port: null,
    reader: null,
    connected: false,
    keepOpen: false, // user intends the monitor to stay connected
    sawHecate: false,
    reconnecting: false,
  },
  console: {
    port: null,
    connected: false,
    keepOpen: false,
    reconnecting: false,
    lastError: null, // last save error, drives the chip's red state
  },
};

let toastTimer = null;
function toast(msg, kind = "") {
  el.toast.textContent = msg;
  el.toast.className = "toast" + (kind ? " " + kind : "");
  el.toast.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (el.toast.hidden = true), 3500);
}

function setDot(dot, stateName) {
  dot.setAttribute("data-state", stateName);
}

// --------------------------------------------------------------------------
// IndexedDB: persist the drive handle so a reload only needs a re-grant click
// --------------------------------------------------------------------------
const IDB_NAME = "hecate-web";
const IDB_STORE = "handles";
function idb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(IDB_NAME, 1);
    req.onupgradeneeded = () => req.result.createObjectStore(IDB_STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}
async function idbSet(key, val) {
  const db = await idb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, "readwrite");
    tx.objectStore(IDB_STORE).put(val, key);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}
async function idbGet(key) {
  const db = await idb();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(IDB_STORE, "readonly");
    const req = tx.objectStore(IDB_STORE).get(key);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

// --------------------------------------------------------------------------
// view / status wiring
// --------------------------------------------------------------------------
function updateView() {
  const anyConnected = state.drive.connected || state.monitor.connected;
  el.landing.hidden = anyConnected;
  el.console.hidden = !anyConnected;

  // topbar chips
  setDot(el.chipDriveDot, state.drive.connected ? (state.drive.writable ? "good" : "warn") : "off");
  setDot(el.chipMonitorDot, state.monitor.connected ? "good" : state.monitor.reconnecting ? "warn" : "off");
  setDot(el.chipConsoleDot, state.console.lastError ? "bad"
    : state.console.connected ? "good"
    : state.console.reconnecting ? "warn" : "off");
  el.chipDriveLabel.textContent = state.drive.connected
    ? state.drive.writable
      ? "Drive: R/W"
      : "Drive: read-only"
    : "Drive";
  el.chipMonitorLabel.textContent = state.monitor.connected
    ? "Monitor"
    : state.monitor.reconnecting
    ? "Monitor…"
    : "Monitor";
}

// ==========================================================================
// DRIVE  (File System Access)
// ==========================================================================
async function pickDrive() {
  try {
    const root = await window.showDirectoryPicker({ id: "circuitpy", mode: "readwrite" });
    await useDrive(root, /*isFresh*/ true);
    await idbSet("driveRoot", root);
  } catch (err) {
    if (err && err.name === "AbortError") return; // user cancelled the picker
    setHint(el.driveHint, "Could not open the drive: " + (err?.message || err), "err");
  }
}

async function restoreDrive({ silent } = {}) {
  const root = await idbGet("driveRoot");
  if (!root) return false;
  const perm = await root.queryPermission({ mode: "readwrite" });
  if (perm === "granted") {
    try {
      await useDrive(root, false);
      return true;
    } catch {
      return false;
    }
  }
  if (!silent) {
    // needs a user gesture to re-grant; surface a one-click button
    const ok = (await root.requestPermission({ mode: "readwrite" })) === "granted";
    if (ok) {
      await useDrive(root, false);
      return true;
    }
  }
  return false;
}

// Confirm the handle really points at a CircuitPython board, wire up state.
async function useDrive(root, isFresh) {
  await root.values().next();
  // Sanity: a CIRCUITPY drive has boot_out.txt (CircuitPython writes it at boot)
  // and our workshop code.py. We don't hard-fail if boot_out.txt is missing
  // (some boards/filesystems differ) but we do want code.py to exist.
  let board = "";
  try {
    const bootFile = await (await root.getFileHandle("boot_out.txt")).getFile();
    board = parseBoardName(await bootFile.text());
  } catch {
    /* boot_out.txt optional */
  }

  state.drive.root = root;
  state.drive.cwd = root;
  state.drive.path = [];
  state.drive.board = board;
  state.drive.connected = true;
  // Optimistic: we hold a read/write permission grant. We can't test whether the
  // underlying FAT mount is actually read-only without writing a temp file, which
  // would make CircuitPython auto-reload the board on every drive open. So assume
  // writable and correct to read-only on the first failed save (standalone / BTN held).
  state.drive.writable = true;

  await listDir();
  // Load code.py into the editor and, in doing so, learn if the drive is writable.
  await loadEditable();
  updateView();
  if (isFresh) {
    setHint(el.driveHint, "Drive connected" + (board ? " — " + board : ""), "ok");
    toast("Drive connected" + (board ? " — " + board : ""), "ok");
  }
}

function parseBoardName(text) {
  // boot_out.txt line 1 looks like:
  //   Adafruit CircuitPython 9.1.1 on 2024-07-25; Xiaomao with rp2040
  const first = (text.split(/\r?\n/)[0] || "").trim();
  const m = first.match(/;\s*(.+?)(?:\s+with\s+|$)/);
  return m ? m[1].trim() : first.slice(0, 60);
}

async function listDir() {
  const dir = state.drive.cwd;
  if (!dir) return;
  const dirs = [];
  const files = [];
  try {
    for await (const [name, handle] of dir.entries()) {
      if (name.startsWith(".")) continue; // hide dotfiles / metadata
      (handle.kind === "directory" ? dirs : files).push({ name, handle });
    }
  } catch (err) {
    setDriveInfo("Could not read folder: " + (err?.message || err));
    return;
  }
  dirs.sort((a, b) => a.name.localeCompare(b.name));
  files.sort((a, b) => a.name.localeCompare(b.name));

  el.filelist.innerHTML = "";
  // ".." up entry when not at root
  if (state.drive.path.length) {
    el.filelist.appendChild(makeEntry("..", "up", () => navigateUp()));
  }
  for (const d of dirs) {
    el.filelist.appendChild(makeEntry(d.name, "dir", () => enterDir(d)));
  }
  for (const f of files) {
    const isCode = state.drive.path.length === 0 && f.name === EDITABLE_FILE;
    el.filelist.appendChild(
      makeEntry(f.name, isCode ? "codepy" : "file", () => openFile(f, isCode))
    );
  }
  renderBreadcrumb();
  renderDriveInfo();
}

function makeEntry(name, kind, onClick) {
  const li = document.createElement("li");
  const icon = { up: "↩", dir: "▸", codepy: "★", file: "·" }[kind] || "·";
  li.innerHTML = `<span class="ficon">${icon}</span><span class="fname"></span>`;
  li.querySelector(".fname").textContent = name;
  if (kind === "dir" || kind === "up") li.classList.add("dir");
  if (kind === "codepy") {
    li.classList.add("is-codepy");
    const tag = document.createElement("span");
    tag.className = "fedit";
    tag.textContent = "editable";
    li.appendChild(tag);
  }
  li.addEventListener("click", onClick);
  return li;
}

function renderBreadcrumb() {
  el.breadcrumb.innerHTML = "";
  const mk = (label, idx) => {
    const a = document.createElement("a");
    a.textContent = label;
    a.addEventListener("click", () => jumpTo(idx));
    return a;
  };
  el.breadcrumb.appendChild(mk("CIRCUITPY", -1));
  state.drive.path.forEach((seg, i) => {
    el.breadcrumb.appendChild(document.createTextNode(" / "));
    el.breadcrumb.appendChild(mk(seg.name, i));
  });
}

function renderDriveInfo() {
  const bits = [];
  if (state.drive.board) bits.push(state.drive.board);
  bits.push(state.drive.writable ? "read/write" : "read-only (standalone?)");
  setDriveInfo(bits.join(" · "));
}
function setDriveInfo(text) {
  el.driveInfo.textContent = text;
}

async function enterDir(entry) {
  state.drive.path.push({ name: entry.name, handle: entry.handle });
  state.drive.cwd = entry.handle;
  await listDir();
}
async function navigateUp() {
  await jumpTo(state.drive.path.length - 2);
}
async function jumpTo(idx) {
  // idx === -1 -> root; otherwise index into path
  if (idx < 0) {
    state.drive.path = [];
    state.drive.cwd = state.drive.root;
  } else {
    state.drive.path = state.drive.path.slice(0, idx + 1);
    state.drive.cwd = state.drive.path[idx].handle;
  }
  await listDir();
}

// ==========================================================================
// EDITOR  (CodeMirror 6)
// ==========================================================================
// A thin wrapper so the rest of the app can treat the editor like the old
// textarea: get/set text and toggle read-only. Line numbers, Python syntax
// highlighting, history, search and bracket matching come from basicSetup.
let cmView = null;
const cmEditable = new Compartment();

function editableExtensions(editable) {
  return [EditorState.readOnly.of(!editable), EditorView.editable.of(editable)];
}

function initEditor() {
  // oneDark supplies token colors; this overrides the editor chrome so it
  // blends into the Hecate palette instead of oneDark's own grey.
  const hecateTheme = EditorView.theme(
    {
      "&": { height: "100%", backgroundColor: "var(--bg)", color: "var(--fg)" },
      ".cm-scroller": { fontFamily: "var(--mono)", fontSize: "13px", lineHeight: "1.5" },
      ".cm-gutters": {
        backgroundColor: "var(--bg-2)", color: "var(--fg-faint)",
        border: "none", borderRight: "1px solid var(--line)",
      },
      ".cm-activeLine": { backgroundColor: "rgba(176,97,255,.06)" },
      ".cm-activeLineGutter": { backgroundColor: "rgba(176,97,255,.10)" },
      "&.cm-focused .cm-cursor": { borderLeftColor: "var(--accent)" },
      ".cm-selectionBackground, &.cm-focused .cm-selectionBackground": {
        backgroundColor: "rgba(176,97,255,.25)",
      },
    },
    { dark: true }
  );
  cmView = new EditorView({
    parent: el.editor,
    state: EditorState.create({
      doc: "",
      extensions: [
        basicSetup,
        python(),
        oneDark,
        hecateTheme,
        keymap.of([indentWithTab]),
        placeholder("Open the CIRCUITPY drive to edit code.py…"),
        cmEditable.of(editableExtensions(false)),
        EditorView.updateListener.of((u) => { if (u.docChanged) markDirty(); }),
      ],
    }),
  });
}

function editorGetValue() {
  return cmView ? cmView.state.doc.toString() : "";
}
function editorSetValue(text) {
  if (!cmView) return;
  cmView.dispatch({ changes: { from: 0, to: cmView.state.doc.length, insert: text } });
}

async function loadEditable() {
  // Always load the root code.py as the primary editable target.
  if (isDirty()) return;
  try {
    const fh = await state.drive.root.getFileHandle(EDITABLE_FILE);
    await putFileInEditor(fh, EDITABLE_FILE, /*editable*/ true, /*isCodepy*/ true);
  } catch (err) {
    editorSetValue("");
    setEditorReadOnly(true);
    showEditorBanner(
      `Couldn't open ${EDITABLE_FILE} on this drive (${err?.message || err}).`,
      "warn"
    );
  }
}

async function openFile(entry, isCodepy) {
  // The editor is *locked* to code.py. Any other file opens read-only so
  // students can look but can only edit code.py.
  if (isDirty() && !confirmDiscard()) return;
  try {
    const fh = entry.handle;
    const editable = isCodepy;
    await putFileInEditor(fh, entry.name, editable, isCodepy);
  } catch (err) {
    toast("Could not open " + entry.name + ": " + (err?.message || err), "err");
  }
}

async function putFileInEditor(fileHandle, name, editable, isCodepy) {
  const file = await fileHandle.getFile();
  const text = await file.text();
  state.editor.fileHandle = fileHandle;
  state.editor.name = name;
  editorSetValue(text);
  state.editor.baseline = editorGetValue();
  el.editorFilename.textContent = name;
  setEditorReadOnly(!editable);
  markDirty(false);
  highlightActiveFile(name);

  // banner + badge explain *why* something is / isn't editable
  el.editorBadge.hidden = false;
  if (editable) {
    el.editorBadge.textContent = "R/W";
    el.editorBadge.className = "badge badge-rw";
    hideEditorBanner();
  } else {
    el.editorBadge.textContent = "read-only";
    el.editorBadge.className = "badge badge-ro";
    showEditorBanner(
      `Viewing ${name}. Only ${EDITABLE_FILE} is editable — use “Edit code.py” to get back.`,
      "info"
    );
  }
}

function highlightActiveFile(name) {
  el.filelist.querySelectorAll("li").forEach((li) => {
    const fn = li.querySelector(".fname");
    li.classList.toggle("is-active", fn && fn.textContent === name && !li.classList.contains("dir"));
  });
}

function setEditorReadOnly(ro) {
  state.editor.readOnly = ro;
  if (cmView) cmView.dispatch({ effects: cmEditable.reconfigure(editableExtensions(!ro)) });
  el.editor.classList.toggle("is-readonly", ro);
  el.btnSave.disabled = ro;
}

function isDirty() {
  return editorGetValue() !== state.editor.baseline;
}
function markDirty(force) {
  const dirty = force === undefined ? isDirty() : force;
  el.dirtyDot.hidden = !dirty;
  el.btnSave.disabled = state.editor.readOnly || !dirty;
}

async function saveEditor() {
  if (state.editor.readOnly) return;
  if (state.editor.name !== EDITABLE_FILE) return; // guard: only code.py is saveable
  const text = editorGetValue();
  try {
    await ensureConsole();
    setEditorStatus("Saving over the REPL…");
    await saveCodeViaSerial(text);
    state.editor.baseline = text;
    markDirty(false);
    state.console.lastError = null;
    setEditorStatus("Saved " + timeNow() + " — reloading the board.");
    toast("Saved code.py — reloading", "ok");
  } catch (err) {
    state.console.lastError = err?.message || String(err);
    showEditorBanner("Save failed: " + state.console.lastError, "warn");
    toast("Save failed", "err");
  }
  updateView();
}

async function revertEditor() {
  if (!state.editor.fileHandle) return;
  if (isDirty() && !confirmDiscard()) return;
  try {
    const file = await state.editor.fileHandle.getFile();
    const text = await file.text();
    editorSetValue(text);
    state.editor.baseline = editorGetValue();
    markDirty(false);
    setEditorStatus("Reloaded from board " + timeNow());
  } catch (err) {
    toast("Reload failed: " + (err?.message || err), "err");
  }
}

function confirmDiscard() {
  return window.confirm("You have unsaved changes. Discard them?");
}

function setEditorStatus(text) {
  el.editorStatus.textContent = text;
}
function showEditorBanner(text, kind) {
  el.editorBanner.textContent = text;
  el.editorBanner.className = "editor-banner" + (kind === "info" ? " info" : "");
  el.editorBanner.hidden = false;
}
function hideEditorBanner() {
  el.editorBanner.hidden = true;
}

// ==========================================================================
// MONITOR  (Web Serial)
// ==========================================================================
async function connectMonitorInteractive() {
  try {
    const port = await navigator.serial.requestPort();
    await openMonitor(port, /*announce*/ true);
  } catch (err) {
    if (err && err.name === "NotFoundError") return; // user dismissed the chooser
    setHint(el.monitorHint, "Could not connect: " + (err?.message || err), "err");
  }
}

async function openMonitor(port, announce) {
  if (state.monitor.connected && state.monitor.port === port) return;
  try {
    await port.open({ baudRate: MONITOR_BAUD });
  } catch (err) {
    // A port that is already open (e.g. re-selected) throws InvalidStateError.
    if (!(err && err.name === "InvalidStateError")) {
      setHint(el.monitorHint, "Could not open port: " + (err?.message || err), "err");
      return;
    }
  }
  state.monitor.port = port;
  state.monitor.connected = true;
  state.monitor.keepOpen = true;
  state.monitor.reconnecting = false;
  el.btnReconnectMonitor.hidden = true;
  setMonitorStatus("Connected.");
  updateView();
  if (announce) {
    setHint(el.monitorHint, "Monitor connected", "ok");
    toast("Monitor connected", "ok");
  }
  readMonitorLoop(port); // fire and forget
}

let readingActive = false;
async function readMonitorLoop(port) {
  if (readingActive) return;
  readingActive = true;
  const decoder = new TextDecoder("utf-8", { fatal: false });
  try {
    while (port.readable) {
      let reader = null;
      try {
        reader = port.readable.getReader();
        state.monitor.reader = reader;
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          if (value) appendMonitor(decoder.decode(value, { stream: true }));
        }
      } catch {
        break; // device went away (unplug / soft-reload)
      } finally {
        if (reader) reader.releaseLock();
      }
    }
  } finally {
    state.monitor.reader = null;
    onMonitorDropped();
    readingActive = false;
  }
}

function onMonitorDropped() {
  const wasConnected = state.monitor.connected;
  state.monitor.connected = false;
  try {
    state.monitor.port && state.monitor.port.close();
  } catch {
    /* already closing */
  }
  if (state.monitor.keepOpen) {
    // Almost always a soft-reload after a save; try to come back automatically.
    state.monitor.reconnecting = true;
    setMonitorStatus("Disconnected — reconnecting…");
    el.btnReconnectMonitor.hidden = false;
    scheduleMonitorReconnect(800);
  } else if (wasConnected) {
    setMonitorStatus("Disconnected.");
  }
  updateView();
}

let reconnectTimer = null;
function scheduleMonitorReconnect(delay) {
  clearTimeout(reconnectTimer);
  reconnectTimer = setTimeout(tryMonitorReconnect, delay);
}

async function tryMonitorReconnect() {
  if (state.monitor.connected || !state.monitor.keepOpen) return;
  // Prefer the exact port object we used before; after a CircuitPython
  // soft-reload getPorts() returns the same object once it re-enumerates.
  try {
    const ports = await navigator.serial.getPorts();
    let target = state.monitor.port && ports.includes(state.monitor.port) ? state.monitor.port : null;
    if (!target && ports.length === 1) target = ports[0]; // unambiguous single grant
    if (!target) {
      // still gone (or ambiguous) — keep trying quietly
      scheduleMonitorReconnect(1500);
      return;
    }
    await openMonitor(target, false);
    setMonitorStatus("Reconnected " + timeNow() + ".");
  } catch {
    scheduleMonitorReconnect(1500);
  }
}

async function reconnectMonitorClick() {
  clearTimeout(reconnectTimer);
  state.monitor.keepOpen = true;
  try {
    const ports = await navigator.serial.getPorts();
    let target = state.monitor.port && ports.includes(state.monitor.port) ? state.monitor.port : null;
    if (!target && ports.length === 1) target = ports[0];
    if (target) {
      await openMonitor(target, true);
      return;
    }
  } catch {}
  await connectMonitorInteractive();
}

// ==========================================================================
// CONSOLE / REPL
// ==========================================================================
const CTRL_A = 1, CTRL_B = 2, CTRL_C = 3, CTRL_D = 4, EOT = "\x04";

async function connectConsoleInteractive() {
  try {
    const port = await navigator.serial.requestPort();
    await openConsole(port);
  } catch (err) {
    if (err && err.name === "NotFoundError") return;
    toast("Could not connect REPL: " + (err?.message || err), "err");
  }
}

async function openConsole(port) {
  if (state.console.connected && state.console.port === port) return;
  try {
    await port.open({ baudRate: MONITOR_BAUD });
  } catch (err) {
    if (!(err && err.name === "InvalidStateError")) throw err;
  }
  state.console.port = port;
  state.console.connected = true;
  state.console.keepOpen = true;
  state.console.reconnecting = false;
  state.console.lastError = null;
  updateView();
}

function onConsoleDropped() {
  state.console.connected = false;
  try {
    state.console.port && state.console.port.close();
  } catch {}
  if (state.console.keepOpen) {
    state.console.reconnecting = true;
    scheduleConsoleReconnect(800);
  }
  updateView();
}

let consoleReconnectTimer = null;
function scheduleConsoleReconnect(delay) {
  clearTimeout(consoleReconnectTimer);
  consoleReconnectTimer = setTimeout(tryConsoleReconnect, delay);
}

async function tryConsoleReconnect() {
  if (state.console.connected || !state.console.keepOpen) return;
  try {
    const ports = await navigator.serial.getPorts();
    let target = state.console.port && ports.includes(state.console.port) ? state.console.port : null;
    if (!target && ports.length === 1) target = ports[0];
    if (!target && state.monitor.port) target = ports.find((p) => p !== state.monitor.port) || null;
    if (!target) {
      scheduleConsoleReconnect(1500);
      return;
    }
    await openConsole(target);
  } catch {
    scheduleConsoleReconnect(1500);
  }
}

async function ensureConsole() {
  if (state.console.connected && state.console.port) return;
  await connectConsoleInteractive();
  if (!state.console.connected) throw new Error("REPL console not connected");
}

function toBase64(bytes) {
  let s = "";
  for (let i = 0; i < bytes.length; i++) s += String.fromCharCode(bytes[i]);
  return btoa(s);
}

async function saveCodeViaSerial(content) {
  const port = state.console.port;
  if (!port || !state.console.connected) throw new Error("REPL console not connected");
  const writer = port.writable.getWriter();
  const reader = port.readable.getReader();
  const enc = new TextEncoder();
  const dec = new TextDecoder();
  let buf = "";
  let timedOut = false;
  const send = (d) => writer.write(d instanceof Uint8Array ? d : enc.encode(d));
  const readUntil = async (needle, ms) => {
    const t = setTimeout(() => {
      timedOut = true;
      reader.cancel().catch(() => {});
    }, ms || 5000);
    try {
      while (buf.indexOf(needle) === -1) {
        const { value, done } = await reader.read();
        if (done) throw new Error(timedOut ? "REPL timed out" : "console closed");
        buf += dec.decode(value, { stream: true });
      }
    } finally {
      clearTimeout(t);
    }
    const end = buf.indexOf(needle) + needle.length;
    const chunk = buf.slice(0, end);
    buf = buf.slice(end);
    return chunk;
  };
  const rawExec = async (code) => {
    await send(code);
    await send(new Uint8Array([CTRL_D]));
    await readUntil("OK");
    await readUntil(EOT);
    const err = await readUntil(EOT);
    await readUntil(">");
    const trace = err.replace(/\x04/g, "").trim();
    if (trace) throw new Error(trace.split("\n").pop());
  };
  try {
    await send(new Uint8Array([CTRL_C]));
    await new Promise((r) => setTimeout(r, 150));
    buf = "";
    await send(new Uint8Array([CTRL_A]));
    await readUntil("raw REPL");
    await readUntil(">");
    await rawExec("import binascii");
    await rawExec("f=open('code.py','wb')");
    const bytes = enc.encode(content);
    for (let i = 0; i < bytes.length; i += 192) {
      await rawExec("f.write(binascii.a2b_base64('" + toBase64(bytes.slice(i, i + 192)) + "'))");
    }
    await rawExec("f.close()");
    await send(new Uint8Array([CTRL_B]));
    await new Promise((r) => setTimeout(r, 80));
    await send(new Uint8Array([CTRL_D]));
  } catch (err) {
    try { reader.releaseLock(); } catch {}
    try { writer.releaseLock(); } catch {}
    onConsoleDropped();
    throw err;
  }
  try { reader.releaseLock(); } catch {}
  try { writer.releaseLock(); } catch {}
}

function appendMonitor(text) {
  if (!text) return;
  text = text.replace(/\r/g, "");
  if (!text) return;
  if (state.monitor.lastCh && state.monitor.lastCh !== "\n" &&
      /^\d+\.\d{3} \[[^\]\n]+\] /.test(text)) {
    text = "\n" + text;
  }
  text = text.replace(/(?<=[^\d.\s\n])(?=\d+\.\d{3} \[[^\]\n]+\] )/g, "\n");
  state.monitor.lastCh = text.charAt(text.length - 1);
  if (!state.monitor.sawHecate && /\[hecate\]/i.test(text)) {
    state.monitor.sawHecate = true;
    el.monitorBadge.hidden = false;
    el.monitorBadge.textContent = "Hecate";
  }
  const box = el.monitorOut;
  const atBottom = box.scrollHeight - box.scrollTop - box.clientHeight < 4;
  box.appendChild(document.createTextNode(text));
  // trim to cap
  if (box.textContent.length > MONITOR_CAP) {
    box.textContent = box.textContent.slice(-MONITOR_CAP);
  }
  if (el.autoscroll.checked && atBottom) box.scrollTop = box.scrollHeight;
}

function setMonitorStatus(text) {
  el.monitorStatus.textContent = text;
}

// ==========================================================================
// polling — keep the landing page live, auto-restore what we can
// ==========================================================================
async function poll() {
  // Drive: if we lost it but still hold a granted handle, silently restore.
  if (!state.drive.connected) {
    await restoreDrive({ silent: true }).catch(() => {});
  } else {
    // detect the drive being yanked
    try {
      const perm = await state.drive.root.queryPermission({ mode: "read" });
      if (perm !== "granted") {
        state.drive.connected = false;
      } else {
        await state.drive.root.getFileHandle("boot_out.txt");
      }
    } catch {
      state.drive.connected = false;
    }
  }
  // Monitor: if the user has connected before this session and it dropped,
  // the reconnect loop already handles it. Nothing extra needed here.
  updateView();
}

// ==========================================================================
// event wiring
// ==========================================================================
function setHint(node, text, kind) {
  node.textContent = text;
  node.className = "hint" + (kind ? " " + kind : "");
}
function timeNow() {
  // Date.now()/new Date() are fine in the browser (only forbidden in workflow scripts)
  const d = new Date();
  return d.toLocaleTimeString();
}

function switchTab(name) {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("is-active", t.dataset.pane === name));
  document.querySelectorAll(".pane").forEach((p) => p.classList.toggle("is-shown", p.dataset.pane === name));
  // CodeMirror can't measure while its pane is display:none (narrow layout);
  // re-measure once the editor becomes visible so gutters/scroll size correctly.
  if (name === "editor" && cmView) cmView.requestMeasure();
}

function wireEvents() {
  el.btnOpenDrive.addEventListener("click", pickDrive);
  el.chipDrive.addEventListener("click", () => {
    if (!state.drive.connected) pickDrive();
  });
  el.btnConnectMonitor.addEventListener("click", connectMonitorInteractive);
  el.chipMonitor.addEventListener("click", () => {
    if (!state.monitor.connected) connectMonitorInteractive();
  });
  el.chipConsole.addEventListener("click", () => {
    if (!state.console.connected) connectConsoleInteractive();
  });

  el.btnRefreshFiles.addEventListener("click", () => listDir());
  el.btnSave.addEventListener("click", saveEditor);
  el.btnRevert.addEventListener("click", revertEditor);
  el.btnEditCodepy.addEventListener("click", () => loadEditable());

  // Ctrl/Cmd+S saves (CodeMirror leaves this key unbound, so it reaches here)
  window.addEventListener("keydown", (e) => {
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") {
      e.preventDefault();
      saveEditor();
    }
  });

  el.btnClearMonitor.addEventListener("click", () => (el.monitorOut.textContent = ""));
  el.btnReconnectMonitor.addEventListener("click", reconnectMonitorClick);
  el.autoscroll.addEventListener("change", () => {
    if (el.autoscroll.checked) el.monitorOut.scrollTop = el.monitorOut.scrollHeight;
  });

  // responsive tabs
  document.querySelectorAll(".tab").forEach((t) => t.addEventListener("click", () => switchTab(t.dataset.pane)));
  switchTab("editor");

  // Web Serial hot-plug events
  if (navigator.serial) {
    navigator.serial.addEventListener("connect", () => {
      if (state.monitor.keepOpen && !state.monitor.connected) scheduleMonitorReconnect(300);
      if (state.console.keepOpen && !state.console.connected) scheduleConsoleReconnect(300);
    });
    navigator.serial.addEventListener("disconnect", (e) => {
      if (state.monitor.port && e.target === state.monitor.port) onMonitorDropped();
      if (state.console.port && e.target === state.console.port) onConsoleDropped();
    });
  }

  // warn before losing unsaved edits
  window.addEventListener("beforeunload", (e) => {
    if (isDirty()) {
      e.preventDefault();
      e.returnValue = "";
    }
  });
}

// ==========================================================================
// init
// ==========================================================================
function checkCompat() {
  const missing = [];
  if (!("serial" in navigator)) missing.push("Web Serial");
  if (!("showDirectoryPicker" in window)) missing.push("File System Access");
  if (missing.length) {
    el.landingCompat.innerHTML =
      "⚠ This browser is missing " +
      missing.join(" and ") +
      ". Use a recent <strong>Chrome, Edge, or Brave</strong> on desktop over " +
      "<code>http://localhost</code> or HTTPS.";
    el.btnConnectMonitor.disabled = !("serial" in navigator);
    el.btnOpenDrive.disabled = !("showDirectoryPicker" in window);
    return false;
  }
  return true;
}

async function init() {
  initEditor();
  wireEvents();
  const ok = checkCompat();
  updateView();
  if (ok) {
    // Try to restore a previously-granted drive without prompting.
    await restoreDrive({ silent: true }).catch(() => {});
    updateView();
  }
  setInterval(poll, POLL_MS);
}

init();
