#!/usr/bin/env python3
"""Cheat sheet (Super+H): every shortcut Hyprland has loaded right now, with its description.

Built from `hyprctl binds -j`, so it is always current (no hand-kept list to go stale).
Your own / newer shortcuts are pinned at the top (★). Type to search, Esc closes.
Replaces KoolDots' scripts/KeyHints.sh (a fixed list); bound in UserConfigs/user_keybinds.lua.
"""
import json, subprocess, sys

PINNED = [   # (modmask, key) shown first with a star, in this order
    (72, 'T'), (64, 'W'), (72, 'W'), (72, 'L'), (73, 'L'), (64, 'TAB'), (65, 'TAB'), (64, 'D'),
    (65, 'N'), (68, 'N'), (12, 'P'), (64, 'K'), (64, 'F'), (64, 'V'),
]
MODS = [(64, 'Super'), (4, 'Ctrl'), (8, 'Alt'), (1, 'Shift')]
NICE = {'RETURN': 'Enter', 'TAB': 'Tab', 'SPACE': 'Space', 'PRINT': 'Print', 'ESCAPE': 'Esc', 'GRAVE': '`',
        'MOUSE:272': 'Left drag', 'MOUSE:273': 'Right drag', 'MOUSE_DOWN': 'Scroll down', 'MOUSE_UP': 'Scroll up',
        'PERIOD': '.', 'COMMA': ',', 'SLASH': '/', 'BACKSLASH': '\\', 'MINUS': '-', 'EQUAL': '=',
        'BRACKETLEFT': '[', 'BRACKETRIGHT': ']', 'SEMICOLON': ';', 'APOSTROPHE': "'"}


def combo(mask, key):
    k = key.upper()
    k = NICE.get(k, k[3:].title() if k.startswith('XF8') else key if len(key) > 1 and not key.isupper() else k)
    return '+'.join([n for b, n in MODS if mask & b] + [k])


def main():
    try:
        binds = json.loads(subprocess.run(['hyprctl', '-j', 'binds'], capture_output=True, text=True).stdout)
    except ValueError:
        binds = []
    rows, seen = {}, set()
    for b in binds:
        if b.get('submap'):
            continue
        desc = (b.get('description') or '').strip()
        if not desc:
            continue
        ident = (b['modmask'], b['key'].upper(), desc.lower())
        if ident in seen:
            continue
        seen.add(ident)
        rows.setdefault((b['modmask'], b['key'].upper()), []).append((combo(b['modmask'], b['key']), desc))
    pinned = [(c, d, '★') for pk in PINNED for c, d in rows.pop(pk, [])]
    rest = sorted(((c, d, '') for v in rows.values() for c, d in v), key=lambda r: (r[0].split('+')[-1].lower(), r[0]))
    args = []
    for c, d, star in pinned + rest:
        args += [star, c, d]
    subprocess.run(['pkill', '-x', 'yad'])
    subprocess.run(['yad', '--center', '--title=Shortcuts', '--width=760', '--height=720', '--no-buttons',
                    '--list', '--search-column=3', '--column=', '--column=Keys', '--column=What it does',
                    '--text=<b>All shortcuts</b>  ·  ★ = yours / newer  ·  type to search  ·  Esc closes'] + args,
                   env={**__import__('os').environ, 'GDK_BACKEND': 'wayland'})
    return 0


if __name__ == '__main__':
    sys.exit(main())
