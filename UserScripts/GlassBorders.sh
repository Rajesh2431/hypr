#!/usr/bin/env bash
# Obsidian Glass window decoration: thin soft gray-blue border, rounded corners, soft wide shadow.
# Applied at login and after every wallpaper change through RainbowBordersStartup.sh
# (mode "glass" in UserScripts/rainbow-borders.mode). Same values as the Obsidian block in user_decorations.lua.
exec hyprctl eval '
hl.config({
  general = { border_size = 1,
              col = { active_border = { colors = { "rgba(78b9e7aa)", "rgba(7ed6de66)" }, angle = 135 },
                      inactive_border = "rgba(39425166)" } },
  decoration = { rounding = 12,
                 shadow = { enabled = true, range = 18, render_power = 3, offset = "0 6", sharp = false,
                            color = "rgba(00000077)", color_inactive = "rgba(00000044)" } },
  group = { col = { border_active = "rgba(78b9e7cc)" } },
})' >/dev/null
