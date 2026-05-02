#!/usr/bin/env python3
"""Guard LLM Wiki raw ingests against duplicate source files.

The manifest is JSON Lines at `.llm-wiki/ingest-manifest.jsonl`: one JSON
object per successful ingest record. The guard starts with deterministic hashes:
a byte SHA-256 for every file, plus a normalized text SHA-256 for plain-text
files.
"""

import argparse
import hashlib
import json
import re
import unicodedata
from collections.abc import Iterator
from datetime import datetime, timezone
from pathlib import Path

CHUNK_SIZE = 1024 * 1024
MANIFEST_PATH = Path(".llm-wiki") / "ingest-manifest.jsonl"
RAW_DIR = Path("raw")
IGNORED_RAW_FILES = {".gitkeep", ".DS_Store"}
PLAIN_TEXT_SUFFIXES = {".txt", ".md", ".csv", ".json", ".jsonl", ".html", ".htm"}


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(Path.cwd().resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def is_plain_text_file(path: Path) -> bool:
    return path.suffix.lower() in PLAIN_TEXT_SUFFIXES


def normalize_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = text.casefold()
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def text_sha256_file(path: Path) -> str:
    text = path.read_text(encoding="utf-8", errors="replace")
    return sha256_text(normalize_text(text))


def should_ignore_raw_file(path: Path) -> bool:
    return path.name in IGNORED_RAW_FILES


def iter_files(root: Path) -> Iterator[Path]:
    if not root.exists():
        return

    for path in sorted(root.rglob("*")):
        if path.is_file() and not should_ignore_raw_file(path):
            yield path


def audit_command(args: argparse.Namespace) -> int:
    records = read_jsonl(args.manifest)
    known_count = 0
    new_count = 0
    files = []

    for path in iter_files(args.raw_dir):
        candidate = build_file_record(path)
        duplicate = find_duplicate(records, candidate)

        if duplicate is not None:
            kind, match = duplicate
            status = "known"
            known_count += 1
        else:
            kind = None
            status = "new"
            new_count += 1

        file_result = {
            "status": status,
            "source_path": candidate["source_path"],
            "byte_sha256": candidate["byte_sha256"],
            "size_bytes": candidate["size_bytes"],
        }

        if "text_sha256" in candidate:
            file_result["text_sha256"] = candidate["text_sha256"]

        if kind is not None:
            file_result["duplicate_kind"] = kind

        files.append(file_result)

    print_json(
        {
            "raw_dir": args.raw_dir.as_posix(),
            "known_count": known_count,
            "new_count": new_count,
            "file_count": known_count + new_count,
            "files": files,
        }
    )
    return 0


def index_existing_command(args: argparse.Namespace) -> int:
    records = read_jsonl(args.manifest)
    written = []
    skipped = []

    for path in iter_files(args.raw_dir):
        candidate = build_file_record(path)
        duplicate = find_duplicate(records, candidate)

        if duplicate is not None:
            kind, match = duplicate
            skipped.append(
                {
                    "duplicate_kind": kind,
                    "match": match,
                    "candidate": candidate,
                }
            )
            continue

        candidate["ingested_at"] = utc_now_iso()
        append_jsonl(args.manifest, candidate)

        records.append(candidate)
        written.append(candidate)

    print_json(
        {
            "status": "indexed",
            "raw_dir": args.raw_dir.as_posix(),
            "written_count": len(written),
            "skipped_count": len(skipped),
            "written": written,
            "skipped": skipped,
        }
    )

    return 0


def print_json(value: dict) -> None:
    print(json.dumps(value, sort_keys=True))


def read_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []

    records = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue

            try:
                records.append(json.loads(line))
            except json.JSONDecodeError as error:
                raise SystemExit(
                    f"ingest_guard: invalid JSON in {path} "
                    f"on line {line_number}: {error.msg}"
                ) from error

    return records


def append_jsonl(path: Path, record: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, sort_keys=True) + "\n")


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()

    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)

    return digest.hexdigest()


