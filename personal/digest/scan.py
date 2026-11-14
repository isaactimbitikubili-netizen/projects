#!/usr/bin/env python3
"""Inventory scattered notes and produce a one-at-a-time triage queue.

Stdlib only. Scans content roots (Desktop, Documents, Downloads, Sync) and
writes index.csv, duplicates.md, and queue.md next to this script. Decisions
live in decisions.csv and survive rescans.

Usage:
    python3 scan.py                  # rescan + rebuild queue
    python3 scan.py --next 10        # show next 10 untriaged
    python3 scan.py --preview ID     # read the first page of one item
    python3 scan.py --mark ID STATUS # keep | compost | defer | moved | duplicate
    python3 scan.py --open ID        # open in the default app
    python3 scan.py --stats          # counts by root, type, status
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import os
import re
import subprocess
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path

HOME = Path.home()
HERE = Path(__file__).resolve().parent
DEFAULT_ROOTS = [HOME / "Desktop", HOME / "Documents", HOME / "Downloads", HOME / "Sync"]
EXTENSIONS = {".md", ".txt", ".docx", ".odt", ".tex", ".pdf"}
SKIP_DIRS = {
    ".git", "node_modules", ".obsidian", ".venv", "venv", "__pycache__",
    ".cache", ".Trash", "Trash", "site-packages", "dist", "build", ".next",
    ".stfolder", ".mypy_cache", ".pytest_cache", ".tox",
}
STATUSES = ("keep", "compost", "defer", "moved", "duplicate")

STATE = HERE / "decisions.csv"
INDEX = HERE / "index.csv"
QUEUE = HERE / "queue.md"
DUPLICATES = HERE / "duplicates.md"

PRIORITY = {
    "Desktop/ent": 0,
    "Desktop/root_WIPS": 1,
    "Documents/LML_entry": 2,
    "Desktop/zamzam": 3,
    "Downloads": 4,
    "Documents": 5,
    "Desktop": 6,
    "Sync": 7,
}


def root_label(path: Path) -> str:
    try:
        rel = path.relative_to(HOME)
    except ValueError:
        return path.parts[0] if path.parts else str(path)
    parts = rel.parts
    if len(parts) > 1 and parts[0] in {"Desktop", "Documents", "Downloads", "Sync"}:
        return f"{parts[0]}/{parts[1]}"
    return parts[0] if parts else str(path)


def file_id(path: Path) -> str:
    return hashlib.sha1(str(path).encode("utf-8", "replace")).hexdigest()[:8]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def strip_xml(text: str) -> str:
    text = re.sub(r"<w:tab[^>]*/>", " ", text)
    text = re.sub(r"<w:br[^>]*/>", "\n", text)
    text = re.sub(r"<[^>]+>", " ", text)
    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&apos;", "'")
    return re.sub(r"[ \t]+", " ", text).strip()


def extract_text(path: Path, limit: int = 2400) -> str:
    ext = path.suffix.lower()
    try:
        if ext in {".md", ".txt", ".tex"}:
            raw = path.read_text(encoding="utf-8", errors="replace")
            return raw[:limit]
        if ext == ".docx":
            with zipfile.ZipFile(path) as zf:
                raw = zf.read("word/document.xml").decode("utf-8", "replace")
            return strip_xml(raw)[:limit]
        if ext == ".odt":
            with zipfile.ZipFile(path) as zf:
                raw = zf.read("content.xml").decode("utf-8", "replace")
            return strip_xml(raw)[:limit]
        if ext == ".pdf":
            out = subprocess.run(
                ["pdftotext", "-f", "1", "-l", "2", "-q", str(path), "-"],
                capture_output=True, text=True, timeout=20, check=False,
            )
            return (out.stdout or "")[:limit]
    except (OSError, KeyError, zipfile.BadZipFile, subprocess.SubprocessError):
        return ""
    return ""


def title_of(path: Path) -> str:
    ext = path.suffix.lower()
    if ext in {".md", ".txt", ".tex"}:
        try:
            with path.open(encoding="utf-8", errors="replace") as fh:
                for _ in range(30):
                    line = fh.readline()
                    if not line:
                        break
                    s = line.strip()
                    if not s or s.startswith("---") or s.startswith("%"):
                        continue
                    if s.startswith("#"):
                        s = s.lstrip("#").strip()
                    return s[:120]
        except OSError:
            pass
    elif ext in {".docx", ".odt"}:
        text = extract_text(path, limit=300)
        first = text.splitlines()[0].strip() if text else ""
        if first:
            return first[:120]
    return path.stem[:120]


def iter_files(roots: list[Path]):
    seen = set()
    for root in roots:
        if not root.exists():
            continue
        for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
            dirnames[:] = sorted(d for d in dirnames if d not in SKIP_DIRS and not d.startswith(".Trash"))
            for name in sorted(filenames):
                path = Path(dirpath) / name
                if path.suffix.lower() not in EXTENSIONS or path.is_symlink():
                    continue
                try:
                    key = str(path.resolve())
                except OSError:
                    key = str(path)
                if key in seen:
                    continue
                seen.add(key)
                yield path


def scan(roots: list[Path]) -> list[dict]:
    rows = []
    for path in iter_files(roots):
        try:
            stat = path.stat()
        except OSError:
            continue
        rows.append({
            "id": file_id(path),
            "path": str(path),
            "root": root_label(path),
            "ext": path.suffix.lower().lstrip("."),
            "size": stat.st_size,
            "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d"),
            "sha256": sha256(path),
            "title": title_of(path).replace("\n", " "),
        })
    return rows


def mark_duplicates(rows: list[dict]) -> None:
    groups = defaultdict(list)
    for row in rows:
        groups[row["sha256"]].append(row)
    for group in groups.values():
        if len(group) < 2:
            continue
        canonical = min(
            group,
            key=lambda r: (
                0 if "/workspace/" in r["path"] else 1,
                len(Path(r["path"]).parts),
                -Path(r["path"]).stat().st_mtime,
            ),
        )
        for row in group:
            row["duplicate_of"] = "" if row is canonical else canonical["id"]


def load_decisions() -> dict[str, dict]:
    if not STATE.exists():
        return {}
    with STATE.open(newline="", encoding="utf-8") as fh:
        return {row["id"]: row for row in csv.DictReader(fh)}


def save_decisions(decisions: dict[str, dict]) -> None:
    fields = ["id", "path", "status", "note", "date"]
    with STATE.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in sorted(decisions.values(), key=lambda r: r["date"], reverse=True):
            writer.writerow({key: row.get(key, "") for key in fields})


def write_index(rows: list[dict]) -> None:
    fields = ["id", "path", "root", "ext", "size", "mtime", "sha256", "title", "duplicate_of"]
    with INDEX.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=fields)
        writer.writeheader()
        for row in sorted(rows, key=lambda r: (r["root"], r["path"])):
            writer.writerow({key: row.get(key, "") for key in fields})


def write_duplicates(rows: list[dict]) -> None:
    groups = defaultdict(list)
    for row in rows:
        if row.get("duplicate_of") or any(r.get("duplicate_of") == row["id"] for r in rows):
            groups[row["sha256"]].append(row)
    lines = [
        "# Duplicate groups",
        "",
        "Same SHA-256, different paths. Keep one canonical copy; mark the rest `duplicate`.",
        "",
    ]
    count = 0
    for digest, group in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        if len(group) < 2:
            continue
        count += 1
        lines.append(f"## Group {count} ({len(group)} copies, {group[0]['size']} bytes)")
        lines.append("")
        for row in sorted(group, key=lambda r: r["path"]):
            role = "canonical" if not row.get("duplicate_of") else f"copy of {row['duplicate_of']}"
            lines.append(f"- `{row['id']}` — {role} — `{row['path']}`")
        lines.append("")
    if count == 0:
        lines.append("No duplicates found.")
    DUPLICATES.write_text("\n".join(lines) + "\n", encoding="utf-8")


def suggest(path: str) -> str:
    if "/root_WIPS/mini-ISP" in path:
        return "Extract gates/numbers to vault; then archive"
    if "/root_WIPS/wifi_retail" in path:
        return "Compare with vault node1; extract evidence, compost draft"
    if "/root_WIPS/oldWorkInNeedofSalvage" in path:
        return "Salvage one artifact; compost the rest"
    if "/root_WIPS/LML_entry" in path or "/Documents/LML_entry" in path:
        return "Duplicate LML vault: keep one, compost the other"
    if "/zamzam" in path:
        return "Folded 2026-11-11; verify, then compost"
    if "/Desktop/ent" in path:
        return "Business note: move decision to consulting/ or vault"
    if "/Downloads" in path:
        return "Default compost unless it is a source"
    return "Preview, then keep/compost"


def untriaged(rows: list[dict], decisions: dict[str, dict]) -> list[dict]:
    out = [r for r in rows if r["id"] not in decisions and not r.get("duplicate_of")]
    return sorted(
        out,
        key=lambda r: (PRIORITY.get(r["root"], 9), r["mtime"]),
        reverse=False,
    )


def cell(text: str, limit: int = 70) -> str:
    return text.replace("|", "\\|").replace("\n", " ")[:limit]


def write_queue(rows: list[dict], decisions: dict[str, dict]) -> None:
    items = untriaged(rows, decisions)
    lines = [
        "# Digest queue",
        "",
        f"Generated {datetime.now().strftime('%Y-%m-%d %H:%M')} · {len(items)} untriaged of {len(rows)} scanned.",
        "",
        "Rule: one item per Green session. `--preview` before deciding. Default is compost.",
        "Mark with `--mark ID keep|compost|defer|moved`. Nothing is deleted by this script.",
        "",
        "| ID | Path | Modified | Title | Suggested |",
        "|---|---|---|---|---|",
    ]
    for row in items[:80]:
        lines.append(
            f"| `{row['id']}` | `{cell(row['path'], 90)}` | {row['mtime']} | {cell(row['title'])} | {suggest(row['path'])} |"
        )
    if len(items) > 80:
        lines.append(f"| … | {len(items) - 80} more | | | use `--next` |")
    QUEUE.write_text("\n".join(lines) + "\n", encoding="utf-8")


def load_index() -> list[dict]:
    if not INDEX.exists():
        return []
    with INDEX.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def find_row(rows: list[dict], ident: str) -> dict | None:
    for row in rows:
        if row["id"] == ident:
            return row
    return None


def cmd_scan(args) -> int:
    roots = [Path(p).expanduser() for p in args.roots.split(",")] if args.roots else list(DEFAULT_ROOTS)
    if args.include_workspace:
        roots.append(HOME / "workspace")
    rows = scan(roots)
    mark_duplicates(rows)
    decisions = load_decisions()
    write_index(rows)
    write_duplicates(rows)
    write_queue(rows, decisions)
    dupes = sum(1 for r in rows if r.get("duplicate_of"))
    print(f"scanned {len(rows)} files · {len(untriaged(rows, decisions))} untriaged · {dupes} duplicate copies")
    print(f"queue:    {QUEUE}")
    print(f"index:    {INDEX}")
    print(f"dupes:    {DUPLICATES}")
    return 0


def cmd_next(args) -> int:
    rows = load_index()
    if not rows:
        print("No index yet. Run: python3 scan.py")
        return 1
    decisions = load_decisions()
    items = untriaged(rows, decisions)[: args.count]
    if not items:
        print("Queue empty.")
        return 0
    for row in items:
        print(f"{row['id']}  {row['mtime']}  {row['path']}")
        print(f"      {row['title'][:100]}")
        print(f"      {suggest(row['path'])}")
    return 0


def cmd_preview(args) -> int:
    row = find_row(load_index(), args.id)
    if not row:
        print(f"Unknown id: {args.id}")
        return 1
    path = Path(row["path"])
    print(f"{path}\n{row['title']}\n{row['size']} bytes · modified {row['mtime']}\n")
    text = extract_text(path)
    if not text.strip():
        print("(no text extracted — open it with --open)")
        return 0
    print(text)
    return 0


def cmd_mark(args) -> int:
    row = find_row(load_index(), args.id)
    if not row:
        print(f"Unknown id: {args.id}")
        return 1
    decisions = load_decisions()
    decisions[args.id] = {
        "id": args.id,
        "path": row["path"],
        "status": args.status,
        "note": args.note or "",
        "date": datetime.now().strftime("%Y-%m-%d"),
    }
    save_decisions(decisions)
    print(f"{args.id} → {args.status} ({row['path']})")
    return 0


def cmd_open(args) -> int:
    row = find_row(load_index(), args.id)
    if not row:
        print(f"Unknown id: {args.id}")
        return 1
    subprocess.Popen(["xdg-open", row["path"]])
    print(row["path"])
    return 0


def cmd_stats(args) -> int:
    rows = load_index()
    if not rows:
        print("No index yet. Run: python3 scan.py")
        return 1
    decisions = load_decisions()
    print(f"total: {len(rows)} files")
    print("\nby root:")
    for name, count in Counter(r["root"] for r in rows).most_common():
        print(f"  {count:5d}  {name}")
    print("\nby type:")
    for name, count in Counter(r["ext"] for r in rows).most_common():
        print(f"  {count:5d}  {name}")
    print("\nby status:")
    statuses = Counter(d["status"] for d in decisions.values())
    for name in STATUSES:
        print(f"  {statuses.get(name, 0):5d}  {name}")
    print(f"  {sum(1 for r in rows if r.get('duplicate_of')):5d}  duplicate copies")
    print(f"  {sum(1 for r in rows if r['id'] not in decisions and not r.get('duplicate_of')):5d}  untriaged")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--roots", help="comma-separated roots (default: Desktop, Documents, Downloads, Sync)")
    parser.add_argument("--include-workspace", action="store_true", help="also scan ~/workspace")
    parser.add_argument("--next", dest="count", type=int, default=None, help="show next N untriaged")
    parser.add_argument("--preview", dest="preview_id", metavar="ID", help="print the first page of one item")
    parser.add_argument("--mark", nargs=2, metavar=("ID", "STATUS"), help="record a decision")
    parser.add_argument("--note", help="note for --mark")
    parser.add_argument("--open", dest="open_id", metavar="ID", help="open one item")
    parser.add_argument("--stats", action="store_true", help="counts by root, type, status")
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    if args.mark:
        args.id, args.status = args.mark
        if args.status not in STATUSES:
            parser.error(f"status must be one of: {', '.join(STATUSES)}")
        return cmd_mark(args)
    if args.preview_id:
        args.id = args.preview_id
        return cmd_preview(args)
    if args.open_id:
        args.id = args.open_id
        return cmd_open(args)
    if args.stats:
        return cmd_stats(args)
    if args.count is not None:
        return cmd_next(args)
    return cmd_scan(args)


if __name__ == "__main__":
    sys.exit(main())
