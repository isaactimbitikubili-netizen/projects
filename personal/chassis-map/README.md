# Chassis Map

Single-file static app — no build step, no dependencies, no network. Open `index.html`
directly, or use the `projects/.vscode/launch.json` launcher.

Eight body baselines across three layers — nervous system → structure → biology — reduced to
one decision per day: **Restore / Foundation / Rehydrate / Build**. Anti-spiral framing is a
feature, not decoration: every metric is read as a 7+ log range, never a single verdict.

Educational tool only, not medical advice.

## Data

- **Storage:** browser `localStorage`, single key `chassis-map.v1`.
- **Clean slate (2026-10-24):** the pre-rename key `tensegrityLogs.v1` and its migration
  fallback were discarded — no compatibility layer, no read-through. History starts empty.
- **There is no other copy.** Clearing site data loses everything that has not been exported.

### Durability (status: exposed)

`localStorage` is the only place this data exists — it is origin-scoped, clearable by a
single "clear browsing data" action, and invisible to git and Syncthing. Export after any
session worth keeping; the export is the first action, always.

## Export → vault

`📋 Fortnight export` downloads `tracker-fortnight-YYYY-MM-DD.md`, which feeds the single
health ledger (`vault/Logs/fortnight-performance-log.md`) through `daily_log.py`:

```sh
python3 projects/personal/daily-log/daily_log.py --merge tracker-fortnight-YYYY-MM-DD.md
```

The merge is append-only, dedupes by `### date`, and is idempotent — re-running it skips
every day already present. Always `--dry-run` first.

The `tracker-fortnight-*.md` filename and the `trackerExport.v1` stamp key are **contract** —
`daily_log.py`, `paper-template.md` and `AGENTS.md` depend on them. Do not rename them.

`⬇ CSV` and `⬇ JSON` are full-history backups of everything, independent of the ledger.
