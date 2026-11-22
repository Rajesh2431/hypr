#!/usr/bin/env bash
# Desktop styles: save the whole look (waybar layout + CSS, lock screen, rofi, island/Control Center/
# power menu look, overview, window borders/blur/animations, GTK, Qt, cursor, kitty, Neovim colours,
# wallpaper) as one folder, and switch between saved styles.
#
#   Styles.sh list                 saved styles (* = active)
#   Styles.sh current              name of the active style
#   Styles.sh apply NAME           switch to NAME (the live desktop is kept as "_previous" first)
#   Styles.sh restore              go back to "_previous" (run again to swap back)
#   Styles.sh save NAME            snapshot the live desktop as NAME (overwrites NAME)
#   Styles.sh rename OLD NEW
#   Styles.sh delete NAME
#   Styles.sh check NAME           validate a style without applying it
#   Styles.sh menu                 rofi picker (Super+Alt+T)
#
# Styles live in ~/.config/hypr/themes/NAME/:
#   files/          copies of the paths in themes/manifest.txt (only the per-style files; the widget
#                   code, scripts and assets are shared by every style)
#   absent.txt      manifest paths that did not exist when saved (removed when the style is applied)
#   style.env       GTK / icon / cursor / sound theme names, colour scheme
#   wallpaper       the wallpaper image (preview.png = its thumbnail)
#   hooks/apply.sh  optional, run after the files are in place (for settings inside shared files)
# Applying is checked: if Hyprland reports config errors or waybar / the island don't come back,
# the previous desktop is restored automatically and the style is not marked active.
set -uo pipefail

ROOT="$HOME/.config/hypr/themes"
MANIFEST="$ROOT/manifest.txt"
WALL="$HOME/.config/hypr/wallpaper_effects/.wallpaper_current"
SCRIPTS="$HOME/.config/hypr/scripts"
EXCLUDES=(--exclude '*.bak' --exclude '*.bak-*' --exclude '*.bak.*' --exclude '__pycache__')
ISLAND_RE='(^|/)qs -c island$'

note() { notify-send -a Styles -i preferences-desktop-theme "Styles" "$1" 2>/dev/null; echo "$1"; }
die() { note "$1"; exit 1; }
paths() { grep -v -e '^[[:space:]]*#' -e '^[[:space:]]*$' "$MANIFEST" | grep -v -e '\.\.' -e '^/'; }
valid() { [[ "$1" =~ ^[A-Za-z0-9_.+-]+$ && "$1" != . && "$1" != .. && "$1" != _backups ]] || die "Bad style name: '$1' (letters, digits, - _ . + only)"; }
gs() { gsettings get "$1" "$2" 2>/dev/null | tr -d "'"; }
current() { cat "$ROOT/.current" 2>/dev/null; }
is_style() { [ -d "$ROOT/$1/files" ]; }
theme_dir() {   # theme_dir KIND NAME -> 0 if an installed theme of that name exists
  local d
  case "$1" in
    gtk)  for d in "$HOME/.themes" "$HOME/.local/share/themes" /usr/share/themes; do [ -d "$d/$2" ] && return 0; done ;;
    icon) for d in "$HOME/.icons" "$HOME/.local/share/icons" /usr/share/icons; do [ -d "$d/$2" ] && return 0; done ;;
    sound) for d in "$HOME/.local/share/sounds" /usr/share/sounds; do [ -d "$d/$2" ] && return 0; done ;;
  esac
  return 1
}

