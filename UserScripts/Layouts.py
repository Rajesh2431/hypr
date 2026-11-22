#!/usr/bin/env python3
"""Window layout presets, per workspace (menu: Arch logo -> Window layout).

  Layouts.py set PRESET [WORKSPACE]   apply to the active workspace (or WORKSPACE id) and remember it
  Layouts.py status                   preset of the active workspace
  Layouts.py list                     preset keys + labels
  Layouts.py next | prev              cycle the active workspace through the presets (Super+Alt+L / +Shift)
  Layouts.py watch                    keep Columns / Focus Column widths when windows open (daemon)

Presets (all built-in Hyprland 0.57 layouts or Lua layouts from UserConfigs/layout_presets.lua):
  dwindle · master · scrolling · monocle      the four built-ins, as before
  centered   Centered Master  master, orientation center (main window in the middle)
  top        Master Top       master, orientation top (main wide on top, stack below)
  columns    Columns          scrolling, each column half the screen
  focus      Focus Column     scrolling, 70 % column, neighbours peeking
  tabbed     Tabbed           dwindle with every window in one tab group (new windows join it)
  grid       Grid             lua:grid, windows split evenly

Saved as hl.workspace_rule lines in UserConfigs/workspaces.lua (layout + layout_opts), so they
survive reloads and reboots; preset names in ~/.local/state/hypr/layout-presets.json.
`Layouts.py watch` (started at login and when a column preset is used) re-applies the Columns /
Focus Column width after a window opens: the Scrolling layout resets column widths then.
"""
import json, os, re, subprocess, sys, time

HOME = os.path.expanduser('~')
RULES = os.path.join(HOME, '.config/hypr/UserConfigs/workspaces.lua')
STATE_DIR = os.path.join(HOME, '.local/state/hypr')
STATE = os.path.join(STATE_DIR, 'layout-presets.json')

PRESETS = {   # key: (label, layout, layout_opts, column width, tabbed)
    'dwindle':   ('Dwindle', 'dwindle', {}, None, False),
    'master':    ('Master', 'master', {'orientation': 'left'}, None, False),
    'centered':  ('Centered Master', 'master', {'orientation': 'center'}, None, False),
    'top':       ('Master Top', 'master', {'orientation': 'top'}, None, False),
    'scrolling': ('Scrolling', 'scrolling', {}, None, False),
    'columns':   ('Columns', 'scrolling', {}, 0.5, False),
    'focus':     ('Focus Column', 'scrolling', {}, 0.7, False),
    'monocle':   ('Monocle', 'monocle', {}, None, False),
    'tabbed':    ('Tabbed', 'dwindle', {}, None, True),
    'grid':      ('Grid', 'lua:grid', {}, None, False),
}


def run(*a):
    return subprocess.run(a, capture_output=True, text=True)


def hj(what):
    try:
        return json.loads(run('hyprctl', '-j', what).stdout)
    except ValueError:
        return {} if what in ('activeworkspace', 'activewindow') else []


def ev(lua):
    out = run('hyprctl', 'eval', lua).stdout.strip()
    return out in ('', 'ok')


def dsp(lua):
    run('hyprctl', 'dispatch', lua)


def lua_val(v):
    if isinstance(v, bool): return 'true' if v else 'false'
    if isinstance(v, (int, float)): return repr(v)
    return '"%s"' % str(v).replace('\\', '\\\\').replace('"', '\\"')


def rule_lua(ws, mon, layout, opts):
    s = 'hl.workspace_rule({ workspace = %s, monitor = %s, layout = %s' % (lua_val(ws), lua_val(mon), lua_val(layout))
    if opts:
        s += ', layout_opts = { %s }' % ', '.join('%s = %s' % (k, lua_val(v)) for k, v in opts.items())
    return s + ' })'


def load_state():
    try:
        return json.load(open(STATE))
    except (OSError, ValueError):
        return {}


def save_state(st):
    os.makedirs(STATE_DIR, exist_ok=True)
    tmp = STATE + '.tmp'; json.dump(st, open(tmp, 'w'), indent=1); os.replace(tmp, STATE)
    if any(PRESETS.get(k, (0, 0, 0, None))[3] for k in st.values()):
        start_watcher()


def persist_rule(ws, mon, layout, opts):
    """replace this workspace+monitor's rule line in workspaces.lua (same file KoolDots' switcher uses)."""
    try:
        lines = open(RULES).read().splitlines()
    except OSError:
        lines = []
    pat = re.compile(r'^hl\.workspace_rule\(\{\s*workspace\s*=\s*"%s"\s*,\s*monitor\s*=\s*"%s"\s*,\s*layout' % (re.escape(str(ws)), re.escape(mon)))
    lines = [l for l in lines if not pat.match(l)]
    lines.append(rule_lua(str(ws), mon, layout, opts))
    tmp = RULES + '.tmp'; open(tmp, 'w').write('\n'.join(lines) + '\n'); os.replace(tmp, RULES)


def ws_windows(wsid):
    return [c for c in hj('clients') if c.get('workspace', {}).get('id') == wsid and not c.get('floating') and c.get('mapped', True)]


def ungroup(wsid):
    """dissolve every tab group on the workspace."""
    done = set()
    for c in ws_windows(wsid):
        g = tuple(sorted(c.get('grouped') or []))
        if len(g) > 1 and g not in done:
            done.add(g)
            dsp('hl.dsp.focus({ window = "address:%s" })' % c['address'])
            dsp('hl.dsp.group.toggle()')


