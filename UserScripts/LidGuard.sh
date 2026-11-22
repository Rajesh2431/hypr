#!/usr/bin/env bash
# Lid handling that never leaves Hyprland with zero monitors.
#
#   LidGuard.sh close    lid closed
#   LidGuard.sh open     lid opened
#   LidGuard.sh resume   after sleep (hypridle after_sleep_cmd): safety net
#
# Why: the old rule disabled eDP-1 on every lid close. With no external monitor
# that is the ONLY screen, so Hyprland had no output exactly while hyprlock was
# starting and logind was suspending. Journal 25 Oct - 11 Nov 2026: lid closed
# while unlocked -> the machine went down within 2 minutes of opening the lid in
# 5 of 6 cases (vs 5 of 57 when it was already locked), and waybar aborted on
# about half of all wakes.
#
# Now: the panel is only switched off in clamshell mode (an external monitor is
# connected, logind does not suspend then). Otherwise it is left alone: logind
# suspends and hypridle locks before sleep.
# Log: $XDG_RUNTIME_DIR/hypr_lidguard.log
set -u
ACTION="${1:-}"
LOG="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/hypr_lidguard.log"
INTERNAL_RE='^(eDP|LVDS|DSI)-'

log() { printf '%s %s\n' "$(date '+%F %T')" "$*" >>"$LOG" 2>/dev/null || true; }

internal() {
  hyprctl monitors all -j 2>/dev/null |
    jq -r --arg re "$INTERNAL_RE" 'first(.[] | select(.name | test($re)) | .name) // "eDP-1"' 2>/dev/null || echo eDP-1
}
# real external monitors that are enabled (headless / fallback outputs do not count)
externals() {
  hyprctl monitors -j 2>/dev/null |
    jq --arg re "$INTERNAL_RE" '[.[] | select((.name | test($re)) | not) | select(.name | test("^(HEADLESS|FALLBACK)") | not)] | length' 2>/dev/null || echo 0
}
is_disabled() {
  hyprctl monitors all -j 2>/dev/null | jq -e --arg m "$1" '.[] | select(.name == $m) | .disabled == true' >/dev/null 2>&1
}
lid_is_open() { grep -q open /proc/acpi/button/lid/*/state 2>/dev/null; }

enable_panel() {
  local mon="$1" i
  for i in 1 2 3; do
    hyprctl -r eval "hl.monitor({ output = [[$mon]], disabled = false })" >>"$LOG" 2>&1 || true
    hyprctl dispatch hl.dsp.dpms "{ action = \"on\" }" >>"$LOG" 2>&1 || true
    is_disabled "$mon" || { log "panel $mon is on"; return 0; }
    sleep 0.3
  done
  log "WARNING: $mon still disabled after 3 tries"
}

mon="$(internal)"
case "$ACTION" in
  close)
    n="$(externals)"
    if [ "${n:-0}" -gt 0 ]; then
      log "lid closed, $n external monitor(s): clamshell, switching $mon off"
      hyprctl -r eval "hl.monitor({ output = [[$mon]], disabled = true })" >>"$LOG" 2>&1 || true
    else
      log "lid closed, no external monitor: leaving $mon on (logind suspends, hypridle locks)"
    fi
    ;;
  open)
    if is_disabled "$mon"; then log "lid opened: $mon was off, switching it on"; enable_panel "$mon"
    else log "lid opened: $mon already on"; fi
    ;;
  resume)
    # after sleep: if the lid is open but the panel is off (a missed lid event), bring it back
    if lid_is_open && is_disabled "$mon"; then log "resume: lid open but $mon off, switching it on"; enable_panel "$mon"
    else log "resume: nothing to do (lid $(lid_is_open && echo open || echo closed))"; fi
    ;;
  *) echo "usage: $0 close|open|resume" >&2; exit 2 ;;
esac