# ---------------------------------------------------------------- save
save() {
  local name="$1" dir new p origin
  valid "$name"
  dir="$ROOT/$name"; new="$ROOT/.$name.new"
  origin=$(current)
  rm -rf -- "$new"; mkdir -p "$new/files"
  : > "$new/absent.txt"
  while IFS= read -r p; do
    if [ -e "$HOME/$p" ] || [ -L "$HOME/$p" ]; then
      (cd "$HOME" && rsync -aR "${EXCLUDES[@]}" "./$p" "$new/files/") || { rm -rf -- "$new"; die "Copy failed: $p"; }
    else
      echo "$p" >> "$new/absent.txt"
    fi
  done < <(paths)
  cat > "$new/style.env" <<EOF
GTK_THEME='$(gs org.gnome.desktop.interface gtk-theme)'
ICON_THEME='$(gs org.gnome.desktop.interface icon-theme)'
CURSOR_THEME='$(gs org.gnome.desktop.interface cursor-theme)'
CURSOR_SIZE='$(gs org.gnome.desktop.interface cursor-size)'
COLOR_SCHEME='$(gs org.gnome.desktop.interface color-scheme)'
SOUND_THEME='$(gs org.gnome.desktop.sound theme-name)'
ORIGIN='${origin}'
SAVED='$(date '+%F %R')'
EOF
  if [ -s "$WALL" ]; then
    cp -f -- "$WALL" "$new/wallpaper"
    magick "$new/wallpaper" -resize '480x270^' -gravity center -extent 480x270 "$new/preview.png" 2>/dev/null
  fi
  [ -d "$dir/hooks" ] && cp -a -- "$dir/hooks" "$new/"          # keep a style's hooks when re-saving it
  rm -rf -- "$dir"; mv -- "$new" "$dir"
  if [ "$name" != _previous ]; then
    echo "$name" > "$ROOT/.current"
    note "Saved style \"$name\" ($(du -sh "$dir" | cut -f1))"
  fi
}

# ---------------------------------------------------------------- check
check() {   # check NAME -> prints problems, returns 1 if the style can't be applied
  local name="$1" dir bad=0 p t
  dir="$ROOT/$name"
  is_style "$name" || { echo "no style called \"$name\""; return 1; }
  [ -f "$dir/style.env" ] || { echo "$name: style.env missing"; bad=1; }
  # shellcheck source=/dev/null
  t=$( . "$dir/style.env" 2>/dev/null
    [ -z "${GTK_THEME:-}" ]    || theme_dir gtk "$GTK_THEME"     || echo "GTK theme not installed: $GTK_THEME"
    [ -z "${ICON_THEME:-}" ]   || theme_dir icon "$ICON_THEME"   || echo "icon theme not installed: $ICON_THEME"
    [ -z "${CURSOR_THEME:-}" ] || theme_dir icon "$CURSOR_THEME" || echo "cursor theme not installed: $CURSOR_THEME"
    [ -z "${SOUND_THEME:-}" ]  || theme_dir sound "$SOUND_THEME" || echo "sound theme not installed: $SOUND_THEME" )
  [ -n "$t" ] && { echo "$t"; bad=1; }
  while IFS= read -r p; do
    t="$dir/files/$p"
    if [ -L "$t" ] && [ ! -e "$t" ]; then echo "$name: link target missing for $p -> $(readlink "$t")"; bad=1; fi
  done < <(paths)
  [ "$(df -Pm "$HOME" | awk 'NR==2 {print $4}')" -gt 200 ] || { echo "less than 200 MB free in \$HOME"; bad=1; }
  return $bad
}

# ---------------------------------------------------------------- apply helpers
copy_files() {   # copy_files DIR : put the style's files in place (rsync writes a temp file, then renames)
  local dir="$1" p src dst
  while IFS= read -r p; do
    src="$dir/files/$p"; dst="$HOME/$p"
    if [ -d "$src" ] && [ ! -L "$src" ]; then
      { [ -L "$dst" ] || [ -f "$dst" ]; } && rm -f -- "$dst"
      mkdir -p -- "$dst"
      rsync -a --delete "${EXCLUDES[@]}" "$src/" "$dst/" || return 1
    elif [ -e "$src" ] || [ -L "$src" ]; then
      [ -d "$dst" ] && [ ! -L "$dst" ] && rm -rf -- "${HOME:?}/$p"
      mkdir -p -- "$(dirname -- "$dst")"
      rsync -a "$src" "$dst" || return 1
    elif grep -qxF -- "$p" "$dir/absent.txt" 2>/dev/null; then
      rm -rf -- "${HOME:?}/$p"
    fi   # path added to the manifest after this style was saved: leave the live file alone
  done < <(paths)
}

