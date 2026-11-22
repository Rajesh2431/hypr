#!/bin/bash
# D-Bus activation target for org.freedesktop.Notifications -> the Dynamic Island.
# (~/.local/share/dbus-1/services/org.erikreider.swaync.service)
#
# Why a wrapper: something sends a notification in the first second of login, before
# Hyprland exists. Starting `qs -c island` then aborts ("no Wayland display"), and D-Bus
# retried for every notification: ~28 quickshell crashes (and core dumps) per login.
#
# Now: wait for the desktop. Normally the session's own startup entry launches the
# island (with the full Hyprland environment) and takes the bus name; then this just
# exits. Only if no island shows up once Wayland is ready does it start one itself.
rt="${XDG_RUNTIME_DIR:-/run/user/$(id -u)}"
running() { pgrep -f "qs -c island$" >/dev/null 2>&1; }

wl=""
ready_at=0
i=0
while [ "$i" -lt 100 ]; do                      # up to 20 s
  running && exit 0                             # the startup entry (or another activation) won
  if [ -z "$wl" ]; then
    for s in "$rt"/wayland-[0-9]*; do
      case "$s" in *.lock | *awww*) continue ;; esac
      [ -S "$s" ] && { wl="$(basename "$s")"; ready_at="$i"; break; }
    done
  elif [ $((i - ready_at)) -ge 15 ]; then       # desktop up for 3 s and still no island
    break
  fi
  i=$((i + 1))
  sleep 0.2
done
[ -n "$wl" ] || exit 0                          # no desktop: nothing to show notifications on
running && exit 0

# take the session environment Hyprland exported (WAYLAND_DISPLAY, HYPRLAND_INSTANCE_SIGNATURE, ...)
eval "$(systemctl --user show-environment 2>/dev/null | sed -n 's/^\([A-Za-z_][A-Za-z0-9_]*\)=\(.*\)$/export \1=\2/p')"
[ -n "${WAYLAND_DISPLAY:-}" ] || export WAYLAND_DISPLAY="$wl"
if [ -z "${HYPRLAND_INSTANCE_SIGNATURE:-}" ]; then
  for d in "$rt"/hypr/*/; do
    [ -S "${d}.socket.sock" ] && { HYPRLAND_INSTANCE_SIGNATURE="$(basename "$d")"; export HYPRLAND_INSTANCE_SIGNATURE; break; }
  done
fi
exec env __EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/50_mesa.json /usr/bin/qs -c island
