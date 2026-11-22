#!/usr/bin/env python3
"""AI usage for Waybar (cffi/menu-widget.so): Claude, Codex, OpenCode, Antigravity.

Bar: AI icon + the highest plan-limit % in use (green / yellow / red).
Menu: one section per tool.
  Claude      5-hour + weekly limits (Claude Code's own login, api.anthropic.com
              /api/oauth/usage — the numbers /usage shows), today's Claude Code tokens
  Codex       5-hour + weekly limits from the latest ~/.codex/sessions rollout log
  OpenCode    tokens / cost today and last 7 days (~/.local/share/opencode/opencode.db)
  Antigravity activity (last used, conversations today) — it stores no quota on disk

Claude is checked every 5 min, local files every 60 s (every 10 s while the menu is open).
Never refreshes or rewrites any login token.

  ai.py status
"""
import ctypes as _ctypes, signal as _signal
import sys as _sys
if len(_sys.argv) > 1 and _sys.argv[1] == "status":
    try:
        _ctypes.CDLL("libc.so.6").prctl(1, _signal.SIGTERM)
    except Exception:
        pass

import datetime as dt
import glob
import html
import json
import os
import select
import shutil
import sqlite3
import sys
import time
import urllib.error
import urllib.request

HOME = os.path.expanduser("~")
PUNK = os.environ.get("PUNK_ICONS") == "1"   # Spider-Punk style: icon comes from CSS (state class), no glyph
I_AI, I_CLAUDE, I_CODEX, I_OC, I_AG = "\U000f06a9", "\U000f0b79", "\U000f0174", "\U000f018d", "\U000f0eb5"
I_WEB, I_REFRESH, I_CLOCK = "\U000f059f", "\U000f0450", "\U000f0954"
GREEN, YELLOW, RED, DIM = "#30d158", "#ffd60a", "#ff453a", "#8a8a8e"


# ------------------------------------------------------------ helpers
def tint(pct):
    return RED if pct >= 90 else YELLOW if pct >= 70 else GREEN


def meter(pct, n=10):
    k = max(0, min(n, round(pct / 100 * n)))
    return f"<span color='{tint(pct)}'>{'▰' * k}</span><span alpha='30%'>{'▱' * (n - k)}</span>"


def until(ts):
    s = int(ts - time.time())
    if s <= 0:
        return "now"
    d, r = divmod(s, 86400)
    h, r = divmod(r, 3600)
    m = r // 60
    return f"{d}d {h}h" if d else f"{h}h {m:02d}m" if h else f"{m}m"


def ago(ts):
    if not ts:
        return "never"
    s = int(time.time() - ts)
    if s < 3600:
        return f"{max(1, s // 60)} min ago"
    if s < 86400:
        return f"{s // 3600} h ago"
    return dt.datetime.fromtimestamp(ts).strftime("%d %b")


def kfmt(n):
    return f"{n / 1e6:.1f}M" if n >= 1e6 else f"{n / 1e3:.1f}k" if n >= 1e3 else str(int(n))


def iso(s):
    try:
        return dt.datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp()
    except Exception:
        return 0


# ------------------------------------------------------------ Claude
_claude = {"at": 0, "data": None, "err": "", "cred_mtime": None}
CRED = f"{HOME}/.claude/.credentials.json"


def claude_limits():
    # a new login (account switch, /login, token refresh) rewrites the credentials file:
    # re-check right away instead of waiting for the 5-minute cache
    try:
        mt = os.path.getmtime(CRED)
    except OSError:
        mt = None
    if mt != _claude["cred_mtime"]:
        _claude["cred_mtime"], _claude["at"] = mt, 0
    if time.time() - _claude["at"] < 300 and (_claude["data"] or _claude["err"]):
        return _claude
    _claude["at"] = time.time()
    try:
        cred = json.load(open(CRED))["claudeAiOauth"]
    except Exception:
        _claude.update(data=None, err="not logged in"); return _claude
    if cred.get("expiresAt", 0) / 1000 < time.time():
        _claude.update(err="login expired · open Claude Code to refresh"); return _claude
    req = urllib.request.Request("https://api.anthropic.com/api/oauth/usage", headers={
        "Authorization": "Bearer " + cred["accessToken"], "anthropic-beta": "oauth-2025-04-20",
        "User-Agent": "waybar-ai-usage/1.0"})
    try:
        d = json.loads(urllib.request.urlopen(req, timeout=8).read())
        limits = []
        for key, label in (("five_hour", "5-hour"), ("seven_day", "Week"), ("seven_day_opus", "Week · Opus"),
                           ("seven_day_sonnet", "Week · Sonnet")):
            v = d.get(key)
            if isinstance(v, dict) and v.get("utilization") is not None:
                limits.append({"label": label, "pct": float(v["utilization"]), "reset": iso(v.get("resets_at") or "")})
        _claude.update(data={"plan": cred.get("subscriptionType", "").title(), "limits": limits}, err="")
    except urllib.error.HTTPError as e:
        _claude.update(err=f"HTTP {e.code}" + (" · open Claude Code to refresh login" if e.code == 401 else ""))
    except Exception:
        _claude.update(err="offline")
    return _claude


