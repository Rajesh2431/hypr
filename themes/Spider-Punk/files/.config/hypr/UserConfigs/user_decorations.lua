-- ==================================================
--  KoolDots (2026)
--  Project URL: https://github.com/LinuxBeginnings
--  License: GNU GPLv3
--  SPDX-License-Identifier: GPL-3.0-or-later
-- ==================================================
-- User decorations overrides template.
-- Keep this repo copy as comments only; put active custom values in:
--   ~/.config/hypr/UserConfigs/user_decorations.lua
--
-- Uncomment and edit examples below if you want defaults in the repo template.

-- Example general overrides:
hl.config({
  general = {
    border_size = 1,
    gaps_in = 4,
    gaps_out = 6,
  },
})

-- Example decoration overrides:
hl.config({
  decoration = {
    rounding = 10,
    active_opacity = 1.0,
    inactive_opacity = 0.95,
    fullscreen_opacity = 1.0,
    dim_inactive = true,
    dim_strength = 0.1,
    dim_special = 0.8,
    shadow = {
      enabled = true,
      range = 2,
      render_power = 1,
      color = "rgba(8db4ffff)",
      color_inactive = "rgba(5f6578ff)",
    },
    blur = {
      enabled = true,
      size = 7,
      passes = 2,
      noise = 0.012,
      contrast = 1.0,
      brightness = 0.9,
      vibrancy = 0.12,
      new_optimizations = true,
      xray = false,
      ignore_opacity = true,
      special = true,
      popups = true,
    },
  },
})

-- Example group styling:
hl.config({
  group = {
    col = {
      border_active = "rgba(ffffffff)",
    },
    groupbar = {
      col = {
        active = "rgba(0f111aff)",
      },
    },
  },
})

-- Spider-Punk (2026-11-07): ink gradient border, angular corners, blue misprint shadow.
-- Same values as UserScripts/PunkBorders.sh (re-applied after wallpaper changes via rainbow-borders.mode = punk).
hl.config({
  general = {
    border_size = 2,
    col = {
      active_border = { colors = { "rgba(ff1744ff)", "rgba(ff2e93ff)", "rgba(00b8ffff)" }, angle = 45 },
      inactive_border = "rgba(1e151cdd)",
    },
  },
  decoration = {
    rounding = 4,
    shadow = { enabled = true, range = 1, render_power = 1, offset = "5 5", sharp = true,
               color = "rgba(00b8ffd9)", color_inactive = "rgba(05030699)" },
  },
  group = { col = { border_active = "rgba(ffd43bff)" } },
})
