#!/bin/sh
set -eu
cd -- "$(dirname -- "$0")"
# Build to a new inode so rebuilding cannot corrupt a library Waybar has loaded.
build_output=$(mktemp ./photo-preview.XXXXXX.so)
trap 'rm -f -- "$build_output"' EXIT HUP INT TERM
cc -std=c11 -O2 -Wall -Wextra -Werror -fPIC -shared \
  photo-preview.c -o "$build_output" $(pkg-config --cflags --libs gtk+-3.0)
chmod 755 "$build_output"
mv -f -- "$build_output" photo-preview.so
