#!/usr/bin/env python3
"""Daily log — paper-first tracker; injects ledger blocks into the fortnight log.

Paper line (canonical, 11 fields — 'bio' is a FIXED label, 2nd field):
  YYYY-MM-DD|bio|pulse_bpm|sleep_bed-wake|washedfaceY/N|drunkwaterY/N|typingY/N|amG/Y/R/B|brushedteethY/N|friction|statement
  friction = thought→action gap (20m, 2h, -). statement = cue for next day/log.
Extended line (16 fields) adds the evening mini-row (pm|mover|deep|load|social) after teeth:
  YYYY-MM-DD|bio|pulse|sleep|face|water|typing|am|teeth|pm|mover|deep|load|social|friction|statement
Examples:
  2026-10-17|bio|68|23-06|Y|Y|N|G|Y|2h|prep soap for carwash next time
  2026-10-17|bio|68|23-06|Y|Y|N|G|Y|Y|Y|2|3|N|2h|prep soap for carwash next time

Ledger target: /home/step1/workspace/vault/Logs/fortnight-performance-log.md
Inserts blocks immediately before the LEDGER END marker. Append-only, dedupes by '### date'.
Tracker export (index.html 'Fortnight export') folds in with --merge: vitals/load fill their
fields ([tracker] prefixed), tests/bio/note go to Anomaly, sleep tokens stripped.

Usage:
  python3 daily_log.py --interactive            # wizard in paper-column order, then inject
  python3 daily_log.py --parse "2026-10-17|bio|68|23-06|Y|Y|N|G|Y|2h|note"
  python3 daily_log.py --parse "raw line" --dry-run   # validate only, no write
  python3 daily_log.py --batch week1.txt         # end-of-week: inject many lines at once
  python3 daily_log.py --batch week1.txt --merge tracker-fortnight-2026-10-17.md
  python3 daily_log.py --merge tracker-fortnight-2026-10-17.md
  python3 daily_log.py --show                   # print current ledger block
  python3 daily_log.py --paper                  # print printable paper table
  python3 daily_log.py --serve [--port 8000]    # browser UI mirroring paper, Submit injects

Paper: fill ~07:00, zero math, day number only. Digitize in a 7-day batch.
Stdlib only.
"""
from __future__ import annotations
import argparse
import datetime as dt
import html
import re
import sys
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

LEDGER_PATH = Path("/home/step1/workspace/vault/Logs/fortnight-performance-log.md")
START_MARK = "<!-- LEDGER START -->"
END_MARK = "<!-- LEDGER END -->"
LEDGER_DATE_RE = re.compile(r"^### (\d{4}-\d{2}-\d{2})$")

FIELD_ORDER = ["date", "bio", "pulse", "sleep", "face", "water", "typing", "am",
               "teeth", "friction", "statement"]
FIELD_ORDER_EXT = ["date", "bio", "pulse", "sleep", "face", "water", "typing", "am",
                   "teeth", "pm", "mover", "deep", "load", "social", "friction", "statement"]

# ---------------------------------------------------------------- validation

def _clean_text(v: str, *, allow_empty: bool = False, max_len: int = 200) -> str:
    v = (v or "").strip()
    if "|" in v:
        raise ValueError("'|' not allowed inside a field (it is the column separator).")
    v = re.sub(r"\s+", " ", v)
    if not v and not allow_empty:
        raise ValueError("field is required (use '-' if skipped).")
    if len(v) > max_len:
        raise ValueError(f"too long (max {max_len} chars). Keep friction<=3 words, statement<=12 words.")
    return v

def _prev_month(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)

def _valid_date(y: int, m: int, d: int) -> dt.date | None:
    try:
        return dt.date(y, m, d)
    except ValueError:
        return None

def norm_date(v: str) -> str:
    v = (v or "").strip()
    today = dt.date.today()
    # paper shortcut: bare day number "17" -> most recent past 17th (month auto-resolves)
    if re.fullmatch(r"\d{1,2}", v):
        day = int(v)
        cand = _valid_date(today.year, today.month, day)
        if cand is None or cand > today:
            y, m = _prev_month(today.year, today.month)
            cand = _valid_date(y, m, day)
            if cand is None:
                raise ValueError(f"bad date {v!r}: no such day in the last two months.")
        return cand.isoformat()
    # also accept 10-15 or 10/15 (month-day)
    m = re.fullmatch(r"(\d{1,2})[-/](\d{1,2})", v)
    if m:
        mo, day = int(m.group(1)), int(m.group(2))
        cand = _valid_date(today.year, mo, day)
        if cand is None:
            raise ValueError(f"bad date {v!r}: month/day does not exist.")
        if cand > today:
            cand = _valid_date(today.year - 1, mo, day)
        return cand.isoformat()
    try:
        return dt.date.fromisoformat(v).isoformat()
    except ValueError:
        raise ValueError(f"bad date {v!r}: use YYYY-MM-DD or day number like '17'.")

