import argparse
import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class ArchiveInspection:
    database_path: Path
    archive_root: Path
    has_uploads: bool
    channels: list[dict[str, str]]
    message_count: int
    thread_parent_count: int
    reply_count: int


@dataclass(frozen=True)
class SlackMessage:
    archive_path: Path
    chunk_id: int
    session_id: int
    chunk_type_id: int
    channel_id: str
    message_ts: str
    thread_ts: str | None
    parent_id: int | None
    is_parent: bool
    text: str
    data: dict


@dataclass(frozen=True)
class ThreadGroup:
    thread_ts: str | None
    messages: list[SlackMessage]
    reactivated: bool = False


@dataclass(frozen=True)
class SlackChannel:
    channel_id: str
    name: str


SLACK_MENTION_REGEX = re.compile(r"<@([A-Z0-9]+)>")

REQUIRED_TABLES = (
    "MESSAGE",
    "CHANNEL",
    "S_USER",
    "CHUNK",
    "TYPES",
)

REQUIRED_COLUMNS = {
    "CHANNEL": {"ID", "NAME"},
    "MESSAGE": {
        "ID",
        "CHUNK_ID",
        "CHANNEL_ID",
        "TS",
        "PARENT_ID",
        "THREAD_TS",
        "IS_PARENT",
        "TXT",
        "DATA",
    },
}


class InvalidSlackdumpDatabaseError(RuntimeError):
    """Raised when a SQLite file is not a compatible Slackdump archive."""


# ---------------------------------------------------------------------------
# Parsing and formatting helpers
# ---------------------------------------------------------------------------


def message_payload_hash(message: SlackMessage) -> str:
    serialized = json.dumps(
        message.data,
        sort_keys=True,
        separators=(",", ":"),
    )

    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def parse_json_object(raw_data: bytes | str | None) -> dict:
    if not raw_data:
        return {}

    if isinstance(raw_data, bytes):
        raw_data = raw_data.decode("utf-8", errors="replace")

    try:
        value = json.loads(raw_data)
    except (TypeError, json.JSONDecodeError):
        return {}

    return value if isinstance(value, dict) else {}


def load_user_names(connection: sqlite3.Connection) -> dict[str, str]:
    names: dict[str, str] = {}

    for row in connection.execute("SELECT ID, USERNAME, DATA FROM S_USER"):
        data = parse_json_object(row["DATA"])
        profile = data.get("profile", {})

        name = (
            profile.get("display_name")
            or data.get("real_name")
            or data.get("name")
            or row["USERNAME"]
            or row["ID"]
        )
        names[row["ID"]] = name

    return names


def archive_identity(
    archive_path: Path,
    raw_dir: Path,
) -> str:
    try:
        return archive_path.resolve().relative_to(raw_dir.resolve()).as_posix()
    except ValueError:
        return archive_path.resolve().as_posix()


def message_key(message: SlackMessage, raw_dir: Path) -> tuple[str, str, str]:
    return (
        archive_identity(message.archive_path, raw_dir),
        message.channel_id,
        message.message_ts,
    )


