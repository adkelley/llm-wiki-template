import contextlib
import importlib.util
import io
import json
import os
import sys
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import Mock, patch

MODULE_PATH = Path(__file__).resolve().parents[1] / "slack_send.py"
SPEC = importlib.util.spec_from_file_location("slack_send", MODULE_PATH)
if SPEC is None or SPEC.loader is None:  # pragma: no cover - import guard
    raise RuntimeError(f"Unable to load {MODULE_PATH}")
slack_send = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = slack_send
SPEC.loader.exec_module(slack_send)


def load_test_credentials(test_case: unittest.TestCase):
    handle = tempfile.NamedTemporaryFile(delete=False)
    path = Path(handle.name)
    try:
        handle.write(b"SLACK_TOKEN=xoxc-test-token\nSLACK_COOKIE=xoxd-test-cookie\n")
    finally:
        handle.close()

    os.chmod(path, 0o600)
    test_case.addCleanup(path.unlink, missing_ok=True)
    return slack_send.load_credentials(path)


class CredentialLoadingTests(unittest.TestCase):
    def write_credentials(self, text: str, mode: int = 0o600) -> Path:
        handle = tempfile.NamedTemporaryFile(delete=False)
        path = Path(handle.name)
        try:
            handle.write(text.encode("utf-8"))
        finally:
            handle.close()
        os.chmod(path, mode)
        self.addCleanup(path.unlink, missing_ok=True)
        return path

    def test_loads_required_slackdump_values(self):
        path = self.write_credentials(
            "SLACK_TOKEN=xoxc-test-token\nSLACK_COOKIE=xoxd-test-cookie\n"
        )

        credentials = slack_send.load_credentials(path)

        self.assertEqual(credentials.token, "xoxc-test-token")
        self.assertEqual(credentials.cookie, "xoxd-test-cookie")

    def test_rejects_missing_required_value(self):
        path = self.write_credentials("SLACK_TOKEN=xoxc-test-token\n")

        with self.assertRaises(slack_send.CredentialError):
            slack_send.load_credentials(path)

    def test_rejects_invalid_token_and_cookie_prefixes(self):
        cases = (
            "SLACK_TOKEN=oauth-token\nSLACK_COOKIE=xoxd-cookie\n",
            "SLACK_TOKEN=xoxc-token\nSLACK_COOKIE=session-cookie\n",
        )
        for content in cases:
            with self.subTest(content=content):
                path = self.write_credentials(content)
                with self.assertRaises(slack_send.CredentialError):
                    slack_send.load_credentials(path)

    def test_rejects_group_or_world_readable_file(self):
        path = self.write_credentials(
            "SLACK_TOKEN=xoxc-token\nSLACK_COOKIE=xoxd-cookie\n", 0o644
        )

        with self.assertRaises(slack_send.CredentialError):
            slack_send.load_credentials(path)

        @patch.object(
            slack_send,
            "load_credentials",
            side_effect=slack_send.CredentialError("credentials file not found"),
        )
        def test_reports_credential_error_as_json(self, load_credentials):
            exit_code, output = self.run_cli(
                [
                    "--channel",
                    "general",
                    "--message",
                    "hello",
                ]
            )

            self.assertEqual(exit_code, 1)
            self.assertFalse(output["ok"])
            self.assertEqual(output["error"]["code"], "credentials_error")
            self.assertNotIn("traceback", output)
            self.assertEqual(
                output["error"]["message"],
                "Unable to load Slack credentials. "
                "Check the Slackdump credentials file.",
            )
            self.assertEqual(
                output["error"]["message"],
                "Slack channel was not found or matched multiple channels.",
            )


