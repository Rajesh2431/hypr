-- User keybind overrides.
-- Add, override, or rebind keybinds here.
--
-- =============================================================================
-- KEYBIND RULES & SYNTAX
-- =============================================================================
-- • bind("MODS", "KEY", action, [options])
-- • unbind("MODS", "KEY")
--
-- Supported modifiers:
--   "SUPER", "SHIFT", "CTRL", "ALT", or combinations like "SUPER SHIFT", "SUPER ALT"
--
-- Actions:
--   • exec_cmd("command")       -> launches a terminal command or script
--   • dispatch("dispatcher", [arg]) -> triggers a Hyprland dispatcher (e.g. killactive, togglefloating)
--
-- =============================================================================
-- EXAMPLES
-- =============================================================================
--
-- NOTE ON LUA REBINDS:
--   Yes — same rule as Hyprlang applies in practice: if a key combo is already bound,
--   unbind("MODS", "KEY") first, then bind(...) it to the new action.
--   This keeps behavior explicit and avoids duplicate/conflicting binds.
--
-- 1. ADDING A BRAND NEW KEYBIND (combo not used by default):
--    bind("SUPER", "Z", exec_cmd("ghostty"), { description = "Launch Ghostty" })
--    bind("SUPER SHIFT", "V", exec_cmd("pavucontrol"), { description = "Audio Control" })
--    bind("SUPER", "X", dispatch("killactive"), { description = "Close active window" })
--
-- 2. OVERRIDING AN EXISTING COMBO WITH A DIFFERENT APP/COMMAND:
--    -- To replace what SUPER+Return opens (default: kitty):
--    unbind("SUPER", "Return")
--    bind("SUPER", "Return", exec_cmd("ghostty"), { description = "Launch Ghostty" })
--
-- 3. REBINDING / MOVING AN ACTION TO A NEW KEY COMBINATION:
--    -- Example: Move File Manager from SUPER+E to SUPER+F, and use SUPER+E for Emacs:
--    unbind("SUPER", "E")       -- unbind default file manager from SUPER+E
--    unbind("SUPER", "F")       -- unbind whatever SUPER+F was doing (default: fake fullscreen)
--    bind("SUPER", "F", exec_cmd("$HOME/.config/hypr/scripts/LaunchFileManager.sh '$files' '$term'"), { description = "File manager" })
--    bind("SUPER", "E", exec_cmd("emacsclient -c -a 'emacs'"), { description = "Launch Emacs" })
--
-- 4. REBINDING COMPOSITOR DISPATCHERS (e.g. workspace, fullscreen, floating):
--    unbind("SUPER", "Q")
--    bind("SUPER", "Q", dispatch("killactive"), { description = "Close active window" })
--    unbind("SUPER", "F") -- default fakefullscreen
--    bind("SUPER SHIFT", "F", dispatch("fullscreen", "0"), { description = "Toggle fullscreen" })
--    bind("SUPER ALT", "W", dispatch("workspace", "special:scratchpad"), { description = "Toggle scratchpad" })
--
-- 5. BIND OPTIONS (locked, repeating):
--    -- locked = true     -> runs even when lockscreen is active (e.g. media keys)
--    -- repeating = true  -> repeats when key is held down (e.g. volume / brightness)
--    bind("CTRL ALT", "bracketright", exec_cmd("$HOME/.config/hypr/scripts/Brightness.sh --inc"), { description = "Brightness up", repeating = true })
--    bind("", "XF86AudioMute", exec_cmd("$HOME/.config/hypr/scripts/Volume.sh --toggle"), { description = "Mute audio", locked = true })
--
-- =============================================================================
local user_keybinds_helper = nil
do
  local source = (debug.getinfo(1, "S") or {}).source or ""
  local source_path = source:match("^@(.+)$")
  local source_dir = source_path and source_path:match("^(.*)/[^/]+$") or nil
  local home = os.getenv("HOME") or ""
  local candidate_paths = {
    source_dir and (source_dir .. "/../lua/user_keybinds_helper.lua") or nil,
    home ~= "" and (home .. "/.config/hypr/lua/user_keybinds_helper.lua") or nil,
    home ~= "" and (home .. "/.config/hypr/user_keybinds_helper.lua") or nil,
  }

  local tried_paths = {}
  for _, helper_path in ipairs(candidate_paths) do
    if helper_path then
      table.insert(tried_paths, helper_path)
      local f = io.open(helper_path, "r")
      if f then
        f:close()
        local loaded_ok, loaded_helpers = pcall(dofile, helper_path)
        if loaded_ok and type(loaded_helpers) == "table" and loaded_helpers.bind then
          user_keybinds_helper = loaded_helpers
          break
        end
      end
    end
  end

  if not user_keybinds_helper then
    error("Failed to load user_keybinds_helper.lua from: " .. table.concat(tried_paths, ", "))
  end
