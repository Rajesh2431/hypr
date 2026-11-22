#!/usr/bin/env bash
# waybar clock middle-click: ask how many minutes, then start the island timer
m=$(printf '5\n10\n15\n25\n45\n60\n' | rofi -dmenu -p "Timer (minutes)" -theme-str 'window { width: 320px; } listview { lines: 6; }')
case "$m" in ''|*[!0-9]*) exit 0 ;; esac
[ "$m" -gt 0 ] && qs ipc -c island call timer start "$m"
