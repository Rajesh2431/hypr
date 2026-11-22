#!/usr/bin/env python3
"""Choose a photo for Waybar's image module without modifying the originals."""

import argparse
import fcntl
import hashlib
import html
import json
import os
from pathlib import Path
import random
import subprocess
import sys
import time

import gi

gi.require_version("GdkPixbuf", "2.0")
from gi.repository import GdkPixbuf, GLib


PLACEHOLDER = Path(__file__).resolve().parent.parent / "assets/photo-placeholder.svg"
EXTENSIONS = {
    "." + extension.lower()
    for image_format in GdkPixbuf.Pixbuf.get_formats()
    for extension in image_format.get_extensions()
}


def find_photos(directory):
    if not directory.is_dir():
        return []
    return sorted({
        str(path.resolve())
        for path in directory.rglob("*")
        if path.is_file()
        and path.suffix.lower() in EXTENSIONS
        and "\n" not in str(path)
        and "\r" not in str(path)
    })


def readable_image(path):
    try:
        return GdkPixbuf.Pixbuf.get_file_info(path)[0] is not None
    except (GLib.Error, OSError):
        return False


def choose_photo(photos, state, delay, now):
    """Keep a shuffled queue, noticing added/deleted files on every poll."""
    current = state.get("current")
    unchanged = state.get("photos") == photos
    if (
        unchanged
        and current in photos
        and 0 <= now - state.get("selected_at", 0) < delay
    ):
        return state

    remaining = state.get("remaining", []) if unchanged else []
    selected = None
    # A round may end with damaged files. Start another round immediately
    # instead of briefly showing the empty-folder placeholder.
    for _ in range(2):
        if not remaining:
            remaining = photos.copy()
            random.shuffle(remaining)
            # Do not repeat the last photo between shuffled rounds.
            if len(remaining) > 1 and remaining[-1] == current:
                remaining[0], remaining[-1] = remaining[-1], remaining[0]
        while remaining:
            candidate = remaining.pop()
            if readable_image(candidate):
                selected = candidate
                break
        if selected:
            break

    return {
        "photos": photos,
        "remaining": remaining,
        "current": selected,
        "selected_at": now,
    }


def load_state(path):
    try:
        state = json.loads(path.read_text())
        if (
            isinstance(state, dict)
            and isinstance(state.get("photos"), list)
            and all(isinstance(p, str) for p in state["photos"])
            and isinstance(state.get("remaining"), list)
            and all(p in state["photos"] for p in state["remaining"])
            and (state.get("current") is None or state["current"] in state["photos"])
            and isinstance(state.get("selected_at"), (int, float))
        ):
            return state
    except (OSError, ValueError, TypeError):
        pass
    return {}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path.home() / "Pictures/waybar")
    parser.add_argument("--delay", type=float, default=30, help="Seconds between photos")
    parser.add_argument("--open", action="store_true", help="Open a photo-sized floating viewer")
    args = parser.parse_args()
    if args.delay <= 0:
        parser.error("--delay must be greater than zero")

    directory = args.directory.expanduser().resolve()
    cache_root = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    cache = cache_root / "waybar/photo-showcase"
    cache.mkdir(parents=True, exist_ok=True)
    key = hashlib.sha256(str(directory).encode()).hexdigest()[:16]
    state_path = cache / (key + ".json")

    # Multiple monitor bars share one queue and change photos at the same pace.
    with (cache / (key + ".lock")).open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        state = load_state(state_path)
        photos = find_photos(directory)
        if not args.open:
            state = choose_photo(photos, state, args.delay, time.time())
            temporary = state_path.with_suffix(".tmp")
            temporary.write_text(json.dumps(state))
            temporary.replace(state_path)
        current = state.get("current")

    if args.open:
        if current in photos:
            command = [sys.executable, str(Path(__file__).with_name("photo-viewer.py")), current]
        else:
            command = ["xdg-open", str(directory)]
        subprocess.Popen(command, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)
    elif current:
        print(current)
        print(html.escape(Path(current).name) + " — click to open")
    else:
        print(PLACEHOLDER)
        print("Add photos to " + html.escape(str(directory)))


if __name__ == "__main__":
    try:
        main()
    except (OSError, GLib.Error) as error:
        print(f"photo-showcase: {error}", file=sys.stderr)
        print(PLACEHOLDER)
        print("Photo showcase unavailable")
