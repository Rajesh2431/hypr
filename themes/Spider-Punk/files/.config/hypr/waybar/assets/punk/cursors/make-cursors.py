#!/usr/bin/env python3
"""Spider-Punk cursor theme (original artwork) -> hyprcursor + Xcursor.

  python3 make-cursors.py            # builds ~/.local/share/icons/Spider-Punk-Cursor

Shape names, aliases and hotspot conventions mirror Bibata-Modern-Ice (the previous
theme), so every app finds every cursor. Drawing style: thick black-ink outline,
crimson / paper / yellow fills, a blue "misprint" copy offset to the bottom-right.
Xcursor files are written directly (no xcursorgen needed).
"""
import io, math, os, re, shutil, struct, subprocess, tempfile, zipfile
from pathlib import Path
from PIL import Image

HOME = Path.home()
SRC_THEME = HOME / ".icons/Bibata-Modern-Ice"          # names / aliases / overrides come from here
OUT = HOME / ".local/share/icons/Spider-Punk-Cursor"
NAME = "Spider-Punk-Cursor"

INK, CRIMSON, BLUE, YELLOW, PAPER, PURPLE = "#050306", "#FF1744", "#00B8FF", "#FFD43B", "#F5F0E8", "#8B35FF"
SW = 13            # ink outline width (in the 256 canvas)
MIS = 11           # misprint offset
XSIZES = (24, 32, 40, 48, 64, 96)

# ------------------------------------------------------------------ drawing helpers
def svg(body, defs=""):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 256 256">'
            f'<defs>{defs}<pattern id="ht" width="9" height="9" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">'
            f'<circle cx="4.5" cy="4.5" r="1.7" fill="{INK}" fill-opacity=".22"/></pattern></defs>{body}</svg>')

def inked(shape, fill, rot=0, mis=True, dots=False, cx=128, cy=128):
    """shape: SVG path/polygon markup WITHOUT fill/stroke attributes, drawn three times."""
    r = f' transform="rotate({rot} {cx} {cy})"' if rot else ""
    out = ""
    if mis:
        out += f'<g transform="translate({MIS},{MIS})"><g{r} fill="{BLUE}" stroke="{BLUE}" stroke-width="{SW}" stroke-linejoin="round" stroke-linecap="round">{shape}</g></g>'
    out += f'<g{r} fill="{INK}" stroke="{INK}" stroke-width="{SW * 2}" stroke-linejoin="round" stroke-linecap="round">{shape}</g>'
    out += f'<g{r} fill="{fill}" stroke="none">{shape}</g>'
    if dots:
        out += f'<g{r} fill="url(#ht)" stroke="none">{shape}</g>'
    return out

def rot_pt(x, y, deg, cx=128, cy=128):
    a = math.radians(deg)
    dx, dy = x - cx, y - cy
    return cx + dx * math.cos(a) - dy * math.sin(a), cy + dx * math.sin(a) + dy * math.cos(a)

# ------------------------------------------------------------------ the artwork
ARROW = '<polygon points="40,26 40,196 84,158 114,222 146,208 117,146 176,146"/>'
ARROW_HL = f'<polyline points="56,62 56,150" stroke="{PAPER}" stroke-width="9" stroke-linecap="round" fill="none" opacity=".8"/>'

def arrow(badge="", mirror=False, up=False):
    body = inked(ARROW, CRIMSON, dots=True) + ARROW_HL
    if badge:
        body += badge
    if mirror:
        body = f'<g transform="translate(256,0) scale(-1,1)">{body}</g>'
    if up:
        body = f'<g transform="rotate(45 128 128) translate(30,10)">{body}</g>'
    return svg(body)

def bubble(inner, fill=YELLOW):
    return (f'<circle cx="{190 + MIS * .6}" cy="{190 + MIS * .6}" r="46" fill="{BLUE}"/>'
            f'<circle cx="190" cy="190" r="46" fill="{fill}" stroke="{INK}" stroke-width="{SW}"/>{inner}')

