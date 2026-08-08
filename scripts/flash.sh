#!/usr/bin/env bash
#
# flash.sh — flash CircuitPython + Hecate onto Xiaomao (RP2040) boards.
#
# Driven by the Makefile; run `make help` for the friendly entry points.
# Subcommands: circuitpy | hecate | all | forever | list | help
#
# Design notes
#   * Boards are identified by the *specific block device that appears*, never
#     by the CIRCUITPY / RPI-RP2 label — on a USB hub several boards share the
#     same label, so the label alone is ambiguous.
#   * If a board's filesystem is already mounted (you run an automounter), we
#     reuse that mountpoint. If not (a bare box with no automount), we mount the
#     device ourselves, to a private dir, with $SUDO. Either way works.
#   * Bootloader entry is manual: hold BOOTSEL while plugging a board in and it
#     enumerates as the RPI-RP2 drive, ready for the .uf2.
#
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIRMWARE="${FIRMWARE:-$ROOT/firmware/firmware.uf2}"
SUDO="${SUDO:-sudo}"
POLL="${POLL:-0.4}"           # seconds between device scans
WAIT_REBOOT="${WAIT_REBOOT:-45}"   # seconds to wait for a board to re-enumerate

OS="${OS:-$(uname -s)}"      # Linux or Darwin (macOS): selects discovery + mounting
VOLROOT="${VOLROOT:-/Volumes}"  # where macOS auto-mounts drives (overridable for tests)
# macOS: don't scatter ._AppleDouble sidecars onto the FAT drive during cp.
[ "$OS" = Darwin ] && export COPYFILE_DISABLE=1

# Files copied to a CIRCUITPY drive by the `hecate` step.
HECATE_FILES=(boot.py code.py hecate.py)
HECATE_DIRS=(lib)

OURS_MOUNTS=()                # mountpoints we created, for cleanup on exit
MNT=""                        # set by mount_dev to the resolved mountpoint

_umount() {
  local mnt="$1"
  sync 2>/dev/null || true
  $SUDO umount "$mnt" 2>/dev/null || $SUDO umount -l "$mnt" 2>/dev/null || true
  findmnt -rno TARGET "$mnt" >/dev/null 2>&1 && return 1
  rmdir "$mnt" 2>/dev/null || true
  return 0
}

cleanup() {
  local m
  for m in "${OURS_MOUNTS[@]:-}"; do
    [ -n "$m" ] || continue
    _umount "$m"
  done
}
trap cleanup EXIT

