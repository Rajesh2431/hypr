#!/usr/bin/env bash
# ==================================================
#  Lossless Screenshot for Hyprland
#  grim + slurp, uncompressed PNG (-l 0)
# ==================================================
# Modes:
#   --region, -r        select an area
#   --full,   -f        all monitors
#   --output, -o        focused monitor
#   --window, -w        pick a window
#   --active, -a        active window
#   --in5 / --in10      delayed full screen
#   --annotate, -e      region + satty annotation
#   --clipboard-only    do not write to disk
# Options:
#   --delay N           wait N seconds before capture
#   --cursor            include the cursor
#   --compress N        PNG compression 0-9 (0=uncompressed, both lossless)
#   --notify            show a notification (off by default)
#   --silent            force no notification
#   --dir PATH          output directory
#   --open              open the file after saving (off by default)
# ==================================================
set -uo pipefail

PICTURES_DIR="$(xdg-user-dir PICTURES 2>/dev/null || echo "$HOME/Pictures")"
DIR="${PICTURES_DIR}/Screenshots"
MODE=""
DELAY=0
CURSOR=0
# Silent by default: capture + clipboard copy, no popup and no auto-open.
SILENT=1
CLIPBOARD_ONLY=0
OPEN_AFTER=0
ANNOTATE=0
# PNG compression level: 0 = uncompressed, 9 = max (both are lossless)
PNG_LEVEL=0

CONFIG_HOME="${XDG_CONFIG_HOME:-$HOME/.config}"
SOUNDS="${CONFIG_HOME}/hypr/scripts/Sounds.sh"
ICON="${CONFIG_HOME}/swaync/icons/picture.png"

usage() {
  sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    -r|--region)   MODE="region" ;;
    -f|--full)     MODE="full" ;;
    -o|--output)   MODE="output" ;;
    -w|--window)   MODE="window" ;;
    -a|--active)   MODE="active" ;;
    -e|--annotate) MODE="region"; ANNOTATE=1 ;;
    --in5)         MODE="full"; DELAY=5 ;;
    --in10)        MODE="full"; DELAY=10 ;;
    --clipboard-only) CLIPBOARD_ONLY=1 ;;
    --delay)       shift; DELAY="${1:-0}" ;;
    --compress)    shift; PNG_LEVEL="${1:-6}" ;;
    --cursor)      CURSOR=1 ;;
    --notify)      SILENT=0 ;;
    --silent)      SILENT=1 ;;
    --open)        OPEN_AFTER=1 ;;
    --dir)         shift; DIR="${1:-$DIR}" ;;
    -h|--help)     usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

[[ -n "$MODE" ]] || { usage; exit 2; }

mkdir -p "$DIR" || exit 1
STAMP="$(date +%Y-%m-%d_%H-%M-%S)"
FILE="${DIR}/Screenshot_${STAMP}_${RANDOM}.png"
TMP="$(mktemp --suffix=.png)"
trap 'rm -f "$TMP"' EXIT

geometry=""

case "$MODE" in
  region)
    geometry="$(slurp -d 2>/dev/null)" || exit 0
    [[ -n "$geometry" ]] || exit 0
    ;;
  output)
    focused="$(hyprctl monitors -j | jq -r '.[] | select(.focused) | .name' | head -n1)"
    [[ -n "$focused" && "$focused" != "null" ]] || exit 0
    geometry="$focused"
    ;;
  active)
    geometry="$(hyprctl activewindow -j 2>/dev/null \
      | jq -r 'if (.at and .size) then "\(.at[0]),\(.at[1]) \(.size[0])x\(.size[1])" else empty end')"
    [[ -n "$geometry" ]] || exit 0
    ;;
  window)
    geometry="$(hyprctl clients -j \
      | jq -r '.[] | select(.mapped and (.hidden | not)) | "\(.at[0]),\(.at[1]) \(.size[0])x\(.size[1])"' \
      | slurp -r 2>/dev/null)" || exit 0
    [[ -n "$geometry" ]] || exit 0
    ;;
  full)
    geometry=""
    ;;
esac

if (( DELAY > 0 )); then
  for (( i = DELAY; i > 0; i-- )); do
    (( SILENT == 0 )) && notify-send -h string:x-canonical-private-synchronous:shot -t 900 \
      -i "$ICON" "Taking shot" "in: ${i}s"
    sleep 1
  done
fi

grim_args=(-t png -l "$PNG_LEVEL")
(( CURSOR == 1 )) && grim_args+=(-c)

if [[ "$MODE" == "output" ]]; then
  grim "${grim_args[@]}" -o "$geometry" "$TMP" || exit 1
elif [[ -n "$geometry" ]]; then
  grim "${grim_args[@]}" -g "$geometry" "$TMP" || exit 1
else
  grim "${grim_args[@]}" "$TMP" || exit 1
fi

[[ -s "$TMP" ]] || { (( SILENT == 0 )) && notify-send -u low -i "$ICON" "Screenshot" "Nothing captured"; exit 1; }

wl-copy --type image/png < "$TMP" || true

if (( ANNOTATE == 1 )); then
  if command -v satty >/dev/null 2>&1; then
    satty -f "$TMP" -o "$FILE" --copy-command wl-copy >/dev/null 2>&1
  elif command -v swappy >/dev/null 2>&1; then
    swappy -f "$TMP" -o "$FILE" >/dev/null 2>&1
  else
    cp "$TMP" "$FILE"
  fi
else
  if (( CLIPBOARD_ONLY == 0 )); then
    cp "$TMP" "$FILE"
  fi
fi

[[ -x "$SOUNDS" ]] && "$SOUNDS" --screenshot >/dev/null 2>&1 &

(( OPEN_AFTER == 1 )) && [[ -e "$FILE" ]] && xdg-open "$FILE" >/dev/null 2>&1 &

if (( SILENT == 0 )); then
  if (( CLIPBOARD_ONLY == 1 )); then
    notify-send -t 4000 -i "$ICON" -a Screenshot "Screenshot" "Copied to clipboard"
  elif [[ -e "$FILE" ]]; then
    resp="$(notify-send -t 8000 -i "$ICON" -a Screenshot \
      -A action1=Open -A action2=Delete \
      -h string:x-canonical-private-synchronous:shot-notify \
      "Screenshot saved" "$(basename "$FILE")")"
    case "$resp" in
      action1) xdg-open "$FILE" >/dev/null 2>&1 & ;;
      action2) rm -f "$FILE" ;;
    esac
  fi
fi

exit 0
