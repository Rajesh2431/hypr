#!/usr/bin/env python3
"""Image / video wallpaper switcher (Super+Alt+W).

  VideoWall.py menu              rofi picker: your videos, back-to-image, pause, folder
  VideoWall.py video FILE        play FILE as the wallpaper on every monitor (looped, muted)
  VideoWall.py image [FILE]      back to a still image (FILE, or the image you had before the video)
  VideoWall.py toggle            switch between the last video and the last image
  VideoWall.py pause | play      manual pause / resume (auto-pause still applies on top)
  VideoWall.py status            mode, file, paused + why
  VideoWall.py restore           at login: start the video again if video mode was on

Engine: mpvpaper (mpv on a background layer), hardware-decoded on the AMD iGPU (VA-API, renderD of
amdgpu) with Mesa EGL, so the NVIDIA dGPU stays asleep. A slot for wallpiper (Wallpaper Engine via
Proton) exists: set ENGINE=wallpiper in ~/.cache/videowall/engine once Wallpaper Engine + wallpiper
are installed (untested until then).

Auto-pause (a small watcher started with the video): on battery, while a fullscreen window covers
the screen, and while the screen is locked (hyprlock). Picking an image with the normal wallpaper
tools (island picker, KoolDots menu) while a video plays switches back to image mode automatically.

Under the video, the image layer (awww) shows a still frame of it, and that frame becomes
.wallpaper_current, so wallust colours, the lock screen and Styles.sh previews match the video.
Videos are looked up in ~/Videos/Wallpapers and ~/Pictures/wallpapers.
"""
import json, os, signal, socket, subprocess, sys, time, glob, hashlib

HOME = os.path.expanduser('~')
STATE = os.path.join(HOME, '.cache/videowall')
SOCK = os.path.join(os.environ.get('XDG_RUNTIME_DIR', '/tmp'), 'videowall-mpv.sock')
WALL = os.path.join(HOME, '.config/hypr/wallpaper_effects/.wallpaper_current')
SCRIPTS = os.path.join(HOME, '.config/hypr/scripts')
VIDEO_DIRS = [os.path.join(HOME, 'Videos/Wallpapers'), os.path.join(HOME, 'Pictures/wallpapers')]
VIDEO_EXT = ('.mp4', '.webm', '.mkv', '.mov', '.m4v', '.avi', '.gif')
MESA_EGL = '/usr/share/glvnd/egl_vendor.d/50_mesa.json'
os.makedirs(os.path.join(STATE, 'thumbs'), exist_ok=True)


# ------------------------------------------------------------------ small helpers
def rd(name, default=''):
    try:
        return open(os.path.join(STATE, name)).read().strip()
    except OSError:
        return default


def wr(name, value):
    tmp = os.path.join(STATE, name + '.tmp')
    with open(tmp, 'w') as f:
        f.write(value + '\n')
    os.replace(tmp, os.path.join(STATE, name))


