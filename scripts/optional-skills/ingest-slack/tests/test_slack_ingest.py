from __future__ import annotations

import importlib.util
import argparse
import io
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "slack_ingest.py"
SPEC = importlib.util.spec_from_file_location("slack_ingest", SCRIPT_PATH)
assert SPEC is not None
assert SPEC.loader is not None

slack_ingest = importlib.util.module_from_spec(SPEC)
sys.modules["slack_ingest"] = slack_ingest
SPEC.loader.exec_module(slack_ingest)


class SlackIngestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary_directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary_directory.cleanup)
        self.raw_dir = Path(self.temporary_directory.name) / "raw"
        self.slack_dir = self.raw_dir / "Slack"

    def create_database(
        self,
        *,
        name: str = "slackdump_20260912_110311",
        include_uploads: bool = True,
        include_duplicate: bool = False,
        include_malformed_data: bool = False,
    ) -> Path:
        archive_root = self.slack_dir / "project-alpha" / name
        archive_root.mkdir(parents=True)
        if include_uploads:
            (archive_root / "__uploads").mkdir()

        database_path = archive_root / "slackdump.sqlite"
        connection = sqlite3.connect(database_path)
        connection.executescript(
            """
            CREATE TABLE MESSAGE (
                ID INTEGER,
                CHUNK_ID INTEGER,
                CHANNEL_ID TEXT,
                TS TEXT,
                PARENT_ID INTEGER,
                THREAD_TS TEXT,
                IS_PARENT SMALLINT,
                TXT TEXT,
                DATA BLOB
            );
            CREATE TABLE CHANNEL (
                ID TEXT,
                NAME TEXT
            );
            CREATE TABLE S_USER (
                ID TEXT,
                USERNAME TEXT,
                DATA BLOB
            );
            CREATE TABLE CHUNK (
                ID INTEGER,
                SESSION_ID INTEGER,
                TYPE_ID INTEGER
            );
            CREATE TABLE TYPES (
                ID INTEGER
            );
            """
        )
        connection.executemany(
            "INSERT INTO CHANNEL (ID, NAME) VALUES (?, ?)",
            [("C1", "alpha"), ("C2", "beta")],
        )
        connection.executemany(
            "INSERT INTO CHUNK (ID, SESSION_ID, TYPE_ID) VALUES (?, ?, ?)",
            [
                (1, 1, 0),
                (2, 2, 0),
                (3, 2, 1),
            ],
        )
        connection.executemany(
            "INSERT INTO S_USER (ID, USERNAME, DATA) VALUES (?, ?, ?)",
            [
                ("U1", "alex", '{"name":"alex","real_name":"Alex Kelley"}'),
                (
                    "U2",
                    "brent",
                    '{"name":"brent","profile":{"display_name":"Brent Holliday"}}',
                ),
                ("U3", "username-only", ""),
                ("U4", "malformed", "not-json"),
            ],
        )
        messages = [
            (1, 1, "C1", "100.001", 1, "100.001", True, "parent", '{"user":"U1"}'),
            (2, 1, "C1", "100.002", 1, "100.001", False, "reply", '{"user":"U2"}'),
            (3, 1, "C2", "101.001", None, None, False, "standalone", '{"user":"U1"}'),
        ]
        if include_duplicate:
            messages.append(
                (4, 2, "C1", "100.001", 1, "100.001", True, "parent", '{"user":"U1"}')
            )
        if include_malformed_data:
            messages.extend(
                [
                    (5, 1, "C1", "100.003", None, None, False, "empty", ""),
                    (6, 1, "C1", "100.004", None, None, False, "malformed", "not-json"),
                ]
            )

        connection.executemany(
            """
            INSERT INTO MESSAGE
                (ID, CHUNK_ID, CHANNEL_ID, TS, PARENT_ID, THREAD_TS,
                 IS_PARENT, TXT, DATA)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            messages,
        )
        connection.commit()
        connection.close()
        return database_path

    def add_message(
        self,
        database_path: Path,
        *,
        message_id: int,
        chunk_id: int,
        channel_id: str,
        message_ts: str,
        text: str,
        user_id: str = "U1",
        thread_ts: str | None = None,
        parent_id: int | None = None,
        is_parent: bool = False,
    ) -> None:
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                """
                INSERT INTO MESSAGE
                    (ID, CHUNK_ID, CHANNEL_ID, TS, PARENT_ID, THREAD_TS,
                     IS_PARENT, TXT, DATA)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    message_id,
                    chunk_id,
                    channel_id,
                    message_ts,
                    parent_id,
                    thread_ts,
                    is_parent,
                    text,
                    json.dumps({"user": user_id, "text": text}),
                ),
            )

    def write_manifest(
        self,
        records: list[dict[str, str]],
    ) -> Path:
        manifest_path = (
            Path(self.temporary_directory.name) / "slack-ingest-manifest.jsonl"
        )
        manifest_path.write_text(
            "".join(json.dumps(record) + "\n" for record in records),
            encoding="utf-8",
        )
        return manifest_path

    def record_args(
        self,
        database_path: Path,
        source_path: Path,
        *,
        channel_id: str = "C1",
        message_ts: str = "100.001",
    ) -> argparse.Namespace:
        return argparse.Namespace(
            database=database_path,
            channel_id=channel_id,
            message_ts=message_ts,
            source_path=source_path,
            raw_dir=Path("raw"),
        )

    def test_find_slackdump_databases_finds_nested_archives(self) -> None:
        first = self.create_database()
        second = self.create_database(name="slackdump_20260913_110311")

        found = slack_ingest.find_slackdump_databases(self.raw_dir)

        self.assertEqual(found, sorted([first, second]))

    def test_find_slackdump_databases_ignores_other_files(self) -> None:
        self.slack_dir.mkdir(parents=True)
        (self.slack_dir / "not-a-database.txt").write_text("ignore")

        self.assertEqual(
            slack_ingest.find_slackdump_databases(self.raw_dir),
            [],
        )

    def test_open_database_is_read_only(self) -> None:
        database_path = self.create_database()

        with slack_ingest.open_database(database_path) as connection:
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("CREATE TABLE should_fail (ID INTEGER)")

    def test_open_database_reads_wal_database_without_sidecars(self) -> None:
        database_path = self.create_database()

        with sqlite3.connect(database_path) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                "INSERT INTO MESSAGE "
                "(ID, CHUNK_ID, CHANNEL_ID, TS, PARENT_ID, THREAD_TS, "
                "IS_PARENT, TXT, DATA) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (4, 1, "C1", "100.003", None, None, False, "wal", "{}"),
            )
            connection.commit()
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")

        for suffix in ("-wal", "-shm"):
            database_path.with_name(database_path.name + suffix).unlink(
                missing_ok=True
            )

        with slack_ingest.open_database(database_path) as connection:
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM MESSAGE").fetchone()[0],
                4,
            )
            with self.assertRaises(sqlite3.OperationalError):
                connection.execute("CREATE TABLE should_fail (ID INTEGER)")

        self.assertFalse(
            database_path.with_name(database_path.name + "-shm").exists()
        )

    def test_open_database_rejects_pending_wal_after_readonly_failure(self) -> None:
        database_path = self.create_database()

        with sqlite3.connect(database_path) as connection:
            connection.execute("PRAGMA journal_mode=WAL")
            connection.execute(
                "INSERT INTO MESSAGE "
                "(ID, CHUNK_ID, CHANNEL_ID, TS, PARENT_ID, THREAD_TS, "
                "IS_PARENT, TXT, DATA) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (4, 1, "C1", "100.003", None, None, False, "wal", "{}"),
            )
            connection.commit()

        wal_path = database_path.with_name(database_path.name + "-wal")
        self.assertTrue(wal_path.exists())
        self.assertGreater(wal_path.stat().st_size, 0)

        with patch.object(
            slack_ingest.sqlite3,
            "connect",
            side_effect=sqlite3.OperationalError("unable to open database file"),
        ):
            with self.assertRaisesRegex(
                sqlite3.OperationalError, "uncheckpointed WAL changes"
            ):
                slack_ingest.open_database(database_path)

    def test_open_database_requires_regular_file(self) -> None:
        missing_path = self.slack_dir / "missing.sqlite"

        with self.assertRaises(FileNotFoundError):
            slack_ingest.open_database(missing_path)

    def test_validate_slackdump_database_rejects_missing_table(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("CREATE TABLE MESSAGE (ID INTEGER)")
        self.addCleanup(connection.close)

        with self.assertRaises(slack_ingest.InvalidSlackdumpDatabaseError):
            slack_ingest.validate_slackdump_database(connection)

    def test_validate_schema_rejects_missing_column(self) -> None:
        connection = sqlite3.connect(":memory:")
        connection.row_factory = sqlite3.Row
        connection.execute("CREATE TABLE CHANNEL (ID TEXT)")
        self.addCleanup(connection.close)

        with self.assertRaises(slack_ingest.InvalidSlackdumpDatabaseError):
            slack_ingest.validate_schema(connection)

    def test_inspect_archive_returns_counts_and_metadata(self) -> None:
        database_path = self.create_database()

        inspection = slack_ingest.inspect_archive(database_path)

        self.assertEqual(inspection.database_path, database_path)
        self.assertEqual(inspection.archive_root, database_path.parent)
        self.assertTrue(inspection.has_uploads)
        self.assertEqual(
            inspection.channels,
            [
                {"id": "C1", "name": "alpha"},
                {"id": "C2", "name": "beta"},
            ],
        )
        self.assertEqual(inspection.message_count, 3)
        self.assertEqual(inspection.thread_parent_count, 1)
        self.assertEqual(inspection.reply_count, 1)

    def test_inspect_archive_reports_missing_uploads(self) -> None:
        database_path = self.create_database(include_uploads=False)

        inspection = slack_ingest.inspect_archive(database_path)

        self.assertFalse(inspection.has_uploads)

    def test_fetch_messages_returns_message_records(self) -> None:
        database_path = self.create_database()

        messages = slack_ingest.fetch_messages(database_path)

        self.assertEqual(len(messages), 3)
        self.assertEqual(messages[0].channel_id, "C1")
        self.assertEqual(messages[0].message_ts, "100.001")
        self.assertEqual(messages[0].thread_ts, "100.001")
        self.assertTrue(messages[0].is_parent)
        self.assertEqual(messages[0].text, "parent")
        self.assertEqual(messages[0].data, {"user": "U1"})

    def test_fetch_messages_filters_by_channel(self) -> None:
        database_path = self.create_database()

        messages = slack_ingest.fetch_messages(database_path, channel_id="C2")

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].channel_id, "C2")
        self.assertEqual(messages[0].text, "standalone")

    def test_fetch_messages_exposes_duplicate_rows_for_later_deduplication(
        self,
    ) -> None:
        database_path = self.create_database(include_duplicate=True)

        messages = slack_ingest.fetch_messages(database_path)

        matching = [message for message in messages if message.message_ts == "100.001"]
        self.assertEqual(len(matching), 2)
        self.assertEqual(
            {(message.channel_id, message.message_ts) for message in matching},
            {("C1", "100.001")},
        )

    def test_fetch_messages_handles_empty_and_malformed_data(self) -> None:
        database_path = self.create_database(include_malformed_data=True)

        messages = slack_ingest.fetch_messages(database_path)

        by_text = {message.text: message for message in messages}
        self.assertEqual(by_text["empty"].data, {})
        self.assertEqual(by_text["malformed"].data, {})

    def test_add_message_simulates_archive_update(self) -> None:
        database_path = self.create_database()

        before = slack_ingest.fetch_canonical_messages(database_path)
        self.add_message(
            database_path,
            message_id=9,
            chunk_id=1,
            channel_id="C1",
            message_ts="100.003",
            text="new message",
        )

        after = slack_ingest.fetch_canonical_messages(database_path)

        self.assertEqual(len(after), len(before) + 1)
        self.assertIn(
            "new message",
            {message.text for message in after},
        )

    def test_message_key_includes_archive_and_message_identity(self) -> None:
        first_database = self.create_database(name="slackdump_20260912_110311")
        second_database = self.create_database(name="slackdump_20260913_110311")

        first_message = slack_ingest.fetch_canonical_messages(first_database)[0]
        second_message = slack_ingest.fetch_canonical_messages(second_database)[0]

        self.assertNotEqual(
            slack_ingest.message_key(first_message, self.raw_dir),
            slack_ingest.message_key(second_message, self.raw_dir),
        )
        self.assertEqual(
            slack_ingest.message_key(first_message, self.raw_dir)[1:],
            ("C1", "100.001"),
        )

    def test_archive_identity_uses_path_relative_to_raw_directory(self) -> None:
        database_path = self.create_database()

        identity = slack_ingest.archive_identity(database_path, self.raw_dir)

        self.assertEqual(
            identity,
            "Slack/project-alpha/slackdump_20260912_110311/slackdump.sqlite",
        )

    def test_archive_identity_falls_back_for_database_outside_raw_directory(
        self,
    ) -> None:
        database_path = Path(self.temporary_directory.name) / "external.sqlite"
        database_path.touch()

        identity = slack_ingest.archive_identity(database_path, self.raw_dir)

        self.assertEqual(identity, str(database_path.resolve()))

    def test_message_payload_hash_is_stable_for_json_key_order(self) -> None:
        database_path = self.create_database()
        message = slack_ingest.fetch_canonical_messages(database_path)[0]
        reordered = slack_ingest.SlackMessage(
            archive_path=message.archive_path,
            chunk_id=message.chunk_id,
            session_id=message.session_id,
            chunk_type_id=message.chunk_type_id,
            channel_id=message.channel_id,
            message_ts=message.message_ts,
            thread_ts=message.thread_ts,
            parent_id=message.parent_id,
            is_parent=message.is_parent,
            text=message.text,
            data={"user": "U1"},
        )

        self.assertEqual(
            slack_ingest.message_payload_hash(message),
            slack_ingest.message_payload_hash(reordered),
        )

    def test_serialize_message_for_ingestion_matches_manifest_contract(self) -> None:
        database_path = self.create_database()
        message = slack_ingest.fetch_canonical_messages(database_path)[0]
        channel = slack_ingest.SlackChannel("C1", "alpha")
        ingested_at = datetime(2026, 9, 16, 19, 45, 0, 123456, timezone.utc)
        source_path = Path("wiki/sources/slack-C1-100.001.md")

        record = slack_ingest.serialize_message_for_ingestion(
            message,
            channel,
            source_path,
            ingested_at,
            self.raw_dir,
        )

        self.assertEqual(
            record,
            {
                "archive_path": (
                    "Slack/project-alpha/slackdump_20260912_110311/slackdump.sqlite"
                ),
                "channel_id": "C1",
                "message_ts": "100.001",
                "payload_sha256": slack_ingest.message_payload_hash(message),
                "source_path": "wiki/sources/slack-C1-100.001.md",
                "ingested_at": "2026-09-16T19:45:00.123456Z",
            },
        )

    def test_load_ingested_message_keys_reads_simulated_manifest(self) -> None:
        database_path = self.create_database()
        message = slack_ingest.fetch_canonical_messages(database_path)[0]
        archive_path, channel_id, message_ts = slack_ingest.message_key(
            message, self.raw_dir
        )
        manifest_path = self.write_manifest(
            [
                {
                    "archive_path": archive_path,
                    "channel_id": channel_id,
                    "message_ts": message_ts,
                    "source_path": "wiki/sources/slack-C1-100.001.md",
                }
            ]
        )

        keys = slack_ingest.load_ingested_message_keys(manifest_path)

        self.assertEqual(
            keys,
            {(archive_path, channel_id, message_ts)},
        )

    def test_manifest_filters_processed_messages_after_archive_update(self) -> None:
        database_path = self.create_database()
        initial_messages = slack_ingest.fetch_canonical_messages(database_path)
        processed_message = initial_messages[0]
        processed_key = slack_ingest.message_key(
            processed_message,
            self.raw_dir,
        )
        manifest_path = self.write_manifest(
            [
                {
                    "archive_path": processed_key[0],
                    "channel_id": processed_key[1],
                    "message_ts": processed_key[2],
                }
            ]
        )

        self.add_message(
            database_path,
            message_id=9,
            chunk_id=1,
            channel_id="C1",
            message_ts="100.003",
            text="new message after resume",
        )
        updated_messages = slack_ingest.fetch_canonical_messages(database_path)
        ingested_keys = slack_ingest.load_ingested_message_keys(manifest_path)
        new_messages = [
            message
            for message in updated_messages
            if slack_ingest.message_key(message, self.raw_dir) not in ingested_keys
        ]

        self.assertEqual(len(new_messages), len(updated_messages) - 1)
        self.assertIn(
            "new message after resume",
            {message.text for message in new_messages},
        )

    def test_load_ingested_message_keys_returns_empty_for_missing_manifest(
        self,
    ) -> None:
        manifest_path = Path(self.temporary_directory.name) / "missing.jsonl"

        self.assertEqual(
            slack_ingest.load_ingested_message_keys(manifest_path),
            set(),
        )

    def test_record_command_writes_repository_slack_manifest(self) -> None:
        database_path = self.create_database()
        source_path = (
            Path(self.temporary_directory.name)
            / "wiki"
            / "sources"
            / "slack-C1-100.001.md"
        )
        source_path.parent.mkdir(parents=True)
        source_path.write_text("# Slack message\n", encoding="utf-8")

        original_directory = Path.cwd()
        os.chdir(self.temporary_directory.name)
        self.addCleanup(lambda: os.chdir(original_directory))

        result = slack_ingest.record_command(
            self.record_args(database_path, Path("wiki/sources/slack-C1-100.001.md"))
        )

        manifest_path = (
            Path(".llm-wiki") / "slack" / database_path.parent.name
            / "slack-ingest-manifest.jsonl"
        )
        self.assertEqual(result, 0)
        self.assertTrue(manifest_path.is_file())
        record = json.loads(manifest_path.read_text(encoding="utf-8"))
        self.assertEqual(record["archive_path"], slack_ingest.archive_identity(database_path, Path("raw")))
        self.assertEqual(record["channel_id"], "C1")
        self.assertEqual(record["message_ts"], "100.001")
        self.assertEqual(record["source_path"], "wiki/sources/slack-C1-100.001.md")
        self.assertEqual(record["payload_sha256"], slack_ingest.message_payload_hash(
            slack_ingest.fetch_canonical_messages(database_path, "C1")[0]
        ))
        self.assertTrue(record["ingested_at"].endswith("Z"))

    def test_record_command_is_idempotent_for_same_message(self) -> None:
        database_path = self.create_database()
        source_path = (
            Path(self.temporary_directory.name)
            / "wiki"
            / "sources"
            / "slack-C1-100.001.md"
        )
        source_path.parent.mkdir(parents=True)
        source_path.write_text("# Slack message\n", encoding="utf-8")

        original_directory = Path.cwd()
        os.chdir(self.temporary_directory.name)
        self.addCleanup(lambda: os.chdir(original_directory))
        args = self.record_args(database_path, Path("wiki/sources/slack-C1-100.001.md"))

        slack_ingest.record_command(args)
        slack_ingest.record_command(args)

        manifest_path = (
            Path(".llm-wiki") / "slack" / database_path.parent.name
            / "slack-ingest-manifest.jsonl"
        )
        records = [
            line
            for line in manifest_path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        ]
        self.assertEqual(len(records), 1)

    def test_record_command_rejects_missing_message(self) -> None:
        database_path = self.create_database()
        source_path = (
            Path(self.temporary_directory.name)
            / "wiki"
            / "sources"
            / "missing.md"
        )
        source_path.parent.mkdir(parents=True)
        source_path.write_text("# Missing\n", encoding="utf-8")

        original_directory = Path.cwd()
        os.chdir(self.temporary_directory.name)
        self.addCleanup(lambda: os.chdir(original_directory))

        with self.assertRaisesRegex(ValueError, "Message not found"):
            slack_ingest.record_command(
                self.record_args(
                    database_path,
                    Path("wiki/sources/missing.md"),
                    message_ts="999.999",
                )
            )

    def test_record_command_rejects_source_outside_wiki_sources(self) -> None:
        database_path = self.create_database()
        source_path = Path(self.temporary_directory.name) / "outside.md"
        source_path.write_text("# Outside\n", encoding="utf-8")

        original_directory = Path.cwd()
        os.chdir(self.temporary_directory.name)
        self.addCleanup(lambda: os.chdir(original_directory))

        with self.assertRaisesRegex(ValueError, "under wiki/sources"):
            slack_ingest.record_command(
                self.record_args(database_path, Path("outside.md"))
            )

    def test_find_uningested_messages_returns_all_with_missing_manifest(self) -> None:
        database_path = self.create_database()
        messages = slack_ingest.fetch_canonical_messages(database_path)

        found = slack_ingest.find_uningested_messages(
            messages,
            set(),
            self.raw_dir,
        )

        self.assertEqual(found, messages)

    def test_find_uningested_messages_excludes_recorded_parent(self) -> None:
        database_path = self.create_database()
        messages = slack_ingest.fetch_canonical_messages(database_path)
        parent = next(message for message in messages if message.is_parent)
        ingested_keys = {slack_ingest.message_key(parent, self.raw_dir)}

        found = slack_ingest.find_uningested_messages(
            messages,
            ingested_keys,
            self.raw_dir,
        )

        self.assertNotIn(parent, found)
        self.assertEqual(len(found), len(messages) - 1)

    def test_find_uningested_messages_does_not_cross_archive_boundaries(self) -> None:
        first_database = self.create_database(name="slackdump_20260912_110311")
        second_database = self.create_database(name="slackdump_20260913_110311")
        first_messages = slack_ingest.fetch_canonical_messages(first_database)
        second_messages = slack_ingest.fetch_canonical_messages(second_database)
        ingested_keys = {slack_ingest.message_key(second_messages[0], self.raw_dir)}

        found = slack_ingest.find_uningested_messages(
            first_messages,
            ingested_keys,
            self.raw_dir,
        )

        self.assertEqual(found, first_messages)

    def test_find_uningested_messages_returns_empty_when_all_recorded(self) -> None:
        database_path = self.create_database()
        messages = slack_ingest.fetch_canonical_messages(database_path)
        ingested_keys = {
            slack_ingest.message_key(message, self.raw_dir) for message in messages
        }

        found = slack_ingest.find_uningested_messages(
            messages,
            ingested_keys,
            self.raw_dir,
        )

        self.assertEqual(found, [])

    def test_fetch_canonical_messages_keeps_latest_duplicate(self) -> None:
        database_path = self.create_database(include_duplicate=True)

        messages = slack_ingest.fetch_canonical_messages(database_path)

        matching = [message for message in messages if message.message_ts == "100.001"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].chunk_id, 2)
        self.assertEqual(matching[0].session_id, 2)

    def test_fetch_canonical_messages_groups_thread_broadcast_duplicates(self) -> None:
        database_path = self.create_database()
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                "INSERT INTO CHUNK (ID, SESSION_ID, TYPE_ID) VALUES (?, ?, ?)",
                (4, 2, 1),
            )
            connection.execute(
                """
                INSERT INTO MESSAGE
                    (ID, CHUNK_ID, CHANNEL_ID, TS, PARENT_ID, THREAD_TS,
                     IS_PARENT, TXT, DATA)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    7,
                    4,
                    "C1",
                    "100.002",
                    1,
                    "100.001",
                    False,
                    "reply",
                    '{"user":"U2","subtype":"thread_broadcast"}',
                ),
            )

        messages = slack_ingest.fetch_canonical_messages(database_path)

        matching = [message for message in messages if message.message_ts == "100.002"]
        self.assertEqual(len(matching), 1)
        self.assertEqual(matching[0].data["subtype"], "thread_broadcast")

    def test_fetch_canonical_messages_filters_by_channel(self) -> None:
        database_path = self.create_database()

        messages = slack_ingest.fetch_canonical_messages(
            database_path,
            channel_id="C2",
        )

        self.assertEqual(len(messages), 1)
        self.assertEqual(messages[0].channel_id, "C2")

    def test_fetch_canonical_messages_preserves_provenance(self) -> None:
        database_path = self.create_database()

        messages = slack_ingest.fetch_canonical_messages(database_path)

        parent = next(
            message for message in messages if message.message_ts == "100.001"
        )
        self.assertEqual(parent.chunk_id, 1)
        self.assertEqual(parent.session_id, 1)
        self.assertEqual(parent.chunk_type_id, 0)

    def test_resolve_author_prefers_profile_display_name(self) -> None:
        database_path = self.create_database()

        with slack_ingest.open_database(database_path) as connection:
            name = slack_ingest.resolve_author_name(connection, "U2")

        self.assertEqual(name, "Brent Holliday")

    def test_resolve_author_falls_back_to_real_name(self) -> None:
        database_path = self.create_database()

        with slack_ingest.open_database(database_path) as connection:
            name = slack_ingest.resolve_author_name(connection, "U1")

        self.assertEqual(name, "Alex Kelley")

    def test_resolve_author_falls_back_to_username(self) -> None:
        database_path = self.create_database()

        with slack_ingest.open_database(database_path) as connection:
            name = slack_ingest.resolve_author_name(connection, "U3")

        self.assertEqual(name, "username-only")

    def test_resolve_author_falls_back_to_id_for_unknown_or_malformed_users(
        self,
    ) -> None:
        database_path = self.create_database()

        with slack_ingest.open_database(database_path) as connection:
            self.assertEqual(
                slack_ingest.resolve_author_name(connection, "UNKNOWN"),
                "UNKNOWN",
            )
            self.assertEqual(
                slack_ingest.resolve_author_name(connection, "U4"),
                "malformed",
            )
            self.assertEqual(
                slack_ingest.resolve_author_name(connection, None),
                "<unknown>",
            )

    def test_format_message_preview_includes_resolved_author_and_thread_status(
        self,
    ) -> None:
        database_path = self.create_database()
        message = slack_ingest.fetch_messages(database_path)[1]

        formatted = slack_ingest.format_message_preview(message, "Brent Holliday")

        self.assertEqual(
            formatted,
            "[1970-01-01T00:01:40.002000Z] reply to "
            "1970-01-01T00:01:40.001000Z | Brent Holliday\n  reply",
        )

    def test_group_messages_combines_thread_parent_and_replies(self) -> None:
        database_path = self.create_database()
        messages = slack_ingest.fetch_canonical_messages(database_path)

        groups = slack_ingest.group_messages(messages)

        threaded_group = next(group for group in groups if group.thread_ts == "100.001")
        self.assertEqual(
            [message.message_ts for message in threaded_group.messages],
            ["100.001", "100.002"],
        )

    def test_group_messages_keeps_standalone_message_as_its_own_group(self) -> None:
        database_path = self.create_database()
        messages = slack_ingest.fetch_canonical_messages(database_path)

        groups = slack_ingest.group_messages(messages)

        standalone_group = next(group for group in groups if group.thread_ts is None)
        self.assertEqual(len(standalone_group.messages), 1)
        self.assertEqual(standalone_group.messages[0].message_ts, "101.001")

    def test_group_messages_orders_groups_and_messages_by_timestamp(self) -> None:
        database_path = self.create_database()
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                """
                INSERT INTO MESSAGE
                    (ID, CHUNK_ID, CHANNEL_ID, TS, PARENT_ID, THREAD_TS,
                     IS_PARENT, TXT, DATA)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    8,
                    1,
                    "C2",
                    "101.000",
                    None,
                    None,
                    False,
                    "earlier standalone",
                    '{"user":"U1"}',
                ),
            )

        messages = slack_ingest.fetch_canonical_messages(database_path)
        groups = slack_ingest.group_messages(messages)

        self.assertEqual(
            [group.messages[0].message_ts for group in groups],
            ["100.001", "101.000", "101.001"],
        )

    def test_parser_requires_inspect_command(self) -> None:
        parser = slack_ingest.build_parser()

        args = parser.parse_args(["inspect", "--raw-dir", "custom-raw"])

        self.assertEqual(args.command, "inspect")
        self.assertEqual(args.raw_dir, Path("custom-raw"))
        self.assertIsNone(args.database)

    def test_threads_command_prints_numbered_thread_groups(self) -> None:
        database_path = self.create_database()
        parser = slack_ingest.build_parser()
        args = parser.parse_args(["threads", "--database", str(database_path)])
        output = io.StringIO()

        with redirect_stdout(output):
            result = slack_ingest.threads_command(args)

        self.assertEqual(result, 0)
        rendered = output.getvalue()
        self.assertIn("Database: slackdump.sqlite", rendered)
        self.assertIn("Thread groups: 2", rendered)
        self.assertRegex(
            rendered,
            r"1\. .*C1.*1970-01-01T00:01:40\.001000Z.*2 messages.*Alex Kelley",
        )
        self.assertIn("parent | Alex Kelley", rendered)
        self.assertRegex(
            rendered,
            r"2\. .*C2.*1970-01-01T00:01:41\.001000Z.*1 message.*Alex Kelley.*",
        )
        self.assertIn("standalone | Alex Kelley", rendered)

    def test_threads_command_filters_thread_groups_by_channel(self) -> None:
        database_path = self.create_database()
        parser = slack_ingest.build_parser()
        args = parser.parse_args(
            [
                "threads",
                "--database",
                str(database_path),
                "--channel-id",
                "C1",
            ]
        )
        output = io.StringIO()

        with redirect_stdout(output):
            result = slack_ingest.threads_command(args)

        self.assertEqual(result, 0)
        rendered = output.getvalue()
        self.assertIn("Thread groups: 1", rendered)
        self.assertIn("C1", rendered)
        self.assertNotIn("C2", rendered)


