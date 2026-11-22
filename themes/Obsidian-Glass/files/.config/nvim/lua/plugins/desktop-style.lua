-- Desktop style: Obsidian Glass (per-style file managed by ~/.config/hypr/UserScripts/Styles.sh).
-- tokyonight "night", transparent so kitty's frosted glass shows through, recoloured to the Obsidian palette.
-- C/C++ and other languages are highlighted by LazyVim's treesitter as usual.
return {
  {
    "folke/tokyonight.nvim",
    opts = {
      style = "night",
      transparent = true,
      styles = { sidebars = "transparent", floats = "transparent", comments = { italic = true } },
      on_colors = function(c)
        c.bg = "#101116"; c.bg_dark = "#101116"; c.bg_float = "#191B23"; c.bg_sidebar = "#101116"
        c.bg_highlight = "#191B23"; c.bg_visual = "#2A3A50"; c.border = "#394251"
        c.fg = "#E6E8F0"; c.fg_dark = "#9CA4B5"; c.comment = "#687184"; c.fg_gutter = "#3A4150"
        c.blue = "#78B9E7"; c.cyan = "#7ED6DE"
      end,
    },
  },
  { "LazyVim/LazyVim", opts = { colorscheme = "tokyonight-night" } },
}
