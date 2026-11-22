#!/usr/bin/env bash
# Waybar custom/clipboard: icon only; tooltip = how many entries cliphist holds and the latest one.
# Click (module config) opens the history picker (scripts/ClipManager.sh, Super+V).
n=$(cliphist list 2>/dev/null | wc -l)
last=$(cliphist list 2>/dev/null | head -1 | cut -f2- | cut -c1-60 | sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g; s/\\/\\\\/g; s/"/\\"/g' | tr -d '\000-\037')
printf '{"text":" ","class":"%s","tooltip":"<b>Clipboard</b>  %s items\\nLatest: %s\\n<span alpha=\\"55%%\\" size=\\"small\\">Click: history (Super+V) · Right-click: clear history</span>"}\n' \
  "$([ "$n" -gt 0 ] && echo has || echo empty)" "$n" "${last:-–}"
