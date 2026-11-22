#!/usr/bin/env bash
# ==================================================
#  KoolDots (2026)
#  Project URL: https://github.com/LinuxBeginnings
#  License: GNU GPLv3
#  SPDX-License-Identifier: GPL-3.0-or-later
# ==================================================
# WaybarCava.sh — one cava stream per Waybar instance
# Original concept by LinuxBeginnings; this variant focuses on lifecycle hardening.

set -euo pipefail

# Ensure cava exists
if ! command -v cava >/dev/null 2>&1; then
  echo "cava not found in PATH" >&2
  exit 1
fi

# 0..7 → ▁▂▃▄▅▆▇█
bar="▁▂▃▄▅▆▇█"
dict="s/;//g"
bar_length=${#bar}
for ((i = 0; i < bar_length; i++)); do
  dict+=";s/$i/${bar:$i:1}/g"
done

# Each bar gets its own stream. A global pidfile/pkill would make a second
# bar terminate the first bar's visualizer.
RUNTIME_DIR="${XDG_RUNTIME_DIR:-/tmp}"
pidfile="$RUNTIME_DIR/waybar-cava.$$.pid"

# Unique temp config + cleanup on exit
config_file="$(mktemp "$RUNTIME_DIR/waybar-cava.XXXXXX.conf")"
cleanup() {
  # Kill children (cava, sed) of this script, then remove our own files
  pkill -P "$$" 2>/dev/null || true
  rm -f "$config_file" "$pidfile"
}
trap cleanup EXIT INT TERM
printf '%d' $$ >"$pidfile"

# If Waybar is killed without signaling its custom modules, the pipe can stay
# open while cava is idle, so SIGPIPE alone may never terminate this stream.
# Stay alive only while at least one Waybar process exists; this also handles
# reparenting after an ungraceful bar shutdown.
(
  while pgrep -x "waybar" >/dev/null 2>&1 || pgrep -x '.waybar-wrapped' >/dev/null 2>&1; do
    sleep 2
  done
  kill -TERM "$$" 2>/dev/null || true
) &

cat >"$config_file" <<EOF
[general]
framerate = 30
bars = 10

[input]
method = pulse
source = auto

[output]
method = raw
raw_target = /dev/stdout
data_format = ascii
ascii_max_range = 7
EOF

# Stream cava output and translate digits 0..7 to bar glyphs
# (no exec: keep this shell as the parent so the trap can reap children)
cava -p "$config_file" | sed -u "$dict"
