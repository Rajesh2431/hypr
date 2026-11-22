#!/usr/bin/env bash
# ==================================================
#  KoolDots (2026)
#  Project URL: https://github.com/LinuxBeginnings
#  License: GNU GPLv3
#  SPDX-License-Identifier: GPL-3.0-or-later
# ==================================================

# Modified version of Refresh.sh but waybar wont refresh
# Used by automatic wallpaper change
# Modified inorder to refresh rofi background, Wallust, SwayNC only

SCRIPTSDIR=${XDG_CONFIG_HOME:-$HOME/.config}/hypr/scripts
QS_TEXTINPUT_LOG_RULE="qt.qpa.wayland.textinput.warning=false"

# Kill already running processes
_ps=(rofi)
for _prs in "${_ps[@]}"; do
    if pidof "${_prs}" >/dev/null; then
        pkill "${_prs}"
    fi
done

# quit ags & relaunch ags
ags -q && ags &

# quit quickshell & relaunch quickshell
# quit quickshell & relaunch quickshell — but only KoolDots' own instances
# (overview, qs-hyprview…), each with its original arguments. Never touch the
# Dynamic Island / Control Center (qs -c island) or the power menu. The old
# "pkill qs && qs" killed every instance and relaunched a default config that
# doesn't exist, so the island and the overview both vanished.
for _qpid in $(pgrep -x qs); do
  _qcmd=$(tr '\0' '\n' < "/proc/$_qpid/cmdline" 2>/dev/null) || continue
  case "$_qcmd" in *island*|*powermenu*) continue ;; esac
  mapfile -t _qargs <<< "$_qcmd"
  kill "$_qpid" 2>/dev/null && (sleep 0.5; setsid "${_qargs[@]}" >/dev/null 2>&1 &) &
done


# reload swaync
(swaync-client -R -rs --skip-wait >/dev/null 2>&1 &)

# Re-apply the selected Rainbow Borders mode. The single implementation lives
# in RainbowBordersStartup.sh so this script, Refresh.sh and the wallpaper pass
# cannot drift apart.
sleep 1
if [ -x "${SCRIPTSDIR}/RainbowBordersStartup.sh" ]; then
  "${SCRIPTSDIR}/RainbowBordersStartup.sh" >/dev/null 2>&1 || true
fi

exit 0
