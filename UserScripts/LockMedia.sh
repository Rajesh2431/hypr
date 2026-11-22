#!/usr/bin/env bash
# Now-playing info for the hyprlock media card (hyprlock.conf + hyprlock-punk-art.conf).
#   LockMedia.sh art      cover image path (square crop, cached)
#   LockMedia.sh card [punk|glass]  card background image, tinted with the cover's colour (lockmedia-card.py)
#   LockMedia.sh title    track title (shortened)
#   LockMedia.sh artist   artist (shortened)
#   LockMedia.sh source   e.g. "SPOTIFY · PLAYING", in the cover's colour
# Picks the player that is playing (Spotify first), else one that is paused.
# Nothing playing: card, cover, title and source are blank; "artist" shows a faint "Nothing playing".
CACHE="${XDG_CACHE_HOME:-$HOME/.cache}/lockmedia"
ASSETS="$HOME/.config/hypr/waybar/assets/punk/lock"
NOART="$ASSETS/media-idle.png"      # cover for a track that has no artwork
BLANK="$ASSETS/blank.png"           # fully transparent: hides an image widget
mkdir -p "$CACHE"

player() {
  local p s best=""
  for p in $(playerctl -l 2>/dev/null | sort -r); do    # sort -r: "spotify" before "firefox…"
    s=$(playerctl -p "$p" status 2>/dev/null)
    [ "$s" = Playing ] && { echo "$p"; return; }
    [ "$s" = Paused ] && [ -z "$best" ] && best="$p"
  done
  echo "$best"
}
short() { local t="$1" n="$2"; [ "${#t}" -gt "$n" ] && t="${t:0:$((n - 1))}…"; printf '%s' "$t"; }
esc() { sed 's/&/\&amp;/g; s/</\&lt;/g; s/>/\&gt;/g'; }

# build (once per track artwork) the square cover, the tinted card and the accent colour
prepare() {
  local url src
  url=$(playerctl -p "$p" metadata mpris:artUrl 2>/dev/null)
  key=$(printf '%s' "$url" | md5sum | cut -c1-16)
  sq="$CACHE/$key-sq.png"; acc="$CACHE/$key-accent.txt"
  card="$CACHE/$key-card.png"; [ "$STYLE" = punk ] || card="$CACHE/$key-card-$STYLE.png"
  if [ ! -s "$sq" ]; then
    case "$url" in
      file://*) src="${url#file://}" ;;
      http*) src="$CACHE/$key.img"; [ -s "$src" ] || curl -sfL --max-time 5 -o "$src" "$url" || rm -f "$src" ;;
      *) src="" ;;
    esac
    { [ -n "$src" ] && [ -s "$src" ] && magick "$src" -resize '300x300^' -gravity center -extent 300x300 "$sq" 2>/dev/null; } ||
      cp "$NOART" "$sq"
  fi
  [ -s "$card" ] && [ -s "$acc" ] || python3 "$HOME/.config/hypr/UserScripts/lockmedia-card.py" "$sq" "$card" "$acc" "$STYLE" 2>/dev/null
  find "$CACHE" -type f -mtime +7 -delete 2>/dev/null
}

STYLE="${2:-punk}"                  # card look: punk (comic panel) or glass (Obsidian Glass)
p=$(player)
case "$1" in
  art)    [ -z "$p" ] && { echo "$BLANK"; exit; }; prepare; echo "$sq" ;;
  card)   [ -z "$p" ] && { echo "$BLANK"; exit; }; prepare; [ -s "$card" ] && echo "$card" || echo "$BLANK" ;;
  title)  [ -z "$p" ] && exit; short "$(playerctl -p "$p" metadata xesam:title 2>/dev/null)" 34 | esc ;;
  artist)
    [ -z "$p" ] && { echo "<span alpha='60%'>♪  Nothing playing</span>"; exit; }
    short "$(playerctl -p "$p" metadata xesam:artist 2>/dev/null)" 38 | esc ;;
  source)
    [ -z "$p" ] && exit
    prepare; c=$(cat "$acc" 2>/dev/null); c=${c:-#FF1744}
    name=${p%%.*}; s=$(playerctl -p "$p" status 2>/dev/null)
    echo "<span foreground='$c'>${name^^}  ·  ${s^^}</span>" ;;
  *) echo "usage: $0 art|card|title|artist|source" >&2; exit 2 ;;
esac
