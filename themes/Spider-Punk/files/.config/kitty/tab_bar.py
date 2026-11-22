# SPIDER-PUNK tab bar for kitty  (loaded by `tab_bar_style custom`)
#
#   ▐ 󱐋 PUNK ▌ 1 zsh  2 nvim ●  3 btop ⁽²⁾                splits ▪ ❒3
#
#  • Tabs are cut with hard diagonal slants (ripped-poster edges), no rounding.
#  • Active tab: crimson slab, bold off-white title, yellow index.
#  • Inactive tabs: oxblood paper, photocopy-grey text.
#  • Right edge: layout of the active tab + its window count (+ session name).
#  If anything here throws, kitty logs it and falls back to its built-in style,
#  so a bug can never leave you without tabs.

from kitty.fast_data_types import Screen, get_boss
from kitty.tab_bar import DrawData, ExtraData, TabBarData, as_rgb, draw_title


def _c(hexstr: str) -> int:
    return as_rgb(int(hexstr.lstrip('#'), 16))


INK      = _c('#0a0406')   # tab bar background (matches tab_bar_background)
PAPER    = _c('#1c0d12')   # inactive slab
CRIMSON  = _c('#c8243a')   # active slab
YELLOW   = _c('#f2c53d')
MAGENTA  = _c('#d63a9c')
COBALT   = _c('#3f6fff')
OFFWHITE = _c('#fff4ee')
MUTED    = _c('#a2939a')
FAINT    = _c('#6e5662')

CUT_L = ''   #   lower-right triangle  (left edge of a slab)
CUT_R = ''   #   upper-left triangle   (right edge of a slab)
SUPERSCRIPT = str.maketrans('0123456789', '⁰¹²³⁴⁵⁶⁷⁸⁹')


def _badge(screen: Screen) -> None:
    """Identity tag at the far left: yellow sticker with a lightning bolt."""
    screen.cursor.bg = INK
    screen.cursor.fg = YELLOW
    screen.draw(CUT_L)
    screen.cursor.bg = YELLOW
    screen.cursor.fg = INK
    screen.cursor.bold = True
    screen.draw(' 󱐋 PUNK ')
    screen.cursor.bold = False
    screen.cursor.bg = INK
    screen.cursor.fg = YELLOW
    screen.draw(CUT_R + ' ')


def _status_text() -> str:
    try:
        tab = get_boss().active_tab
    except Exception:
        tab = None
    if tab is None:
        return ''
    layout = tab.current_layout.name
    n = len(tab)
    session = getattr(tab, 'created_in_session_name', '') or ''
    parts = [layout]
    if n > 1:
        parts.append(f'❒{n}')
    if session:
        parts.append(f'󰆍 {session}')
    return ' ▪ '.join(parts)


def _draw_status(screen: Screen) -> None:
    text = _status_text()
    if not text:
        return
    # +3: cut glyph, leading space, trailing space (the last cell gets erased by kitty)
    width = len(text) + 4
    start = screen.columns - width
    if start <= screen.cursor.x + 1:
        return
    screen.cursor.x = start
    screen.cursor.bg = INK
    screen.cursor.fg = PAPER
    screen.draw(CUT_L)
    screen.cursor.bg = PAPER
    screen.cursor.fg = COBALT
    screen.cursor.bold = True
    screen.draw(' ' + text + ' ')
    screen.cursor.bold = False
    screen.cursor.bg = INK
    screen.draw(' ')


def draw_tab(
    draw_data: DrawData, screen: Screen, tab: TabBarData,
    before: int, max_title_length: int, index: int, is_last: bool,
    extra_data: ExtraData,
) -> int:
    if index == 1:
        _badge(screen)

    slab = CRIMSON if tab.is_active else PAPER
    fg = OFFWHITE if tab.is_active else MUTED

    # left diagonal cut
    screen.cursor.bg = INK
    screen.cursor.fg = slab
    screen.draw(CUT_L)

    # index
    screen.cursor.bg = slab
    screen.cursor.fg = YELLOW if tab.is_active else FAINT
    screen.cursor.bold = True
    screen.draw(f'{index} ')
    screen.cursor.bold = tab.is_active

    # title (honours tab_title_template / active_tab_title_template)
    screen.cursor.fg = fg
    # truncate BEFORE drawing (keeps the tail: the useful end of a path);
    # ~10 cells are reserved for cuts, index, window count and markers
    limit = max_title_length - 10
    if draw_data.max_tab_title_length > 0:
        limit = min(limit, draw_data.max_tab_title_length)
    limit = max(4, limit)
    if len(tab.title) > limit:
        tab = tab._replace(title='…' + tab.title[-(limit - 1):])
    draw_title(draw_data, screen, tab, index, max_title_length)
    screen.cursor.bold = False

    # window count when the tab is split
    if tab.num_windows > 1:
        screen.cursor.fg = YELLOW if tab.is_active else FAINT
        screen.draw(' ' + str(tab.num_windows).translate(SUPERSCRIPT))

    # attention markers
    if tab.needs_attention:
        screen.cursor.fg = YELLOW
        screen.draw(' 󰂞')
    elif tab.has_activity_since_last_focus and not tab.is_active:
        screen.cursor.fg = MAGENTA
        screen.draw(' ●')

    screen.draw(' ')
    # right diagonal cut
    screen.cursor.bg = INK
    screen.cursor.fg = slab
    screen.draw(CUT_R)
    screen.cursor.fg = INK
    screen.draw(' ')

    end = screen.cursor.x
    if is_last and not extra_data.for_layout:
        _draw_status(screen)
    return end
