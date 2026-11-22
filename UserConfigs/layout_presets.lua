-- Window layout presets (UserScripts/Layouts.py, menu: Arch logo -> Window layout).
--   "lua:grid": a real grid layout (windows split evenly, columns = ceil(sqrt(n))).
-- Per-workspace layout + options are hl.workspace_rule lines in UserConfigs/workspaces.lua.
-- Column widths of the Columns / Focus Column presets are kept by `Layouts.py watch`
-- (the Scrolling layout resets widths when a window opens; hl.timer proved unreliable for this).
hl.layout.register("grid", {
  recalculate = function(ctx)
    local n = #ctx.targets
    if n == 0 then return end
    local cols = math.ceil(math.sqrt(n))
    local rows = math.ceil(n / cols)
    for i, t in ipairs(ctx.targets) do
      t:place(ctx:grid_cell(i, cols, rows))
    end
  end,
})
-- drop the window.open hook of an earlier version if the Lua state survived a reload
if LP and LP.sub then pcall(function() LP.sub:remove() end); LP.sub = nil end
