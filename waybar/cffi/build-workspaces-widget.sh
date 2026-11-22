#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
# Build to a new inode so rebuilding cannot corrupt a library Waybar has loaded.
out=$(mktemp ./workspaces-widget.XXXXXX.so)
trap 'rm -f -- "$out"' EXIT HUP INT TERM
cc -std=c11 -O2 -Wall -Wextra -Werror -fPIC -shared \
  workspaces-widget.c -o "$out" $(pkg-config --cflags --libs gtk+-3.0 gtk-layer-shell-0)
chmod 755 "$out"
mv -f -- "$out" workspaces-widget.so
