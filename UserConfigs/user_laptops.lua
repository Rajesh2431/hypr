-- ==================================================
--  KoolDots (2026)
--  Project URL: https://github.com/LinuxBeginnings
--  License: GNU GPLv3
--  SPDX-License-Identifier: GPL-3.0-or-later
-- ==================================================
-- User laptop overrides template.
-- Add lid/display behavior here if you need laptop-specific logic.

-- Examples:
-- hl.monitor({ output = "eDP-1", mode = "preferred", position = "auto", scale = "1" })
-- hl.monitor({ output = "eDP-1", disabled = true })

-- Lid handling goes through UserScripts/LidGuard.sh (2026-11-11).
-- The old rule here disabled eDP-1 on EVERY lid close. Without an external monitor
-- that left Hyprland with no screen while hyprlock started and the system suspended:
-- lid closed while unlocked -> the machine went down right after opening in 5 of 6 cases,
-- and waybar aborted on about half of all wakes. LidGuard only switches the panel off
-- when an external monitor is connected (clamshell); otherwise logind just suspends.
-- Previous version: user_laptops.lua.bak-lid
hl.bind("switch:on:Lid Switch", function()
  hl.exec_cmd(os.getenv("HOME") .. "/.config/hypr/UserScripts/LidGuard.sh close")
end)

hl.bind("switch:off:Lid Switch", function()
  hl.exec_cmd(os.getenv("HOME") .. "/.config/hypr/UserScripts/LidGuard.sh open")
end)

-- ROG/Armory Crate button: open asusctl (was rog-control-center)
hl.unbind("", "xf86Launch1")