def norm_pulse(v: str) -> str:
    v = (v or "").strip()
    if v in ("", "-", "?", "~"):
        return "-"
    if not re.fullmatch(r"\d{2,3}", v):
        raise ValueError(f"bad pulse {v!r}: 2-3 digits (bpm) or '-' if skipped.")
    n = int(v)
    if not 30 <= n <= 220:
        raise ValueError(f"pulse {n} out of range 30-220.")
    return str(n)

def norm_sleep(v: str) -> str:
    v = (v or "").strip()
    if v in ("", "-", "?", "~"):
        return "-"
    v = v.replace("–", "-").replace("—", "-").replace(":", "").replace(" ", "").replace(".", "")
    # accept 2306 (bed 23, wake 06) or 23-06 or 2330-0630
    if re.fullmatch(r"\d{1,2}-\d{1,2}", v):
        return v
    if re.fullmatch(r"\d{3,4}-\d{3,4}", v):
        return v
    raise ValueError(f"bad sleep {v!r}: use bed-wake like '23-06' or '-' if skipped.")

_YN_MAP = {
    "y": "Y", "yes": "Y", "1": "Y", "true": "Y", "✓": "Y", "✔": "Y", "x": "Y",
    "n": "N", "no": "N", "0": "N", "false": "N", "✗": "N", "×": "N",
}
_YN_MISSED = {"", "-", "—", "?", "~", "na", "n/a", "missed", "skip", "skipped"}

def norm_yn(v: str, name: str) -> str:
    # Paper blank / '-' means MISSED (distinct from N). Never conflate the two.
    s = (v or "").strip()
    if s.lower() in _YN_MISSED:
        return "-"
    key = s.lower()
    if key in _YN_MAP:
        return _YN_MAP[key]
    if s.upper() in ("Y", "N"):
        return s.upper()
    raise ValueError(f"bad {name} {v!r}: use Y / N / - (missed).")

_STATE_MAP = {
    "g": "G", "green": "G",
    "y": "Y", "yellow": "Y",
    "r": "R", "red": "R",
    "b": "B", "black": "B",
    "-": "-", "": "-", "?": "-", "~": "-",
}
_STATE_GLYPH = {"G": "🟢", "Y": "🟡", "R": "🔴", "B": "🔵", "-": "-"}
_CHAIN_GLYPH = {"Y": "✓", "N": "—", "-": "-"}

def norm_state(v: str) -> str:
    key = (v or "").strip().lower()
    if key in _STATE_MAP:
        return _STATE_MAP[key]
    raise ValueError(f"bad state {v!r}: use G / Y / R / B / - (missed).")

def norm_load(v: str) -> str:
    v = (v or "").strip()
    if v in ("", "-", "?", "~"):
        return "-"
    if not re.fullmatch(r"[1-5]", v):
        raise ValueError(f"bad load {v!r}: 1-5 or '-' if skipped.")
    return v

def norm_deep(v: str) -> str:
    v = (v or "").strip()
    if v in ("", "-", "?", "~"):
        return "-"
    v = re.sub(r"h(rs?)?$", "", v.lower()).strip()
    if not re.fullmatch(r"\d{1,2}(\.\d)?", v):
        raise ValueError(f"bad deep-work hours {v!r}: e.g. 2, 1.5, 2h, or '-'.")
    return v + "h"

# ---------------------------------------------------------------- ledger blocks

