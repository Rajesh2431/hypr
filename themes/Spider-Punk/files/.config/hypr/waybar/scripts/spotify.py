#!/usr/bin/env python3
"""Spotify for Waybar (Web API via spotipy).

  spotify.py status [--cffi]  feed for the waybar module (--cffi: cffi/spotify-widget.so)
  spotify.py auth          one-time browser login (token cached)
  spotify.py toggle|next|prev|like|shuffle|repeat|volup|voldown|open|menu

Credentials: ~/.config/spotify-bar/credentials.env  (SPOTIPY_CLIENT_ID, ...)
Token cache: ~/.cache/spotify-bar/token

Playback control uses the local Spotify client over MPRIS (playerctl) when it is
the active device, which also works without Premium. Otherwise it uses the
Web API, which needs Premium.
"""
# die with the parent (waybar / quickshell), and make our own long-running
# children (pactl subscribe, nmcli monitor, dbus-monitor, ...) die with us
import ctypes as _ctypes, signal as _signal
def _pdeathsig():
    try:
        _ctypes.CDLL("libc.so.6", use_errno=True).prctl(1, _signal.SIGTERM)   # PR_SET_PDEATHSIG
    except Exception:
        pass
import sys as _sys
if len(_sys.argv) > 1 and _sys.argv[1] == "status":   # only the long-running feed, never one-shot actions
    _pdeathsig()

import html
import json
import os
import subprocess
import sys
import time
from pathlib import Path

CONF = Path.home() / ".config/spotify-bar"
CACHE = Path.home() / ".cache/spotify-bar"
TOKEN = CACHE / "token"
TRIGGER = CACHE / "refresh"
STATE = CACHE / "state.json"
ROFI_THEME = Path.home() / ".config/hypr/rofi/config-rofi-Beats-menu.rasi"
SCOPE = ("user-read-playback-state user-modify-playback-state user-read-currently-playing "
         "user-library-read user-library-modify playlist-read-private playlist-read-collaborative")

GREEN = "#1DB954"
# bar text budget; keep equal to "label-chars" of cffi/spotify in UserModules
LABEL_CHARS = int(os.environ.get("SPOTIFY_BAR_CHARS", "40"))
I_SPOTIFY = ""
I_PLAY, I_PAUSE = "\U000f040a", "\U000f03e4"
I_HEART, I_HEART_O = "\U000f02d1", "\U000f02d5"
I_SHUFFLE, I_REPEAT, I_REPEAT_ONE = "\U000f049d", "\U000f0456", "\U000f0458"
I_PREV, I_NEXT = "\U000f04ae", "\U000f04ad"
I_LIST, I_DEVICE, I_OPEN = "\U000f0cb8", "\U000f04c3", "\U000f03cc"

CACHE.mkdir(parents=True, exist_ok=True)
os.chmod(CACHE, 0o700)


def load_env():
    f = CONF / "credentials.env"
    if f.exists():
        for line in f.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def auth_manager(open_browser=False):
    load_env()
    from spotipy.cache_handler import CacheFileHandler
    from spotipy.oauth2 import SpotifyOAuth
    return SpotifyOAuth(scope=SCOPE, open_browser=open_browser,
                        cache_handler=CacheFileHandler(cache_path=str(TOKEN)))


def client():
    """Spotify client, or None when not logged in yet (never blocks on a browser)."""
    import spotipy
    am = auth_manager()
    if not am.validate_token(am.cache_handler.get_cached_token()):
        return None
    return spotipy.Spotify(auth_manager=am, requests_timeout=6, retries=0)