class CliValidationTests(unittest.TestCase):
    def run_cli(self, argv):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            exit_code = slack_send.main(argv)
        self.assertEqual(stdout.getvalue().count("\n"), 1)
        return exit_code, json.loads(stdout.getvalue())

    def test_requires_channel_and_message(self):
        for argv in ([], ["--channel", "general"], ["--message", "hello"]):
            with self.subTest(argv=argv):
                exit_code, output = self.run_cli(argv)
                self.assertEqual(exit_code, 2)
                self.assertFalse(output["ok"])
                self.assertEqual(output["error"]["code"], "invalid_arguments")

    def test_rejects_empty_message(self):
        exit_code, output = self.run_cli(
            [
                "--channel",
                "general",
                "--message",
                "",
            ]
        )

        self.assertEqual(exit_code, 2)
        self.assertFalse(output["ok"])
        self.assertEqual(output["error"]["code"], "invalid_arguments")

    def test_rejects_whitespace_only_message(self):
        exit_code, output = self.run_cli(
            [
                "--channel",
                "general",
                "--message",
                "   ",
            ]
        )

        self.assertEqual(exit_code, 2)
        self.assertFalse(output["ok"])
        self.assertEqual(output["error"]["code"], "invalid_arguments")

    def test_rejects_whitespace_only_channel(self):
        exit_code, output = self.run_cli(
            [
                "--channel",
                "   ",
                "--message",
                "hello",
            ]
        )

        self.assertEqual(exit_code, 2)
        self.assertFalse(output["ok"])
        self.assertEqual(output["error"]["code"], "invalid_arguments")

    def test_rejects_conflicting_dry_run_and_confirm(self):
        exit_code, output = self.run_cli(
            [
                "--channel",
                "general",
                "--message",
                "hello",
                "--dry-run",
                "--confirm",
            ]
        )

        self.assertEqual(exit_code, 2)
        self.assertFalse(output["ok"])
        self.assertEqual(output["error"]["code"], "invalid_arguments")

    def test_rejects_invalid_thread_timestamp(self):
        exit_code, output = self.run_cli(
            [
                "--channel",
                "general",
                "--message",
                "hello",
                "--thread-ts",
                "not-a-timestamp",
            ]
        )

        self.assertEqual(exit_code, 2)
        self.assertFalse(output["ok"])
        self.assertEqual(output["error"]["code"], "invalid_arguments")

    def test_rejects_thread_timestamp_with_trailing_text(self):
        exit_code, output = self.run_cli(
            [
                "--channel",
                "general",
                "--message",
                "hello",
                "--thread-ts",
                "1712345678.123456-extra",
            ]
        )

        self.assertEqual(exit_code, 2)
        self.assertFalse(output["ok"])
        self.assertEqual(output["error"]["code"], "invalid_arguments")

    @patch.object(slack_send, "send_message")
    @patch.object(slack_send, "fetch_channels")
    @patch.object(slack_send, "load_credentials")
    def test_accepts_valid_thread_timestamp(
        self,
        load_credentials,
        fetch_channels,
        send_message,
    ):
        load_credentials.return_value = slack_send.Credentials(
            token="xoxc-test-token",
            cookie="xoxd-test-cookie",
        )
        fetch_channels.return_value = [
            {"id": "C123", "name": "general"},
        ]
        send_message.return_value = {
            "channel": "C123",
            "ts": "1712345678.123456",
        }

        exit_code, output = self.run_cli(
            [
                "--channel",
                "general",
                "--message",
                "hello",
                "--thread-ts",
                "1712345678.000001",
                "--confirm",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(output["ok"])
        self.assertEqual(output["thread_ts"], "1712345678.000001")
        send_message.assert_called_once_with(
            load_credentials.return_value,
            "C123",
            "hello",
            slack_send.http_post,
            "1712345678.000001",
        )

    @patch.object(slack_send, "send_message")
    @patch.object(slack_send, "fetch_channels")
    @patch.object(slack_send, "load_credentials")
    def test_defaults_to_dry_run(
        self,
        load_credentials,
        fetch_channels,
        send_message,
    ):
        load_credentials.return_value = slack_send.Credentials(
            token="xoxc-test-token",
            cookie="xoxd-test-cookie",
        )
        fetch_channels.return_value = [
            {"id": "C123", "name": "general"},
        ]

        exit_code, output = self.run_cli(
            [
                "--channel",
                "general",
                "--message",
                "hello",
            ]
        )

        self.assertEqual(output["channel_id"], "C123")
        self.assertEqual(output["channel_name"], "general")
        self.assertEqual(output["message"], "hello")
        self.assertIsNone(output["thread_ts"])
        self.assertEqual(exit_code, 0)
        self.assertTrue(output["ok"])
        self.assertTrue(output["dry_run"])
        send_message.assert_not_called()

    @patch.object(slack_send, "send_message")
    @patch.object(slack_send, "fetch_channels")
    @patch.object(slack_send, "load_credentials")
    def test_confirm_disables_dry_run(
        self,
        load_credentials,
        fetch_channels,
        send_message,
    ):
        load_credentials.return_value = slack_send.Credentials(
            token="xoxc-test-token",
            cookie="xoxd-test-cookie",
        )
        fetch_channels.return_value = [
            {"id": "C123", "name": "general"},
        ]
        send_message.return_value = {
            "channel": "C123",
            "ts": "1712345678.123456",
        }

        exit_code, output = self.run_cli(
            [
                "--channel",
                "general",
                "--message",
                "hello",
                "--confirm",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(output["ok"])
        self.assertFalse(output["dry_run"])
        send_message.assert_called_once()

    @patch.object(slack_send, "send_message")
    @patch.object(slack_send, "fetch_channels")
    @patch.object(slack_send, "load_credentials")
    def test_confirmed_cli_send(
        self,
        load_credentials,
        fetch_channels,
        send_message,
    ):
        load_credentials.return_value = slack_send.Credentials(
            token="xoxc-test-token",
            cookie="xoxd-test-cookie",
        )
        fetch_channels.return_value = [
            {"id": "C123", "name": "general"},
        ]
        send_message.return_value = {
            "channel": "C123",
            "ts": "1712345678.123456",
        }

        exit_code, output = self.run_cli(
            [
                "--channel",
                "#general",
                "--message",
                "Hello",
                "--confirm",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(output["ok"])
        self.assertFalse(output["dry_run"])
        self.assertEqual(output["channel_id"], "C123")
        self.assertEqual(output["message_ts"], "1712345678.123456")

        send_message.assert_called_once()

    @patch.object(slack_send, "send_message")
    @patch.object(slack_send, "fetch_channels")
    @patch.object(slack_send, "load_credentials")
    def test_confirmed_channel_id_send_skips_channel_lookup(
        self,
        load_credentials,
        fetch_channels,
        send_message,
    ):
        load_credentials.return_value = slack_send.Credentials(
            token="xoxc-test-token",
            cookie="xoxd-test-cookie",
        )
        send_message.return_value = {
            "channel": "C123",
            "ts": "1712345678.123456",
        }

        exit_code, output = self.run_cli(
            [
                "--channel",
                "C123",
                "--message",
                "hello",
                "--confirm",
            ]
        )

        self.assertEqual(exit_code, 0)
        self.assertTrue(output["ok"])
        self.assertEqual(output["channel_id"], "C123")
        fetch_channels.assert_not_called()
        send_message.assert_called_once()

    @patch.object(slack_send, "fetch_channels")
    @patch.object(slack_send, "load_credentials")
    def test_reports_channel_resolution_error_as_json(
        self,
        load_credentials,
        fetch_channels,
    ):
        load_credentials.return_value = slack_send.Credentials(
            token="xoxc-test-token",
            cookie="xoxd-test-cookie",
        )
        fetch_channels.return_value = [
            {"id": "C123", "name": "general"},
        ]

        exit_code, output = self.run_cli(
            [
                "--channel",
                "missing",
                "--message",
                "hello",
            ]
        )

        self.assertEqual(exit_code, 1)
        self.assertFalse(output["ok"])
        self.assertEqual(output["error"]["code"], "channel_error")

        @patch.object(slack_send, "fetch_channels")
        @patch.object(slack_send, "load_credentials")
        def test_reports_slack_api_error_as_json(
            self,
            load_credentials,
            fetch_channels,
        ):
            load_credentials.return_value = slack_send.Credentials(
                token="xoxc-test-token",
                cookie="xoxd-test-cookie",
            )
            fetch_channels.side_effect = slack_send.SlackApiError(
                "invalid_auth: xoxc-secret-token"
            )

            exit_code, output = self.run_cli(
                [
                    "--channel",
                    "general",
                    "--message",
                    "hello",
                ]
            )

            self.assertEqual(exit_code, 1)
            self.assertFalse(output["ok"])
            self.assertEqual(
                output["error"]["message"],
                "Slack rejected the request. "
                "Your session may be expired or lack permission.",
            )
            self.assertNotIn("xoxc-secret-token", json.dumps(output))

    @patch.object(slack_send, "fetch_channels")
    @patch.object(slack_send, "load_credentials")
    def test_reports_network_error_as_json(
        self,
        load_credentials,
        fetch_channels,
    ):
        load_credentials.return_value = slack_send.Credentials(
            token="xoxc-test-token",
            cookie="xoxd-test-cookie",
        )
        fetch_channels.side_effect = urllib.error.URLError(
            "network details should not leak"
        )

        exit_code, output = self.run_cli(
            [
                "--channel",
                "general",
                "--message",
                "hello",
            ]
        )

        self.assertEqual(exit_code, 1)
        self.assertFalse(output["ok"])
        self.assertEqual(output["error"]["code"], "network_error")
        self.assertNotIn("network details", json.dumps(output))
        self.assertEqual(
            output["error"]["message"],
            "Unable to reach Slack. Check your network connection and try again.",
        )

    @patch.object(slack_send, "send_message")
    @patch.object(slack_send, "fetch_channels")
    @patch.object(slack_send, "load_credentials")
    def test_reports_send_api_error_as_json(
        self,
        load_credentials,
        fetch_channels,
        send_message,
    ):
        load_credentials.return_value = slack_send.Credentials(
            token="xoxc-test-token",
            cookie="xoxd-test-cookie",
        )
        fetch_channels.return_value = [
            {"id": "C123", "name": "general"},
        ]
        send_message.side_effect = slack_send.SlackApiError(
            "message send failed: secret should not leak"
        )

        exit_code, output = self.run_cli(
            [
                "--channel",
                "general",
                "--message",
                "hello",
                "--confirm",
            ]
        )

        self.assertEqual(exit_code, 1)
        self.assertFalse(output["ok"])
        self.assertEqual(output["error"]["code"], "slack_api_error")
        self.assertNotIn("secret should not leak", json.dumps(output))

    @patch.object(slack_send, "send_message")
    @patch.object(slack_send, "fetch_channels")
    @patch.object(slack_send, "load_credentials")
    def test_reports_send_network_error_as_json(
        self,
        load_credentials,
        fetch_channels,
        send_message,
    ):
        load_credentials.return_value = slack_send.Credentials(
            token="xoxc-test-token",
            cookie="xoxd-test-cookie",
        )
        fetch_channels.return_value = [
            {"id": "C123", "name": "general"},
        ]
        send_message.side_effect = urllib.error.URLError(
            "transport details should not leak"
        )

        exit_code, output = self.run_cli(
            [
                "--channel",
                "general",
                "--message",
                "hello",
                "--confirm",
            ]
        )

        self.assertEqual(exit_code, 1)
        self.assertFalse(output["ok"])
        self.assertEqual(output["error"]["code"], "network_error")
        self.assertNotIn("transport details", json.dumps(output))


class HttpTransportTests(unittest.TestCase):
    @patch.object(urllib.request, "urlopen")
    def test_http_post_builds_form_encoded_post_request(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b'{"ok": true, "channels": []}'

        result = slack_send.http_post(
            "https://slack.com/api/conversations.list",
            data={
                "token": "xoxc-test-token",
                "types": "public_channel,private_channel",
            },
            headers={"Cookie": "d=xoxd-test-cookie"},
        )

        self.assertEqual(result, {"ok": True, "channels": []})
        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_method(), "POST")
        self.assertEqual(
            request.data,
            b"token=xoxc-test-token&types=public_channel%2Cprivate_channel",
        )
        self.assertEqual(request.get_header("Cookie"), "d=xoxd-test-cookie")
        self.assertEqual(
            request.get_header("Content-type"),
            "application/x-www-form-urlencoded",
        )
        self.assertEqual(urlopen.call_args.kwargs["timeout"], 30)


class ChannelResolutionTests(unittest.TestCase):
    def test_resolves_unique_channel_name(self):
        channel = slack_send.resolve_channel(
            "#general",
            channels=[
                {"id": "C123", "name": "general"},
                {"id": "C456", "name": "random"},
            ],
        )

        self.assertEqual(channel["id"], "C123")
        self.assertEqual(channel["name"], "general")

    def test_resolves_channel_id(self):
        channel = slack_send.resolve_channel(
            "C456",
            channels=[
                {"id": "C123", "name": "general"},
                {"id": "C456", "name": "random"},
            ],
        )

        self.assertEqual(channel["id"], "C456")
        self.assertEqual(channel["name"], "random")

    def test_rejects_ambiguous_channel_name(self):
        with self.assertRaises(slack_send.ChannelResolutionError):
            slack_send.resolve_channel(
                "general",
                channels=[
                    {"id": "C123", "name": "general"},
                    {"id": "C456", "name": "general"},
                ],
            )

    def test_rejects_unknown_channel(self):
        with self.assertRaises(slack_send.ChannelResolutionError):
            slack_send.resolve_channel(
                "missing",
                channels=[
                    {"id": "C123", "name": "general"},
                    {"id": "C456", "name": "random"},
                ],
            )

    def test_resolves_id_even_when_other_names_are_ambiguous(self):
        channel = slack_send.resolve_channel(
            "C456",
            channels=[
                {"id": "C123", "name": "general"},
                {"id": "C456", "name": "general"},
            ],
        )

        self.assertEqual(channel["id"], "C456")
        self.assertEqual(channel["name"], "general")


class ChannelFetchTests(unittest.TestCase):
    def test_fetches_channels_with_slackdump_credentials(self):
        credentials = load_test_credentials(self)
        http_post = Mock(
            return_value={
                "ok": True,
                "channels": [
                    {"id": "C123", "name": "general"},
                    {"id": "C456", "name": "random"},
                ],
            }
        )

        channels = slack_send.fetch_channels(credentials, http_post=http_post)

        self.assertEqual(
            channels,
            [
                {"id": "C123", "name": "general"},
                {"id": "C456", "name": "random"},
            ],
        )
        http_post.assert_called_once_with(
            "https://slack.com/api/conversations.list",
            data={
                "token": "xoxc-test-token",
                "types": "public_channel,private_channel",
            },
            headers={"Cookie": "d=xoxd-test-cookie"},
        )

    def test_rejects_failed_slack_response(self):
        credentials = load_test_credentials(self)

        http_post = Mock(
            return_value={
                "ok": False,
                "error": "invalid_auth",
            }
        )

        with self.assertRaises(slack_send.SlackApiError):
            slack_send.fetch_channels(credentials, http_post=http_post)

    def test_fetches_all_channel_pages(self):
        credentials = load_test_credentials(self)

        http_post = Mock(
            side_effect=[
                {
                    "ok": True,
                    "channels": [{"id": "C123", "name": "general"}],
                    "response_metadata": {"next_cursor": "cursor-2"},
                },
                {
                    "ok": True,
                    "channels": [{"id": "C456", "name": "random"}],
                    "response_metadata": {"next_cursor": ""},
                },
            ]
        )

        channels = slack_send.fetch_channels(credentials, http_post=http_post)

        self.assertEqual(
            channels,
            [
                {"id": "C123", "name": "general"},
                {"id": "C456", "name": "random"},
            ],
        )
        self.assertEqual(http_post.call_count, 2)
        self.assertEqual(
            http_post.call_args_list[1].kwargs["data"]["cursor"], "cursor-2"
        )

    def test_sends_message(self):
        # Load credentials from a temporary 0600 file.
        credentials = load_test_credentials(self)

        http_post = Mock(
            return_value={
                "ok": True,
                "ts": "1712345678.123456",
                "channel": "C123",
            }
        )

        result = slack_send.send_message(
            credentials,
            channel_id="C123",
            message="Hello from the wiki",
            http_post=http_post,
        )

        self.assertEqual(result["ts"], "1712345678.123456")
        http_post.assert_called_once_with(
            "https://slack.com/api/chat.postMessage",
            data={
                "token": "xoxc-test-token",
                "channel": "C123",
                "text": "Hello from the wiki",
            },
            headers={"Cookie": "d=xoxd-test-cookie"},
        )

    def test_sends_thread_reply(self):
        credentials = load_test_credentials(self)

        http_post = Mock(
            return_value={
                "ok": True,
                "ts": "1712345678.123456",
                "channel": "C123",
            }
        )

        result = slack_send.send_message(
            credentials,
            channel_id="C123",
            message="Following up",
            thread_ts="1712345678.000001",
            http_post=http_post,
        )

        self.assertEqual(result["ts"], "1712345678.123456")
        http_post.assert_called_once_with(
            "https://slack.com/api/chat.postMessage",
            data={
                "token": "xoxc-test-token",
                "channel": "C123",
                "text": "Following up",
                "thread_ts": "1712345678.000001",
            },
            headers={"Cookie": "d=xoxd-test-cookie"},
        )

    def test_rejects_failed_message_send(self):
        credentials = load_test_credentials(self)

        http_post = Mock(
            return_value={
                "ok": False,
                "error": "channel_not_found",
            }
        )

        with self.assertRaises(slack_send.SlackApiError):
            slack_send.send_message(
                credentials,
                channel_id="C123",
                message="Hello",
                http_post=http_post,
            )

    def test_returns_sanitized_message_result(self):
        credentials = load_test_credentials(self)

        http_post = Mock(
            return_value={
                "ok": True,
                "channel": "C123",
                "ts": "1712345678.123456",
                "message": {
                    "text": "Hello",
                    "token": "should-not-be-returned",
                },
            }
        )

        result = slack_send.send_message(
            credentials,
            channel_id="C123",
            message="Hello",
            http_post=http_post,
        )

        self.assertEqual(
            result,
            {
                "channel": "C123",
                "ts": "1712345678.123456",
            },
        )
        self.assertNotIn("message", result)


if __name__ == "__main__":
    unittest.main()