def build_block(d: dict) -> str:
    # 'bio' is a FIXED label in the template, not a variable — always emitted literally.
    date = norm_date(d.get("date", ""))
    am = _STATE_GLYPH[norm_state(d.get("am", d.get("state", "-")))]
    pm = _STATE_GLYPH[norm_state(d.get("pm", "-"))]
    sleep = norm_sleep(d.get("sleep", "-"))
    pulse = norm_pulse(d.get("pulse", "-"))
    mover = norm_yn(d.get("mover", "-"), "mover")
    deep = norm_deep(d.get("deep", "-"))
    load = norm_load(d.get("load", "-"))
    social = norm_yn(d.get("social", "-"), "social")
    chain = "".join(_CHAIN_GLYPH[norm_yn(d.get(k, "-"), k)] for k in ("face", "water", "typing", "teeth"))
    friction = _clean_text(d.get("friction", ""), allow_empty=True, max_len=60) or ""
    statement = _clean_text(d.get("statement", ""), allow_empty=True, max_len=200) or ""
    friction = "" if friction == "-" else friction
    statement = "" if statement == "-" else statement
    if friction and statement:
        cue = f"{friction} → {statement}"
    else:
        cue = friction or statement or "-"
    anomaly = _clean_text(d.get("anomaly", ""), allow_empty=True, max_len=200) or "-"
    return "\n".join([
        f"### {date}",
        f"- **AM:** {am} **Sleep:** {sleep} **Vitals:** {pulse}",
        f"- **PM:** {pm} **Mover:** {mover} **Deep:** {deep} **Load:** {load} **Social:** {social}",
        f"- **Chain:** {chain} **Friction→Cue:** {cue}",
        f"- **Anomaly:** {anomaly}",
    ])

def parse_fields(line: str) -> dict:
    s = (line or "").strip().strip("()").strip()
    parts = [p.strip() for p in s.split("|")]
    if len(parts) == len(FIELD_ORDER):
        keys = FIELD_ORDER
    elif len(parts) == len(FIELD_ORDER_EXT):
        keys = FIELD_ORDER_EXT
    else:
        raise ValueError(
            f"expected {len(FIELD_ORDER)} or {len(FIELD_ORDER_EXT)} |-separated fields, got {len(parts)}. Templates:\n"
            "  11: YYYY-MM-DD|bio|pulse|sleep|face|water|typing|am|teeth|friction|statement\n"
            "  16: ...|am|teeth|pm|mover|deep|load|social|friction|statement (adds the evening mini-row)")
    d = dict(zip(keys, parts))
    if d.get("bio", "").lower() != "bio":
        raise ValueError("2nd field must be the literal 'bio' label.")
    return d

# ---------------------------------------------------------------- ledger text ops

def read_ledger(path: Path | None = None) -> str:
    return (path or LEDGER_PATH).read_text(encoding="utf-8")

def _parts(text: str) -> tuple[str, str, str]:
    if START_MARK not in text or END_MARK not in text:
        raise RuntimeError("LEDGER START/END markers not found — refusing to write.")
    si, ei = text.index(START_MARK), text.index(END_MARK)
    if si > ei:
        raise RuntimeError("START marker is after END marker — file looks corrupt, refusing to write.")
    return text[:si + len(START_MARK)], text[si + len(START_MARK):ei], text[ei:]

def _join_mid(mid: str, lines: list[str]) -> str:
    body = "\n".join(lines)
    if mid.startswith("\n") and not body.startswith("\n"):
        body = "\n" + body
    if mid.endswith("\n") and not body.endswith("\n"):
        body += "\n"
    return body

def _append_lines(lines: list[str], block_lines: list[str]) -> None:
    if not lines or lines[-1].strip():
        lines.append("")
    lines.extend(block_lines)

def _has_block(mid: str, date: str) -> bool:
    return re.search(rf"^### {re.escape(date)}$", mid, re.M) is not None

def _apply_block(text: str, block: str) -> tuple[str, str]:
    date = block.splitlines()[0][4:]
    head, mid, tail = _parts(text)
    if _has_block(mid, date):
        return text, f"duplicate — {date} already in ledger, not added."
    lines = mid.splitlines()
    _append_lines(lines, block.splitlines())
    return head + _join_mid(mid, lines) + tail, f"injected:\n{block}"

def _find_block(lines: list[str], date: str) -> tuple[int, int] | None:
    start = None
    for i, l in enumerate(lines):
        if l.strip() == f"### {date}":
            start = i
            continue
        if start is not None and LEDGER_DATE_RE.match(l.strip()):
            return start, i
    if start is not None:
        return start, len(lines)
    return None