def build_file_record(path: Path) -> dict:
    record = {
        "schema_version": 1,
        "source_path": display_path(path),
        "size_bytes": path.stat().st_size,
        "byte_sha256": sha256_file(path),
    }

    if is_plain_text_file(path):
        record["text_sha256"] = text_sha256_file(path)

    return record


def require_file(path: Path) -> Path:
    if not path.exists():
        raise SystemExit(f"ingest_guard: file does not exist: {path}")

    if not path.is_file():
        raise SystemExit(f"ingest_guard: path is not a file: {path}")

    return path


def hash_command(args: argparse.Namespace) -> int:
    path = require_file(args.path)

    record = build_file_record(path)
    print_json(record)
    return 0


def find_matching_byte_hash(records: list[dict], byte_sha256: str) -> dict | None:
    for record in records:
        if record.get("byte_sha256") == byte_sha256:
            return record

    return None


def find_matching_text_hash(records: list[dict], text_sha256: str) -> dict | None:
    for record in records:
        if record.get("text_sha256") == text_sha256:
            return record

    return None


def duplicate_result(kind: str, match: dict, candidate: dict) -> dict:
    return {
        "status": "duplicate",
        "duplicate_kind": kind,
        "match": match,
        "candidate": candidate,
    }


def find_duplicate(records: list[dict], candidate: dict) -> tuple[str, dict] | None:

    match = find_matching_byte_hash(records, candidate["byte_sha256"])

    if match is not None:
        return ("byte", match)

    if "text_sha256" in candidate:
        match = find_matching_text_hash(records, candidate["text_sha256"])
        if match is not None:
            return ("text", match)

    return None


def record_command(args: argparse.Namespace) -> int:
    path = require_file(args.path)
    candidate = build_file_record(path)
    records = read_jsonl(args.manifest)

    duplicate = find_duplicate(records, candidate)
    if duplicate is not None:
        kind, match = duplicate
        print_json(duplicate_result(kind, match, candidate))
        return 1

    candidate["ingested_at"] = utc_now_iso()

    append_jsonl(args.manifest, candidate)
    print_json(candidate)
    return 0


def check_command(args: argparse.Namespace) -> int:
    path = require_file(args.path)
    candidate = build_file_record(path)
    records = read_jsonl(args.manifest)

    duplicate = find_duplicate(records, candidate)
    if duplicate is not None:
        kind, match = duplicate
        print_json(duplicate_result(kind, match, candidate))
        return 1

    print_json(
        {
            "status": "new",
            "candidate": candidate,
        },
    )
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ingest_guard",
        description="Guard LLM Wiki raw ingests against duplicate source files",
    )

    parser.add_argument(
        "--manifest",
        type=Path,
        default=MANIFEST_PATH,
        help="path to the manifest JSONL file",
    )
    parser.add_argument(
        "--raw-dir", type=Path, default=RAW_DIR, help="raw directory to inspect"
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    hash_parser = subparsers.add_parser(
        "hash", help="compute the SHA-256 hash of a file"
    )
    hash_parser.add_argument(
        "path", type=Path, help="file to hash, such as raw/README.md"
    )
    hash_parser.set_defaults(func=hash_command)

    record_parser = subparsers.add_parser(
        "record", help="append a successful ingest record to the manifest"
    )
    record_parser.add_argument(
        "path", type=Path, help="file to record, such as raw/README.md"
    )
    record_parser.set_defaults(func=record_command)

    check_parser = subparsers.add_parser(
        "check", help="check a file against the manifest for duplicates"
    )
    check_parser.add_argument(
        "path", type=Path, help="file to check, such as raw/README.md"
    )
    check_parser.set_defaults(func=check_command)

    audit_parser = subparsers.add_parser(
        "audit", help="inspect raw/ against the manifest without writing"
    )
    audit_parser.set_defaults(func=audit_command)

    index_existing_parser = subparsers.add_parser(
        "index-existing", help="backfill the manifest with existing files in raw/"
    )
    index_existing_parser.set_defaults(func=index_existing_command)

    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
