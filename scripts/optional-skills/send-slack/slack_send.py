#!/usr/bin/env python3
"""Find Slack bot mentions and send confirmed webhook responses."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import stat
import subprocess
import sys
import hashlib
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
INGEST_PATHS = (
    ROOT / "skills/ingest-slack/slack_ingest.py",
    ROOT / "scripts/optional-skills/ingest-slack/slack_ingest.py",
)
CONFIG_PATH = ROOT / ".llm-wiki/slack/send-slack.env"
MANIFEST_PATH = ROOT / ".llm-wiki/slack/send-slack-manifest.jsonl"
MENTION_RE = re.compile(r"<@([A-Z0-9]+)>")


def load_ingest_module():
    ingest_path = next((path for path in INGEST_PATHS if path.is_file()), None)
    if ingest_path is None:
        raise RuntimeError("Unable to locate the installed Slackdump helper")
    spec = importlib.util.spec_from_file_location("slack_ingest", ingest_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("Unable to load the Slackdump helper")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class SendSlackError(RuntimeError):
    pass


def load_config(path: Path = CONFIG_PATH) -> dict[str, str]:
    if not path.is_file():
        raise SendSlackError(f"Configuration file not found: {path}")
    if stat.S_IMODE(path.stat().st_mode) & 0o077:
        raise SendSlackError("Configuration file must have mode 600")

    values: dict[str, str] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        key, separator, value = line.partition("=")
        if separator:
            values[key.strip()] = value.strip().strip('"').strip("'")

    required = (
        "SLACK_CHANNEL_ID",
        "SLACK_CHANNEL_NAME",
        "SLACK_BOT_NAME",
        "SLACK_WEBHOOK_URL",
    )
    if any(not values.get(key) for key in required):
        raise SendSlackError(
            "Configuration must define channel ID, channel name, bot name, and webhook URL"
        )
    if not values["SLACK_WEBHOOK_URL"].startswith("https://hooks.slack.com/"):
        raise SendSlackError("SLACK_WEBHOOK_URL must be a Slack HTTPS webhook URL")
    return values


def discover_database(ingest, raw_dir: Path, explicit: Path | None) -> Path:
    paths = [explicit] if explicit else ingest.find_slackdump_databases(raw_dir)
    if len(paths) != 1:
        raise SendSlackError("Expected exactly one Slackdump SQLite database")
    return paths[0]


def validate_channel(ingest, database: Path, config: dict[str, str]):
    with ingest.open_database(database) as connection:
        ingest.validate_slackdump_database(connection)
        ingest.validate_schema(connection)
        channel = ingest.resolve_archive_channel(connection)
        user_names = ingest.load_user_names(connection)
        bot_ids = []
        bot_name = config["SLACK_BOT_NAME"].removeprefix("@").casefold()
        for row in connection.execute("SELECT ID, USERNAME, DATA FROM S_USER"):
            data = ingest.parse_json_object(row["DATA"])
            profile = data.get("profile", {})
            names = {
                row["USERNAME"],
                data.get("name"),
                data.get("real_name"),
                profile.get("display_name"),
                profile.get("real_name"),
            }
            if any(name and name.casefold() == bot_name for name in names):
                bot_ids.append(row["ID"])
    if channel.channel_id != config["SLACK_CHANNEL_ID"] or channel.name != config["SLACK_CHANNEL_NAME"]:
        raise SendSlackError(
            f"Archive channel {channel.name} ({channel.channel_id}) does not match configured channel"
        )
    if len(bot_ids) != 1:
        raise SendSlackError(
            f"Configured Slack bot name matched {len(bot_ids)} users; expected exactly one"
        )
    return channel, user_names, {bot_ids[0]}


def read_manifest(path: Path = MANIFEST_PATH) -> set[tuple[str, str, str]]:
    if not path.exists():
        return set()
    keys = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            keys.add((record["archive_path"], record["channel_id"], record["message_ts"]))
    return keys


def find_candidates(ingest, database: Path, raw_dir: Path, config: dict[str, str]):
    channel, user_names, bot_ids = validate_channel(ingest, database, config)
    messages = ingest.fetch_canonical_messages(database, channel.channel_id)
    handled = read_manifest()
    groups = ingest.group_messages(messages)
    candidates = []
    for group in groups:
        matches = []
        for message in group.messages:
            if message.data.get("subtype") in {"channel_join", "channel_leave"}:
                continue
            if bot_ids.intersection(MENTION_RE.findall(message.text)):
                matches.append(message)
        if not matches:
            continue
        trigger = matches[-1]
        key = ingest.message_key(trigger, raw_dir)
        if key in handled:
            continue
        candidates.append({
            "archive_path": key[0],
            "channel_id": channel.channel_id,
            "channel_name": channel.name,
            "message_ts": trigger.message_ts,
            "thread_ts": group.thread_ts,
            "author": user_names.get(trigger.data.get("user"), trigger.data.get("user", "<unknown>")),
            "messages": [
                {"ts": m.message_ts, "author": user_names.get(m.data.get("user"), m.data.get("user", "<unknown>")), "text": m.text}
                for m in group.messages
            ],
        })
    return candidates


def append_manifest(record: dict, path: Path = MANIFEST_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def send_webhook(url: str, text: str) -> None:
    payload = json.dumps({"text": text}, ensure_ascii=False)
    try:
        subprocess.run(
            ["curl", "--fail-with-body", "--silent", "--show-error", "-X", "POST",
             "-H", "Content-type: application/json", "--data", payload, url],
            check=True, capture_output=True, text=True, timeout=30,
        )
    except subprocess.CalledProcessError as error:
        if error.returncode == 6:
            detail = "DNS lookup failed"
        elif error.returncode == 28:
            detail = "request timed out"
        else:
            detail = "webhook rejected the request"
        raise SendSlackError(f"Slack webhook delivery failed: {detail}") from error
    except subprocess.TimeoutExpired as error:
        raise SendSlackError("Slack webhook delivery failed: request timed out") from error
    except OSError as error:
        raise SendSlackError("Slack webhook delivery failed: curl is unavailable") from error


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("candidates", "send"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--database", type=Path)
        sub.add_argument("--raw-dir", type=Path, default=ROOT / "raw")
    send = subparsers.choices["send"]
    send.add_argument("--message-ts", required=True)
    send.add_argument("--message", required=True)
    send.add_argument("--confirm", action="store_true")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command == "send" and not args.confirm:
            raise SendSlackError("Sending requires --confirm after conversational confirmation")
        ingest = load_ingest_module()
        config = load_config()
        database = discover_database(ingest, args.raw_dir, args.database)
        candidates = find_candidates(ingest, database, args.raw_dir, config)
        if args.command == "candidates":
            print(json.dumps(candidates, ensure_ascii=False, indent=2))
            return 0
        selected = next((item for item in candidates if item["message_ts"] == args.message_ts), None)
        if selected is None:
            raise SendSlackError("Message is not an unanswered bot candidate")
        send_webhook(config["SLACK_WEBHOOK_URL"], args.message)
        append_manifest({**{key: selected[key] for key in ("archive_path", "channel_id", "message_ts", "thread_ts")}, "sent_at": datetime.now(timezone.utc).isoformat(), "answer_sha256": hashlib.sha256(args.message.encode()).hexdigest()})
        print(json.dumps({"ok": True, "message_ts": args.message_ts}))
        return 0
    except SendSlackError as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
