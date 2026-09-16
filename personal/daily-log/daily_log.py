#!/usr/bin/env python3
"""Daily log — paper-first tracker with one-click inbox injection.

Template (canonical — 'bio' is a FIXED label, 2nd field):
  YYYY-MM-DD|bio|pulse_bpm|sleep_-_|washedfaceY/N|drunkwaterY/N|typingY/N|stateG/Y/R/B|brushedteethY/N|friction|statement
  friction = thought→action gap (20m, 2h, -). statement = cue for next day/log.
Example:
  2026-09-15|bio|68|23-06|Y|Y|N|Y|Y|2h|prep soap for carwash next time

Usage:
  python3 daily_log.py --interactive            # wizard in paper-column order, then inject
  python3 daily_log.py --parse "2026-09-15|bio|68|23-06|Y|Y|N|Y|Y|2h|note"
  python3 daily_log.py --parse "raw line" --dry-run   # validate only, no write
  python3 daily_log.py --batch week1.txt         # end-of-week: inject many lines at once
  python3 daily_log.py --batch week1.txt --dry-run   # validate the batch, no write
  python3 daily_log.py --show                   # print current INBOX block
  python3 daily_log.py --paper                  # print printable paper table
  python3 daily_log.py --serve [--port 8000]    # browser UI mirroring paper, Submit injects

Injection target: /home/step1/workspace/vault/Logs/tracker-inbox.md
Inserts line(s) immediately before the INBOX END marker. Append-only, dedupes exact lines.
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

INBOX_PATH = Path("/home/step1/workspace/vault/Logs/tracker-inbox.md")
START_MARK = "<!-- ====================================== INBOX START ====================================== -->"
END_MARK = "<!-- ====================================== INBOX END ======================================== -->"

FIELD_ORDER = ["date", "bio", "pulse", "sleep", "face", "water", "typing",
               "state", "teeth", "friction", "statement"]

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

def norm_date(v: str) -> str:
    v = (v or "").strip()
    # paper shortcut: bare day number "15" -> 2026-09-15
    if re.fullmatch(r"\d{1,2}", v):
        v = f"2026-09-{int(v):02d}"
    # also accept 09-15 or 9/15
    m = re.fullmatch(r"0?9[-/](\d{1,2})", v)
    if m:
        v = f"2026-09-{int(m.group(1)):02d}"
    try:
        d = dt.date.fromisoformat(v)
    except ValueError:
        raise ValueError(f"bad date {v!r}: use YYYY-MM-DD or day number like '15'.")
    return d.isoformat()

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
    if re.fullmatch(r"\d{3,4}", v):  # duration fallback e.g. "65" -> keep as-is? reject, be explicit
        raise ValueError(f"bad sleep {v!r}: use bed-wake like '23-06' or '-' if skipped.")
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

def norm_state(v: str) -> str:
    key = (v or "").strip().lower()
    if key in _STATE_MAP:
        return _STATE_MAP[key]
    raise ValueError(f"bad state {v!r}: use G / Y / R / B / - (missed).")

def build_line(d: dict) -> str:
    # 'bio' is a FIXED label in the template, not a variable — always emitted literally.
    # Paper has no BIO cell; transcription/app insert it automatically.
    date = norm_date(d.get("date", ""))
    pulse = norm_pulse(d.get("pulse", "-"))
    sleep = norm_sleep(d.get("sleep", "-"))
    face = norm_yn(d.get("face", "-"), "face")
    water = norm_yn(d.get("water", "-"), "water")
    typing = norm_yn(d.get("typing", "-"), "typing")
    state = norm_state(d.get("state", "-"))
    teeth = norm_yn(d.get("teeth", "-"), "teeth")
    # friction = thought→action gap (e.g. 20m, 2h, 3d). Statement = compressed cue for next day/log.
    friction = _clean_text(d.get("friction", ""), allow_empty=True, max_len=60) or "-"
    statement = _clean_text(d.get("statement", ""), allow_empty=True, max_len=200) or "-"
    return f"{date}|bio|{pulse}|{sleep}|{face}|{water}|{typing}|{state}|{teeth}|{friction}|{statement}"

def parse_raw(line: str) -> str:
    """Take a hand-transcribed raw line (with or without parens/spaces) -> canonical line."""
    s = (line or "").strip()
    s = s.strip("()").strip()
    parts = [p.strip() for p in s.split("|")]
    if len(parts) != 11:
        raise ValueError(f"expected 11 |-separated fields, got {len(parts)}. Template:\n"
                         "YYYY-MM-DD|bio|pulse|sleep|face|water|typing|state|teeth|friction|statement")
    keys = FIELD_ORDER
    return build_line(dict(zip(keys, parts)))

# ---------------------------------------------------------------- injection

def read_inbox(path: Path | None = None) -> str:
    return (path or INBOX_PATH).read_text(encoding="utf-8")

def inbox_lines(path: Path | None = None) -> list[str]:
    text = read_inbox(path)
    si, ei = text.index(START_MARK), text.index(END_MARK)
    block = text[si + len(START_MARK):ei]
    return [l for l in (x.strip() for x in block.splitlines()) if l]

def inject_line(line: str, path: Path | None = None, dry_run: bool = False) -> str:
    line = parse_raw(line)  # validates + normalizes even if already canonical
    path = path or INBOX_PATH
    text = read_inbox(path)
    if START_MARK not in text or END_MARK not in text:
        raise RuntimeError("INBOX START/END markers not found — refusing to write.")
    si, ei = text.index(START_MARK), text.index(END_MARK)
    if si > ei:
        raise RuntimeError("START marker is after END marker — file looks corrupt, refusing to write.")
    block = text[si + len(START_MARK):ei]
    existing = [l.strip() for l in block.splitlines() if l.strip()]
    if line.strip() in existing:
        return "duplicate — already in inbox, not added."
    new_block = block
    if not new_block.endswith("\n"):
        new_block += "\n"
    new_block += line.strip() + "\n"
    new_text = text[:si + len(START_MARK)] + new_block + text[ei:]
    if dry_run:
        return f"DRY-RUN OK (not written):\n{line.strip()}"
    path.write_text(new_text, encoding="utf-8")
    return f"injected:\n{line.strip()}"

# ---------------------------------------------------------------- paper

def inject_batch(text: str, path: Path | None = None, dry_run: bool = False) -> tuple[str, int]:
    """Inject many raw lines at once (end-of-week transcription). Returns (report, exit_code).

    Blank lines skipped. Continues past per-line errors; reports each line's fate.
    """
    path = path or INBOX_PATH
    added, dupes, errs = [], [], []
    n = 0
    for raw in (text or "").splitlines():
        if not raw.strip():
            continue
        n += 1
        try:
            res = inject_line(raw, path=path, dry_run=dry_run)
            if res.startswith("duplicate"):
                dupes.append(raw.strip())
            else:
                added.append(parse_raw(raw))
        except Exception as e:  # noqa: BLE001 — per-line report, keep going
            errs.append(f"line {n} {raw.strip()!r}: {e}")
    tag = "DRY-RUN — nothing written" if dry_run else "done"
    report = [f"{tag}: {len(added)} added, {len(dupes)} duplicates, {len(errs)} errors (of {n} lines)."]
    report += [f"  + {l}" for l in added]
    report += [f"  = dupe {l}" for l in dupes]
    report += [f"  ! {e}" for e in errs]
    return "\n".join(report), (1 if errs else 0)

# ---------------------------------------------------------------- paper

PAPER = """DAILY LOG — paper sheet (Sept 2026). Fill ~07:00 (1hr after 06:00 wake). ZERO math on paper.
One row/day, <30s, pen only. Digitize in a batch at end of the 7-day period.
Mark:  ✓ = Y   — = N   blank = missed (transcribe blank as '-').
STATE: circle one of G Y R B. 'bio' is a FIXED label — no BIO cell, the app inserts it.

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
STATEMENT = compressed cue for the next day/log (e.g. 'prep soap for carwash next time',
'volatile home situation', 'driving tomorrow', 'components before labels').