def test_record_parser_requires_all_arguments(self) -> None:
    parser = slack_ingest.build_parser()

    with self.assertRaises(SystemExit):
        parser.parse_args(["record"])


def test_record_parser_accepts_all_required_arguments(self) -> None:
    parser = slack_ingest.build_parser()

    args = parser.parse_args(
        [
            "record",
            "--database",
            "raw/Slack/archive/slackdump.sqlite",
            "--channel-id",
            "C123",
            "--message-ts",
            "1787662025.876289",
            "--source-path",
            "wiki/sources/slack-C123-1787662025.876289.md",
        ]
    )

    self.assertEqual(args.command, "record")
    self.assertEqual(args.channel_id, "C123")
    self.assertEqual(args.message_ts, "1787662025.876289")
    self.assertEqual(
        args.source_path,
        Path("wiki/sources/slack-C123-1787662025.876289.md"),
    )


class SlackDecisionTests(SlackIngestTests):
    def test_skipped_thread_with_new_reply_returns_full_reactivated_thread(self) -> None:
        database_path = self.create_database()
        messages = slack_ingest.fetch_canonical_messages(database_path)
        threaded = [message for message in messages if message.thread_ts == "100.001"]
        skipped = {slack_ingest.message_key(threaded[0], self.raw_dir)}

        groups = slack_ingest.find_reactivated_thread_groups(
            messages, set(), skipped, self.raw_dir
        )

        self.assertEqual(len(groups), 1)
        self.assertTrue(groups[0].reactivated)
        self.assertEqual(groups[0].messages, threaded)

    def test_skipped_thread_without_new_reply_stays_hidden(self) -> None:
        database_path = self.create_database()
        messages = slack_ingest.fetch_canonical_messages(database_path)
        threaded = [message for message in messages if message.thread_ts == "100.001"]
        skipped = {slack_ingest.message_key(message, self.raw_dir) for message in threaded}

        groups = slack_ingest.find_reactivated_thread_groups(
            messages, set(), skipped, self.raw_dir
        )

        self.assertEqual(groups, [])

    def test_ingested_thread_with_new_reply_returns_full_reactivated_thread(self) -> None:
        database_path = self.create_database()
        messages = slack_ingest.fetch_canonical_messages(database_path)
        threaded = [message for message in messages if message.thread_ts == "100.001"]
        ingested = {slack_ingest.message_key(threaded[0], self.raw_dir)}

        groups = slack_ingest.find_reactivated_thread_groups(
            messages, ingested, set(), self.raw_dir
        )

        self.assertEqual(len(groups), 1)
        self.assertTrue(groups[0].reactivated)
        self.assertEqual(groups[0].messages, threaded)

    def test_message_decision_excludes_only_that_message(self) -> None:
        database_path = self.create_database()
        messages = slack_ingest.fetch_canonical_messages(database_path)
        skipped = {slack_ingest.message_key(messages[0], self.raw_dir)}
        remaining = slack_ingest.find_uningested_messages(
            messages, set(), self.raw_dir, skipped
        )
        self.assertNotIn(messages[0], remaining)
        self.assertEqual(len(remaining), len(messages) - 1)

    def test_subtype_rule_excludes_matching_messages(self) -> None:
        database_path = self.create_database(include_malformed_data=True)
        with sqlite3.connect(database_path) as connection:
            connection.execute(
                "UPDATE MESSAGE SET DATA = ? WHERE TS = ?",
                (json.dumps({"subtype": "channel_join", "user": "U1"}), "100.003"),
            )
            connection.commit()
        messages = slack_ingest.fetch_canonical_messages(database_path)
        remaining = slack_ingest.find_uningested_messages(
            messages, set(), self.raw_dir,
            rules=[{"scope": "subtype", "subtype": "channel_join", "decision": "skip"}],
        )
        self.assertNotIn("100.003", {m.message_ts for m in remaining})

    def test_subtype_rule_can_be_scoped_to_channel(self) -> None:
        message = slack_ingest.fetch_canonical_messages(self.create_database())[0]
        self.assertFalse(slack_ingest.message_matches_rules(message, [{
            "scope": "subtype", "subtype": "channel_join", "channel_id": "C2",
            "decision": "skip",
        }]))


if __name__ == "__main__":
    unittest.main()