set_theme_names() {
  # shellcheck source=/dev/null
  . "$1/style.env"
  [ -n "${GTK_THEME:-}" ]    && gsettings set org.gnome.desktop.interface gtk-theme "$GTK_THEME"
  [ -n "${ICON_THEME:-}" ]   && gsettings set org.gnome.desktop.interface icon-theme "$ICON_THEME"
  [ -n "${CURSOR_THEME:-}" ] && gsettings set org.gnome.desktop.interface cursor-theme "$CURSOR_THEME"
  [ -n "${CURSOR_SIZE:-}" ]  && gsettings set org.gnome.desktop.interface cursor-size "$CURSOR_SIZE"
  [ -n "${COLOR_SCHEME:-}" ] && gsettings set org.gnome.desktop.interface color-scheme "$COLOR_SCHEME"
  [ -n "${SOUND_THEME:-}" ]  && gsettings set org.gnome.desktop.sound theme-name "$SOUND_THEME"
  [ -n "${CURSOR_THEME:-}" ] && hyprctl setcursor "$CURSOR_THEME" "${CURSOR_SIZE:-24}" >/dev/null
  return 0
}

set_wallpaper() {
  if [ -s "$1/wallpaper" ]; then
    # same steps as KoolDots' WallpaperSelect.sh: set it, record it, re-run wallust (+ borders, hyprctl reload)
    awww img "$1/wallpaper" --transition-type fade --transition-duration 1.2 --transition-fps 60 >/dev/null 2>&1
    cp -f -- "$1/wallpaper" "$WALL"
    cp -f -- "$1/wallpaper" "${WALL}_eDP-1"
    "$SCRIPTS/WallustSwww.sh" "$WALL" >/dev/null 2>&1
  fi
  hyprctl reload >/dev/null
  "$SCRIPTS/RainbowBordersStartup.sh" >/dev/null 2>&1 &
}

restart_ui() {
  # waybar: exactly one bar (a full restart also reloads rebuilt cffi widgets)
  pkill -x waybar
  for _ in 1 2 3 4 5 6 7 8 9 10; do pgrep -x waybar >/dev/null || break; sleep 0.2; done
  pkill -9 -x waybar 2>/dev/null
  setsid -f waybar -c "$HOME/.config/hypr/waybar/config" -s "$HOME/.config/hypr/waybar/style.css" >/dev/null 2>&1
  # island = notifications + Control Center (same command as UserConfigs/user_startup.lua)
  pkill -f "$ISLAND_RE"
  for _ in 1 2 3 4 5 6 7 8 9 10; do pgrep -f "$ISLAND_RE" >/dev/null || break; sleep 0.2; done
  setsid -f env __EGL_VENDOR_LIBRARY_FILENAMES=/usr/share/glvnd/egl_vendor.d/50_mesa.json qs -c island >/dev/null 2>&1
  # KoolDots overview, only if it was running
  if pkill -f '^qs .*-c overview$'; then
    sleep 0.4; setsid -f qs --log-rules qt.qpa.wayland.textinput.warning=false -c overview >/dev/null 2>&1
  fi
  pkill -USR1 -x kitty    # kitty re-reads kitty.conf
  return 0
}

live_count() { pgrep "$@" | while read -r pid; do [ "$(ps -o stat= -p "$pid" | cut -c1)" = Z ] || echo "$pid"; done | wc -l; }