B_PLUS = bubble(f'<path d="M190 166 V214 M166 190 H214" stroke="{INK}" stroke-width="15" stroke-linecap="square"/>')
B_LINK = bubble(f'<polygon points="198,156 170,196 188,196 180,226 212,182 194,182 206,156" fill="{CRIMSON}" stroke="{INK}" stroke-width="5" stroke-linejoin="round"/>', PAPER)
B_HELP = bubble(f'<text x="190" y="214" text-anchor="middle" font-family="Bangers" font-size="74" fill="{INK}">?</text>')
B_NO = bubble(f'<circle cx="190" cy="190" r="24" fill="none" stroke="{INK}" stroke-width="10"/><path d="M173 173 L207 207" stroke="{INK}" stroke-width="10"/>', CRIMSON)
B_MENU = bubble(f'<path d="M168 174 H212 M168 190 H212 M168 206 H212" stroke="{INK}" stroke-width="9" stroke-linecap="square"/>', PAPER)
B_MOVE = bubble(f'<path d="M190 160 V220 M160 190 H220" stroke="{INK}" stroke-width="9"/><polygon points="190,152 180,166 200,166" fill="{INK}"/><polygon points="190,228 180,214 200,214" fill="{INK}"/><polygon points="152,190 166,180 166,200" fill="{INK}"/><polygon points="228,190 214,180 214,200" fill="{INK}"/>', PAPER)

def spinner(frame, n=8, cx=128, cy=128, r=78, w=34, small=False):
    """Ink ring cut into n segments; the lit one walks round (crimson -> yellow -> blue trail)."""
    if small:
        cx, cy, r, w = 190, 190, 38, 18
    segs = ""
    for i in range(n):
        a0 = math.radians(i * 360 / n - 90 + 4)
        a1 = math.radians((i + 1) * 360 / n - 90 - 4)
        k = (frame - i) % n
        col = CRIMSON if k == 0 else YELLOW if k == 1 else BLUE if k == 2 else "#2A1C26"
        x0, y0 = cx + r * math.cos(a0), cy + r * math.sin(a0)
        x1, y1 = cx + r * math.cos(a1), cy + r * math.sin(a1)
        segs += (f'<path d="M{x0:.1f} {y0:.1f} A{r} {r} 0 0 1 {x1:.1f} {y1:.1f}" stroke="{col}" stroke-width="{w}" fill="none"/>')
    ring = (f'<circle cx="{cx + (6 if small else MIS)}" cy="{cy + (6 if small else MIS)}" r="{r}" stroke="{BLUE}" stroke-width="{w + 10}" fill="none" opacity=".9"/>'
            f'<circle cx="{cx}" cy="{cy}" r="{r}" stroke="{INK}" stroke-width="{w + (12 if small else 22)}" fill="none"/>')
    return ring + segs

def wait(frame):
    return svg(spinner(frame) + f'<polygon points="136,92 108,136 126,136 116,168 150,120 132,120 144,92" fill="{YELLOW}" stroke="{INK}" stroke-width="6" stroke-linejoin="round"/>')

def progress(frame):
    return svg(inked(ARROW, CRIMSON, dots=True) + ARROW_HL + spinner(frame, small=True))

HAND = ('<path d="M104 30 h34 v86 h10 v-14 h30 v18 h4 v-8 h28 v96 l-16 30 h-108 l-38 -66 l20 -16 l36 28 z"/>')
HAND_LINES = f'<path d="M138 116 v34 M178 120 v30" stroke="{INK}" stroke-width="7" stroke-linecap="round"/>'
CUFF = f'<rect x="84" y="226" width="114" height="22" fill="{CRIMSON}" stroke="{INK}" stroke-width="8"/>'
FIST = ('<path d="M66 104 h34 v-12 h30 v10 h4 v-10 h30 v10 h4 v-8 h28 v120 l-16 24 h-108 l-12 -30 z"/>')
FIST_LINES = f'<path d="M100 104 v30 M134 102 v32 M168 104 v30" stroke="{INK}" stroke-width="7" stroke-linecap="round"/>'
OPEN = ('<path d="M66 70 h26 v70 h4 v-104 h28 v100 h4 v-112 h28 v112 h4 v-96 h28 v104 h4 v-60 h26 v130 l-20 30 h-104 l-28 -44 z"/>')

def hand():
    return svg(inked(HAND, PAPER) + HAND_LINES + CUFF)
def grab():
    return svg(inked(OPEN, PAPER) + CUFF)
def grabbing():
    return svg(inked(FIST, PAPER) + FIST_LINES + CUFF)

