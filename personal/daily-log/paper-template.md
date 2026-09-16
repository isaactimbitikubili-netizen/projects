# Daily Log — paper sheet (Sept 2026)

Fill at ~07:00 (1hr after 06:00 wake). ZERO math on paper. One row/day, <30s, pen only.
No digitizing during the week — transcribe all 7 lines in one batch at end of the period.

## Mark legend (write at top of every paper sheet)

- `✓` = Y, `—` = N, blank = missed (transcribe blank as `-`)
- STATE: circle one of `G Y R B` (Green / Yellow / Red / Black)
- `bio` is a FIXED label — there is no BIO cell. The app inserts it.

## Columns (left → right, mirrors app + file format)

| # | Paper head | Maps to template | Width hint | How to mark at 07:00 |
|---|------------|------------------|------------|----------------------|
| 1 | D | `2026-09-_` | 2ch | day number only (`15`) — no date math |
| 2 | ♥ | `pulse_bpm` | 3ch | bpm or `-` |
| 3 | SLP | `sleep_-_` | 5ch | bed-wake `23-06` or `-` |
| 4 | F | `washedfaceY/N` | 1ch | ✓ / — |
| 5 | W | `drunkwaterY/N` | 1ch | ✓ / — |
| 6 | T | `typingY/N` | 1ch | ✓ / — |
| 7 | ST | `stateG/Y/R/B` | 1ch | circle G/Y/R/B |
| 8 | B | `brushedteethY/N` | 1ch | ✓ / — |
| 9 | FRICTION | `friction_` | ~6ch | thought→action gap: `20m`, `2h`, `3d`, `-` |
| 10 | STATEMENT | `statement_` | rest of line | cue for next day/log, ≤12 words |

## Rule this on paper (landscape) — 7 rows = 1 week per block

```
D | ♥  | SLEEP | F | W | T | STATE   | B | FRICTION | STATEMENT
--|----|-------|---|---|---|---------|---|----------|----------
  |    |       |   |   |   | G Y R B |   |          |
  |    |       |   |   |   | G Y R B |   |          |
  |    |       |   |   |   | G Y R B |   |          |
  |    |       |   |   |   | G Y R B |   |          |
  |    |       |   |   |   | G Y R B |   |          |
  |    |       |   |   |   | G Y R B |   |          |
  |    |       |   |   |   | G Y R B |   |          |
```

## End-of-week transcription (one batch, 7 lines)

Left→right, `|` between fields, `bio` written literally in 2nd position.
Day number alone is fine — the app expands `15` → `2026-09-15`.

```
2026-09-15|bio|68|23-06|Y|Y|N|Y|Y|2h|prep soap for carwash next time
```

Statement examples: `prep soap for carwash next time`, `volatile home situation`,
`driving tomorrow`, `components before labels processing`.

## Example

Paper row:

```
15 | 68 | 23-06 | ✓ | ✓ | — | (Y) | ✓ | 2h | prep soap for carwash next time
```

Transcribed:

```
2026-09-15|bio|68|23-06|Y|Y|N|Y|Y|2h|prep soap for carwash next time
```

## App (`projects/personal/daily-log/daily_log.py`, stdlib only)

- `python3 daily_log.py --batch week1.txt` — inject the week's 7 lines at once.
- `python3 daily_log.py --batch week1.txt --dry-run` — validate first, no write.
- `python3 daily_log.py --parse "LINE"` — single line. `--interactive` — wizard.
- `python3 daily_log.py --serve --port 8000` — browser form in paper order + batch box.
- `python3 daily_log.py --show` — list current inbox lines.
- `python3 daily_log.py --paper` — print ASCII sheet.

Target: `vault/Logs/tracker-inbox.md`, inserted before `INBOX END`. Append-only, dedupes exact lines.
