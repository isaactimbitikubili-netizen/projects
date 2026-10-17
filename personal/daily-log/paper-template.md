# Daily Log — paper sheet

Fill at ~07:00 (1hr after 06:00 wake). ZERO math on paper. One row/day, <30s, pen only.
No digitizing during the week — transcribe all 7 lines in one batch at end of the period.
Optional evening mini-row under each day (~20:00): PM state · MOV · DEEP · LOAD · SOC.

## Mark legend (write at top of every paper sheet)

- `✓` = Y, `—` = N, blank = missed (transcribe blank as `-`)
- STATE: circle one of `G Y R B` (Green / Yellow / Red / Black)
- `bio` is a FIXED label — there is no BIO cell. The app inserts it.

## Columns (left → right, mirrors file format)

| # | Paper head | Maps to | Width hint | How to mark at 07:00 |
|---|------------|---------|------------|----------------------|
| 1 | D | `date` | 2ch | day number only (`17`) — month resolves itself |
| 2 | ♥ | `pulse` | 3ch | bpm or `-` |
| 3 | SLP | `sleep` | 5ch | bed-wake `23-06` or `-` |
| 4 | F | `face` | 1ch | ✓ / — |
| 5 | W | `water` | 1ch | ✓ / — |
| 6 | T | `typing` | 1ch | ✓ / — |
| 7 | ST | `am` state | 1ch | circle G/Y/R/B |
| 8 | B | `teeth` | 1ch | ✓ / — |
| 9 | FRICTION | `friction` | ~6ch | thought→action gap: `20m`, `2h`, `3d`, `-` |
| 10 | STATEMENT | `statement` | rest | cue for next day/log, ≤12 words |

Evening mini-row (same row, below):

| PM | MOV | DEEP | LOAD | SOC |
|----|-----|------|------|-----|
| circle G/Y/R/B | ✓ / — | `__h` | 1-5 | ✓ / — |

## Rule this on paper (landscape) — 7 rows = 1 week per block

```
D | ♥  | SLEEP | F | W | T | STATE   | B | FRICTION | STATEMENT
--|----|-------|---|---|---|---------|-----|----------|----------
  |    |       |   |   |   | G Y R B |   |          |
  |    |       |   |   |   | G Y R B |   |          |
  |    |       |   |   |   | G Y R B |   |          |
  |    |       |   |   |   | G Y R B |   |          |
  |    |       |   |   |   | G Y R B |   |          |
  |    |       |   |   |   | G Y R B |   |          |
  |    |       |   |   |   | G Y R B |   |          |
PM G/Y/R/B · MOV ✓/— · DEEP __h · LOAD 1-5 · SOC ✓/—   (repeat under each row)
```

## End-of-week transcription (one batch, 7 lines)

Left→right, `|` between fields, `bio` written literally in 2nd position.
Day number alone is fine — expanded to the most recent matching date.

Without the evening mini-row (11 fields):

```
2026-10-15|bio|68|23-06|Y|Y|N|G|Y|2h|prep soap for carwash next time
```

With the evening mini-row (16 fields — `pm|mover|deep|load|social` after `teeth`):

```
2026-10-15|bio|68|23-06|Y|Y|N|G|Y|Y|Y|2|3|N|2h|prep soap for carwash next time
```

Statement examples: `prep soap for carwash next time`, `volatile home situation`,
`driving tomorrow`, `components before labels processing`.

## Example

Paper row:

```
17 | 68 | 23-06 | ✓ | ✓ | — | (G) | ✓ | 2h | prep soap for carwash next time
PM: (Y) · MOV ✓ · DEEP 2 · LOAD 3 · SOC —
```

Transcribed (full 16-field line):

```
2026-10-17|bio|68|23-06|Y|Y|N|G|Y|Y|Y|2|3|N|2h|prep soap for carwash next time
```

## App (`projects/personal/daily-log/daily_log.py`, stdlib only)

Writes ledger blocks (AM · Sleep · Vitals / PM · Mover · Deep · Load · Social / Chain · Friction→Cue /
Anomaly) into `vault/Logs/fortnight-performance-log.md` between the `LEDGER START/END` markers.

- `python3 daily_log.py --batch week1.txt --dry-run` — validate first, no write.
- `python3 daily_log.py --batch week1.txt` — inject the week's lines as blocks.
- `python3 daily_log.py --batch week1.txt --merge tracker-fortnight-YYYY-MM-DD.md` — batch, then tracker.
- `python3 daily_log.py --merge tracker-fortnight-YYYY-MM-DD.md` — tracker export only.
- `python3 daily_log.py --parse "LINE"` — single line. `--interactive` — wizard.
- `python3 daily_log.py --serve --port 8000` — browser form in paper order + batch box.
- `python3 daily_log.py --show` — print current ledger blocks.
- `python3 daily_log.py --paper` — print ASCII sheet.

Tracker export comes from `projects/personal/tensegrity-tracker/index.html` → "📋 Fortnight export"
(Dashboard). Merge folds: `Vitals`/`Load` into their fields (`[tracker]` prefix), `Tests`/`Bio`/`Note`
into `Anomaly`; sleep tokens from `Bio` are dropped — paper owns sleep. `--batch` always runs before
`--merge` in the same command. Append-only, dedupes by `### date`.
