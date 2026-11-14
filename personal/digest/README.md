# Digest queue

Scans where work accumulates outside the live workspace and turns it into a
one-at-a-time queue. The point is to finish old material, not to build another
system around it.

## Run

```bash
cd ~/workspace/projects/personal/digest
python3 scan.py                  # rescan + rebuild queue
python3 scan.py --next 10        # show the next 10 untriaged
python3 scan.py --preview ID     # read the first page of one item
python3 scan.py --open ID        # open it in the default app
python3 scan.py --mark ID keep   # keep | compost | defer | moved | duplicate
python3 scan.py --mark ID compost --note "superseded by node1-register"
python3 scan.py --stats          # counts by root, type, status
```

## Rules

- One item per Green session. Default outcome: **compost**.
- Nothing is deleted or moved by this script. `--mark` records a decision only.
- `decisions.csv` is the state and survives rescans. `index.csv`, `queue.md`,
  and `duplicates.md` are regenerated.
- Duplicates are grouped by SHA-256. The canonical copy is the one already under
  `~/workspace`, otherwise the shortest path.
- IDs are path-based. If you move a file, rescan and mark the new ID.

## Roots

Default: `~/Desktop`, `~/Documents`, `~/Downloads`, `~/Sync`.
`~/workspace` is excluded because it is the live system. Add it with
`--include-workspace` only when you want to audit the live workspace too.

The queue orders the known piles first: `Desktop/ent`, `Desktop/root_WIPS`,
`Documents/LML_entry`, `Desktop/zamzam`, then `Downloads` and the rest.
