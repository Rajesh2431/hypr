#!/usr/bin/env bash
# SPIDER-PUNK theme utilities.   usage: theme-utils.sh {palette|doctor|logo <ascii|image|none>} [--wait]
#   palette  – swatches of the 16 ANSI slots + role colours, read live from the theme file
#   doctor   – validates every file the setup references + kitty/starship/zsh syntax
#   logo     – persist the startup banner mode (state in ~/.local/state/spiderpunk/logo)
# Also reachable as the `spiderpunk` shell function and ctrl+alt+p in kitty.
set -u
KDIR="$HOME/.config/kitty"
THEME="$KDIR/themes/spiderpunk.conf"
STATE="${XDG_STATE_HOME:-$HOME/.local/state}/spiderpunk"

hex2sgr() { local h=${1#\#}; printf '%d;%d;%d' 0x${h:0:2} 0x${h:2:2} 0x${h:4:2}; }
val() { awk -v k="$1" '$1==k{print $2; exit}' "$THEME"; }

palette() {
  local bg; bg=$(val background)
  printf '\n  \e[1;38;2;%sm▚ SPIDER-PUNK PALETTE\e[0m  \e[38;2;%sm(%s)\e[0m\n\n' "$(hex2sgr "$(val color3)")" "$(hex2sgr "$(val color8)")" "$THEME"
  local names=(black red green yellow blue magenta cyan white) i n h hb
  for i in 0 1 2 3 4 5 6 7; do
    h=$(val color$i); hb=$(val color$((i+8)))
    printf '  \e[48;2;%sm      \e[0m \e[48;2;%sm      \e[0m  \e[38;2;%sm%-8s\e[0m %s  %s   \e[38;2;%smSample text\e[0m \e[1;38;2;%smBold\e[0m\n' \
      "$(hex2sgr "$h")" "$(hex2sgr "$hb")" "$(hex2sgr "$h")" "${names[$i]}" "$h" "$hb" "$(hex2sgr "$h")" "$(hex2sgr "$hb")"
  done
  printf '\n'
  for n in background foreground cursor selection_background active_border_color inactive_border_color active_tab_background url_color; do
    h=$(val $n)
    printf '  \e[48;2;%sm    \e[0m  %-24s %s\n' "$(hex2sgr "$h")" "$n" "$h"
  done
  printf '\n'
}

doctor() {
  local ok=0 bad=0 f
  pass() { printf '  \e[32m✔\e[0m %s\n' "$1"; ok=$((ok+1)); }
  fail() { printf '  \e[31m✘\e[0m %s\n' "$1"; bad=$((bad+1)); }
  echo "▚ files"
  for f in "$KDIR/kitty.conf" "$THEME" "$KDIR/tab_bar.py" "$KDIR/ssh.conf" \
           "$KDIR/assets/spiderpunk-ascii.txt" "$HOME/.config/zsh/spiderpunk.zsh" \
           "$HOME/.config/starship.toml" "$HOME/.config/fastfetch/spiderpunk.jsonc" \
           "$HOME/.config/btop/themes/spiderpunk.theme" "$HOME/.config/lsd/colors.yaml"; do
    [[ -r $f ]] && pass "$f" || fail "missing: $f"
  done
  # Hyprland points KITTY_CONFIG_DIRECTORY at hypr/UserConfigs — make sure the shim is intact
  local U="${KITTY_CONFIG_DIRECTORY:-$KDIR}"
  if [[ $U != "$KDIR" ]]; then
    grep -q "include $KDIR/kitty.conf" "$U/kitty.conf" 2>/dev/null && pass "$U/kitty.conf includes $KDIR/kitty.conf" || fail "$U/kitty.conf does not include $KDIR/kitty.conf"
    [[ -e $U/tab_bar.py ]] && pass "$U/tab_bar.py present" || fail "$U/tab_bar.py missing (tab bar falls back to default)"
  fi
  echo "▚ syntax"
  local out
  out=$(kitty +runpy 'from kitty.config import load_config; load_config("'"$U"'/kitty.conf")' 2>&1)
  [[ -z $out ]] && pass "kitty config parses cleanly" || fail "kitty: $out"
  out=$(kitty +runpy 'import runpy; m=runpy.run_path("'"$KDIR"'/tab_bar.py"); assert "draw_tab" in m' 2>&1)
  [[ -z $out ]] && pass "tab_bar.py imports, defines draw_tab" || fail "tab_bar.py: $out"
  zsh -n "$HOME/.zshrc" && zsh -n "$HOME/.config/zsh/spiderpunk.zsh" && pass "zsh syntax" || fail "zsh syntax"
  out=$(STARSHIP_LOG=warn starship prompt 2>&1 >/dev/null)
  [[ -z $out ]] && pass "starship config renders without warnings" || fail "starship: $out"
  printf '\n  %d ok, %d problems\n' "$ok" "$bad"
  [[ $bad -eq 0 ]]
}

logo() {
  case ${1:-} in
    ascii|image|none) mkdir -p "$STATE"; echo "$1" > "$STATE/logo"; echo "startup banner → $1 (new shells)";;
    *) echo "usage: spiderpunk logo {ascii|image|none}   (current: $(cat "$STATE/logo" 2>/dev/null || echo image))"; return 2;;
  esac
}

cmd=${1:-palette}; shift || true
wait_after=0; [[ " $* " == *" --wait "* ]] && wait_after=1
case $cmd in
  palette) palette ;;
  doctor)  doctor ;;
  logo)    logo "${1:-}" ;;
  *) echo "usage: $(basename "$0") {palette|doctor|logo <ascii|image|none>}"; exit 2 ;;
esac
rc=$?
if (( wait_after )); then read -rsn1 -p $'  \e[2m(any key to close)\e[0m'; fi
exit $rc
