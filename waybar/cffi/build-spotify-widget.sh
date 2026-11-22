#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
# Build to a new inode so rebuilding cannot corrupt a library Waybar has loaded.
out=$(mktemp ./spotify-widget.XXXXXX.so)
trap 'rm -f -- "$out"' EXIT HUP INT TERM
cc -std=c11 -O2 -Wall -Wextra -Werror -fPIC -shared \
  spotify-widget.c -o "$out" $(pkg-config --cflags --libs gtk+-3.0)
chmod 755 "$out"
mv -f -- "$out" spotify-widget.so