def notify(msg, body=""):
    subprocess.Popen(["notify-send", "-a", "Spotify", "-i", "spotify-client", "-t", "2500", msg, body],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def poke():
    TRIGGER.touch()


def fmt_ms(ms):
    s = max(0, int(ms // 1000))
    return f"{s // 60}:{s % 60:02d}"


def local_player():
    """True when the desktop Spotify client is running (MPRIS)."""
    try:
        out = subprocess.run(["playerctl", "-l"], capture_output=True, text=True, timeout=2).stdout
        return "spotify" in out.split()
    except Exception:
        return False


def pctl(*args):
    return subprocess.run(["playerctl", "-p", "spotify", *args], capture_output=True, timeout=3).returncode == 0


# --------------------------------------------------------------------- status
COVERS = CACHE / "covers"
LYRICS = CACHE / "lyrics"
SETTINGS = CACHE / "settings.json"
LRCLIB = "https://lrclib.net/api"
UA = {"User-Agent": "waybar-spotify (github.com/LinuxBeginnings KoolDots user script)"}


def settings():
    try:
        return {"lyrics": True, **json.loads(SETTINGS.read_text())}
    except Exception:
        return {"lyrics": True}


def item_meta(item):
    """(title, artist, album, year, image_url) for a track or episode."""
    title = item.get("name", "")
    if item.get("type") == "episode":
        show = item.get("show") or {}
        artist, album = show.get("name", ""), show.get("publisher", "")
        year, images = (item.get("release_date") or "")[:4], item.get("images") or show.get("images") or []
    else:
        alb = item.get("album") or {}
        artist = ", ".join(a["name"] for a in item.get("artists", []))
        album, year, images = alb.get("name", ""), (alb.get("release_date") or "")[:4], alb.get("images") or []
    url = images[0]["url"] if images else None   # largest first
    return title, artist, album, year, url


def fetch_cover(url):
    import hashlib
    import requests
    COVERS.mkdir(exist_ok=True)
    path = COVERS / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".jpg")
    if not path.exists():
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        tmp = path.with_suffix(".tmp")
        tmp.write_bytes(r.content)
        tmp.replace(path)
        # keep the cache small
        files = sorted(COVERS.glob("*.jpg"), key=lambda p: p.stat().st_mtime)
        for old in files[:-60]:
            old.unlink(missing_ok=True)
    return str(path)


def parse_lrc(text):
    import re
    out = []
    for line in (text or "").splitlines():
        stamps = re.findall(r"\[(\d+):(\d+(?:\.\d+)?)\]", line)
        words = re.sub(r"\[[^\]]*\]", "", line).strip()
        for m, s in stamps:
            out.append((int(m) * 60000 + float(s) * 1000, words))
    return sorted(out)


def fetch_lyrics(item):
    """Synced lyrics from LRCLIB, cached per track: list of (ms, line) or []."""
    import requests
    LYRICS.mkdir(exist_ok=True)
    path = LYRICS / f"{item['id']}.json"
    if path.exists():
        return [tuple(x) for x in json.loads(path.read_text())]
    title, artist, album, _, _ = item_meta(item)
    lines = []
    q = {"track_name": title, "artist_name": artist.split(",")[0], "album_name": album,
         "duration": round((item.get("duration_ms") or 0) / 1000)}
    r = requests.get(f"{LRCLIB}/get", params=q, headers=UA, timeout=10)
    if r.status_code == 200 and r.json().get("syncedLyrics"):
        lines = parse_lrc(r.json()["syncedLyrics"])
    elif r.status_code in (200, 404):
        r = requests.get(f"{LRCLIB}/search", params={"track_name": title, "artist_name": q["artist_name"]},
                         headers=UA, timeout=10)
        if r.ok:
            dur = q["duration"]
            hits = [h for h in r.json() if h.get("syncedLyrics") and abs((h.get("duration") or 0) - dur) <= 4]
            if hits:
                lines = parse_lrc(hits[0]["syncedLyrics"])
    else:
        r.raise_for_status()
    path.write_text(json.dumps(lines))
    return lines


def status_loop(cffi=False, island=False):
    from concurrent.futures import ThreadPoolExecutor
    pool = ThreadPoolExecutor(2)
    sp, sp_checked = None, 0
    pb, fetched, last_trig = None, 0.0, 0.0
    liked = {}                 # track id -> bool
    covers, lyrics, jobs = {}, {}, {}   # url -> path, track id -> lines, key -> future
    backoff, error, last_out, last_emit = 0.0, None, None, 0.0
    opts, opts_mtime = settings(), 0.0

    # MPRIS follower: the local client announces play/pause/track changes (and its
    # own start-up) instantly, so the API is re-polled at once instead of waiting
    # for the next 6 s tick or an error backoff
    import threading
    mpris = [0]
    def follow_mpris():
        while True:
            try:
                p = subprocess.Popen(["playerctl", "-p", "spotify", "-F", "metadata", "--format",
                                      "{{status}}|{{mpris:trackid}}"],
                                     stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                for _ in p.stdout:
                    mpris[0] += 1
                p.wait()
            except Exception:
                pass
            time.sleep(3)
    threading.Thread(target=follow_mpris, daemon=True).start()
    last_mpris = 0

    def emit(obj):
        nonlocal last_out, last_emit
        if cffi:
            line = "\x1f".join([obj.get("class", ""), obj.get("cover", ""),
                                obj.get("text", ""), obj.get("tooltip", ""),
                                obj.get("key", "")]).replace("\n", "\x1e")
        else:
            line = json.dumps({k: v for k, v in obj.items() if k != "cover"})
        if line != last_out or time.time() - last_emit > 10:
            sys.stdout.write(line + "\n")
            sys.stdout.flush()
            last_out, last_emit = line, time.time()

    def background(key, fn, *args):
        """Run fn in a thread once per key; return result when ready, else None."""
        f = jobs.get(key)
        if f is None:
            jobs[key] = pool.submit(fn, *args)
            return None
        if not f.done():
            return None
        try:
            return f.result()
        except Exception:
            return None

    while True:
        now = time.time()
        trig = TRIGGER.stat().st_mtime if TRIGGER.exists() else 0
        kick = mpris[0] != last_mpris       # Spotify itself changed state
        if kick:
            last_mpris, backoff = mpris[0], 0.0
        if SETTINGS.exists() and SETTINGS.stat().st_mtime != opts_mtime:
            opts_mtime, opts = SETTINGS.stat().st_mtime, settings()
        if sp is None and now - sp_checked > 5:
            sp_checked = now
            try:
                sp = client()
            except Exception:
                sp = None
        if sp is None and island:
            emit_island({"state": "login"})
            time.sleep(2)
            continue
        if sp is None:
            emit({"text": ("" if cffi else f"<span color='{GREEN}'>{I_SPOTIFY}</span> ") + "Log in",
                  "tooltip": "<b>Spotify</b>: not logged in\nClick to log in", "class": "login"})
            time.sleep(2)
            continue

        if (CACHE / "liked-dirty").exists():
            (CACHE / "liked-dirty").unlink(missing_ok=True)
            liked.clear()
        playing = bool(pb and pb.get("is_playing"))
        due = (2.5 if playing else 6) + backoff
        if kick or trig != last_trig or now - fetched >= due:
            if kick or trig != last_trig:
                time.sleep(0.35)   # let Spotify apply the change first
            last_trig = trig
            try:
                pb = sp.current_playback(additional_types="episode")
                fetched, backoff, error = time.time(), 0.0, None
                item = (pb or {}).get("item")
                if item and item.get("type") == "track" and item["id"] and item["id"] not in liked:
                    liked[item["id"]] = bool(sp.current_user_saved_tracks_contains([item["id"]])[0])
                STATE.write_text(json.dumps({"pb": pb, "liked": liked.get(item["id"]) if item else None}))
            except Exception as e:  # network / rate limit / token
                fetched, backoff = time.time(), min(60.0, backoff * 2 + 5)
                error = str(e).splitlines()[0][:120]
                if "401" in error or "token" in error.lower():
                    sp = None

        item = (pb or {}).get("item") or {}
        cover = lines = None
        if item:
            url = item_meta(item)[4]
            if url:
                cover = covers.get(url) or background(("c", url), fetch_cover, url)
                if cover:
                    covers[url] = cover
            if item.get("type") == "track" and item.get("id"):
                tid = item["id"]
                if tid in lyrics:
                    lines = lyrics[tid]
                else:
                    res = background(("l", tid), fetch_lyrics, item)
                    job = jobs[("l", tid)]
                    if res is not None:
                        lyrics[tid] = lines = res
                    elif job.done() and job.exception() is not None:
                        # network hiccup: forget the failed job and retry in 30 s
                        if time.time() - getattr(job, "failed_at", 0) > 30:
                            if not hasattr(job, "failed_at"):
                                job.failed_at = time.time()
                            else:
                                jobs.pop(("l", tid), None)
        if island:
            emit_island(island_state(pb, fetched, liked, error, cover, lines))
        else:
            emit(render(pb, fetched, liked, error, cffi=cffi, cover=cover, lines=lines,
                        lyrics_on_bar=opts.get("lyrics", True)))

        # tick fast enough for lyric timing; wake early on actions
        for _ in range(2):
            time.sleep(0.125)
            if mpris[0] != last_mpris or (TRIGGER.exists() and TRIGGER.stat().st_mtime != last_trig):
                break


_island_last = [None]


def emit_island(d):
    if d.get("title") and d.get("cover"):
        remember_last(d)
    out = json.dumps(d, ensure_ascii=False)
    if out != _island_last[0]:
        try:
            print(out, flush=True)
        except BrokenPipeError:
            sys.exit(0)
        _island_last[0] = out


LAST = CACHE / "last.json"


def remember_last(d):
    keep = {k: d.get(k) for k in ("title", "artist", "album", "cover", "key", "duration", "progress")}
    try:
        if not LAST.exists() or json.loads(LAST.read_text()).get("key") != keep["key"] or d.get("playing"):
            LAST.write_text(json.dumps(keep))
    except Exception:
        pass


def last_played():
    try:
        d = json.loads(LAST.read_text())
        return d if d.get("title") else None
    except Exception:
        return None


def island_state(pb, fetched, liked, error, cover, lines):
    """Structured state for the Quickshell Dynamic Island (progress is
    interpolated on the island side from progress + at)."""
    item = (pb or {}).get("item")
    if not item:
        return {"state": "offline" if error else "idle", "error": error or "", "last": last_played(),
                "app": subprocess.run(["pgrep", "-x", "spotify"], capture_output=True).returncode == 0}
    title, artist, album, year, _ = item_meta(item)
    return {
        "state": "playing" if pb.get("is_playing") else "paused",
        "key": item.get("id") or item.get("uri") or title,
        "title": title, "artist": artist, "album": album, "year": year,
        "cover": cover or "", "duration": item.get("duration_ms") or 0,
        "progress": pb.get("progress_ms") or 0, "at": fetched,
        "playing": bool(pb.get("is_playing")), "liked": liked.get(item.get("id")),
        "device": (pb.get("device") or {}).get("name", ""),
        "shuffle": bool(pb.get("shuffle_state")), "repeat": pb.get("repeat_state", "off"),
        "lyrics": lines,   # None = still loading, [] = none found, [[ms, text], ...]
    }


def bar(frac, width):
    frac = min(1.0, max(0.0, frac))
    pos = int(round(frac * (width - 1)))
    return "━" * pos + "●" + "─" * (width - 1 - pos)


def clip(s, n):
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def render(pb, fetched, liked, error, cffi=False, cover=None, lines=None, lyrics_on_bar=True):
    item = (pb or {}).get("item")
    icon = "" if cffi else f"<span color='{GREEN}'>{I_SPOTIFY}</span> "
    if not item:
        if error:
            return {"text": icon.strip(), "tooltip": f"<b>Spotify</b>: {html.escape(error)}", "class": "offline"}
        return {"text": icon.strip(),
                "tooltip": "<b>Spotify</b>  ·  nothing playing\n\n<span alpha='55%' size='small'>"
                           "Left: open Spotify · Right: playlists / devices menu</span>",
                "class": "idle"}

    playing = pb.get("is_playing")
    progress = pb.get("progress_ms") or 0
    if playing:
        progress += (time.time() - fetched) * 1000
    dur = item.get("duration_ms") or 1
    progress = min(progress, dur)
    title, artist, album, year, _ = item_meta(item)
    is_liked = liked.get(item.get("id"))

    # current lyric line
    idx = -1
    if lines:
        for i, (t, _) in enumerate(lines):
            if t <= progress + 150:
                idx = i
            else:
                break
    cur = lines[idx][1] if lines and idx >= 0 else ""

    dim = "" if playing else " alpha='55%'"
    if lyrics_on_bar and cur:
        label = f"<span color='{GREEN}'>♪</span> <span{dim}><i>{html.escape(clip(cur, LABEL_CHARS - 4))}</i></span>"
    else:
        label = f"<span{dim}>{html.escape(clip(f'{title} · {artist}' if artist else title, LABEL_CHARS - 2))}</span>"
    heart = f" <span color='{GREEN}'>{I_HEART}</span>" if is_liked else ""
    text = f"{icon}{label}{heart}"

    dev = pb.get("device") or {}
    vol = dev.get("volume_percent")
    rep = pb.get("repeat_state", "off")
    rep_icon = I_REPEAT_ONE if rep == "track" else I_REPEAT
    on = lambda b: f"<span color='{GREEN}'>" if b else "<span alpha='40%'>"
    state_icon = I_PAUSE if playing else I_PLAY
    tip = [
        f"<span size='large'><b>{html.escape(title)}</b></span>",
        html.escape(artist),
        f"<i><span alpha='70%'>{html.escape(album)}</span></i>" + (f"  <span alpha='50%'>({year})</span>" if year else ""),
        "",
        f"<span color='{GREEN}'>{state_icon}</span>  {fmt_ms(progress)}  <tt>{bar(progress / dur, 18)}</tt>  {fmt_ms(dur)}",
        f"<span size='small'>{I_DEVICE}  {html.escape(dev.get('name', '?'))}" + (f"  ·  {vol}%" if vol is not None else "")
        + f"     {on(pb.get('shuffle_state'))}{I_SHUFFLE}</span>  {on(rep != 'off')}{rep_icon}</span>"
        + (f"     <span color='{GREEN}'>{I_HEART}</span>" if is_liked else f"     <span alpha='40%'>{I_HEART_O}</span>")
        + "</span>",
    ]
    if lines:
        tip.append("")
        lo = max(0, idx - 1)
        for j in range(lo, min(len(lines), lo + 5)):
            words = html.escape(lines[j][1]) or "♪"
            if j == idx:
                tip.append(f"<span color='{GREEN}' size='large'><b>{words}</b></span>")
            else:
                tip.append(f"<span alpha='45%'>{words}</span>")
    elif lines is not None and item.get("type") == "track":
        tip += ["", "<span alpha='40%' size='small'>No synced lyrics found</span>"]
    if error:
        tip.append(f"<span color='#ff6b6b' size='small'>{html.escape(error)}</span>")
    tip += ["", "<span alpha='45%' size='small'>Left: play/pause · Middle: like · Right: menu\n"
                "Scroll: volume · Side buttons: prev/next</span>"]
    return {"text": text, "tooltip": "\n".join(tip), "class": "playing" if playing else "paused",
            "key": item.get("id") or item.get("uri") or title,
            "cover": cover or ""}


# -------------------------------------------------------------------- actions
def cached_state():
    try:
        d = json.loads(STATE.read_text())
        return d.get("pb") or {}, d.get("liked")
    except Exception:
        return {}, None


def local_is_active(pb):
    """Local client running and it is (or likely is) the active device."""
    if not local_player():
        return False
    dev = (pb or {}).get("device") or {}
    return not dev or dev.get("type") == "Computer"


def api(fn, ok_msg=None):
    sp = client()
    if sp is None:
        notify("Spotify", "Not logged in. Click the Spotify module to log in.")
        return False
    try:
        fn(sp)
        if ok_msg:
            notify(*ok_msg)
        return True
    except Exception as e:
        msg = str(e)
        if "PREMIUM" in msg.upper() or "403" in msg:
            notify("Spotify", "This control needs Spotify Premium (or the desktop app as the active device).")
        elif "NO_ACTIVE_DEVICE" in msg or "404" in msg:
            notify("Spotify", "No active device. Open Spotify somewhere or pick a device from the menu.")
        else:
            notify("Spotify error", msg.splitlines()[0][:200])
        return False


def act_toggle():
    pb, _ = cached_state()
    if local_is_active(pb) and pctl("play-pause"):
        return
    api(lambda sp: sp.pause_playback() if (sp.current_playback() or {}).get("is_playing") else sp.start_playback())


def act_next():
    pb, _ = cached_state()
    if not (local_is_active(pb) and pctl("next")):
        api(lambda sp: sp.next_track())


def act_prev():
    pb, _ = cached_state()
    if not (local_is_active(pb) and pctl("previous")):
        api(lambda sp: sp.previous_track())


def act_like():
    def go(sp):
        item = (sp.current_playback() or {}).get("item")
        if not item or item.get("type") != "track":
            notify("Spotify", "Nothing to like right now.")
            return
        tid, name = item["id"], item["name"]
        if sp.current_user_saved_tracks_contains([tid])[0]:
            sp.current_user_saved_tracks_delete([tid])
            notify("Removed from Liked Songs", name)
        else:
            sp.current_user_saved_tracks_add([tid])
            notify("Added to Liked Songs", name)
        (CACHE / "liked-dirty").touch()   # status loop re-reads like state
    api(go)


def act_shuffle():
    def go(sp):
        new = not (sp.current_playback() or {}).get("shuffle_state")
        sp.shuffle(new)
        notify("Shuffle " + ("on" if new else "off"))
    pb, _ = cached_state()
    if not api(go) and local_is_active(pb):
        pctl("shuffle", "Toggle")


def act_repeat():
    order = {"off": "context", "context": "track", "track": "off"}
    def go(sp):
        new = order[(sp.current_playback() or {}).get("repeat_state", "off")]
        sp.repeat(new)
        notify("Repeat: " + {"off": "off", "context": "all", "track": "one"}[new])
    api(go)


def act_resume():
    if subprocess.run(["pgrep", "-x", "spotify"], capture_output=True).returncode != 0:
        subprocess.Popen(["spotify"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
        notify("Opening Spotify…", (last_played() or {}).get("title", ""))
    for _ in range(40):                      # up to ~20 s for the app to register on MPRIS
        if local_player():
            time.sleep(1.0)                  # let it load the last session
            if pctl("play"):
                return
        time.sleep(0.5)
    api(lambda sp: sp.start_playback())      # fallback: Web API (Premium)


def act_seek(ms):
    ms = max(0, int(float(ms)))
    pb, _ = cached_state()
    if local_is_active(pb) and pctl("position", f"{ms / 1000:.2f}"):
        return
    api(lambda sp: sp.seek_track(ms))


def act_volume(delta):
    pb, _ = cached_state()
    if local_is_active(pb) and pctl("volume", f"{abs(delta) / 100}{'+' if delta > 0 else '-'}"):
        return
    def go(sp):
        cur = ((sp.current_playback() or {}).get("device") or {}).get("volume_percent")
        if cur is not None:
            sp.volume(max(0, min(100, cur + delta)))
    api(go)


def act_open():
    if subprocess.run(["pgrep", "-x", "spotify"], capture_output=True).returncode == 0:
        subprocess.run(["hyprctl", "dispatch", 'hl.dsp.focus({ window = "class:^(Spotify|spotify)$" })'],
                       capture_output=True)
    else:
        subprocess.Popen(["spotify"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)


def rofi(entries, prompt, mesg=None):
    cmd = ["rofi", "-dmenu", "-i", "-p", prompt, "-format", "i"]
    if ROFI_THEME.exists():
        cmd += ["-config", str(ROFI_THEME), "-theme-str", "entry { placeholder: \"" + prompt + "\"; } listview { lines: 9; }"]
    if mesg:
        cmd += ["-mesg", mesg]
    r = subprocess.run(cmd, input="\n".join(entries), capture_output=True, text=True)
    out = r.stdout.strip()
    return int(out) if r.returncode == 0 and out.isdigit() else None


def act_playlists():
    sp = client()
    if sp is None:
        return notify("Spotify", "Not logged in.")
    me = sp.me()
    items, res = [], sp.current_user_playlists(limit=50)
    while res:
        items += [p for p in res["items"] if p]
        res = sp.next(res) if res.get("next") and len(items) < 200 else None
    names = [f"{I_HEART}  Liked Songs"] + [f"{I_LIST}  {p['name']}" for p in items]
    i = rofi(names, "Play playlist")
    if i is None:
        return
    if i == 0:
        ctx = f"spotify:user:{me['id']}:collection"
        label = "Liked Songs"
    else:
        ctx, label = items[i - 1]["uri"], items[i - 1]["name"]
    api(lambda s: s.start_playback(context_uri=ctx), ("Playing", label))


def act_devices():
    sp = client()
    if sp is None:
        return notify("Spotify", "Not logged in.")
    devs = sp.devices().get("devices", [])
    if not devs:
        return notify("Spotify", "No devices found. Open Spotify on a device first.")
    names = [f"{'● ' if d['is_active'] else '   '}{d['name']}  ({d['type']})" for d in devs]
    i = rofi(names, "Play on device")
    if i is not None:
        d = devs[i]
        api(lambda s: s.transfer_playback(d["id"], force_play=True), ("Playing on", d["name"]))


def act_menu():
    pb, is_liked = cached_state()
    item = (pb or {}).get("item") or {}
    playing = pb.get("is_playing") if pb else False
    rep = {"off": "off", "context": "all", "track": "one"}.get((pb or {}).get("repeat_state", "off"), "off")
    entries = [
        (f"{I_PAUSE if playing else I_PLAY}  {'Pause' if playing else 'Play'}", act_toggle),
        (f"{I_NEXT}  Next", act_next),
        (f"{I_PREV}  Previous", act_prev),
        (f"{I_HEART if not is_liked else I_HEART_O}  {'Remove from' if is_liked else 'Add to'} Liked Songs", act_like),
        (f"{I_SHUFFLE}  Shuffle: {'on' if (pb or {}).get('shuffle_state') else 'off'}", act_shuffle),
        (f"{I_REPEAT}  Repeat: {rep}", act_repeat),
        (f"\U000f0cb9  Lyrics on bar: {'on' if settings().get('lyrics', True) else 'off'}", act_lyrics),
        (f"{I_LIST}  Playlists…", act_playlists),
        (f"{I_DEVICE}  Devices…", act_devices),
        (f"{I_OPEN}  Open Spotify", act_open),
    ]
    mesg = None
    if item:
        artist = ", ".join(a["name"] for a in item.get("artists", [])) or (item.get("show") or {}).get("name", "")
        mesg = f"{item.get('name', '')}  —  {artist}"
    i = rofi([e[0] for e in entries], "Spotify", mesg)
    if i is not None:
        entries[i][1]()


def act_lyrics():
    o = settings()
    o["lyrics"] = not o.get("lyrics", True)
    SETTINGS.write_text(json.dumps(o))
    notify("Lyrics on bar " + ("on" if o["lyrics"] else "off"))


def act_auth():
    import spotipy
    am = auth_manager(open_browser=True)
    print("Opening the browser for Spotify login… (waiting for the redirect on 127.0.0.1:8888)")
    am.get_access_token(as_dict=False)
    me = spotipy.Spotify(auth_manager=am).me()
    print(f"Logged in as {me.get('display_name') or me['id']} ({me.get('product', '?')})")
    notify("Spotify connected", f"Logged in as {me.get('display_name') or me['id']}")


def act_click():
    """Left click: log in if needed, else play/pause."""
    am = auth_manager()
    if not am.cache_handler.get_cached_token():
        term = os.environ.get("TERMINAL") or "kitty"
        subprocess.Popen([term, "-e", sys.executable, __file__, "auth"], start_new_session=True)
    elif not (cached_state()[0] or {}).get("item"):
        act_open()          # nothing playing: open the app
    else:
        act_toggle()


ACTIONS = {
    "toggle": act_toggle, "click": act_click, "next": act_next, "prev": act_prev, "like": act_like,
    "shuffle": act_shuffle, "repeat": act_repeat, "volup": lambda: act_volume(5),
    "voldown": lambda: act_volume(-5), "open": act_open, "menu": act_menu,
    "playlists": act_playlists, "lyrics": act_lyrics, "resume": act_resume, "devices": act_devices, "auth": act_auth,
}

if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "status":
        status_loop(cffi="--cffi" in sys.argv, island="--island" in sys.argv)
    elif cmd == "seek" and len(sys.argv) == 3:
        act_seek(sys.argv[2])
        poke()
    elif cmd in ACTIONS:
        ACTIONS[cmd]()
        poke()
    else:
        sys.exit(__doc__)