say()  { printf '\033[35m▸\033[0m %s\n' "$*" >&2; }        # hecate purple
ok()   { printf '\033[32m✓\033[0m %s\n' "$*" >&2; }
warn() { printf '\033[33m!\033[0m %s\n' "$*" >&2; }
die()  { printf '\033[31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

# --- device discovery ------------------------------------------------------
# Emit one "dev|label|mountpoint" line per board labelled RPI-RP2 or CIRCUITPY.
#   Linux : lsblk -P gives shell-quoted KEY="value" pairs, safe to eval; the
#           block device (/dev/...) is the handle and may be unmounted.
#   macOS : drives auto-mount under $VOLROOT/<label>; the mountpoint IS the
#           handle (no device node needed). A hub of several CIRCUITPY boards
#           gets unique paths (CIRCUITPY, "CIRCUITPY 1", …), so the mountpoint
#           disambiguates them the way the /dev node does on Linux.
list_boards() {
  if [ "$OS" = Darwin ]; then
    local v base
    for v in "$VOLROOT"/*; do
      [ -d "$v" ] || continue
      base="$(basename "$v")"
      case "$base" in
        CIRCUITPY*) printf '%s|%s|%s\n' "$v" "CIRCUITPY" "$v" ;;
        RPI-RP2*)   printf '%s|%s|%s\n' "$v" "RPI-RP2"   "$v" ;;
      esac
    done
    return
  fi
  local NAME LABEL MOUNTPOINT line
  while IFS= read -r line; do
    eval "$line"
    case "$LABEL" in
      RPI-RP2|CIRCUITPY) printf '%s|%s|%s\n' "/dev/$NAME" "$LABEL" "$MOUNTPOINT" ;;
    esac
  done < <(lsblk -Pno NAME,LABEL,MOUNTPOINT 2>/dev/null)
}

boards_with_label() { list_boards | awk -F'|' -v l="$1" '$2==l'; }

# dev|label only (no mountpoint) — a stable key for the forever loop, so a
# mountpoint that appears a moment after the device doesn't read as a new board.
list_board_keys() { list_boards | cut -d'|' -f1,2; }

# Mount a device (or reuse an existing mount); sets MNT to the mountpoint.
# On macOS the OS already mounted it under $VOLROOT and the dev handle *is* the
# mountpoint, so this is a no-op that just records MNT (nothing to unmount later,
# so OURS_MOUNTS stays empty and release_dev/cleanup naturally do nothing).
mount_dev() {
  local dev="$1" existing mnt
  if [ "$OS" = Darwin ]; then
    MNT="$dev"
    return 0
  fi
  existing="$(findmnt -nfo TARGET --source "$dev" 2>/dev/null | head -1)"
  if [ -n "$existing" ]; then MNT="$existing"; return 0; fi
  mnt="${TMPDIR:-/tmp}/hecate-flash/$(basename "$dev")"
  mkdir -p "$mnt"
  if ! $SUDO mount -o "uid=$(id -u),gid=$(id -g),flush" "$dev" "$mnt" 2>/dev/null; then
    rmdir "$mnt" 2>/dev/null || true
    return 1
  fi
  OURS_MOUNTS+=("$mnt")
  MNT="$mnt"
}

# Unmount only if we were the ones who mounted it.
release_dev() {
  local mnt="$1" i
  for i in "${!OURS_MOUNTS[@]}"; do
    if [ "${OURS_MOUNTS[$i]}" = "$mnt" ]; then
      _umount "$mnt" && unset 'OURS_MOUNTS[$i]'
      return
    fi
  done
}

# The CircuitPython version baked into the .uf2 (e.g. 10.2.0-rc.0-2-g...-dirty),
# so the skip check always matches whatever firmware is actually present.
firmware_version() {
  [ -f "$FIRMWARE" ] || return 0
  strings "$FIRMWARE" 2>/dev/null \
    | grep -m1 -oE 'CircuitPython [0-9][^ ]*' | awk '{print $2}'
}

# --- operations ------------------------------------------------------------
flash_uf2() {                       # $1 = RPI-RP2 device; returns 1 on failure
  local dev="$1" mnt
  [ -f "$FIRMWARE" ] || die "firmware not found: $FIRMWARE (run: make firmware)"
  mount_dev "$dev" || { warn "could not mount bootloader drive $dev"; return 1; }
  mnt="$MNT"
  say "writing CircuitPython → $dev"
  if ! cp "$FIRMWARE" "$mnt/"; then
    warn "failed to write firmware to $dev"
    release_dev "$mnt" 2>/dev/null || true
    return 1
  fi
  sync 2>/dev/null || true
  # The RP2040 reboots the instant the .uf2 lands, so the mount vanishes from
  # under us; the release below is best-effort.
  release_dev "$mnt" 2>/dev/null || true
  ok "CircuitPython written; board rebooting"
}

copy_hecate() {                     # $1 = CIRCUITPY device; returns 1 on failure
  local dev="$1" mnt f rc=0
  mount_dev "$dev" || { warn "could not mount CIRCUITPY drive $dev"; return 1; }
  mnt="$MNT"
  # CircuitPython exposes the drive read-only to USB whenever the *board* owns
  # write access (self-powered, BTN held at boot, or mid-session). Detect that
  # up front with a probe write, instead of failing halfway and lying about it.
  if ! (: > "$mnt/.hecate-write-test") 2>/dev/null; then
    release_dev "$mnt"
    warn "$dev is read-only to USB — CircuitPython owns the filesystem."
    warn "  Re-plug the board normally (don't hold BTN) or reset it, then retry."
    return 1
  fi
  rm -f "$mnt/.hecate-write-test" 2>/dev/null || true
  say "writing Hecate → $dev ($mnt)"
  for f in "${HECATE_FILES[@]}"; do
    if [ -f "$ROOT/$f" ]; then
      cp -f "$ROOT/$f" "$mnt/" || { warn "failed to copy $f"; rc=1; }
    else warn "missing $f, skipped"; fi
  done
  for f in "${HECATE_DIRS[@]}"; do
    [ -d "$ROOT/$f" ] && { cp -rf "$ROOT/$f" "$mnt/" || { warn "failed to copy $f/"; rc=1; }; }
  done
  sync 2>/dev/null || true
  release_dev "$mnt"
  if [ "$rc" -eq 0 ]; then ok "Hecate written to $dev"; return 0; fi
  warn "Hecate copy to $dev was incomplete (see above)"
  return 1
}

# Copy Hecate, but first note whether the board already runs our firmware.
handle_circuitpy() {                # $1 = CIRCUITPY device
  local dev="$1" mnt want
  want="$(firmware_version)"
  mount_dev "$dev" || { warn "could not mount $dev"; return 1; }
  mnt="$MNT"
  if [ -n "$want" ] && grep -qF "$want" "$mnt/boot_out.txt" 2>/dev/null; then
    say "$dev already runs CircuitPython $want — skipping firmware"
  elif [ -n "$want" ]; then
    warn "$dev runs a different CircuitPython (want $want); hold BOOTSEL to reflash"
  fi
  copy_hecate "$dev"
}

# Wait until a CIRCUITPY device shows up that isn't in the exclusion set.
wait_for_circuitpy() {              # $1 = newline-separated devices to ignore
  local ignore="$1" deadline dev
  deadline=$(( SECONDS + WAIT_REBOOT ))
  while [ "$SECONDS" -lt "$deadline" ]; do
    while IFS='|' read -r dev _ _; do
      [ -n "$dev" ] || continue
      grep -qxF "$dev" <<<"$ignore" || { echo "$dev"; return 0; }
    done < <(boards_with_label CIRCUITPY)
    sleep "$POLL"
  done
  return 1
}

# --- subcommands -----------------------------------------------------------
cmd_list() {
  local any=0 dev label mnt
  while IFS='|' read -r dev label mnt; do
    [ -n "$dev" ] || continue
    any=1
    printf '  %-10s %-10s %s\n' "$dev" "$label" "${mnt:-(unmounted)}"
  done < <(list_boards)
  [ "$any" = 1 ] || echo "  (no Xiaomao boards detected)"
}

one_device() {                      # $1 = label; echoes the one device, else
  local label="$1" devs n           # returns 1 (none) or 2 (more than one)
  devs="$(boards_with_label "$label" | cut -d'|' -f1)"
  [ -z "$devs" ] && return 1
  n="$(printf '%s\n' "$devs" | grep -c .)"
  if [ "$n" -gt 1 ]; then
    warn "multiple $label boards on the bus — use 'make forever' for a hub"
    return 2
  fi
  echo "$devs"
}

cmd_circuitpy() {
  local dev rc
  dev="$(one_device RPI-RP2)"; rc=$?
  [ "$rc" -eq 1 ] && die "no board in BOOTSEL mode. Hold BOOTSEL while plugging the Xiaomao in."
  [ "$rc" -eq 2 ] && exit 1
  flash_uf2 "$dev" || die "firmware not written"
}

cmd_hecate() {
  local dev rc
  dev="$(one_device CIRCUITPY)"; rc=$?
  [ "$rc" -eq 1 ] && die "no CIRCUITPY drive found. Plug the board in normally (not BOOTSEL)."
  [ "$rc" -eq 2 ] && exit 1
  handle_circuitpy "$dev" || die "Hecate not written — see the note above"
}

cmd_all() {
  local dev newdev
  if dev="$(one_device RPI-RP2)"; then
    flash_uf2 "$dev" || die "firmware not written"
    say "waiting for the board to come back as CIRCUITPY…"
    newdev="$(wait_for_circuitpy "")" || die "board did not re-enumerate as CIRCUITPY within ${WAIT_REBOOT}s"
    copy_hecate "$newdev" || die "Hecate not written — see the note above"
  elif dev="$(one_device CIRCUITPY)"; then
    warn "board already runs CircuitPython; skipping firmware (hold BOOTSEL to reflash)"
    handle_circuitpy "$dev" || die "Hecate not written — see the note above"
  else
    die "no board found. Hold BOOTSEL and plug in for a fresh flash, or plug in normally to just load Hecate."
  fi
  ok "done"
}

cmd_forever() {
  say "Hub mode: hold BOOTSEL and plug in each Xiaomao. Ctrl-C to stop."
  [ -f "$FIRMWARE" ] || die "firmware not found: $FIRMWARE (run: make firmware)"
  say "firmware: CircuitPython $(firmware_version)"
  local count=0 seen cur new dev label
  seen="$(list_board_keys)"         # ignore boards already on the bus at start
  while true; do
    cur="$(list_board_keys)"
    new="$(comm -13 <(sort <<<"$seen") <(sort <<<"$cur") 2>/dev/null)"
    while IFS='|' read -r dev label; do
      [ -n "$dev" ] || continue
      case "$label" in
        RPI-RP2)
          say "[$dev] fresh board — flashing CircuitPython"
          flash_uf2 "$dev" || warn "[$dev] flash failed — skipping"
          ;;                        # on success it reappears as CIRCUITPY next
        CIRCUITPY)
          if handle_circuitpy "$dev"; then
            count=$((count+1)); ok "board #$count done ($dev)"
          else
            warn "[$dev] not written (read-only? re-plug normally to retry) — skipping"
          fi
          ;;
      esac
    done <<<"$new"
    seen="$cur"
    sleep "$POLL"
  done
}

cmd_help() {
  cat >&2 <<EOF
flash.sh <command>   (usually invoked via the Makefile)

  circuitpy   Flash CircuitPython to the one board in BOOTSEL mode
  hecate      Copy Hecate onto the one CIRCUITPY board
  all         Flash CircuitPython, wait for reboot, then copy Hecate
  forever     Hub loop: flash every board as it's plugged in (BOOTSEL),
              skipping the firmware step when it already matches. Ctrl-C to stop.
  list        Show detected boards (debugging)

  Env: FIRMWARE=$FIRMWARE
       SUDO=$SUDO   (set SUDO= to disable if already root)
EOF
}

case "${1:-help}" in
  circuitpy) cmd_circuitpy ;;
  hecate)    cmd_hecate ;;
  all)       cmd_all ;;
  forever)   cmd_forever ;;
  list)      cmd_list ;;
  help|-h|--help) cmd_help ;;
  *) die "unknown command: ${1:-}. Try: circuitpy | hecate | all | forever | list" ;;
esac