Batch transcription (end of week): copy your 7 paper rows into 7 lines, left→right,
'|' between fields, 'bio' inserted literally in 2nd position:
  2026-09-15|bio|68|23-06|Y|Y|N|Y|Y|2h|prep soap for carwash next time
  D = day number ok ('15' -> 2026-09-15, the app expands it).
  '-' anywhere = skipped/missed. Never leave a paper cell ambiguous: '-' beats blank.

Example filled row:
  15 | 68 | 23-06 | ✓ | ✓ | — | (Y) | ✓ | 2h | prep soap for carwash next time
  -> 2026-09-15|bio|68|23-06|Y|Y|N|Y|Y|2h|prep soap for carwash next time
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
<div class="muted">Same left→right order as your paper row. Tick like paper, Submit injects
between INBOX START/END in <code>tracker-inbox.md</code>. Use <code>-</code> for missed.</div>
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
<button type="submit">Inject into tracker-inbox.md →</button>
</form>
<h3>End-of-week batch (paste up to 7 transcribed lines, one per line)</h3>
<form method="post" action="/batch">
<div><label>7 lines, 'bio' in 2nd position</label><textarea name="batch" rows="8" style="width:100%;padding:10px;border-radius:10px;border:1px solid #888;background:inherit;color:inherit" placeholder="2026-09-15|bio|68|23-06|Y|Y|N|Y|Y|2h|prep soap for carwash next time"></textarea></div>
<button type="submit">Inject batch →</button>
</form>
<h3>Preview line</h3>
<pre id="pv"></pre>
<script>
const f=document.querySelector('form'),pv=document.getElementById('pv');
function upd(){const d=new FormData(f);let day=(d.get('date')||'').trim();
if(/^\\d{1,2}$/.test(day))day='2026-09-'+String(day).padStart(2,'0');
pv.textContent=[day||'YYYY-MM-DD','bio',d.get('pulse')||'-',d.get('sleep')||'-',d.get('face'),d.get('water'),d.get('typing'),d.get('state'),d.get('teeth'),d.get('friction')||'-',d.get('statement')||'-'].join('|');}
f.addEventListener('input',upd);upd();
</script>
<p class="muted"><a href="/lines">View current inbox lines</a></p>
</body></html>"""

def _default_date() -> str:
    today = dt.date.today().isoformat()
    return today if today.startswith("2026-09-") else "2026-09-"

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
    def do_GET(self):
        if self.path == "/lines":
            try:
                lines = inbox_lines()
                body = "<h2>Inbox lines</h2><pre>" + html.escape("\n".join(lines) or "(empty)") + '</pre><p><a href="/">← back</a></p>'
                return self._send(body)
            except Exception as e:
                return self._send(f"<p>Error: {html.escape(str(e))}</p>", 500)
        today = dt.date.today().isoformat()
        if today.startswith("2026-09-"):
            default = today
        else:
            default = "2026-09-"
        return self._send(render_page("", default))
    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        data = parse_qs(self.rfile.read(n).decode(), keep_blank_values=True)
        d = {k: (v[0] if v else "") for k, v in data.items()}
        if self.path == "/batch":
            try:
                report, _ = inject_batch(d.get("batch", ""))
                msg = f'<div class="ok">✓ batch result:<br><pre>{html.escape(report)}</pre></div>'
            except Exception as e:
                msg = f'<div class="err">✗ {html.escape(str(e))}</div>'
            return self._send(render_page(msg, d.get("date", _default_date())))
        if self.path != "/inject":
            return self._send("not found", 404)
        try:
            line = build_line(d)
            result = inject_line(line)
            msg = f'<div class="ok">✓ {html.escape(result)}</div>'
        except Exception as e:
            msg = f'<div class="err">✗ {html.escape(str(e))}</div>'
        # re-render with submitted values preserved minimally
        page = render_page(msg, d.get("date", _default_date()))
        return self._send(page)

# ---------------------------------------------------------------- cli

def interactive() -> int:
    print("Daily log — answer in paper order. '-' = missed. Ctrl-C aborts.\n")
    today = dt.date.today().isoformat()
    dflt_date = today if today.startswith("2026-09-") else "2026-09-"
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
        line = build_line(d)
    except ValueError as e:
        print(f"\n✗ invalid: {e}")
        return 2
    print(f"\nPreview:\n  {line}")
    ok = input("Inject between INBOX START/END? [Y/n]: ").strip().lower()
    if ok not in ("", "y", "yes"):
        print("not written.")
        return 0
    try:
        print(inject_line(line))
    except Exception as e:
        print(f"✗ {e}")
        return 3
    return 0

def main(argv=None) -> int:
    global INBOX_PATH
    ap = argparse.ArgumentParser(description="Daily log injector (paper-first).")
    ap.add_argument("--parse", metavar="LINE", help="validate + inject one raw |-separated line")
    ap.add_argument("--batch", metavar="FILE", help="inject many lines at once (end-of-week file, use - for stdin)")
    ap.add_argument("--dry-run", action="store_true", help="validate only, do not write")
    ap.add_argument("--interactive", action="store_true", help="wizard in paper order")
    ap.add_argument("--show", action="store_true", help="print current inbox block")
    ap.add_argument("--paper", action="store_true", help="print printable paper template")
    ap.add_argument("--serve", action="store_true", help="serve browser UI that injects on submit")
    ap.add_argument("--port", type=int, default=8000)
    ap.add_argument("--inbox", default=str(INBOX_PATH))
    args = ap.parse_args(argv)
    INBOX_PATH = Path(args.inbox)

    if args.paper:
        print(PAPER)
        return 0
    if args.show:
        try:
            for l in inbox_lines():
                print(l)
        except Exception as e:
            print(f"✗ {e}", file=sys.stderr)
            return 1
        return 0
    if args.serve:
        srv = HTTPServer(("127.0.0.1", args.port), Handler)
        print(f"Daily log UI → http://127.0.0.1:{args.port}/  (Ctrl-C to stop)")
        print(f"Injects into: {INBOX_PATH}")
        try:
            srv.serve_forever()
        except KeyboardInterrupt:
            print("\nstopped.")
        return 0
    if args.parse is not None:
        try:
            if args.dry_run:
                print(inject_line(args.parse, dry_run=True))
            else:
                print(inject_line(args.parse))
        except Exception as e:
            print(f"✗ {e}", file=sys.stderr)
            return 1
        return 0
    if args.batch is not None:
        try:
            text = sys.stdin.read() if args.batch == "-" else Path(args.batch).read_text(encoding="utf-8")
            report, code = inject_batch(text, dry_run=args.dry_run)
            print(report)
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