end
local exec_cmd = user_keybinds_helper.exec_cmd
local dispatch = user_keybinds_helper.dispatch
local bind = user_keybinds_helper.bind
local unbind = user_keybinds_helper.unbind

-- =============================================================================
-- USER KEYBINDS
-- =============================================================================

-- SUPER+V: clipboard (cliphist via rofi)
bind("SUPER", "V", exec_cmd("$HOME/.config/hypr/scripts/ClipManager.sh"), { description = "Clipboard manager" })

-- SUPER+K: Konsole terminal (unbind KoolDots' "cycle previous window" first, else both ran)
unbind("SUPER", "K")
bind("SUPER", "K", exec_cmd("konsole"), { description = "Launch Konsole" })

-- SUPER+F: Firefox (unbind maximize, replace with Firefox)
unbind("SUPER", "F")
bind("SUPER", "F", exec_cmd("firefox"), { description = "Launch Firefox" })

-- SUPER+B: Google Chrome (unbind default xdg-open browser, replace with Chrome)
unbind("SUPER", "B")
bind("SUPER", "B", exec_cmd("google-chrome-stable"), { description = "Launch Google Chrome" })

-- SUPER+L: lock screen (hyprlock)
bind("SUPER", "L", exec_cmd("hyprlock"), { description = "Lock screen" })

-- SUPER+SHIFT+F: keep toggle fullscreen (original behavior preserved)
unbind("SUPER SHIFT", "F")
bind("SUPER SHIFT", "F", dispatch("fullscreen", ""), { description = "Toggle fullscreen" })

-- =============================================================================
-- LOSSLESS SCREENSHOTS (UserScripts/lossless-screenshot.sh)
-- Uncompressed PNG (-l 0), grim + slurp
-- --clipboard-only: no files written, no popup, no auto-open
-- =============================================================================
local shot = "$HOME/.config/hypr/UserScripts/lossless-screenshot.sh --clipboard-only"

-- Full screen / all monitors
unbind("SUPER", "Print")
bind("SUPER", "Print", exec_cmd(shot .. " --full"), { description = "Screenshot: all monitors" })

-- Region selection
unbind("SUPER SHIFT", "Print")
bind("SUPER SHIFT", "Print", exec_cmd(shot .. " --region"), { description = "Screenshot: region" })

-- Delayed full screen
unbind("SUPER CTRL", "Print")
bind("SUPER CTRL", "Print", exec_cmd(shot .. " --in5"), { description = "Screenshot: in 5s" })

unbind("SUPER CTRL SHIFT", "Print")
bind("SUPER CTRL SHIFT", "Print", exec_cmd(shot .. " --in10"), { description = "Screenshot: in 10s" })

-- Active window
unbind("ALT", "Print")
bind("ALT", "Print", exec_cmd(shot .. " --active"), { description = "Screenshot: active window" })

-- Pick a window
bind("SUPER ALT", "Print", exec_cmd(shot .. " --window"), { description = "Screenshot: pick window" })

-- Region (clipboard only, no editor)
unbind("SUPER SHIFT", "S")
bind("SUPER SHIFT", "S", exec_cmd(shot .. " --region"), { description = "Screenshot: region (clipboard)" })

-- F6 variants (laptops without a Print key)
unbind("SUPER", "F6")
bind("SUPER", "F6", exec_cmd(shot .. " --full"), { description = "Screenshot: all monitors (F6)" })

unbind("SUPER SHIFT", "F6")
bind("SUPER SHIFT", "F6", exec_cmd(shot .. " --region"), { description = "Screenshot: region (F6)" })

unbind("SUPER CTRL", "F6")
bind("SUPER CTRL", "F6", exec_cmd(shot .. " --in5"), { description = "Screenshot: in 5s (F6)" })

unbind("SUPER ALT", "F6")
bind("SUPER ALT", "F6", exec_cmd(shot .. " --in10"), { description = "Screenshot: in 10s (F6)" })

unbind("ALT", "F6")
bind("ALT", "F6", exec_cmd(shot .. " --active"), { description = "Screenshot: active window (F6)" })

-- Replace hyprshot region binding
unbind("ALT SHIFT", "S")
bind("ALT SHIFT", "S", exec_cmd(shot .. " --region"), { description = "Screenshot: region (ALT+SHIFT+S)" })


-- Spider-Punk desktop: Do Not Disturb (Super+Shift+N opens the Control Center)
bind("SUPER CTRL", "N", exec_cmd("qs ipc -c island call center dnd"), { description = "Do Not Disturb on/off" })

-- Desktop styles: switch between saved looks (UserScripts/Styles.sh, saved in ~/.config/hypr/themes)
bind("SUPER ALT", "T", exec_cmd("$HOME/.config/hypr/UserScripts/Styles.sh menu"), { description = "Switch desktop style" })

-- Wallpaper: image / video switcher (UserScripts/VideoWall.py; videos in ~/Videos/Wallpapers)
bind("SUPER ALT", "W", exec_cmd("$HOME/.config/hypr/UserScripts/VideoWall.py menu"), { description = "Image / video wallpaper" })

-- Window layout presets: cycle all 10 (Dwindle, Master, Centered Master, Master Top, Scrolling, Columns,
-- Focus Column, Monocle, Tabbed, Grid) on the current workspace. Replaces KoolDots' 4-layout toggle.
unbind("SUPER ALT", "L")
bind("SUPER ALT", "L", exec_cmd("$HOME/.config/hypr/UserScripts/Layouts.py next"), { description = "Next window layout" })
bind("SUPER ALT SHIFT", "L", exec_cmd("$HOME/.config/hypr/UserScripts/Layouts.py prev"), { description = "Previous window layout" })

-- =============================================================================
-- Shortcut audit (2026-11-22): conflicts + leftovers
-- =============================================================================
-- SUPER+TAB / SUPER+SHIFT+TAB were bound twice (KoolDots: tab-group switch AND next/previous workspace,
-- both ran). One smart key now: inside a tab group (e.g. the Tabbed layout) -> next/previous tab,
-- otherwise -> next/previous workspace.
unbind("SUPER", "Tab")
unbind("SUPER SHIFT", "Tab")
local function run_dispatcher(d)
  if type(d) == "function" then d() elseif d then hl.dispatch(d) end
end
local tab_next, tab_prev = dispatch("changegroupactive", "f"), dispatch("changegroupactive", "b")
local ws_next, ws_prev = dispatch("workspace", "e+1"), dispatch("workspace", "e-1")
local function in_tab_group()
  local w = hl.get_active_window and hl.get_active_window()
  return w ~= nil and w.group ~= nil and (w.group.size or 0) > 1
end
bind("SUPER", "Tab", function() run_dispatcher(in_tab_group() and tab_next or ws_next) end,
  { description = "next tab (in a tab group) / next workspace" })
bind("SUPER SHIFT", "Tab", function() run_dispatcher(in_tab_group() and tab_prev or ws_prev) end,
  { description = "previous tab (in a tab group) / previous workspace" })

-- Leftovers for things this desktop no longer uses:
unbind("SUPER CTRL", "A")         -- "Ags overview": ags is not installed, it only ran the same overview as SUPER+A
unbind("SUPER CTRL", "W")         -- wlogout theme selector: the power menu is the Quickshell one now
unbind("SUPER CTRL SHIFT", "W")   -- wlogout dynamic-wallpaper selector: same reason

-- SUPER+H: cheat sheet built from the live shortcuts (always current; replaces KoolDots' fixed list)
unbind("SUPER", "H")
bind("SUPER", "H", exec_cmd("$HOME/.config/hypr/UserScripts/KeyHints.py"), { description = "help / cheat sheet (all shortcuts)" })