def make_tabs(wsid, mon):
    """put every tiled window of the workspace into one group (in a row via scrolling, then merge left)."""
    wins = ws_windows(wsid)
    if len(wins) < 1:
        return
    ev(rule_lua(str(wsid), mon, 'scrolling', {})); time.sleep(0.35)
    wins = sorted(ws_windows(wsid), key=lambda c: (c['at'][0], c['at'][1]))
    first = wins[0]
    dsp('hl.dsp.focus({ window = "address:%s" })' % first['address'])
    if len(first.get('grouped') or []) < 2:
        dsp('hl.dsp.group.toggle()')
    for c in wins[1:]:
        if c['address'] in (first.get('grouped') or []):
            continue
        dsp('hl.dsp.focus({ window = "address:%s" })' % c['address'])
        dsp('hl.dsp.window.move({ into_group = "left" })')
        time.sleep(0.08)
    dsp('hl.dsp.focus({ window = "address:%s" })' % first['address'])


WATCH_RE = r'^\S*python3? \S*Layouts\.py watch$'


def start_watcher():
    if run('pgrep', '-f', WATCH_RE).stdout.strip():
        return
    subprocess.Popen(['setsid', '-f', sys.executable, os.path.abspath(__file__), 'watch'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def cmd_watch():
    """Hyprland event stream: after a window opens on the focused workspace with a column preset,
    re-apply that width (several times: apps settle at different speeds)."""
    import socket, threading
    sig = os.environ.get('HYPRLAND_INSTANCE_SIGNATURE', '')
    path = os.path.join(os.environ.get('XDG_RUNTIME_DIR', '/run/user/%d' % os.getuid()), 'hypr', sig, '.socket2.sock')
    s = socket.socket(socket.AF_UNIX); s.connect(path)
    buf = b''

    def resize(ws, width):
        aw = hj('activeworkspace')
        if str(aw.get('id')) == ws and aw.get('tiledLayout') == 'scrolling' and load_state().get(ws) in PRESETS \
                and PRESETS[load_state()[ws]][3] == width:
            dsp('hl.dsp.layout("colresize all %s")' % width)

    while True:
        data = s.recv(4096)
        if not data:
            return 0
        buf += data
        *lines, buf = buf.split(b'\n')
        for line in lines:
            ev_name, _, arg = line.decode('utf-8', 'replace').partition('>>')
            if ev_name != 'openwindow':
                continue
            parts = arg.split(',')
            if len(parts) < 2:
                continue
            ws_name = parts[1]
            ws = next((str(w['id']) for w in hj('workspaces') if w.get('name') == ws_name), ws_name)
            key = load_state().get(ws)
            width = PRESETS.get(key, (0, 0, 0, None))[3] if key else None
            if width:
                for delay in (0.25, 0.7, 1.5, 2.5):
                    threading.Timer(delay, resize, (ws, width)).start()


def note(msg):
    subprocess.Popen(['notify-send', '-e', '-u', 'low', '-a', 'Layout', msg], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def cmd_set(key, wsid=None):
    if key not in PRESETS:
        print('unknown preset; one of:', ' '.join(PRESETS)); return 2
    label, layout, opts, colw, tabbed = PRESETS[key]
    aw = hj('activeworkspace')
    if wsid is None:
        wsid = aw.get('id')
    ws = next((w for w in hj('workspaces') if w.get('id') == wsid), None)
    if not ws:
        print('workspace not found'); return 1
    mon = ws['monitor']
    st = load_state()
    prev = st.get(str(wsid))
    if prev == 'tabbed' and not tabbed:
        ungroup(wsid)
    # options only take effect when the layout changes: hop through another layout first
    hop = 'dwindle' if layout != 'dwindle' else 'master'
    ev(rule_lua(str(wsid), mon, hop, {})); time.sleep(0.6)
    if tabbed:
        make_tabs(wsid, mon)
    if not ev(rule_lua(str(wsid), mon, layout, opts)):
        note('Layout switch failed: ' + label); return 1
    time.sleep(0.3)
    if opts:
        # Hyprland 0.57 applies a rule's layout_opts one switch late (it uses the options stored before
        # this rule): switch away and back once more so the new options are the ones in effect
        ev(rule_lua(str(wsid), mon, hop, {})); time.sleep(0.6)
        ev(rule_lua(str(wsid), mon, layout, opts)); time.sleep(0.3)
    st[str(wsid)] = key
    save_state(st)
    if colw and wsid == aw.get('id'):
        dsp('hl.dsp.layout("colresize all %s")' % colw)
    persist_rule(wsid, mon, layout, opts)
    note('%s layout · workspace %s' % (label, ws.get('name', wsid)))
    return 0


def current_key(wsid=None):
    aw = hj('activeworkspace')
    wsid = aw.get('id') if wsid is None else wsid
    key = load_state().get(str(wsid))
    real = next((w.get('tiledLayout') for w in hj('workspaces') if w.get('id') == wsid), aw.get('tiledLayout'))
    if key in PRESETS and PRESETS[key][1] == real:
        return key
    return real if real in PRESETS else ('grid' if real == 'lua:grid' else real or 'dwindle')


def main(a):
    c = a[0] if a else ''
    if c == 'set' and len(a) > 1:
        return cmd_set(a[1], int(a[2]) if len(a) > 2 else None)
    if c == 'status':
        k = current_key(); print(k + '\t' + (PRESETS[k][0] if k in PRESETS else k)); return 0
    if c == 'list':
        for k, v in PRESETS.items(): print(k + '\t' + v[0])
        return 0
    if c == 'watch':
        return cmd_watch()
    if c in ('next', 'prev'):
        keys = list(PRESETS); k = current_key(); step = 1 if c == 'next' else -1
        return cmd_set(keys[(keys.index(k) + step) % len(keys)] if k in keys else keys[0])
    print(__doc__); return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