def run(*cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def note(msg):
    subprocess.Popen(['notify-send', '-a', 'Wallpaper', '-i', 'preferences-desktop-wallpaper', 'Wallpaper', msg],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    print(msg)


def amd_render_node():
    for n in sorted(glob.glob('/sys/class/drm/renderD*')):
        try:
            if os.path.basename(os.readlink(n + '/device/driver')) == 'amdgpu':
                return '/dev/dri/' + os.path.basename(n)
        except OSError:
            pass
    return ''


def awww_image():
    """path of the image awww shows now (first output)."""
    out = run('awww', 'query').stdout
    for line in out.splitlines():
        if 'image:' in line:
            return line.split('image:', 1)[1].strip()
    return ''


def pids(pattern):
    out = run('pgrep', '-f', pattern).stdout.split()
    return [int(p) for p in out if int(p) != os.getpid()]


def mpv(cmd):
    """send one JSON IPC command to the wallpaper's mpv; returns the reply or None."""
    try:
        s = socket.socket(socket.AF_UNIX); s.settimeout(1); s.connect(SOCK)
        s.sendall((json.dumps({'command': cmd}) + '\n').encode())
        data = s.recv(4096).decode(); s.close()
        return json.loads(data.splitlines()[0])
    except (OSError, ValueError, IndexError):
        return None


def set_image_layer(path, wallust=True):
    """KoolDots' steps for an image: awww + .wallpaper_current + wallust (colours, borders, reload)."""
    run('awww', 'img', path, '--transition-type', 'fade', '--transition-duration', '0.8', '--transition-fps', '60')
    for dst in (WALL, WALL + '_eDP-1'):
        try:
            with open(path, 'rb') as a, open(dst + '.tmp', 'wb') as b:
                b.write(a.read())
            os.replace(dst + '.tmp', dst)
        except OSError:
            pass
    if wallust:
        subprocess.Popen([os.path.join(SCRIPTS, 'WallustSwww.sh'), WALL], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def frame_of(video):
    """a still frame of the video (cached) -> png path."""
    key = hashlib.md5(video.encode()).hexdigest()[:16]
    out = os.path.join(STATE, 'thumbs', key + '-frame.png')
    if not os.path.exists(out):
        run('ffmpeg', '-y', '-loglevel', 'error', '-ss', '1', '-i', video, '-frames:v', '1', out)
        if not os.path.exists(out):
            run('ffmpeg', '-y', '-loglevel', 'error', '-i', video, '-frames:v', '1', out)
    return out if os.path.exists(out) else ''


def thumb_of(video):
    key = hashlib.md5(video.encode()).hexdigest()[:16]
    out = os.path.join(STATE, 'thumbs', key + '.png')
    if not os.path.exists(out):
        run('ffmpegthumbnailer', '-i', video, '-o', out, '-s', '256', '-t', '15%')
    return out


def videos():
    found = []
    for d in VIDEO_DIRS:
        if os.path.isdir(d):
            for f in sorted(os.listdir(d)):
                if f.lower().endswith(VIDEO_EXT):
                    found.append(os.path.join(d, f))
    return found


# ------------------------------------------------------------------ engines
def engine():
    return rd('engine', 'mpvpaper')


def stop_video_engine():
    for p in pids(r'^mpvpaper .*videowall-mpv\.sock'):
        try:
            os.kill(p, signal.SIGTERM)
        except OSError:
            pass
    if engine() == 'wallpiper' and run('which', 'wallpiperctl').returncode == 0:
        run('wallpiperctl', 'stop')
    for _ in range(20):
        if not pids(r'^mpvpaper .*videowall-mpv\.sock'):
            break
        time.sleep(0.1)
    try:
        os.unlink(SOCK)
    except OSError:
        pass


def start_video_engine(path):
    if engine() == 'wallpiper':
        # Wallpaper Engine via Proton (https://github.com/ejalxndr/wallpiper). Needs Wallpaper Engine installed.
        if run('which', 'wallpiperctl').returncode != 0:
            note('wallpiper is not installed (it also needs Wallpaper Engine from Steam). Using mpvpaper.')
        else:
            if not pids('wallpiperd'):
                subprocess.Popen(['setsid', '-f', 'env', 'WALLPIPER_PORTAL=hyprland', 'wallpiperd'],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                time.sleep(3)
            return run('wallpiperctl', 'set', path).returncode == 0
    node = amd_render_node()
    opts = ['no-audio', 'loop', 'panscan=1.0', 'hwdec=vaapi', 'profile=fast', 'input-ipc-server=' + SOCK,
            'keep-open=yes', 'osc=no', 'osd-level=0', 'msg-level=all=error']
    if node:
        opts.append('vaapi-device=' + node)
    env = dict(os.environ)
    # render + decode on the AMD iGPU and keep the NVIDIA dGPU asleep: the session forces NVIDIA
    # (LIBVA_DRIVER_NAME=nvidia, PRIME offload…), which would make VA-API fail and mpv decode on the CPU
    for k in ('__NV_PRIME_RENDER_OFFLOAD', '__GLX_VENDOR_LIBRARY_NAME', 'NVD_BACKEND', 'GBM_BACKEND', '__VK_LAYER_NV_optimus'):
        env.pop(k, None)
    env['LIBVA_DRIVER_NAME'] = 'radeonsi'
    env['DRI_PRIME'] = '0'
    if os.path.exists(MESA_EGL):
        env['__EGL_VENDOR_LIBRARY_FILENAMES'] = MESA_EGL
    vk = '/usr/share/vulkan/icd.d/radeon_icd.x86_64.json'
    if os.path.exists(vk):
        env['VK_DRIVER_FILES'] = vk
    subprocess.Popen(['setsid', '-f', 'mpvpaper', '-o', ' '.join(opts), 'ALL', path], env=env,
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(40):
        if mpv(['get_property', 'pause']) is not None:
            return True
        time.sleep(0.1)
    return bool(pids(r'^mpvpaper .*videowall-mpv\.sock'))


def start_watcher():
    for p in pids(r'^\S*python3? \S*VideoWall\.py watch$'):
        try:
            os.kill(p, signal.SIGTERM)
        except OSError:
            pass
    subprocess.Popen(['setsid', '-f', sys.executable, os.path.abspath(__file__), 'watch'],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def stop_watcher():
    for p in pids(r'^\S*python3? \S*VideoWall\.py watch$'):
        try:
            os.kill(p, signal.SIGTERM)
        except OSError:
            pass


# ------------------------------------------------------------------ commands
def cmd_video(path):
    path = os.path.abspath(os.path.expanduser(path))
    if not os.path.isfile(path):
        note('Video not found: ' + path); return 1
    if rd('mode') != 'video':
        cur = awww_image()
        if cur and not cur.startswith(STATE):
            wr('image', cur)                      # remember the still image to come back to
    stop_video_engine()
    frame = frame_of(path)
    if frame:
        set_image_layer(frame)                    # colours + lock screen follow the video
    if not start_video_engine(path):
        note('Could not start the video wallpaper'); return 1
    wr('mode', 'video'); wr('video', path); wr('frame', frame)
    if rd('manual-pause') == '1':
        wr('manual-pause', '0')
    start_watcher()
    note('Video wallpaper: ' + os.path.basename(path))
    return 0


def cmd_image(path=None):
    path = os.path.abspath(os.path.expanduser(path)) if path else rd('image')
    stop_watcher(); stop_video_engine()
    wr('mode', 'image')
    if path and os.path.isfile(path):
        wr('image', path)
        set_image_layer(path)
        note('Image wallpaper: ' + os.path.basename(path))
    else:
        note('Video wallpaper stopped')
    return 0


def cmd_toggle():
    if rd('mode') == 'video':
        return cmd_image()
    v = rd('video')
    if v and os.path.isfile(v):
        return cmd_video(v)
    note('No video chosen yet: Super+Alt+W'); return 1


def cmd_pause(on):
    wr('manual-pause', '1' if on else '0')
    mpv(['set_property', 'pause', bool(on)])
    return 0


def cmd_status():
    r = mpv(['get_property', 'pause'])
    print(json.dumps({'mode': rd('mode', 'image'), 'engine': engine(), 'video': rd('video'), 'image': rd('image'),
                      'running': r is not None, 'paused': (r or {}).get('data'), 'reason': rd('reason'),
                      'manual_pause': rd('manual-pause') == '1'}, indent=1))
    return 0


def cmd_restore():
    if rd('mode') == 'video' and os.path.isfile(rd('video')):
        time.sleep(2)                             # let awww / the layer shell come up first
        return cmd_video(rd('video'))
    return 0


def on_battery():
    for ac in glob.glob('/sys/class/power_supply/*/online'):
        try:
            if 'ADP' in ac or 'AC' in ac:
                return open(ac).read().strip() == '0'
        except OSError:
            pass
    return False


def covered():
    """every monitor's visible workspace has a fullscreen window."""
    try:
        mons = json.loads(run('hyprctl', '-j', 'monitors').stdout)
        wss = {w['id']: w for w in json.loads(run('hyprctl', '-j', 'workspaces').stdout)}
        return bool(mons) and all(wss.get(m['activeWorkspace']['id'], {}).get('hasfullscreen') for m in mons)
    except (ValueError, KeyError):
        return False


def cmd_watch():
    """auto-pause loop (2 s); exits when the video stops."""
    signal.signal(signal.SIGTERM, lambda *a: sys.exit(0))
    last = None
    misses = 0
    while rd('mode') == 'video':
        r = mpv(['get_property', 'pause'])
        if r is None:
            misses += 1
            if misses > 5:
                break                             # mpv gone
            time.sleep(2); continue
        misses = 0
        # someone picked an IMAGE with another tool while the video played -> image mode
        cur = awww_image()
        if cur and not cur.startswith(STATE) and cur != rd('frame'):
            wr('image', cur); stop_video_engine(); wr('mode', 'image'); wr('reason', '')
            note('Image wallpaper picked: video wallpaper stopped')
            break
        why = []
        if rd('manual-pause') == '1': why.append('manual')
        if on_battery(): why.append('battery')
        if covered(): why.append('fullscreen')
        if pids(r'^hyprlock'): why.append('locked')
        want = bool(why)
        if want != last or (r.get('data') != want):
            mpv(['set_property', 'pause', want])
            wr('reason', ','.join(why))
            last = want
        time.sleep(2)
    return 0


def cmd_menu():
    rofi = ['rofi', '-config', os.path.join(HOME, '.config/hypr/rofi/config.rasi'), '-dmenu', '-i', '-p', 'Wallpaper',
            '-show-icons', '-theme-str',
            'window { width: 640px; } listview { lines: 8; columns: 1; } element { orientation: horizontal; '
            'children: [ element-icon, element-text ]; } element-icon { size: 54px; } element-text { vertical-align: 0.5; }']
    mode, cur_v, img = rd('mode', 'image'), rd('video'), rd('image')
    rows, acts = [], []
    if mode == 'video':
        paused = (mpv(['get_property', 'pause']) or {}).get('data')
        rows.append(('Back to image wallpaper' + (': ' + os.path.basename(img) if img else ''), img or 'image-x-generic'))
        acts.append(('image', None))
        rows.append(('Resume video' if rd('manual-pause') == '1' else 'Pause video', 'media-playback-pause'))
        acts.append(('pause', rd('manual-pause') != '1'))
    rows.append(('Pick an image…  (Super+W)', 'image-x-generic')); acts.append(('picker', None))
    for v in videos():
        label = os.path.basename(v) + ('   ✓ playing' if mode == 'video' and v == cur_v else '')
        rows.append((label, thumb_of(v))); acts.append(('video', v))
    rows.append(('Open video folder (~/Videos/Wallpapers)…', 'folder-videos')); acts.append(('folder', None))
    data = ''.join('%s\0icon\x1f%s\n' % (t, i) for t, i in rows)
    p = subprocess.run(rofi + ['-format', 'i'], input=data, capture_output=True, text=True)
    if p.returncode != 0 or not p.stdout.strip().isdigit():
        return 0
    act, arg = acts[int(p.stdout.strip())]
    if act == 'image': return cmd_image()
    if act == 'pause': return cmd_pause(arg)
    if act == 'video': return cmd_video(arg)
    if act == 'picker':
        subprocess.Popen(['qs', 'ipc', '-c', 'island', 'call', 'wallpaper', 'toggle']); return 0
    if act == 'folder':
        os.makedirs(VIDEO_DIRS[0], exist_ok=True)
        subprocess.Popen(['xdg-open', VIDEO_DIRS[0]], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL); return 0
    return 0


def main(a):
    c = a[0] if a else ''
    if c == 'video' and len(a) > 1: return cmd_video(a[1])
    if c == 'image': return cmd_image(a[1] if len(a) > 1 else None)
    if c == 'toggle': return cmd_toggle()
    if c == 'pause': return cmd_pause(True)
    if c == 'play': return cmd_pause(False)
    if c == 'status': return cmd_status()
    if c == 'restore': return cmd_restore()
    if c == 'watch': return cmd_watch()
    if c == 'menu': return cmd_menu()
    print(__doc__); return 2


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