def claude_tokens_today():
    start = dt.datetime.combine(dt.date.today(), dt.time()).timestamp()
    tot, seen = 0, set()
    for f in glob.glob(f"{HOME}/.claude/projects/*/*.jsonl"):
        try:
            if os.path.getmtime(f) < start:
                continue
            for line in open(f, errors="replace"):
                if '"usage"' not in line:
                    continue
                try:
                    o = json.loads(line)
                except ValueError:
                    continue
                if iso(o.get("timestamp", "")) < start:
                    continue
                m = o.get("message") or {}
                mid = m.get("id") or o.get("uuid")
                if mid in seen:
                    continue
                seen.add(mid)
                u = m.get("usage") or {}
                tot += sum(int(u.get(k) or 0) for k in ("input_tokens", "output_tokens",
                                                       "cache_creation_input_tokens", "cache_read_input_tokens"))
        except OSError:
            continue
    return tot


# ------------------------------------------------------------ Codex
def codex_limits():
    files = []
    for d in sorted(glob.glob(f"{HOME}/.codex/sessions/*/*/*"), reverse=True)[:6]:
        files += glob.glob(d + "/rollout-*.jsonl")
    files.sort(key=os.path.getmtime, reverse=True)
    for f in files[:4]:
        rl = None
        try:
            for line in open(f, errors="replace"):
                if '"rate_limits"' in line:
                    try:
                        o = json.loads(line)
                    except ValueError:
                        continue
                    p = o.get("payload") or {}
                    rl = p.get("rate_limits") or (p.get("info") or {}).get("rate_limits") or rl
        except OSError:
            continue
        if rl:
            out = []
            for key, label in (("primary", "5-hour"), ("secondary", "Week")):
                v = rl.get(key) or {}
                if v.get("used_percent") is not None:
                    reset = float(v.get("resets_at") or 0)
                    pct = float(v["used_percent"]) if reset > time.time() else 0.0   # window already reset
                    w = int(v.get("window_minutes") or 0)
                    lab = "5-hour" if w == 300 else "Week" if w == 10080 else (f"{w // 60}-hour" if w else label)
                    out.append({"label": lab, "pct": pct, "reset": reset})
            return {"limits": out, "last": os.path.getmtime(f)}
    return None


