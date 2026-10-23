# Chassis Map

Single-file static app — no build step, no dependencies, no network. Open `index.html`
directly, or use the `projects/.vscode/launch.json` launcher.

Eight body baselines across three layers — nervous system → structure → biology — reduced to
one decision per day: **Restore / Foundation / Rehydrate / Build**. Anti-spiral framing is a
feature, not decoration: every metric is read as a 7+ log range, never a single verdict.

Educational tool only, not medical advice.

## Data

- **Storage:** browser `localStorage`, key `chassis-map.v1`.
- **Legacy key** `tensegrityLogs.v1` (pre-rename) is still read as a fallback and migrated
  forward on load. `Clear all` removes both. Once every device has opened the app and
  confirmed its history, the legacy key can be dropped.
- **There is no other copy.** Clearing site data loses everything that has not been exported.

### Durability (current status: exposed)

No `tracker-fortnight-*` file exists anywhere on disk. The dataset has never been durably
copied — only a `tensegrity-log.csv` was ever produced and it now sits in the trash.
Export before anything else; the export is the first action, always.

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