def _add_seg(line: str, field: str, seg: str) -> str:
    m = re.search(rf"(\*\*{field}:\*\* )(\S+)", line)
    if not m:
        return line
    val = m.group(2)
    new = f"**{field}:** {seg}" if val == "-" else f"**{field}:** {val} · {seg}"
    return line.replace(m.group(0), new, 1)

def _add_anomaly(line: str, seg: str) -> str:
    marker = "**Anomaly:** "
    head, found, content = line.partition(marker)
    if not found:
        return line
    content = content.strip()
    if content in ("-", ""):
        return head + marker + seg
    return head + marker + content + " " + seg

# ---------------------------------------------------------------- tracker merge

_TRACKER_LINE = re.compile(r"^- \*\*(Vitals|Load|Tests|Bio|Note):\*\*\s*(.*)$")

def _strip_sleep(content: str) -> str:
    keep = [s.strip() for s in content.split("·") if s.strip() and not re.search(r"sleep", s, re.I)]
    return " · ".join(keep)

def parse_tracker(text: str) -> dict[str, dict[str, str]]:
    days: dict[str, dict[str, str]] = {}
    date = None
    for line in (text or "").splitlines():
        h = re.fullmatch(r"### (\d{4}-\d{2}-\d{2})", line.strip())
        if h:
            date = h.group(1)
            try:
                dt.date.fromisoformat(date)
            except ValueError:
                raise ValueError(f"bad date {date!r} in tracker file.")
            days.setdefault(date, {})
            continue
        if date is None:
            continue
        m = _TRACKER_LINE.match(line.strip())
        if m and m.group(2).strip():
            days[date][m.group(1)] = m.group(2).strip()
    return days

def _merge_segments(info: dict[str, str]) -> dict[str, str]:
    segs = {}
    if info.get("Vitals"):
        segs["vitals"] = f"[tracker] {info['Vitals']}"
    if info.get("Load"):
        segs["load"] = f"[tracker] {info['Load']}"
    parts = []
    if info.get("Tests"):
        parts.append(f"tests: {info['Tests']}")
    if info.get("Bio"):
        b = _strip_sleep(info["Bio"])
        if b:
            parts.append(f"bio: {b}")
    if info.get("Note"):
        parts.append(f"note: {info['Note']}")
    if parts:
        segs["anomaly"] = "[tracker] " + " | ".join(parts)
    return segs

def block_from_segments(date: str, segs: dict[str, str]) -> str:
    return "\n".join([
        f"### {date}",
        f"- **AM:** - **Sleep:** - **Vitals:** {segs.get('vitals', '-')}",
        f"- **PM:** - **Mover:** - **Deep:** - **Load:** {segs.get('load', '-')} **Social:** -",
        "- **Chain:** ---- **Friction→Cue:** -",
        f"- **Anomaly:** {segs.get('anomaly', '-')}",
    ])

def _apply_merge(text: str, tracker_text: str) -> tuple[str, str]:
    days = parse_tracker(tracker_text)
    if not days:
        return text, "merge: no '### YYYY-MM-DD' sections found — nothing to do."
    head, mid, tail = _parts(text)
    lines = mid.splitlines()
    created = updated = skipped = 0
    for date in sorted(days):
        segs = _merge_segments(days[date])
        if not segs:
            continue
        span = _find_block(lines, date)
        if span is None:
            _append_lines(lines, block_from_segments(date, segs).splitlines())
            created += 1
            continue
        start, end = span
        applied = 0
        for i in range(start, end):
            if segs.get("vitals") and lines[i].startswith("- **AM:**") and segs["vitals"] not in lines[i]:
                lines[i] = _add_seg(lines[i], "Vitals", segs["vitals"])
                applied += 1
            elif segs.get("load") and lines[i].startswith("- **PM:**") and segs["load"] not in lines[i]:
                lines[i] = _add_seg(lines[i], "Load", segs["load"])
                applied += 1
            elif segs.get("anomaly") and lines[i].startswith("- **Anomaly:**") and segs["anomaly"] not in lines[i]:
                lines[i] = _add_anomaly(lines[i], segs["anomaly"])
                applied += 1
        if applied:
            updated += 1
        else:
            skipped += 1
    return head + _join_mid(mid, lines) + tail, \
        f"merge: {created} created, {updated} updated, {skipped} already present (of {len(days)} tracker days)."

def ledger_lines(path: Path | None = None) -> list[str]:
    _, mid, _ = _parts(read_ledger(path))
    return [l.rstrip() for l in mid.splitlines() if l.strip()]

