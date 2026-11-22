#!/usr/bin/env python3
"""Open a floating, photo-sized viewer without changing the original image."""

import argparse
from pathlib import Path
import sys

import gi

gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("GdkPixbuf", "2.0")
from gi.repository import Gdk, GdkPixbuf, GLib, Gtk


def fit_size(width, height, max_width, max_height):
    ratio = min(1.0, max_width / width, max_height / height)
    return max(1, round(width * ratio)), max(1, round(height * ratio))


def screen_limits():
    display = Gdk.Display.get_default()
    pointer = display.get_default_seat().get_pointer()
    _, x, y = pointer.get_position()
    monitor = display.get_monitor_at_point(x, y) or display.get_primary_monitor()
    if monitor is None:
        monitor = display.get_monitor(0)
    area = monitor.get_workarea()
    # Reserve space for the title bar, desktop bar, and a comfortable outer gap.
    # Keep the viewer compact: roughly half the previous maximum while still
    # preserving the source image's aspect ratio.
    return max(1, int(area.width * 0.425)), max(1, int(area.height * 0.425) - 24)


class PhotoWindow(Gtk.Window):
    def __init__(self, path):
        super().__init__(title=path.name)
        self.set_role("waybar-photo-viewer")
        self.set_type_hint(Gdk.WindowTypeHint.DIALOG)
        self.set_resizable(False)
        self.set_position(Gtk.WindowPosition.CENTER)

        info, width, height = GdkPixbuf.Pixbuf.get_file_info(str(path))
        if info is None or width <= 0 or height <= 0:
            raise ValueError("This file is not a readable photo")
        max_width, max_height = screen_limits()
        width, height = fit_size(width, height, max_width, max_height)
        pixels = GdkPixbuf.Pixbuf.new_from_file_at_scale(str(path), width, height, True)
        pixels = pixels.apply_embedded_orientation()
        # EXIF orientation may swap width and height after decoding.
        width, height = fit_size(pixels.get_width(), pixels.get_height(),
                                 max_width, max_height)
        if (width, height) != (pixels.get_width(), pixels.get_height()):
            pixels = pixels.scale_simple(width, height, GdkPixbuf.InterpType.BILINEAR)

        header = Gtk.HeaderBar(title=path.name, show_close_button=True)
        self.set_titlebar(header)
        self.image = Gtk.Image.new_from_pixbuf(pixels)
        self.add(self.image)
        self.set_default_size(width, height)
        self.connect("key-press-event", self.on_key)
        self.connect("destroy", lambda *_: Gtk.main_quit())

    def on_key(self, _widget, event):
        if event.keyval == Gdk.KEY_Escape:
            self.destroy()
            return True
        return False


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("photo", type=Path)
    args = parser.parse_args()
    GLib.set_prgname("waybar-photo-viewer")
    GLib.set_application_name("Waybar Photo")
    Gtk.init(None)
    window = PhotoWindow(args.photo.expanduser().resolve())
    window.show_all()
    Gtk.main()


if __name__ == "__main__":
    try:
        main()
    except (OSError, ValueError, GLib.Error) as error:
        print(f"photo-viewer: {error}", file=sys.stderr)
        sys.exit(1)
