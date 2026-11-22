#!/usr/bin/env bash
# Power menu (Quickshell) — replaces wlogout. Toggles on repeated calls.
# Original wlogout launcher kept as Wlogout.sh.wlogout-backup
CFG="$HOME/.config/quickshell/powermenu"
if pgrep -f "^qs -p $CFG" >/dev/null; then
    pkill -f "^qs -p $CFG"
    exit 0
fi
pkill -x wlogout 2>/dev/null
exec env __EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/50_mesa.json qs -p "$CFG" >/dev/null 2>&1   # render on the AMD iGPU