# ---------------------------------------------------------------- batch

def _apply_batch(text: str, batch_text: str) -> tuple[str, str, int]:
    """Apply many raw lines at once (end-of-week transcription). Returns (text, report, exit_code)."""
    added, dupes, errs = [], [], []
    n = 0
    for raw in (batch_text or "").splitlines():
        if not raw.strip():
            continue
        n += 1
        try:
            block = build_block(parse_fields(raw))
            text, status = _apply_block(text, block)
            date = block.splitlines()[0][4:]
            (dupes if status.startswith("duplicate") else added).append(date)
        except Exception as e:  # noqa: BLE001 — per-line report, keep going
            errs.append(f"line {n} {raw.strip()!r}: {e}")
    report = [f"batch: {len(added)} added, {len(dupes)} duplicates, {len(errs)} errors (of {n} lines)."]
    report += [f"  + {l}" for l in added]
    report += [f"  = dupe {l}" for l in dupes]
    report += [f"  ! {e}" for e in errs]
    return text, "\n".join(report), (1 if errs else 0)

# ---------------------------------------------------------------- paper

PAPER = """DAILY LOG — paper sheet. Fill ~07:00 (1hr after 06:00 wake). ZERO math on paper.
One row/day, <30s, pen only. Digitize in a batch at the end of the 7-day period.
Mark:  ✓ = Y   — = N   blank = missed (transcribe blank as '-').
STATE: circle one of G Y R B. 'bio' is a FIXED label — no BIO cell, the app inserts it.
Optional evening mini-row under the day, fill ~20:00 on the same row:
  PM G/Y/R/B · MOV ✓/— · DEEP __h · LOAD 1-5 · SOC ✓/—

Header to rule on paper (landscape, 7 rows = 1 week per block):
┌────┬─────┬────────┬───┬───┬───┬───────────┬───┬──────────┬──────────────────┐
│  D │  ♥  │ SLEEP  │ F │ W │ T │   STATE   │ B │ FRICTION │    STATEMENT     │
│day │ bpm │bed-wake│fce│h2o│typ│ G/Y/R/B   │teeth thought→action │ tomorrow's cue │
├────┼─────┼────────┼───┼───┼───┼───────────┼───┼──────────┼──────────────────┤
│    │     │   -    │   │   │   │ G Y R B   │   │          │                  │
│    │     │   -    │   │   │   │ G Y R B   │   │          │                  │
│    │     │   -    │   │   │   │ G Y R B   │   │          │                  │
│    │     │   -    │   │   │   │ G Y R B   │   │          │                  │
│    │     │   -    │   │   │   │ G Y R B   │   │          │                  │
│    │     │   -    │   │   │   │ G Y R B   │   │          │                  │
│    │     │   -    │   │   │   │ G Y R B   │   │          │                  │
└────┴─────┴────────┴───┴───┴───┴───────────┴───┴──────────┴──────────────────┘

FRICTION = gap between thought and action (e.g. 20m, 2h, 3d, or '-' ).
STATEMENT = compressed cue for the next day/log (e.g. 'prep soap for carwash next time').

Batch transcription (end of week): ONE line per day, left→right, '|' between fields,
'bio' written literally in 2nd position. Include the evening mini-row for the full block:
  Morning (11): 2026-10-17|bio|68|23-06|Y|Y|N|G|Y|2h|prep soap for carwash next time
  Full (16):    2026-10-17|bio|68|23-06|Y|Y|N|G|Y|Y|Y|2|3|N|2h|prep soap for carwash next time
                 (after teeth: pm|mover|deep|load|social)
  D = day number ok ('17' -> most recent 17th; month resolves itself).
  '-' anywhere = skipped/missed. Never leave a paper cell ambiguous: '-' beats blank.

Example filled row:
  17 | 68 | 23-06 | ✓ | ✓ | — | (G) | ✓ | 2h | prep soap for carwash next time
  -> 2026-10-17|bio|68|23-06|Y|Y|N|G|Y|2h|prep soap for carwash next time
"""

# ---------------------------------------------------------------- web UI (mirrors paper order)

PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Daily Log — paper mirror</title>
<style>
:root{color-scheme:dark light}
body{font-family:system-ui,sans-serif;max-width:720px;margin:0 auto;padding:16px;line-height:1.45}
h1{font-size:1.3rem;margin:0 0 4px}.muted{opacity:.7;font-size:.88rem}
form{display:grid;gap:12px;margin-top:12px}
.row{display:grid;grid-template-columns:1fr 1fr;gap:12px}
@media(max-width:560px){.row{grid-template-columns:1fr}}
label{font-weight:650;font-size:.9rem;display:block;margin-bottom:4px}
input[type=text],input[type=number]{width:100%;padding:10px;border-radius:10px;border:1px solid #888;background:inherit;color:inherit;font-size:1rem}
.seg{display:flex;gap:8px;flex-wrap:wrap}
.seg label{font-weight:500;margin:0}
.seg input{display:none}
.seg span{display:inline-block;padding:9px 16px;border:1px solid #888;border-radius:999px;cursor:pointer}
.seg input:checked+span{background:#0e7c66;color:#fff;border-color:#0e7c66;font-weight:700}
button{padding:13px;border:0;border-radius:12px;font-weight:750;font-size:1rem;cursor:pointer;background:#0e7c66;color:#fff}
pre{background:#0003;border:1px solid #8883;border-radius:10px;padding:12px;white-space:pre-wrap}
.ok{background:#0e3d33;border:1px solid #0e7c66;border-radius:10px;padding:12px}
.err{background:#3d1515;border:1px solid #a33;border-radius:10px;padding:12px}
a{color:#0e7c66}
table.paper{border-collapse:collapse;width:100%;font-size:.78rem;margin:10px 0}
table.paper th,table.paper td{border:1px solid #8886;padding:5px 6px;text-align:center}
</style></head><body>
<h1>Daily Log — paper mirror</h1>
<div class="muted">Same left→right order as your paper row. Submit injects a ledger block into
<code>fortnight-performance-log.md</code> between LEDGER START/END. Use <code>-</code> for missed.</div>
<table class="paper"><tr><th>D</th><th>♥</th><th>SLEEP</th><th>F</th><th>W</th><th>T</th><th>STATE</th><th>B</th><th>FRICTION</th><th>STATEMENT</th></tr></table>
%%MSG%%
<form method="post" action="/inject">
<div class="row">
<div><label>Date (YYYY-MM-DD or day no.)</label><input name="date" value="%%DATE%%" required></div>
<div><label>Pulse bpm (or -)</label><input name="pulse" placeholder="68 or -"></div>
</div>
<div class="row">
<div><label>Sleep bed-wake (23-06, or -)</label><input name="sleep" placeholder="23-06 or -"></div>
<div><label>Friction — thought→action gap (20m / 2h / -)</label><input name="friction" type="text" maxlength="60" placeholder="2h"></div>
</div>
<div><label>Washed face</label><div class="seg">
<label><input type="radio" name="face" value="Y"><span>✓ Y</span></label>
<label><input type="radio" name="face" value="N"><span>— N</span></label>
<label><input type="radio" name="face" value="-" checked><span>- missed</span></label></div></div>
<div><label>Drank water</label><div class="seg">
<label><input type="radio" name="water" value="Y"><span>✓ Y</span></label>
<label><input type="radio" name="water" value="N"><span>— N</span></label>
<label><input type="radio" name="water" value="-" checked><span>- missed</span></label></div></div>
<div><label>Typing</label><div class="seg">
<label><input type="radio" name="typing" value="Y"><span>✓ Y</span></label>
<label><input type="radio" name="typing" value="N"><span>— N</span></label>
<label><input type="radio" name="typing" value="-" checked><span>- missed</span></label></div></div>
<div><label>State — circle one (paper: G Y R B)</label><div class="seg">
<label><input type="radio" name="state" value="G"><span>G</span></label>
<label><input type="radio" name="state" value="Y"><span>Y</span></label>
<label><input type="radio" name="state" value="R"><span>R</span></label>
<label><input type="radio" name="state" value="B"><span>B</span></label>
<label><input type="radio" name="state" value="-" checked><span>- missed</span></label></div></div>
<div><label>Brushed teeth</label><div class="seg">
<label><input type="radio" name="teeth" value="Y"><span>✓ Y</span></label>
<label><input type="radio" name="teeth" value="N"><span>— N</span></label>
<label><input type="radio" name="teeth" value="-" checked><span>- missed</span></label></div></div>
<div><label>Statement — cue for next day/log</label><input name="statement" type="text" maxlength="200" placeholder="prep soap for carwash next time"></div>
<button type="submit">Inject ledger block →</button>
</form>
<h3>End-of-week batch (paste up to 7 transcribed lines, one per line)</h3>
<form method="post" action="/batch">
<div><label>7 lines, 11 or 16 fields, 'bio' in 2nd position</label><textarea name="batch" rows="8" style="width:100%;padding:10px;border-radius:10px;border:1px solid #888;background:inherit;color:inherit" placeholder="2026-10-17|bio|68|23-06|Y|Y|N|G|Y|2h|prep soap for carwash next time"></textarea></div>
<button type="submit">Inject batch →</button>
</form>
<h3>Preview block</h3>
<pre id="pv"></pre>
<script>
const f=document.querySelector('form'),pv=document.getElementById('pv');
const G={G:'🟢',Y:'🟡',R:'🔴',B:'🔵','-':'-'},C={Y:'✓',N:'—','-':'-'};
function upd(){
  const d=new FormData(f),v=k=>((d.get(k)||'-')+'').trim()||'-';
  const chain=['face','water','typing','teeth'].map(k=>(C[v(k).toUpperCase()]||'-')).join('');
  const fr=v('friction'),st=v('statement');
  const cue=fr!=='-'&&st!=='-'?fr+' → '+st:(fr!=='-'?fr:(st!=='-'?st:'-'));
  pv.textContent=['### '+v('date'),
    '- **AM:** '+(G[v('state').toUpperCase()]||'-')+' **Sleep:** '+v('sleep')+' **Vitals:** '+v('pulse'),
    '- **PM:** - **Mover:** - **Deep:** - **Load:** - **Social:** -',
    '- **Chain:** '+chain+' **Friction→Cue:** '+cue,
    '- **Anomaly:** -'].join('\\n');
}
f.addEventListener('input',upd);upd();
</script>
<p class="muted"><a href="/lines">View current ledger blocks</a></p>
</body></html>"""

def _default_date() -> str:
    return dt.date.today().isoformat()

def render_page(msg: str = "", date: str = "") -> str:
    # NOTE: plain .replace, NOT str.format — the CSS is full of {braces}.
    return PAGE.replace("%%MSG%%", msg).replace("%%DATE%%", html.escape(date))

class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass
    def _send(self, body: str, code: int = 200):
        b = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)
    def _inject(self, block: str) -> str:
        text = read_ledger()
        new_text, status = _apply_block(text, block)
        if new_text != text:
            LEDGER_PATH.write_text(new_text, encoding="utf-8")
        return status
    def do_GET(self):
        if self.path == "/lines":
            try:
                lines = ledger_lines()
                body = "<h2>Ledger blocks</h2><pre>" + html.escape("\n".join(lines) or "(empty)") + '</pre><p><a href="/">← back</a></p>'
                return self._send(body)
            except Exception as e:
                return self._send(f"<p>Error: {html.escape(str(e))}</p>", 500)
        return self._send(render_page("", _default_date()))
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        data = parse_qs(self.rfile.read(n).decode(), keep_blank_values=True)
        d = {k: (v[0] if v else "") for k, v in data.items()}
        if self.path == "/batch":
            try:
                text = read_ledger()
                new_text, report, _ = _apply_batch(text, d.get("batch", ""))
                if new_text != text:
                    LEDGER_PATH.write_text(new_text, encoding="utf-8")
                msg = f'<div class="ok">✓ batch result:<br><pre>{html.escape(report)}</pre></div>'
            except Exception as e:
                msg = f'<div class="err">✗ {html.escape(str(e))}</div>'
            return self._send(render_page(msg, d.get("date", _default_date())))
        if self.path != "/inject":
            return self._send("not found", 404)
        try:
            result = self._inject(build_block(d))
            msg = f'<div class="ok">✓ {html.escape(result)}</div>'
        except Exception as e:
            msg = f'<div class="err">✗ {html.escape(str(e))}</div>'
        return self._send(render_page(msg, d.get("date", _default_date())))

# ---------------------------------------------------------------- cli

def interactive() -> int:
    print("Daily log — answer in paper order. '-' = missed. Ctrl-C aborts.\n")
    dflt_date = _default_date()
    def ask(name: str, default: str = "-", hint: str = "") -> str:
        h = f" [{hint}]" if hint else ""
        v = input(f"{name}{h} (default '{default}'): ").strip()
        return v if v != "" else default
    try:
        d = {
            "date": ask("D date", dflt_date, "YYYY-MM-DD or day no."),
            "pulse": ask("♥ pulse", "-", "bpm"),
            "sleep": ask("SLEEP", "-", "bed-wake 23-06"),
            "face": ask("F face washed?", "-", "Y/N/-"),
            "water": ask("W water?", "-", "Y/N/-"),
            "typing": ask("T typing?", "-", "Y/N/-"),
            "state": ask("STATE", "-", "G/Y/R/B/-"),
            "teeth": ask("B brushed teeth?", "-", "Y/N/-"),
            "friction": ask("FRICTION thought->action gap", "-", "e.g. 20m, 2h"),
            "statement": ask("STATEMENT cue for next day", "-", "e.g. driving tomorrow"),
        }
    except (KeyboardInterrupt, EOFError):
        print("\naborted.")
        return 1
    try:
        block = build_block(d)
    except ValueError as e:
        print(f"\n✗ invalid: {e}")
        return 2
    print(f"\nPreview:\n{block}")
    ok = input("Inject before LEDGER END? [Y/n]: ").strip().lower()
    if ok not in ("", "y", "yes"):
        print("not written.")
        return 0
    try:
        text = read_ledger()
        new_text, status = _apply_block(text, block)
        if new_text != text:
            LEDGER_PATH.write_text(new_text, encoding="utf-8")
        print(status)
    except Exception as e:
        print(f"✗ {e}")
        return 3
    return 0

def main(argv=None) -> int:
    global LEDGER_PATH
    ap = argparse.ArgumentParser(description="Daily log — paper-first ledger writer.")
    ap.add_argument("--parse", metavar="LINE", help="validate one raw |-separated line and inject its block")
    ap.add_argument("--batch", metavar="FILE", help="inject many paper lines at once (end-of-week file, use - for stdin)")
    ap.add_argument("--merge", metavar="TRACKER_MD", help="fold a tracker Fortnight export into the ledger (runs after --batch)")
    ap.add_argument("--dry-run", action="store_true", help="validate only, do not write")
    ap.add_argument("--interactive", action="store_true", help="wizard in paper order")
    ap.add_argument("--show", action="store_true", help="print current ledger blocks")
    ap.add_argument("--paper", action="store_true", help="print printable paper template")
    ap.add_argument("--serve", action="store_true", help="serve browser UI that injects on submit")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--ledger", default=str(LEDGER_PATH))
    args = ap.parse_args(argv)
    LEDGER_PATH = Path(args.ledger)

    if args.paper:
        print(PAPER)
        return 0
    if args.show:
        try:
            for l in ledger_lines():
                print(l)
        except Exception as e:
            print(f"✗ {e}", file=sys.stderr)
            return 1
        return 0
    if args.serve:
        srv = HTTPServer(("127.0.0.1", args.port), Handler)
        print(f"Daily log UI → http://127.0.0.1:{args.port}/  (Ctrl-C to stop)")
        print(f"Injects into: {LEDGER_PATH}")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped.")
        return 0
    if args.parse is not None:
        try:
            block = build_block(parse_fields(args.parse))
            text = read_ledger()
            new_text, status = _apply_block(text, block)
            if args.dry_run:
                print(f"DRY-RUN — nothing written:\n{status}")
            else:
                if new_text != text:
                    LEDGER_PATH.write_text(new_text, encoding="utf-8")
                print(status)
        except Exception as e:
            print(f"✗ {e}", file=sys.stderr)
            return 1
        return 0
    if args.batch is not None or args.merge is not None:
        try:
            text = read_ledger()
            reports, code = [], 0
            if args.batch is not None:
                batch_text = sys.stdin.read() if args.batch == "-" else Path(args.batch).read_text(encoding="utf-8")
                text, rep, code = _apply_batch(text, batch_text)
                reports.append(rep)
            if args.merge is not None:
                tracker_text = Path(args.merge).read_text(encoding="utf-8")
                text, rep = _apply_merge(text, tracker_text)
                reports.append(rep)
            if args.dry_run:
                reports.insert(0, "DRY-RUN — nothing written.")
            elif text != read_ledger():
                LEDGER_PATH.write_text(text, encoding="utf-8")
            print("\n".join(reports))
            return code
        except Exception as e:
            print(f"✗ {e}", file=sys.stderr)
            return 1
    if args.interactive:
        return interactive()
    ap.print_help()
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