IBEAM = '<path d="M86 34 h84 v24 h-30 v140 h30 v24 h-84 v-24 h30 v-140 h-30 z"/>'
def text(rot=0):
    return svg(inked(IBEAM, CRIMSON, rot=rot) + (f'<g transform="rotate({rot} 128 128)"><path d="M122 70 v116" stroke="{PAPER}" stroke-width="6" opacity=".75"/></g>'))

CROSS = '<path d="M116 20 h24 v76 h76 v24 h-76 v76 h-24 v-76 h-76 v-24 h76 z"/>'
def crosshair():
    hole = f'<circle cx="128" cy="108" r="22" fill="{INK}"/><circle cx="128" cy="108" r="11" fill="{YELLOW}"/>'
    return svg(f'<g transform="translate(0,20)">{inked(CROSS, CRIMSON)}</g>' + hole.replace('cy="108"', 'cy="128"'))
def plus():
    return svg(inked('<path d="M108 40 h40 v68 h68 v40 h-68 v68 h-40 v-68 h-68 v-40 h68 z"/>', YELLOW))
def xcross():
    return svg(inked('<path d="M108 40 h40 v68 h68 v40 h-68 v68 h-40 v-68 h-68 v-40 h68 z"/>', CRIMSON, rot=45))
def dotbox():
    return svg(inked('<path d="M48 48 h160 v160 h-160 z M80 80 v96 h96 v-96 z" fill-rule="evenodd"/>', CRIMSON)
               + f'<circle cx="128" cy="128" r="18" fill="{YELLOW}" stroke="{INK}" stroke-width="8"/>')
def circle():
    return svg(inked('<path fill-rule="evenodd" d="M128 34 a94 94 0 1 0 0.1 0 z M128 74 a54 54 0 1 1 -0.1 0 z"/>', CRIMSON))
def no():
    return svg(inked('<path fill-rule="evenodd" d="M128 34 a94 94 0 1 0 0.1 0 z M128 74 a54 54 0 1 1 -0.1 0 z"/>', CRIMSON)
               + inked('<rect x="112" y="40" width="32" height="176"/>', CRIMSON, rot=-45, mis=False))
def pencil():
    body = ('<path d="M190 26 l40 40 l-132 132 l-56 16 l16 -56 z"/>')
    return svg(inked(body, YELLOW) + f'<path d="M58 158 l40 40" stroke="{INK}" stroke-width="10"/>'
               + f'<polygon points="42,214 50,182 74,206" fill="{CRIMSON}" stroke="{INK}" stroke-width="6"/>'
               + f'<path d="M168 48 l40 40" stroke="{CRIMSON}" stroke-width="16"/>')
def zoom(sign):
    g = ('<path fill-rule="evenodd" d="M104 28 a76 76 0 1 0 0.1 0 z M104 60 a44 44 0 1 1 -0.1 0 z"/>'
         '<path d="M150 162 l20 -20 l66 66 l-20 20 z"/>')
    mark = f'<path d="M80 104 H128" stroke="{INK}" stroke-width="13"/>' + (f'<path d="M104 80 V128" stroke="{INK}" stroke-width="13"/>' if sign == "+" else "")
    return svg(inked(g, CRIMSON) + f'<circle cx="104" cy="104" r="44" fill="{PAPER}"/>' + mark)

DOUBLE = '<path d="M20 128 l52 -48 v30 h112 v-30 l52 48 l-52 48 v-30 h-112 v30 z"/>'
SINGLE = '<path d="M128 22 l58 62 h-36 v138 h-44 v-138 h-36 z"/>'
FOUR = ('<path d="M128 14 l40 42 h-26 v58 h58 v-26 l42 40 l-42 40 v-26 h-58 v58 h26 l-40 42 l-40 -42 h26 v-58 h-58 v26 l-42 -40 '
        'l42 -40 v26 h58 v-58 h-26 z"/>')
def double(rot):
    return svg(inked(DOUBLE, CRIMSON, rot=rot, dots=True))
def single(rot):
    return svg(inked(SINGLE, CRIMSON, rot=rot, dots=True))
def move():
    return svg(inked(FOUR, CRIMSON, dots=True) + f'<circle cx="128" cy="128" r="16" fill="{YELLOW}" stroke="{INK}" stroke-width="7"/>')
# side: arrow pointing at an edge bar (base points UP, bar at top)
SIDE = '<path d="M40 22 h176 v26 h-176 z M128 62 l52 54 h-32 v116 h-40 v-116 h-32 z"/>'
def side(rot):
    return svg(inked(SIDE, CRIMSON, rot=rot, dots=True))
