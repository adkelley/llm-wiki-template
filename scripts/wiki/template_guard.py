#!/usr/bin/env python3
"""Guard managed setup templates against overwriting user edits.

The manifest is JSON Lines at `.llm-wiki/template-manifest.jsonl`: one JSON
object per template copy or update performed by a setup script. The guard uses
the same SHA-256 file hashing helpers as `ingest_guard.py`, but keeps template
update policy separate from raw ingest duplicate detection.
"""

import argparse
from pathlib import Path

from ingest_guard import (
    append_jsonl,
    build_file_record,
    display_path,
    print_json,
    read_jsonl,
    require_file,
    utc_now_iso,
)

MANIFEST_PATH = Path(".llm-wiki") / "template-manifest.jsonl"


def same_byte_hash(left: dict, right: dict) -> bool:
    return left.get("byte_sha256") == right.get("byte_sha256")


def latest_template_record(records: list[dict], target_path: Path) -> dict | None:
    target = display_path(target_path)

    for record in reversed(records):
        if (
            record.get("record_type") == "managed_template"
            and record.get("target_path") == target
        ):
            return record

    return None


def build_template_record(template_path: Path, target_path: Path) -> dict:
    record = build_file_record(template_path)
    record["record_type"] = "managed_template"
    record["template_path"] = display_path(template_path)
    record["target_path"] = display_path(target_path)
    record["installed_at"] = utc_now_iso()
    return record


def status_command(args: argparse.Namespace) -> int:
    template = require_file(args.template)
    target = args.target
    template_record = build_file_record(template)
    records = read_jsonl(args.manifest)
    latest = latest_template_record(records, target)

    if not target.exists():
        print_json(
            {
                "status": "missing",
                "target_path": display_path(target),
                "template": template_record,
                "latest": latest,
            }
        )
        return 0

    target = require_file(target)
    target_record = build_file_record(target)

    if same_byte_hash(target_record, template_record):
        if latest is None or not same_byte_hash(latest, template_record):
            print_json(
                {
                    "status": "record",
                    "target": target_record,
                    "template": template_record,
                    "latest": latest,
                }
            )
            return 0

        print_json(
            {
                "status": "current",
                "target": target_record,
                "template": template_record,
                "latest": latest,
            }
        )
        return 0

    if latest is not None and same_byte_hash(target_record, latest):
        print_json(
            {
                "status": "replace",
                "target": target_record,
                "template": template_record,
                "latest": latest,
            }
        )
        return 0

    print_json(
        {
            "status": "preserve",
            "target": target_record,
            "template": template_record,
            "latest": latest,
        }
    )
    return 0


def record_command(args: argparse.Namespace) -> int:
    template = require_file(args.template)
    record = build_template_record(template, args.target)
    append_jsonl(args.manifest, record)
    print_json(record)
    return 0


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="template_guard",
        description="Guard managed setup templates against overwriting user edits",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=MANIFEST_PATH,
        help="path to the managed-template manifest JSONL file",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    status_parser = subparsers.add_parser(
        "status", help="decide whether a managed template target should be copied"
    )
    status_parser.add_argument(
        "--template",
        type=Path,
        required=True,
        help="source template file, such as scripts/codex/AGENT.md",
    )
    status_parser.add_argument(
        "--target",
        type=Path,
        required=True,
        help="installed target file, such as AGENT.md",
    )
    status_parser.set_defaults(func=status_command)

    record_parser = subparsers.add_parser(
        "record", help="record the template hash installed for a target"
    )
    record_parser.add_argument(
        "--template",
        type=Path,
        required=True,
        help="source template file, such as scripts/codex/AGENT.md",
    )
    record_parser.add_argument(
        "--target",
        type=Path,
        required=True,
        help="installed target file, such as AGENT.md",
    )
    record_parser.set_defaults(func=record_command)

    return parser


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