# ------------------------------------------------------------ OpenCode
def opencode_usage():
    """OpenCode 1 rows live in `message`, OpenCode 2 rows in `session_message` (same db)."""
    db = f"{HOME}/.local/share/opencode/opencode.db"
    if not os.path.exists(db):
        return None
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True, timeout=2)
        day0 = dt.datetime.combine(dt.date.today(), dt.time()).timestamp() * 1000
        week0 = day0 - 6 * 86400000
        tok2 = ("(coalesce(json_extract(data,'$.tokens.input'),0) + coalesce(json_extract(data,'$.tokens.output'),0) + "
                "coalesce(json_extract(data,'$.tokens.reasoning'),0) + coalesce(json_extract(data,'$.tokens.cache.read'),0) + "
                "coalesce(json_extract(data,'$.tokens.cache.write'),0))")
        rows = f"""select time_created t, coalesce(json_extract(data,'$.tokens.total'),0) tok, coalesce(json_extract(data,'$.cost'),0) cost,
                          json_extract(data,'$.modelID') model from message where json_extract(data,'$.role')='assistant'
                   union all
                   select time_created, {tok2}, coalesce(json_extract(data,'$.cost'),0), json_extract(data,'$.model.id')
                          from session_message where type='assistant' and json_extract(data,'$.tokens') is not null"""
        agg = lambda since: con.execute(f"select coalesce(sum(tok),0), coalesce(sum(cost),0), count(*) from ({rows}) where t >= ?", (since,)).fetchone()
        t, w = agg(day0), agg(week0)
        top = con.execute(f"select model, count(*) from ({rows}) where t >= ? group by 1 order by 2 desc limit 1", (week0,)).fetchone()
        last = con.execute("select max(m) from (select max(time_created) m from message union all select max(time_created) from session_message)").fetchone()[0]
        # free models: "Free usage limit reached" (HTTP 429) recorded as a failed idle event
        lim = con.execute("""select time_created, json_extract(data,'$.error.message') from session_message
                             where type='idle' and json_extract(data,'$.error.type')='provider.free-limit'
                             order by time_created desc limit 1""").fetchone()
        ok_after = con.execute("""select count(*) from session_message where type='assistant' and time_created > ?
                                  and json_extract(data,'$.tokens') is not null""", (lim[0] if lim else 0,)).fetchone()[0] if lim else 0
        con.close()
        free_limit = bool(lim and ok_after == 0 and (time.time() * 1000 - lim[0]) < 24 * 3600 * 1000)
        return {"today": t, "week": w, "model": top[0] if top else "", "last": (last or 0) / 1000,
                "free_limit": free_limit, "free_limit_at": (lim[0] / 1000) if lim else 0}
    except Exception:
        return None


# ------------------------------------------------------------ Antigravity
def antigravity_activity():
    base = f"{HOME}/.gemini/antigravity"
    if not os.path.isdir(base):
        return None
    day0 = dt.datetime.combine(dt.date.today(), dt.time()).timestamp()
    convs = glob.glob(base + "/conversations/*") + glob.glob(base + "/brain/*")
    mt = [os.path.getmtime(c) for c in convs if os.path.exists(c)]
    # app activity: its state / summaries / logs are touched whenever Antigravity runs
    seen = [os.path.getmtime(f) for f in (base + "/conversation_summaries.db", base + "/antigravity_state.pbtxt",
                                          f"{HOME}/.config/Antigravity/logs") if os.path.exists(f)]
    return {"today": sum(1 for m in mt if m >= day0), "last": max(mt + seen) if (mt or seen) else 0}


