-- ==================================================
--  KoolDots (2026)
--  Project URL: https://github.com/LinuxBeginnings
--  License: GNU GPLv3
--  SPDX-License-Identifier: GPL-3.0-or-later
-- ==================================================
-- User environment overrides template.
-- Keep this file for personal env additions that should survive updates.

-- Examples:
-- hl.env("QT_QPA_PLATFORMTHEME", "qt6ct")
-- hl.env("GDK_SCALE", "1")
-- hl.env("QT_SCALE_FACTOR", "1")
hl.env("WEATHER_UNITS", "metric")

-- Spider-Punk cursors (~/.local/share/icons/Spider-Punk-Cursor, built by
-- ~/.config/hypr/waybar/assets/punk/cursors/make-cursors.py). Previous: Bibata-Modern-Ice
hl.env("HYPRCURSOR_THEME", "Spider-Punk-Cursor")
hl.env("XCURSOR_THEME", "Spider-Punk-Cursor")