# corner: diagonal arrow into an L bracket (base = top-left)
CORNER = ('<path d="M22 22 h112 v26 h-86 v86 h-26 z M64 64 h74 l-24 24 l104 104 l-28 28 l-104 -104 l-22 24 z"/>')
def corner(rot):
    return svg(inked(CORNER, CRIMSON, rot=rot, dots=True))

# ------------------------------------------------------------------ shape table (Bibata names)
# name: (svg-or-frames, hotspot in the 256 canvas)
ARROW_HOT = (40, 26)
def table():
    t = {}
    t["left_ptr"] = (arrow(), ARROW_HOT)
    t["right_ptr"] = (arrow(mirror=True), (216, 26))
    t["center_ptr"] = (svg(f'<g transform="rotate(30 40 26) translate(0,0)">{inked(ARROW, CRIMSON, dots=True)}{ARROW_HL}</g>'), ARROW_HOT)
    t["context-menu"] = (arrow(B_MENU), ARROW_HOT)
    for n in ("copy", "dnd-copy"):
        t[n] = (arrow(B_PLUS), ARROW_HOT)
    for n in ("link", "dnd-link"):
        t[n] = (arrow(B_LINK), ARROW_HOT)
    for n in ("question_arrow", "dnd-ask"):
        t[n] = (arrow(B_HELP), ARROW_HOT)
    t["dnd_no_drop"] = (arrow(B_NO), ARROW_HOT)
    t["pointer-move"] = (arrow(B_MOVE), ARROW_HOT)
    t["wayland-cursor"] = (arrow(), ARROW_HOT)
    t["left_ptr_watch"] = ([progress(f) for f in range(8)], ARROW_HOT)
    t["wait"] = ([wait(f) for f in range(8)], (128, 128))
    for n in ("hand1", "hand2"):
        t[n] = (hand(), (121, 30))
    t["grabbing"] = (grabbing(), (128, 128))
    t["xterm"] = (text(), (128, 128))
    t["vertical-text"] = (text(90), (128, 128))
    for n in ("crosshair", "cross", "tcross"):
        t[n] = (crosshair(), (128, 128))
    t["plus"] = (plus(), (128, 128))
    t["X_cursor"] = (xcross(), (128, 128))
    t["dotbox"] = (dotbox(), (128, 128))
    t["circle"] = (circle(), (128, 128))
    t["crossed_circle"] = (no(), (128, 128))
    t["pencil"] = (pencil(), (42, 214))
    t["zoom-in"] = (zoom("+"), (104, 104))
    t["zoom-out"] = (zoom("-"), (104, 104))
    t["sb_h_double_arrow"] = (double(0), (128, 128))
    t["sb_v_double_arrow"] = (double(90), (128, 128))
    t["fd_double_arrow"] = (double(-45), (128, 128))   # /  (ne-sw)
    t["bd_double_arrow"] = (double(45), (128, 128))    # \  (nw-se)
    t["move"] = (move(), (128, 128))
    for n, r in (("sb_up_arrow", 0), ("sb_right_arrow", 90), ("sb_down_arrow", 180), ("sb_left_arrow", 270)):
        t[n] = (single(r), rot_pt(128, 22, r))
    for n, r in (("top_side", 0), ("right_side", 90), ("bottom_side", 180), ("left_side", 270),
                 ("top_tee", 0), ("right_tee", 90), ("bottom_tee", 180), ("left_tee", 270)):
        t[n] = (side(r), rot_pt(128, 26, r))
    for n, r in (("top_left_corner", 0), ("top_right_corner", 90), ("bottom_right_corner", 180), ("bottom_left_corner", 270),
                 ("ul_angle", 0), ("ur_angle", 90), ("lr_angle", 180), ("ll_angle", 270)):
        t[n] = (corner(r), rot_pt(26, 26, r))
    return t

# ------------------------------------------------------------------ build
def overrides(shape):
    """define_override lines from Bibata's hyprcursor shape (keeps every alias name)."""
    p = SRC_THEME / "hyprcursors" / f"{shape}.hlc"
    if not p.exists():
        return []
    with zipfile.ZipFile(p) as z:
        meta = z.read("meta.hl").decode()
    return re.findall(r"^define_override\s*=\s*(\S+)", meta, re.M)

