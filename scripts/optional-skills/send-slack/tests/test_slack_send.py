import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "slack_send.py"
SPEC = importlib.util.spec_from_file_location("slack_send", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
slack_send = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(slack_send)


class ConfigTests(unittest.TestCase):
    def write_config(self, text: str, mode: int = 0o600) -> Path:
        handle = tempfile.NamedTemporaryFile(mode="w", delete=False)
        handle.write(text)
        handle.close()
        path = Path(handle.name)
        os.chmod(path, mode)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_loads_webhook_config(self):
        path = self.write_config(
            "SLACK_CHANNEL_ID=C1\nSLACK_CHANNEL_NAME=alpha\nSLACK_BOT_NAME=dobby\n"
            "SLACK_WEBHOOK_URL=https://hooks.slack.com/services/test\n"
        )
        values = slack_send.load_config(path)
        self.assertEqual(values["SLACK_CHANNEL_ID"], "C1")

    def test_rejects_insecure_config(self):
        path = self.write_config(
            "SLACK_CHANNEL_ID=C1\nSLACK_CHANNEL_NAME=alpha\nSLACK_BOT_NAME=dobby\n"
            "SLACK_WEBHOOK_URL=https://hooks.slack.com/services/test\n",
            0o644,
        )
        with self.assertRaises(slack_send.SendSlackError):
            slack_send.load_config(path)

    def test_rejects_missing_values(self):
        path = self.write_config("SLACK_CHANNEL_ID=C1\n")
        with self.assertRaises(slack_send.SendSlackError):
            slack_send.load_config(path)


class WebhookTests(unittest.TestCase):
    @patch.object(slack_send.subprocess, "run")
    def test_json_encodes_answer_and_calls_curl(self, run):
        slack_send.send_webhook("https://hooks.slack.com/services/test", 'say "hi"\n✓')
        command = run.call_args.args[0]
        payload = json.loads(command[command.index("--data") + 1])
        self.assertEqual(payload["text"], 'say "hi"\n✓')
        self.assertEqual(command[-1], "https://hooks.slack.com/services/test")

    @patch.object(slack_send.subprocess, "run", side_effect=OSError)
    def test_hides_webhook_failure_details(self, _run):
        with self.assertRaisesRegex(slack_send.SendSlackError, "curl is unavailable"):
            slack_send.send_webhook("https://hooks.slack.com/services/test", "hello")

    @patch.object(
        slack_send.subprocess,
        "run",
        side_effect=__import__("subprocess").CalledProcessError(6, "curl"),
    )
    def test_classifies_dns_failure_without_secret(self, _run):
        with self.assertRaisesRegex(slack_send.SendSlackError, "DNS lookup failed"):
            slack_send.send_webhook("https://hooks.slack.com/services/test", "hello")


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.manifest = Path(self.temp.name) / "manifest.jsonl"
        self.addCleanup(self.temp.cleanup)

    def test_manifest_records_success_identity(self):
        record = {
            "archive_path": "Slack/archive/slackdump.sqlite",
            "channel_id": "C1",
            "message_ts": "100.001",
            "thread_ts": None,
            "sent_at": "2026-10-07T00:00:00+00:00",
            "answer_sha256": "abc",
        }
        slack_send.append_manifest(record, self.manifest)
        self.assertEqual(json.loads(self.manifest.read_text())["message_ts"], "100.001")

    @patch.object(slack_send, "load_config", return_value={
        "SLACK_CHANNEL_ID": "C1",
        "SLACK_CHANNEL_NAME": "alpha",
        "SLACK_BOT_NAME": "dobby",
        "SLACK_WEBHOOK_URL": "https://hooks.slack.com/services/test",
    })
    @patch.object(slack_send, "discover_database", return_value=Path("archive.sqlite"))
    @patch.object(slack_send, "find_candidates", return_value=[])
    def test_candidates_command_returns_empty_json(self, _find, _discover, _config):
        with patch.object(slack_send, "load_ingest_module", return_value=object()):
            self.assertEqual(slack_send.main(["candidates"]), 0)

    def test_send_requires_confirmation(self):
        self.assertEqual(
            slack_send.main(["send", "--message-ts", "100.001", "--message", "hello"]),
            1,
        )


if __name__ == "__main__":
    unittest.main()
