#!/usr/bin/env python3
"""Wallpaper list + cached thumbnails for the island wallpaper picker.

Prints one JSON line:  {"current": path, "items": [{path, name, thumb, video}, ...]}
Thumbnails: ~/.cache/island/wallthumbs/<hash>.jpg (480 px wide). Missing ones
are reported as "" and generated afterwards in the background (low priority);
the picker then shows them the next time it opens (it reloads on its own when
generation finishes — this script prints a second line {"done": true}).
"""
import ctypes, hashlib, json, os, signal, subprocess, sys
from concurrent.futures import ThreadPoolExecutor

ctypes.CDLL("libc.so.6").prctl(1, signal.SIGTERM)

HOME = os.path.expanduser("~")
try:
    PICS = subprocess.run(["xdg-user-dir", "PICTURES"], capture_output=True, text=True, timeout=2).stdout.strip()
except Exception:
    PICS = ""
WALLDIR = os.path.join(PICS or os.path.join(HOME, "Pictures"), "wallpapers")
CACHE = os.path.join(HOME, ".cache/island/wallthumbs")
IMG = (".jpg", ".jpeg", ".png", ".webp", ".bmp", ".gif")
VID = (".mp4", ".mkv", ".mov", ".webm")


def thumb_for(path):
    st = os.stat(path)
    key = hashlib.sha1(f"{path}:{st.st_mtime_ns}:{st.st_size}".encode()).hexdigest()[:20]
    return os.path.join(CACHE, key + ".jpg")


def make(path, out):
    tmp = out + ".tmp.jpg"
    try:
        if path.lower().endswith(VID):
            cmd = ["ffmpeg", "-v", "error", "-y", "-ss", "1", "-i", path, "-vframes", "1", "-vf", "scale=480:-2", tmp]
        else:
            cmd = ["magick", path + ("[0]" if path.lower().endswith(".gif") else ""), "-auto-orient",
                   "-thumbnail", "480x", "-quality", "82", tmp]
        subprocess.run(["nice", "-n", "15"] + cmd, capture_output=True, timeout=60)
        if os.path.exists(tmp):
            os.replace(tmp, out)
    except Exception:
        pass


def current():
    mon = ""
    try:
        mons = json.loads(subprocess.run(["hyprctl", "-j", "monitors"], capture_output=True, text=True, timeout=2).stdout)
        mon = next((m["name"] for m in mons if m.get("focused")), "")
    except Exception:
        pass
    for link in (f"{HOME}/.config/hypr/rofi/.current_wallpaper_{mon}", f"{HOME}/.config/hypr/rofi/.current_wallpaper"):
        if os.path.exists(link):
            return os.path.realpath(link)
    return ""


def main():
    os.makedirs(CACHE, exist_ok=True)
    items, todo = [], []
    for root, _, files in os.walk(WALLDIR, followlinks=True):
        for f in files:
            if not f.lower().endswith(IMG + VID):
                continue
            p = os.path.join(root, f)
            try:
                t = thumb_for(p)
            except OSError:
                continue
            ok = os.path.exists(t)
            if not ok:
                todo.append((p, t))
            items.append({"path": p, "name": os.path.splitext(f)[0], "thumb": t if ok else "",
                          "video": f.lower().endswith(VID)})
    items.sort(key=lambda x: x["name"].lower())
    print(json.dumps({"current": current(), "dir": WALLDIR, "items": items}, ensure_ascii=False), flush=True)
    if todo:
        with ThreadPoolExecutor(max(2, (os.cpu_count() or 4) // 2)) as pool:
            list(pool.map(lambda a: make(*a), todo))
        print(json.dumps({"done": True}), flush=True)


if __name__ == "__main__":
    main()