def load_manifest_records(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []

    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.strip():
            records.append(json.loads(line))
    return records


def load_ingested_message_keys(path: Path) -> set[tuple[str, str, str]]:
    keys = set()

    for record in load_manifest_records(path):
        keys.add(
            (
                record["archive_path"],
                record["channel_id"],
                record["message_ts"],
            )
        )

    return keys


def archive_state_dir(database_path: Path) -> Path:
    return Path(".llm-wiki") / "slack" / database_path.resolve().parent.name


def decisions_path_from_database(database_path: Path) -> Path:
    return archive_state_dir(database_path) / "decisions.jsonl"


def rules_path_from_database(database_path: Path) -> Path:
    return archive_state_dir(database_path) / "rules.jsonl"


def load_skipped_message_keys(
    database_path: Path,
    raw_dir: Path,
) -> set[tuple[str, str, str]]:
    keys = set()
    for record in load_manifest_records(decisions_path_from_database(database_path)):
        if (
            record.get("decision") == "skip"
            and record.get("scope", "message") == "message"
        ):
            keys.add(
                (record["archive_path"], record["channel_id"], record["message_ts"])
            )
    return keys


def load_archive_ingestion_state(
    database_path: Path, raw_dir: Path
) -> tuple[set[tuple[str, str, str]], set[tuple[str, str, str]], list[dict[str, str]]]:
    """Load all mutable discovery state for one archive in one place."""
    ingested = load_ingested_message_keys(
        manifest_path_from_database(database_path, raw_dir)
    )
    skipped = load_skipped_message_keys(database_path, raw_dir)
    rules = load_manifest_records(rules_path_from_database(database_path))
    return ingested, skipped, rules


def message_matches_rules(message: SlackMessage, rules: list[dict[str, str]]) -> bool:
    for rule in rules:
        if rule.get("decision") != "skip":
            continue
        if rule.get("scope") == "subtype" and rule.get("subtype") == message.data.get(
            "subtype"
        ):
            if not rule.get("channel_id") or rule["channel_id"] == message.channel_id:
                return True
        if rule.get("scope") == "user" and rule.get("user_id") == message.data.get(
            "user"
        ):
            if not rule.get("channel_id") or rule["channel_id"] == message.channel_id:
                return True
    return False


def format_slack_timestamp(timestamp: str) -> str:
    seconds = float(timestamp)
    return (
        datetime.fromtimestamp(
            seconds,
            tz=timezone.utc,
        )
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def resolve_author_name(connection: sqlite3.Connection, author_id: str | None) -> str:
    if not author_id:
        return "<unknown>"

    row = connection.execute(
        """
        SELECT ID, USERNAME, DATA
        FROM S_USER
        WHERE ID = ?
        LIMIT 1
        """,
        (author_id,),
    ).fetchone()

    if row is None:
        return author_id

    data = parse_json_object(row["DATA"])

    return (
        data.get("profile", {}).get("display_name")
        or data.get("real_name")
        or data.get("name")
        or row["USERNAME"]
        or author_id
    )


def author_name_from_map(user_names: dict[str, str], author_id: str | None) -> str:
    if not author_id:
        return "<unknown>"
    return user_names.get(author_id, author_id)


def resolve_archive_channel(
    connection: sqlite3.Connection, channel_id: str | None = None
) -> SlackChannel:
    rows = connection.execute(
        """
        SELECT DISTINCT M.CHANNEL_ID AS channel_id
        FROM MESSAGE AS M
        WHERE M.CHANNEL_ID IS NOT NULL
          AND (? IS NULL OR M.CHANNEL_ID = ?)
        ORDER BY M.CHANNEL_ID
        """,
        (channel_id, channel_id),
    ).fetchall()

    if not rows:
        raise InvalidSlackdumpDatabaseError(
            "The Slackdump database contains no messages with a channel ID."
        )

    if len(rows) > 1:
        channel_ids = ", ".join(row["channel_id"] for row in rows)
        raise InvalidSlackdumpDatabaseError(
            f"Expected one channel per Slackdump database, found multiple: "
            f"{channel_ids}"
        )

    channel_id = rows[0]["channel_id"]

    row = connection.execute(
        """
        SELECT ID, NAME
        FROM CHANNEL
        WHERE ID = ?
        LIMIT 1
        """,
        (channel_id,),
    ).fetchone()

    if row is None:
        raise InvalidSlackdumpDatabaseError(
            f"Channel {channel_id} is referenced by messages but missing"
            f" from the CHANNEL table."
        )

    return SlackChannel(channel_id=row["ID"], name=row["NAME"] or row["ID"])


def resolve_slack_mentions(
    text: str,
    user_names: dict[str, str] | None = None,
) -> str:
    user_names = user_names or {}

    def replace(match: re.Match[str]) -> str:
        user_id = match.group(1)
        return f"@{user_names.get(user_id, user_id)}"

    return SLACK_MENTION_REGEX.sub(replace, text)


# ---------------------------------------------------------------------------
# Message queries and grouping
# ---------------------------------------------------------------------------


def find_uningested_messages(
    messages: list[SlackMessage],
    ingested_keys: set[tuple[str, str, str]],
    raw_dir: Path,
    skipped_keys: set[tuple[str, str, str]] | None = None,
    rules: list[dict[str, str]] | None = None,
) -> list[SlackMessage]:
    skipped_keys = skipped_keys or set()
    rules = rules or []
    return [
        message
        for message in messages
        if message_key(message, raw_dir) not in ingested_keys
        and message_key(message, raw_dir) not in skipped_keys
        and not message_matches_rules(message, rules)
    ]


def fetch_messages(
    database_path: Path, channel_id: str | None = None
) -> list[SlackMessage]:
    query = """
        SELECT
            M.CHANNEL_ID AS channel_id,
            M.CHUNK_ID AS chunk_id,
            C.SESSION_ID AS session_id,
            C.TYPE_ID AS chunk_type_id,
            M.TS AS message_ts,
            M.THREAD_TS AS thread_ts,
            M.PARENT_ID AS parent_id,
            M.IS_PARENT AS is_parent,
            M.TXT AS text,
            M.DATA AS raw_data
        FROM MESSAGE AS M
        JOIN CHUNK AS C ON C.ID = M.CHUNK_ID
    """
    params: tuple[str, ...] = ()
    if channel_id is not None:
        query += " WHERE M.CHANNEL_ID = ?"
        params = (channel_id,)
    query += " ORDER BY M.CHANNEL_ID, M.TS, M.ID"

    messages = []
    with open_database(database_path) as connection:
        for row in connection.execute(query, params):
            messages.append(
                SlackMessage(
                    archive_path=database_path,
                    chunk_id=row["chunk_id"],
                    session_id=row["session_id"],
                    chunk_type_id=row["chunk_type_id"],
                    channel_id=row["channel_id"],
                    message_ts=row["message_ts"],
                    thread_ts=row["thread_ts"],
                    parent_id=row["parent_id"],
                    is_parent=bool(row["is_parent"]),
                    text=row["text"] or "",
                    data=parse_json_object(row["raw_data"]),
                )
            )
    return messages


def fetch_canonical_messages(
    database_path: Path, channel_id: str | None = None
) -> list[SlackMessage]:
    """Return the latest stored row for each logical Slack message.

    Slackdump may store the same message in multiple sessions or chunk types.
    The latest session/chunk wins. For thread broadcasts, prefer the thread
    copy over the channel-history copy when both rows have the same provenance.
    """

    messages = fetch_messages(database_path, channel_id=channel_id)
    canonical: dict[tuple[str, str], SlackMessage] = {}

    def rank(message: SlackMessage) -> tuple[int, int, int]:
        is_thread_broadcast = message.data.get("subtype") == "thread_broadcast"
        prefer_thread_copy = int(is_thread_broadcast and message.chunk_type_id == 1)
        return (message.session_id, message.chunk_id, prefer_thread_copy)

    for message in messages:
        key = (message.channel_id, message.message_ts)
        previous = canonical.get(key)
        if previous is None or rank(message) > rank(previous):
            canonical[key] = message

    return sorted(
        canonical.values(),
        key=lambda message: (message.channel_id, message.message_ts),
    )


def group_messages(messages: list[SlackMessage]) -> list[ThreadGroup]:
    groups_by_key: dict[tuple[str, str], ThreadGroup] = {}
    ordered_groups: list[ThreadGroup] = []

    for message in messages:
        if message.thread_ts is not None:
            key = (message.channel_id, message.thread_ts)
            group_thread_ts = message.thread_ts
        else:
            key = (message.channel_id, message.message_ts)
            group_thread_ts = None

        group = groups_by_key.get(key)
        if group is None:
            group = ThreadGroup(thread_ts=group_thread_ts, messages=[])
            groups_by_key[key] = group
            ordered_groups.append(group)

        group.messages.append(message)

    return ordered_groups


def find_reactivated_thread_groups(
    messages: list[SlackMessage],
    ingested_keys: set[tuple[str, str, str]],
    skipped_keys: set[tuple[str, str, str]],
    raw_dir: Path,
    rules: list[dict[str, str]] | None = None,
) -> list[ThreadGroup]:
    """Return full threads where a new reply follows prior ingestion state."""
    rules = rules or []
    all_groups = group_messages(messages)
    reactivated = []
    for group in all_groups:
        if group.thread_ts is None:
            continue
        has_prior_state = any(
            message_key(m, raw_dir) in ingested_keys
            or message_key(m, raw_dir) in skipped_keys
            for m in group.messages
        )
        has_new = any(
            message_key(m, raw_dir) not in ingested_keys
            and message_key(m, raw_dir) not in skipped_keys
            and not message_matches_rules(m, rules)
            for m in group.messages
        )
        if has_prior_state and has_new:
            reactivated.append(ThreadGroup(group.thread_ts, group.messages, True))
    return reactivated


def discover_thread_groups(
    messages: list[SlackMessage],
    ingested_keys: set[tuple[str, str, str]],
    skipped_keys: set[tuple[str, str, str]],
    raw_dir: Path,
    rules: list[dict[str, str]],
) -> list[ThreadGroup]:
    """Build ordinary and reactivated groups without showing a message twice."""
    new_groups = group_messages(
        find_uningested_messages(messages, ingested_keys, raw_dir, skipped_keys, rules)
    )
    reactivated_groups = find_reactivated_thread_groups(
        messages, ingested_keys, skipped_keys, raw_dir, rules
    )
    reactivated_keys = {
        message_key(message, raw_dir)
        for group in reactivated_groups
        for message in group.messages
    }
    ordinary_groups = [
        group
        for group in new_groups
        if not any(message_key(message, raw_dir) in reactivated_keys for message in group.messages)
    ]
    return ordinary_groups + reactivated_groups


def find_slackdump_databases(raw_dir: Path) -> list[Path]:
    return sorted(raw_dir.glob("Slack/**/slackdump.sqlite"))


# ---------------------------------------------------------------------------
# Database discovery, access, and validation
# ---------------------------------------------------------------------------


def open_database(path: Path) -> sqlite3.Connection:
    if not path.is_file():
        raise FileNotFoundError(f"SQLite archive is not a regular file: {path}")

    uri = f"{path.resolve().as_uri()}?mode=ro"
    connection: sqlite3.Connection | None = None

    try:
        connection = sqlite3.connect(uri, uri=True)
        # sqlite3.connect() may defer opening a WAL database until the first
        # statement. Probe it here so the immutable fallback handles that
        # failure rather than failing later in a message query.
        connection.execute("SELECT 1")
    except sqlite3.OperationalError as error:
        if connection is not None:
            connection.close()

        wal_path = path.with_name(path.name + "-wal")
        if wal_path.is_file() and wal_path.stat().st_size > 0:
            raise sqlite3.OperationalError(
                f"Unable to open Slackdump archive read-only: {path}. "
                f"The archive has uncheckpointed WAL changes in {wal_path}; "
                "close Slackdump or checkpoint the archive before ingesting it."
            ) from error

        immutable_uri = f"{path.resolve().as_uri()}?mode=ro&immutable=1"
        connection = sqlite3.connect(immutable_uri, uri=True)

    assert connection is not None
    connection.row_factory = sqlite3.Row
    return connection


def validate_slackdump_database(connection: sqlite3.Connection) -> None:
    placeholders = ", ".join("?" for _ in REQUIRED_TABLES)
    query = f"""
    SELECT name
    FROM sqlite_master
    WHERE type='table'
      AND name IN ({placeholders});
    """

    found_tables = (row["name"] for row in connection.execute(query, REQUIRED_TABLES))
    missing_tables = set(REQUIRED_TABLES) - set(found_tables)

    if missing_tables:
        missing = ", ".join(missing_tables)
        raise InvalidSlackdumpDatabaseError(f"Missing tables: {missing}")


def validate_schema(connection: sqlite3.Connection) -> None:
    for table, required_columns in REQUIRED_COLUMNS.items():
        rows = connection.execute(f"PRAGMA table_info({table});").fetchall()

        actual_columns = [row["name"] for row in rows]
        missing_columns = required_columns - set(actual_columns)
        if missing_columns:
            raise InvalidSlackdumpDatabaseError(
                f"{table} is missing required columns: "
                f"{', '.join(sorted(missing_columns))}"
            )


def inspect_archive(database_path: Path) -> ArchiveInspection:
    archive_root = database_path.parent
    uploads_dir = archive_root / "__uploads"

    with open_database(database_path) as connection:
        validate_slackdump_database(connection)
        validate_schema(connection)

        channels = [
            {
                "id": row["ID"],
                "name": row["NAME"],
            }
            for row in connection.execute(
                "SELECT ID, NAME FROM CHANNEL ORDER BY NAME, ID"
            )
        ]

        message_count = connection.execute("SELECT COUNT(*) FROM MESSAGE").fetchone()[0]

        thread_parent_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM MESSAGE WHERE
            IS_PARENT IS TRUE
            """
        ).fetchone()[0]

        reply_count = connection.execute(
            """
            SELECT COUNT(*)
            FROM MESSAGE
            WHERE  IS_PARENT = FALSE
              AND PARENT_ID IS NOT NULL
            """
        ).fetchone()[0]

    return ArchiveInspection(
        database_path=database_path,
        archive_root=archive_root,
        has_uploads=uploads_dir.is_dir(),
        channels=channels,
        message_count=message_count,
        thread_parent_count=thread_parent_count,
        reply_count=reply_count,
    )


def print_inspection(inspection: ArchiveInspection) -> None:
    print(f"Archive: {inspection.archive_root}")
    print(f"Database: {inspection.database_path}")
    print(f"Uploads: {'yes' if inspection.has_uploads else 'no'}")
    print(f"Messages: {inspection.message_count}")
    print(f"Thread parents: {inspection.thread_parent_count}")
    print(f"Replies: {inspection.reply_count}")

    print("Channels:")
    for channel in inspection.channels:
        print(f"  {channel['id']}: {channel['name']}")

    print()


# ---------------------------------------------------------------------------
# manifest and ingestion state
# ---------------------------------------------------------------------------


def manifest_path_from_database(
    database_path: Path,
    raw_dir: Path = Path("raw"),
    state_root: Path = Path(".llm-wiki") / "slack",
) -> Path:
    """Return mutable state path for one archive, outside the raw tree."""
    del raw_dir  # Retained for API compatibility; archive names are unique.
    return (
        state_root / database_path.resolve().parent.name / "slack-ingest-manifest.jsonl"
    )


def serialize_message_for_ingestion(
    message: SlackMessage,
    channel: SlackChannel,
    source_path: Path,
    ingested_at: datetime,
    raw_dir: Path,
) -> dict:

    archive_path = archive_identity(message.archive_path, raw_dir)

    return {
        "archive_path": archive_path,
        "channel_id": channel.channel_id,
        "message_ts": message.message_ts,
        "payload_sha256": message_payload_hash(message),
        "source_path": str(source_path),
        "ingested_at": ingested_at.isoformat().replace("+00:00", "Z"),
    }


def append_ingested_message(manifest_path: Path, record: dict[str, str]) -> None:
    """Append one successfully ingested Slack message to the manifest."""

    manifest_path.parent.mkdir(parents=True, exist_ok=True)

    with manifest_path.open("a", encoding="utf-8") as manifest:
        manifest.write(json.dumps(record, sort_keys=True))
        manifest.write("\n")


# ---------------------------------------------------------------------------
# Command-specific rendering and handlers
# ---------------------------------------------------------------------------


def find_database_paths(args: argparse.Namespace) -> list[Path]:
    if args.database is not None:
        return [args.database]
    else:
        return find_slackdump_databases(args.raw_dir)


def inspect_command(args: argparse.Namespace) -> int:
    database_paths = find_database_paths(args)

    if not database_paths:
        print(f"No Slackdump SQLite archives found under {args.raw_dir} / 'Slack'")
        return 0

    for database_path in database_paths:
        try:
            inspection = inspect_archive(database_path)
        except (
            OSError,
            sqlite3.Error,
            InvalidSlackdumpDatabaseError,
        ) as error:
            print(f"Unable to inspect {database_path}: {error}")
            continue

        print_inspection(inspection)

    return 0


def format_message_preview(
    message: SlackMessage,
    author_name: str,
    user_names: dict[str, str] | None = None,
    max_preview_length: int = 120,
) -> str:
    text = " ".join(message.text.split())
    text = text or "<no text>"
    text = resolve_slack_mentions(text, user_names)

    if len(text) > max_preview_length:
        text = text[: max_preview_length - 1].rstrip() + "..."

    if message.is_parent:
        thread_status = "parent"
    elif message.thread_ts:
        thread_status = f"reply to {format_slack_timestamp(message.thread_ts)}"
    else:
        thread_status = "standalone"

    return (
        f"[{format_slack_timestamp(message.message_ts)}] "
        f"{thread_status} | {author_name}\n"
        f"  {text}"
    )


def print_messages(
    database_path: Path,
    messages: list[SlackMessage],
    user_names: dict[str, str] | None = None,
) -> None:
    with open_database(database_path) as connection:
        if user_names is None:
            user_names = load_user_names(connection)

        for message in messages:
            author = message.data.get("user")
            author_name = author_name_from_map(user_names, author)
            print(format_message_preview(message, author_name, user_names))


def messages_command(args: argparse.Namespace) -> int:
    database_paths = find_database_paths(args)

    if not database_paths:
        print(f"No Slackdump SQLite archives found under {args.raw_dir} / 'Slack'")
        return 0

    for database_path in database_paths:
        messages = fetch_canonical_messages(database_path, channel_id=args.channel_id)

        print(f"Database: {database_path}")
        print(f"Messages: {len(messages)}")

        for message in messages:
            print_messages(database_path, [message])

    return 0


def print_threads(database_path: Path, thread_groups: list[ThreadGroup]) -> None:
    with open_database(database_path) as connection:
        user_names = load_user_names(connection)

        for i, group in enumerate(thread_groups, 1):
            first_message = group.messages[0]
            author_id = first_message.data.get("user")
            author_name = author_name_from_map(user_names, author_id)
            status = "thread" if group.thread_ts is not None else "standalone"
            timestamp = format_slack_timestamp(first_message.message_ts)
            count_label = (
                f"{len(group.messages)} message"
                if len(group.messages) == 1
                else f"{len(group.messages)} messages"
            )

            print(
                f"{i}. {first_message.channel_id} | {status} | "
                f"{timestamp} | {count_label} | {author_name}"
            )
            if group.reactivated:
                print("   REACTIVATED: previously excluded thread; review full current context")
            for message in group.messages:
                message_author = message.data.get("user")
                message_author_name = author_name_from_map(user_names, message_author)
                print(
                    format_message_preview(
                        message,
                        message_author_name,
                        user_names,
                    )
                )
            print()


def fetch_archive_channel(database_path: Path, channel_id: str | None) -> SlackChannel:
    with open_database(database_path) as connection:
        validate_slackdump_database(connection)
        validate_schema(connection)
        return resolve_archive_channel(connection, channel_id)


def parse_thread_selection(
    selection: str, thread_groups: list[ThreadGroup]
) -> list[ThreadGroup]:
    if selection == "all":
        return thread_groups
    elif selection == "none":
        return []
    else:
        try:
            indices = [int(i.strip()) for i in selection.split(",")]
            return [thread_groups[i - 1] for i in indices]
        except (ValueError, IndexError):
            print(f"Invalid selection: {selection}")
            return []


def format_thread_group(database_path: Path, group: ThreadGroup) -> str:
    lines = [
        f"Thread: {group.thread_ts or 'standalone'}",
        f"Messages: {len(group.messages)}",
    ]

    with open_database(database_path) as connection:
        user_names = load_user_names(connection)

        for message in group.messages:
            author_id = message.data.get("user")
            author_name = author_name_from_map(user_names, author_id)

            lines.append(
                format_message_preview(
                    message,
                    author_name,
                    user_names,
                ),
            )

    return "\n".join(lines)


def threads_command(args: argparse.Namespace) -> int:
    raw_dir = args.raw_dir
    database_paths = find_database_paths(args)

    if not database_paths:
        print(f"No Slackdump SQLite archives found under {raw_dir} / 'Slack'")
        return 0

    for i, database_path in enumerate(database_paths, 1):
        channel_id = args.channel_id
        messages = fetch_canonical_messages(database_path, channel_id=channel_id)

        ingested_keys, skipped_keys, rules = load_archive_ingestion_state(
            database_path, raw_dir
        )
        thread_groups = discover_thread_groups(
            messages, ingested_keys, skipped_keys, raw_dir, rules
        )

        if not thread_groups:
            print(f"Archive {i}: {database_path.parent}")
            print(f"Database: {database_path.name}")
            print("No new slack messages found.")
            print()
            continue

        print(f"Archive {i}: {database_path.parent}")
        print(f"Database: {database_path.name}")
        try:
            channel = fetch_archive_channel(database_path, channel_id)
        except InvalidSlackdumpDatabaseError as error:
            if channel_id is None and "multiple" in str(error):
                print("Channel: Multiple channels")
            else:
                raise
        else:
            print(f"Channel: {channel.name} ({channel.channel_id})")
        print(f"Thread groups: {len(thread_groups)}")
        print_threads(database_path, thread_groups)
        print()

        try:
            selection = input(
                "Select threads to ingest [e.g. 1,3,12], 'all', or 'none': "
            ).strip()
        except EOFError:
            print("No selection provided; Nothing will be ingested.")
            continue

        selected_groups = parse_thread_selection(
            selection,
            thread_groups,
        )

        selected_messages = [
            message for group in selected_groups for message in group.messages
        ]

        print(f"Selected groups: {len(selected_groups)}")
        print(f"Selected messages: {len(selected_messages)}")
        print()

        for group in selected_groups:
            print()
            print(format_thread_group(database_path, group))

    return 0


def record_command(args: argparse.Namespace) -> int:
    source_path = args.source_path

    if not source_path.is_file():
        raise ValueError(f"source-path must be a regular file: {source_path}")

    if source_path.suffix.lower() != ".md":
        raise ValueError("source-path must be a Markdown file")

    try:
        source_path.resolve().relative_to((Path("wiki") / "sources").resolve())
    except ValueError as exc:
        raise ValueError("source-path must be under wiki/sources/") from exc

    if not args.channel_id.strip():
        raise ValueError("channel-id must not be empty")

    try:
        float(args.message_ts)
    except ValueError as exc:
        raise ValueError("message-ts must be a numeric Slack timestamp") from exc

    messages = fetch_canonical_messages(args.database, args.channel_id)
    message = next(
        (item for item in messages if item.message_ts == args.message_ts),
        None,
    )
    if message is None:
        raise ValueError(
            f"Message not found for channel {args.channel_id} "
            f"and timestamp {args.message_ts}"
        )

    channel = fetch_archive_channel(args.database, args.channel_id)
    manifest_path = manifest_path_from_database(
        args.database, getattr(args, "raw_dir", Path("raw"))
    )
    raw_dir = getattr(args, "raw_dir", Path("raw"))
    record = serialize_message_for_ingestion(
        message,
        channel,
        source_path,
        datetime.now(timezone.utc),
        raw_dir,
    )

    existing_records = load_manifest_records(manifest_path)
    existing = next(
        (
            item
            for item in existing_records
            if (
                item.get("archive_path") == record["archive_path"]
                and item.get("channel_id") == record["channel_id"]
                and item.get("message_ts") == record["message_ts"]
            )
        ),
        None,
    )
    if existing is not None:
        if (
            existing.get("payload_sha256") == record["payload_sha256"]
            and existing.get("source_path") == record["source_path"]
        ):
            print("Slack message is already recorded.")
            return 0
        raise ValueError("Slack message is already recorded with different metadata")

    append_ingested_message(manifest_path, record)
    print(f"Recorded Slack message in {manifest_path}")

    return 0


# ---------------------------------------------------------------------------
# CLI definition and entry point
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Inspect Slackdump SQLite archives and manage incremental Slack "
            "message ingestion."
        ),
        epilog=(
            "By default, commands discover slackdump.sqlite files recursively "
            "under raw/Slack. Use --database to target one explicit SQLite "
            "database. Archive inspection and message/thread listing are "
            "read-only."
        ),
    )

    subparsers = parser.add_subparsers(
        dest="command",
        required=True,
    )

    inspect_parser = subparsers.add_parser(
        "inspect",
        help="Show archive metadata, channels, and message counts.",
        description=(
            "Inspect one explicit Slackdump SQLite database, or every database "
            "found recursively under raw/Slack. Reports the archive root, "
            "attachment directory, channels, and message/thread counts. "
            "This command is read-only."
        ),
    )

    inspect_parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("raw"),
        help=(
            "Repository raw directory containing Slack archives; used only "
            "when --database is omitted (default: %(default)s)."
        ),
    )

    inspect_parser.add_argument(
        "--database",
        type=Path,
        metavar="PATH",
        help=(
            "Inspect this explicit slackdump.sqlite file instead of discovering "
            "databases under raw/Slack."
        ),
    )

    message_parser = subparsers.add_parser(
        "messages",
        help="List canonical messages after archive deduplication.",
        description=(
            "List one canonical row for each logical Slack message after "
            "deduplicating repeated sessions and chunk records. This command "
            "is read-only and does not create ingestion state or Markdown files."
        ),
    )

    message_parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("raw"),
        help=(
            "Repository raw directory containing Slack archives; used only "
            "when --database is omitted (default: %(default)s)."
        ),
    )

    message_parser.add_argument(
        "--database",
        type=Path,
        metavar="PATH",
        help=(
            "Read this explicit slackdump.sqlite file instead of discovering "
            "databases under raw/Slack."
        ),
    )

    message_parser.add_argument(
        "--channel-id",
        type=str,
        metavar="CHANNEL_ID",
        help="Limit output to messages from this Slack channel (optional).",
    )

    threads_parser = subparsers.add_parser(
        "threads",
        help="List thread groups for review and later selection.",
        description=(
            "Group canonical Slack messages into numbered, human-readable "
            "thread candidates for review and selection. Previously recorded "
            "messages are omitted. This command is read-only."
        ),
    )

    threads_parser.add_argument(
        "--channel-id",
        type=str,
        metavar="CHANNEL_ID",
        help="Limit thread candidates to this Slack channel (optional).",
    )

    threads_parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("raw"),
        help=(
            "Repository raw directory containing Slack archives; used only "
            "when --database is omitted (default: %(default)s)."
        ),
    )

    threads_parser.add_argument(
        "--database",
        type=Path,
        metavar="PATH",
        help=(
            "Read this explicit slackdump.sqlite file instead of discovering "
            "databases under raw/Slack."
        ),
    )

    record_parser = subparsers.add_parser(
        "record",
        help="Record one Slack message as successfully ingested.",
        description=(
            "Record a successfully generated Slack source file in the local "
            "Slack ingestion manifest. Future scans use the archive path, "
            "channel ID, and message timestamp to skip this message."
        ),
    )

    record_parser.add_argument(
        "--database",
        required=True,
        type=Path,
        metavar="PATH",
        help="Slackdump database containing the message.",
    )

    record_parser.add_argument(
        "--raw-dir",
        type=Path,
        default=Path("raw"),
        help=(
            "Raw directory containing the archive; used to locate the "
            "repository-level Slack state directory (default: %(default)s)."
        ),
    )

    record_parser.add_argument(
        "--channel-id",
        required=True,
        type=str,
        metavar="CHANNEL_ID",
        help="Slack channel ID where the message was posted.",
    )

    record_parser.add_argument(
        "--message-ts",
        required=True,
        type=str,
        metavar="TIMESTAMP",
        help="Slack message timestamp, for example 1787662025.876289.",
    )

    record_parser.add_argument(
        "--source-path",
        required=True,
        type=Path,
        metavar="PATH",
        help="Generated Markdown source file for the message.",
    )

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    match args.command:
        case "inspect":
            return inspect_command(args)

        case "messages":
            return messages_command(args)

        case "threads":
            return threads_command(args)

        case "record":
            return record_command(args)

        case _:
            parser.error(f"Unknown command: {args.command}")
            return 2


if __name__ == "__main__":
    main()