def render(svgtext, size):
    png = subprocess.run(["rsvg-convert", "-w", str(size), "-h", str(size)], input=svgtext.encode(),
                         capture_output=True, check=True).stdout
    return Image.open(io.BytesIO(png)).convert("RGBA")

def xcursor(frames, hot, path):
    """Write an Xcursor file: every size x every frame, premultiplied ARGB."""
    chunks = []
    for size in XSIZES:
        for f in frames:
            im = render(f, size)
            raw = im.tobytes()            # RGBA -> premultiplied BGRA (little-endian ARGB)
            px = bytearray(len(raw))
            for i in range(0, len(raw), 4):
                r, g, b, a = raw[i], raw[i + 1], raw[i + 2], raw[i + 3]
                px[i], px[i + 1], px[i + 2], px[i + 3] = b * a // 255, g * a // 255, r * a // 255, a
            hx = min(size - 1, round(hot[0] / 256 * size)); hy = min(size - 1, round(hot[1] / 256 * size))
            delay = 70 if len(frames) > 1 else 0
            chunks.append((size, struct.pack("<9I", 36, 0xFFFD0002, size, 1, size, size, hx, hy, delay) + bytes(px)))
    ntoc = len(chunks)
    pos = 16 + ntoc * 12
    toc, data = b"", b""
    for size, c in chunks:
        toc += struct.pack("<3I", 0xFFFD0002, size, pos + len(data))
        data += c
    path.write_bytes(b"Xcur" + struct.pack("<3I", 16, 0x10000, ntoc) + toc + data)

def main():
    shapes = table()
    if OUT.exists():
        shutil.rmtree(OUT)
    (OUT / "cursors").mkdir(parents=True)
    work = Path(tempfile.mkdtemp(prefix="punkcursor-"))
    src = work / "src"
    (src / "hyprcursors").mkdir(parents=True)
    (src / "manifest.hl").write_text(f"name = {NAME}\ndescription = Spider-Punk ink cursors (original)\nversion = 1.0\ncursors_directory = hyprcursors\n")

    for name, (art, hot) in shapes.items():
        frames = art if isinstance(art, list) else [art]
        d = src / "hyprcursors" / name
        d.mkdir()
        lines = ["resize_algorithm = bilinear", f"hotspot_x = {hot[0] / 256:.3f}", f"hotspot_y = {hot[1] / 256:.3f}", ""]
        for i, f in enumerate(frames):
            fn = f"{name}-{i:02d}.svg"
            (d / fn).write_text(f)
            lines.append(f"define_size = 0, {fn}" + (", 70" if len(frames) > 1 else ""))
        lines.append("")
        lines += [f"define_override = {o}" for o in overrides(name)]
        (d / "meta.hl").write_text("\n".join(lines) + "\n")
        xcursor(frames, hot, OUT / "cursors" / name)

    # Xcursor aliases: copy Bibata's symlink map exactly
    for p in sorted((SRC_THEME / "cursors").iterdir()):
        if p.is_symlink():
            tgt = os.readlink(p)
            if (OUT / "cursors" / tgt).exists() and not (OUT / "cursors" / p.name).exists():
                os.symlink(tgt, OUT / "cursors" / p.name)
    missing = [p.name for p in (SRC_THEME / "cursors").iterdir() if not (OUT / "cursors" / p.name).exists()]

    # hyprcursor
    subprocess.run(["hyprcursor-util", "--create", str(src), "-o", str(work)], check=True, capture_output=True)
    built = next(work.glob("theme_*"))
    shutil.copytree(built / "hyprcursors", OUT / "hyprcursors")
    shutil.copy(built / "manifest.hl", OUT / "manifest.hl")
    (OUT / "index.theme").write_text(f"[Icon Theme]\nName={NAME}\nComment=Spider-Punk ink cursors\nInherits=Bibata-Modern-Ice\n")
    (OUT / "cursor.theme").write_text(f"[Icon Theme]\nName={NAME}\nInherits={NAME}\n")
    # keep the SVG sources next to the generator for previews
    prev = Path(__file__).resolve().parent / "preview"
    shutil.rmtree(prev, ignore_errors=True)
    shutil.copytree(src / "hyprcursors", prev)
    shutil.rmtree(work)
    print(f"built {len(shapes)} shapes, {len(list((OUT / 'cursors').iterdir()))} xcursor names, missing: {missing or 'none'}")

if __name__ == "__main__":
    main()
