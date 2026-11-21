#!/usr/bin/env python3
"""Find Slack bot mentions and send confirmed webhook responses."""

from __future__ import annotations

import argparse
import importlib.util
import json
import re
import sqlite3
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
        aliases = {}
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
            for name in filter(None, names):
                aliases.setdefault(name.casefold(), set()).add(row["ID"])
    if channel.channel_id != config["SLACK_CHANNEL_ID"] or channel.name != config["SLACK_CHANNEL_NAME"]:
        raise SendSlackError(
            f"Archive channel {channel.name} ({channel.channel_id}) does not match configured channel"
        )
    return channel, user_names, aliases


# Leave Slack markup, URLs, and inline/fenced code intact.
MENTION_TOKEN = re.compile(
    r"```[\s\S]*?```|`[^`\n]*`|<[^>\n]+>|https?://[^\s]+|"
    r"(?<![\w@.+-])@([\w-]+(?:\.[\w-]+)*)"
)


def resolve_mentions(text, aliases):
    def replace(match):
        name = match.group(1)
        if name is None:
            return match.group()
        ids = aliases.get(name.casefold(), set())
        if len(ids) != 1:
            raise SendSlackError(f"@{name} matched {len(ids)} archive users; expected one")
        return f"<@{next(iter(ids))}>"

    return MENTION_TOKEN.sub(replace, text)


def read_manifest(path: Path = MANIFEST_PATH) -> set[tuple[str, str, str]]:
    if not path.exists():
        return set()
    keys = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            record = json.loads(line)
            keys.add((record["archive_path"], record["channel_id"], record["message_ts"]))
    return keys


def find_candidates(ingest, database, raw_dir, config, validated):
    channel, user_names, aliases = validated
    bot_name = config["SLACK_BOT_NAME"].removeprefix("@").casefold()
    bot_ids = aliases.get(bot_name, set())
    if len(bot_ids) != 1:
        raise SendSlackError(f"Configured Slack bot name matched {len(bot_ids)} users; expected one")
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
            "author": ingest.message_author(user_names, trigger),
            "messages": [
                {"ts": m.message_ts, "author": ingest.message_author(user_names, m), "text": m.text}
                for m in group.messages
            ],
        })
    return candidates


def append_manifest(record: dict, path: Path = MANIFEST_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def send_webhook(url: str, text: str, thread_ts: str | None = None) -> None:
    body = {"text": text}
    if thread_ts:
        body["thread_ts"] = thread_ts
    payload = json.dumps(body, ensure_ascii=False)
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
    for command in ("candidates", "send", "post"):
        sub = subparsers.add_parser(command)
        sub.add_argument("--database", type=Path)
        sub.add_argument("--raw-dir", type=Path, default=ROOT / "raw")
    for command in ("send", "post"):
        sub = subparsers.choices[command]
        sub.add_argument("--message-ts", required=command == "send",
                         help="Archived message to reply to in its thread")
        sub.add_argument("--message", required=True)
        sub.add_argument("--confirm", action="store_true")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    try:
        if args.command != "candidates" and not args.confirm:
            raise SendSlackError("Sending requires --confirm after conversational confirmation")
        ingest = load_ingest_module()
        config = load_config()
        database = discover_database(ingest, args.raw_dir, args.database)
        validated = validate_channel(ingest, database, config)
        channel, _, aliases = validated
        if args.command in {"candidates", "send"}:
            candidates = find_candidates(ingest, database, args.raw_dir, config, validated)
            if args.command == "candidates":
                print(json.dumps(candidates, ensure_ascii=False, indent=2))
                return 0
            selected = next((item for item in candidates if item["message_ts"] == args.message_ts), None)
            if selected is None:
                raise SendSlackError("Message is not an unanswered bot candidate")
            thread_ts = selected["thread_ts"] or args.message_ts
        else:
            handled = read_manifest()
            thread_ts = None
            if args.message_ts is not None:
                messages = ingest.fetch_canonical_messages(database, channel.channel_id)
                target = next((m for m in messages if m.message_ts == args.message_ts), None)
                if target is None:
                    raise SendSlackError("Reply target is absent from the configured channel")
                if ingest.message_key(target, args.raw_dir) in handled:
                    raise SendSlackError("Reply target already has a recorded response")
                thread_ts = target.thread_ts or target.message_ts
        if not args.message.strip():
            raise SendSlackError("Message text is empty")
        text = resolve_mentions(args.message, aliases)
        record = {
            "archive_path": ingest.archive_identity(database, args.raw_dir),
            "channel_id": channel.channel_id,
            "message_ts": args.message_ts,
            "thread_ts": thread_ts,
            "command": args.command,
            "answer_sha256": hashlib.sha256(text.encode()).hexdigest(),
        }
        send_webhook(config["SLACK_WEBHOOK_URL"], text, thread_ts)
        record["sent_at"] = datetime.now(timezone.utc).isoformat()
        try:
            append_manifest(record)
        except OSError:
            raise SendSlackError("Slack accepted the message but manifest recording failed. Do not resend.")
        print(json.dumps({"ok": True, "message_ts": args.message_ts}))
        return 0
    except (RuntimeError, ValueError, KeyError, OSError, sqlite3.Error) as error:
        print(json.dumps({"ok": False, "error": str(error)}))
        return 1


if __name__ == "__main__":
    sys.exit(main())