verify() {   # verify -> prints what's wrong, returns 1 on failure
  local bad=0 w i e
  sleep 3
  e=$(hyprctl configerrors 2>/dev/null | grep -v -e '^$' -e '^no errors' -e '^No errors')
  [ -n "$e" ] && { echo "Hyprland config errors: $e"; bad=1; }
  w=$(live_count -x waybar); i=$(live_count -f "$ISLAND_RE")
  [ "$w" = 1 ] || { echo "waybar processes: $w (expected 1)"; bad=1; }
  [ "$i" = 1 ] || { echo "island processes: $i (expected 1)"; bad=1; }
  return $bad
}

do_apply() {   # do_apply DIR : files + settings + restart (no snapshot, no checks)
  copy_files "$1" || return 1
  [ -x "$1/hooks/apply.sh" ] && "$1/hooks/apply.sh"
  set_theme_names "$1"
  set_wallpaper "$1"
  restart_ui
}

# Lock = a directory holding the switcher's PID. (Not flock: the fd would be inherited by the
# waybar / island processes this script restarts, and they'd hold the lock forever.)
LOCK="$ROOT/.switching"
take_lock() {
  local pid
  if ! mkdir -- "$LOCK" 2>/dev/null; then
    pid=$(cat "$LOCK/pid" 2>/dev/null)
    if [ -n "$pid" ] && [ "$pid" != "$$" ] && kill -0 "$pid" 2>/dev/null && tr '\0' ' ' < "/proc/$pid/cmdline" | grep -q 'Styles.sh'; then
      die "Another style switch is running"
    fi
    rm -rf -- "$LOCK"; mkdir -- "$LOCK" || die "Could not take the style lock"   # stale lock from a crashed run
  fi
  echo $$ > "$LOCK/pid"
  trap 'rm -rf -- "$LOCK"' EXIT
}

# ---------------------------------------------------------------- apply / restore
apply() {
  local name="$1" dir label origin problems tmp=""
  valid "$name"
  is_style "$name" || die "No style called \"$name\""
  problems=$(check "$name" 2>/dev/null) || die "Not applying \"$name\": ${problems//$'\n'/; }"
  take_lock

  if [ "$name" = _previous ]; then
    # restore: swap, so running restore again goes back
    tmp="$ROOT/.restore.$$"
    mv -- "$ROOT/_previous" "$tmp"
    dir="$tmp"
    origin=$(. "$tmp/style.env"; echo "${ORIGIN:-}")
  else
    dir="$ROOT/$name"; origin="$name"
  fi
  save _previous >/dev/null || { [ -n "$tmp" ] && mv -- "$tmp" "$ROOT/_previous"; die "Could not snapshot the live desktop"; }
  label="${origin:-previous}"

  if do_apply "$dir" && problems=$(verify); then
    [ -n "$origin" ] && echo "$origin" > "$ROOT/.current"
    [ -n "$tmp" ] && rm -rf -- "$tmp"
    note "Style \"$label\" applied. Undo: Super+Alt+T → Restore previous"
    return 0
  fi
  # ---- rollback: put the snapshot taken a moment ago back
  note "Switching to \"$label\" failed (${problems//$'\n'/; }). Restoring the previous desktop…"
  do_apply "$ROOT/_previous"
  if [ -n "$tmp" ]; then rm -rf -- "$ROOT/_previous"; mv -- "$tmp" "$ROOT/_previous"; fi
  if problems=$(verify); then note "Previous desktop restored."; else note "Rollback finished with problems: ${problems//$'\n'/; }"; fi
  return 1
}

