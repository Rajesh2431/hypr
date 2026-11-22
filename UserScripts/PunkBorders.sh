#!/usr/bin/env bash
# Spider-Punk window decoration: crimson -> magenta -> blue ink border, angular corners,
# and a hard blue "misprint" offset shadow under the focused window.
# Applied at login and after every wallpaper change through RainbowBordersStartup.sh
# (mode "punk" in UserScripts/rainbow-borders.mode). To go back: pick another mode in the
# Rainbow Borders menu, or delete the mode file.
exec hyprctl eval '
hl.config({
  general = { border_size = 2,
              col = { active_border = { colors = { "rgba(ff1744ff)", "rgba(ff2e93ff)", "rgba(00b8ffff)" }, angle = 45 },
                      inactive_border = "rgba(1e151cdd)" } },
  decoration = { rounding = 4,
                 shadow = { enabled = true, range = 1, render_power = 1, offset = "5 5", sharp = true,
                            color = "rgba(00b8ffd9)", color_inactive = "rgba(05030699)" } },
  group = { col = { border_active = "rgba(ffd43bff)" } },
})' >/dev/null
