#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
# Build to a new inode so rebuilding cannot corrupt a library Waybar has loaded.
out=$(mktemp ./radar-widget.XXXXXX.so)
trap 'rm -f -- "$out"' EXIT HUP INT TERM
cc -std=c11 -O2 -Wall -Wextra -Werror -fPIC -shared \
  radar-widget.c -o "$out" $(pkg-config --cflags --libs gtk+-3.0) -lm
chmod 755 "$out"
mv -f -- "$out" radar-widget.so