# ---------------------------------------------------------------- list / menu
list() {
  local cur d n
  cur=$(current)
  for d in "$ROOT"/*/; do
    n=$(basename "$d"); is_style "$n" || continue
    printf '%s %-20s saved %s\n' "$([ "$n" = "$cur" ] && echo '*' || echo ' ')" "$n" "$(. "$d/style.env"; echo "$SAVED")"
  done
}

# rofi with the active style's own theme (~/.config/hypr/rofi/config.rasi selects it per style)
ROFI=(rofi -config "$HOME/.config/hypr/rofi/config.rasi")
ask() { "${ROFI[@]}" -dmenu -i -p "$1" -l "${2:-0}" -theme-str 'window { width: 440px; } listview { lines: '"${2:-0}"'; }'; }
pick_style() {   # pick_style PROMPT -> a saved style name (not _previous)
  list | awk '{ n = ($1 == "*") ? $2 : $1; if (n != "_previous") print n }' | ask "$1" 8
}

menu() {
  local cur d n pick label
  cur=$(current)
  pick=$({
    for d in "$ROOT"/*/; do
      n=$(basename "$d"); is_style "$n" || continue; [ "$n" = _previous ] && continue
      label="$n"; [ "$n" = "$cur" ] && label="$n   ✓ active"
      printf '%s\0icon\x1f%s\n' "$label" "$d/preview.png"
    done
    is_style _previous && printf 'Restore previous\0icon\x1f%s\n' "$ROOT/_previous/preview.png"
    printf 'Save current desktop as new style…\0icon\x1fdocument-save\n'
    printf 'Rename a style…\0icon\x1fedit-rename\n'
    printf 'Delete a style…\0icon\x1fedit-delete\n'
  } | "${ROFI[@]}" -dmenu -i -p "Style" -show-icons \
      -theme-str 'window { width: 640px; } listview { lines: 7; columns: 1; } element { orientation: horizontal; children: [ element-icon, element-text ]; } element-icon { size: 54px; } element-text { vertical-align: 0.5; }')
  [ -n "$pick" ] || exit 0
  case "$pick" in
    "Restore previous") apply _previous ;;
    "Save current"*)  n=$(ask "New style name" </dev/null); [ -n "$n" ] && save "$n" ;;
    "Rename a"*) d=$(pick_style "Rename which style"); [ -n "$d" ] || exit 0
                  n=$(ask "New name for $d" </dev/null); [ -n "$n" ] && rename "$d" "$n" ;;
    "Delete a"*) d=$(pick_style "Delete which style"); [ -n "$d" ] || exit 0
                  [ "$(printf 'No, keep it\nYes, delete %s\n' "$d" | ask "Delete $d?" 2)" = "Yes, delete $d" ] && delete "$d" ;;
    *) apply "${pick%%   ✓ active}" ;;
  esac
}

rename() {
  valid "$1"; valid "$2"
  [ "$1" != _previous ] || die "\"_previous\" can't be renamed"
  is_style "$1" || die "No style \"$1\""
  [ -e "$ROOT/$2" ] && die "\"$2\" already exists"
  mv -- "$ROOT/$1" "$ROOT/$2"
  [ "$(current)" = "$1" ] && echo "$2" > "$ROOT/.current"
  note "Renamed \"$1\" to \"$2\""
}

delete() {
  valid "$1"; is_style "$1" || die "No style \"$1\""
  [ "$(current)" = "$1" ] && die "\"$1\" is active; switch to another style first"
  rm -rf -- "${ROOT:?}/$1"; note "Deleted style \"$1\""
}

mkdir -p "$ROOT"
case "${1:-}" in
  save)    [ -n "${2:-}" ] || die "usage: $0 save NAME"; save "$2" ;;
  apply)   [ -n "${2:-}" ] || die "usage: $0 apply NAME"; apply "$2" ;;
  restore) is_style _previous || die "Nothing to restore"; apply _previous ;;
  current) current ;;
  list)    list ;;
  check)   [ -n "${2:-}" ] || die "usage: $0 check NAME"; valid "$2"; check "$2" && echo "\"$2\" OK" ;;
  rename)  [ -n "${3:-}" ] || die "usage: $0 rename OLD NEW"; rename "$2" "$3" ;;
  delete)  [ -n "${2:-}" ] || die "usage: $0 delete NAME"; delete "$2" ;;
  menu)    menu ;;
  *) sed -n '2,27p' "$0" | sed 's/^# \{0,1\}//'; exit 2 ;;
esac
