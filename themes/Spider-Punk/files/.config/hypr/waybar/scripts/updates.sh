#!/usr/bin/env bash
# Waybar: pending Arch updates (repo via checkupdates, AUR via yay). Hidden when 0.
#   updates.sh          print JSON for waybar
#   updates.sh run      open a terminal to update, then refresh the module
ICON=$'\U000f03d7'   # package icon
[ "${PUNK_ICONS:-}" = 1 ] && ICON=""   # Spider-Punk style: the package icon comes from CSS
if [[ $1 == run ]]; then
    kitty --class floating-update --title "System update" sh -c \
      'yay -Syu; echo; read -rp "Done — press Enter to close" _' 
    pkill -RTMIN+12 waybar
    exit 0
fi
repo=$(checkupdates 2>/dev/null)
aur=$(yay -Qua 2>/dev/null)
nr=$(grep -c . <<<"$repo"); na=$(grep -c . <<<"$aur")
total=$((nr + na))
if (( total == 0 )); then echo '{"text":""}'; exit 0; fi
list=$(printf '%s\n%s\n' "$repo" "$aur" | grep . | head -15 | awk '{printf "%s  %s → %s\\n", $1, $2, $4}' | sed 's/&/\&amp;/g; s/</\&lt;/g; s/"/\\"/g')
more=""; (( total > 15 )) && more="… and $((total - 15)) more\\n"
printf '{"text":"%s %d","class":"pending","tooltip":"<b>%d updates</b>  (%d repo · %d AUR)\\n\\n%s%s\\nClick to update"}\n' \
  "$ICON" "$total" "$total" "$nr" "$na" "$list" "$more"