# ------------------------------------------------------------ record
def record(is_open):
    E = lambda *f: "\x1c".join(f)
    cl = claude_limits()
    cx, oc, ag = codex_limits(), opencode_usage(), antigravity_activity()
    worst, worst_name = -1, ""

    def limit_rows(limits):
        rows = []
        for l in limits:
            r = f"until reset {until(l['reset'])}" if l["reset"] > time.time() else "reset"
            rows.append(E("note", f"<tt>{l['label']:<7}</tt> {meter(l['pct'])} <b>{l['pct']:.0f}%</b>  <span alpha='55%'>{r}</span>"))
        return rows

    m, tip = [E("header", "<b>AI usage</b>")], ["<b>AI usage</b>", ""]
    # Claude
    m += ["sep", E("header", f"{I_CLAUDE}  Claude" + (f"  <span alpha='55%'>{cl['data']['plan']}</span>" if cl["data"] and cl["data"]["plan"] else ""))]
    if cl["data"]:
        m += limit_rows(cl["data"]["limits"])
        for l in cl["data"]["limits"]:
            if l["pct"] > worst:
                worst, worst_name = l["pct"], "Claude " + l["label"]
        tip.append(f"{I_CLAUDE}  Claude  " + "  ·  ".join(f"{l['label']} {l['pct']:.0f}%" for l in cl["data"]["limits"]))
    if cl["err"]:
        m.append(E("note", f"<span alpha='60%'>{html.escape(cl['err'])}</span>"))
    if is_open:
        m.append(E("note", f"<span alpha='60%'>Claude Code today: {kfmt(claude_tokens_today())} tokens</span>"))
    # Codex
    if cx is not None or shutil.which("codex"):
        m += ["sep", E("header", f"{I_CODEX}  Codex")]
        if cx and cx["limits"]:
            m += limit_rows(cx["limits"])
            m.append(E("note", f"<span alpha='60%'>last session {ago(cx['last'])}</span>"))
            for l in cx["limits"]:
                if l["pct"] > worst:
                    worst, worst_name = l["pct"], "Codex " + l["label"]
            tip.append(f"{I_CODEX}  Codex  " + "  ·  ".join(f"{l['label']} {l['pct']:.0f}%" for l in cx["limits"]))
        else:
            m.append(E("note", "<span alpha='60%'>no limit data yet (use Codex once)</span>"))
    # OpenCode
    if oc:
        (tt, tc, tn), (wt, wc, wn) = oc["today"], oc["week"]
        m += ["sep", E("header", f"{I_OC}  OpenCode"),
              E("note", f"<tt>Today  </tt> {kfmt(tt)} tokens  ·  ${tc:.2f}  ·  {tn} replies"),
              E("note", f"<tt>7 days </tt> {kfmt(wt)} tokens  ·  ${wc:.2f}  ·  {wn} replies"),
              E("note", f"<span alpha='60%'>{html.escape(oc['model'] or '—')}  ·  last used {ago(oc['last'])}</span>")]
        if oc.get("free_limit"):
            m.append(E("note", f"<span color='{RED}'>Free usage limit reached</span>  <span alpha='55%'>{ago(oc['free_limit_at'])}</span>"))
        tip.append(f"{I_OC}  OpenCode  today {kfmt(tt)} tok · ${tc:.2f}")
    # Antigravity
    if ag or shutil.which("antigravity"):
        m += ["sep", E("header", f"{I_AG}  Antigravity")]
        if ag:
            m += [E("note", f"<tt>Today  </tt> {ag['today']} conversation{'s' if ag['today'] != 1 else ''}"),
                  E("note", f"<span alpha='60%'>last used {ago(ag['last'])}  ·  quota is only shown inside Antigravity</span>")]
            tip.append(f"{I_AG}  Antigravity  last used {ago(ag['last'])}")
    m += ["sep",
          E("item", f"{I_WEB}   Claude usage page", "xdg-open https://claude.ai/settings/usage"),
          E("item", f"{I_WEB}   Codex usage page", "xdg-open https://chatgpt.com/codex/settings/usage"),
          E("item", f"{I_WEB}   OpenCode usage page", "xdg-open https://opencode.ai/auth")]

    hover = ""
    if worst >= 0:
        # bar: icon only (coloured by the highest limit); the % slides out on hover
        bar = f"<span color='{tint(worst)}'>{I_AI}</span>"
        hover = f"<span color='{tint(worst)}'>{worst:.0f}%</span>"
        cls = "crit" if worst >= 90 else "warn" if worst >= 70 else "ok"
        tip.insert(1, f"Highest: {worst_name} {worst:.0f}%")
    else:
        bar, cls = I_AI, "idle"
    tip += ["", "<span alpha='55%' size='small'>Click for details</span>"]
    if PUNK:   # robot head from CSS (ai-ok / warn / crit / idle by class)
        bar = ""
    return "\x1f".join([cls, bar, "\n".join(tip), "\x1d".join(m), hover]).replace("\n", "\x1e")


def main():
    force = [False]
    _signal.signal(_signal.SIGUSR1, lambda *_: (force.__setitem__(0, True), _claude.__setitem__("at", 0)))
    last, is_open, next_at = None, False, 0
    while True:
        if time.time() >= next_at or force[0]:
            force[0] = False
            line = record(is_open)
            if line != last:
                try:
                    print(line, flush=True)
                except BrokenPipeError:
                    return
                last = line
            next_at = time.time() + (10 if is_open else 60)
        try:
            r, _, _ = select.select([sys.stdin], [], [], 2)
        except InterruptedError:
            continue
        if r:
            msg = os.read(0, 4096).decode(errors="replace")
            if not msg:
                return
            words = msg.split()
            if words:
                is_open = words[-1] == "open"
                if is_open and time.time() - _claude["at"] > 60:
                    _claude["at"] = 0          # opening the menu = fresh numbers
                next_at = 0


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "status":
        main()
    else:
        sys.exit(__doc__)
