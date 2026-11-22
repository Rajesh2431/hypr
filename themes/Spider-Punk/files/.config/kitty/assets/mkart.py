# Builds ~/.config/kitty/assets/spiderpunk-ascii.txt (fastfetch $N colour codes)
# and spiderpunk-ascii.ansi (truecolor, for `cat`).  E = eye block.
import sys
M = str.maketrans('╲╱◢◣◥◤▌▐', '╱╲◣◢◤◥▐▌')
rows = [  # (left half, 12 cols), centre char
    ("      ▲    ▲", " "),
    ("     ▐█▌  ▐█", "█"),
    ("    ▄▄▄▄████", "█"),
    ("  ▄███▀▀▀▀▀▀", "▀"),
    (" ██▀ ╲   ╲  ", "│"),
    ("██──╲ ◢EEEEE", "│"),
    ("██   ◢EEEEEE", "┼"),
    ("██  ╱ ◥EEEEE", "│"),
    (" ██╲  ╱   ╱ ", "│"),
    ("  ▀██▄ ╲  ─ ", "┼"),
    ("    ▀▀███▄▄▄", "▄"),
]
cap = "⚡ SPIDER ▚ PUNK ⚡"
FF = {'mask': '$1', 'eye': '$4', 'hawk': '$3', 'web': '$5', 'cap': '$2', 'bolt': '$3'}
RGB = {'mask': (224,50,63), 'eye': (255,244,238), 'hawk': (242,197,61), 'web': (63,111,255), 'cap': (214,58,156), 'bolt': (242,197,61)}
def cls(ch, r):
    if ch == ' ': return None
    if r < 2: return 'hawk'
    if ch in 'E◢◣◥◤': return 'eye'
    if ch in '╲╱│┼─': return 'web'
    return 'mask'
def emit(line_chars, fmt):
    out, cur = '', None
    for ch, c in line_chars:
        if c and c != cur:
            out += fmt(c); cur = c
        out += "█" if (ch == "E" and c == "eye") else ch
    return out.rstrip()
W = 25
lines = []
for i, (l, c) in enumerate(rows):
    full = l + c + l[::-1].translate(M)
    lines.append([(ch, cls(ch, i)) for ch in full])
pad = (W - len(cap)) // 2
lines.append([(' ', None)] * pad + [(ch, 'bolt' if ch == '⚡' else ('cap' if ch != ' ' else None)) for ch in cap])
lines.insert(-1, [])
ff = [emit(l, lambda c: FF[c]) for l in lines]
ansi = [emit(l, lambda c: '\x1b[38;2;%d;%d;%dm' % RGB[c]) + '\x1b[0m' for l in lines]
open(sys.argv[1] + '/spiderpunk-ascii.txt', 'w').write('\n'.join(ff) + '\n')
open(sys.argv[1] + '/spiderpunk-ascii.ansi', 'w').write('\n'.join(ansi) + '\n')
for l in lines: print(''.join('█' if ch == 'E' else ch for ch, _ in l))
