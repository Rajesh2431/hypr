-- ==================================================
--  KoolDots (2026)
--  Project URL: https://github.com/LinuxBeginnings
--  License: GNU GPLv3
--  SPDX-License-Identifier: GPL-3.0-or-later
-- ==================================================
-- User animation overrides template.
-- Use this to override defaults from lua/animations.lua.

-- Example:
-- hl.config({
--   animations = {
--     enabled = true,
--   },
-- })
--
-- hl.animation({ leaf = "windows", enabled = true, speed = 5, bezier = "wind", style = "slide" })

-- Obsidian Glass: short, understated motion (no bounce, nothing continuous)
hl.config({ animations = { enabled = true } })
hl.curve("glass", { type = "bezier", points = { { 0.22, 1 }, { 0.36, 1 } } })
hl.curve("glassIn", { type = "bezier", points = { { 0.4, 0 }, { 0.2, 1 } } })
hl.animation({ leaf = "windows", enabled = true, speed = 3.5, bezier = "glass", style = "popin 92%" })
hl.animation({ leaf = "windowsOut", enabled = true, speed = 2.5, bezier = "glassIn", style = "popin 92%" })
hl.animation({ leaf = "border", enabled = true, speed = 6, bezier = "glass" })
hl.animation({ leaf = "fade", enabled = true, speed = 3, bezier = "glass" })
hl.animation({ leaf = "layers", enabled = true, speed = 3, bezier = "glass", style = "fade" })
hl.animation({ leaf = "workspaces", enabled = true, speed = 4, bezier = "glass", style = "slidefade 12%" })
hl.animation({ leaf = "specialWorkspace", enabled = true, speed = 3.5, bezier = "glass", style = "slidevert" })
