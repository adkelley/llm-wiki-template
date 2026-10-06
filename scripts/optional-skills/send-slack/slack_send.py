import argparse
import json
import pathlib
import re
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass


class CredentialError(Exception):
    """Raised when a credential is not found in the credentials file."""


class ChannelResolutionError(Exception):
    """Raised when a channel cannot be resolved."""


class SlackApiError(Exception):
    """Raised when the Slack API returns an error."""


@dataclass(frozen=True)
class Credentials:
    token: str
    cookie: str


DEFAULT_CREDENTIALS_PATH = (
    pathlib.Path.home() / ".cache" / "slackdump" / "slackdump_garibaldi.env"
)
CONVERSATIONS_LIST_URL = "https://slack.com/api/conversations.list"
CHAT_POST_MESSAGE_URL = "https://slack.com/api/chat.postMessage"

TIMESTAMP_REGEX = re.compile(r"\d+\.\d{6}")
CHANNEL_ID_REGEX = re.compile(r"[CDG][A-Z0-9]+")


def cookie_header(credentials: Credentials) -> str:
    if credentials.cookie.startswith("d="):
        return credentials.cookie
    return f"d={credentials.cookie}"


def load_credentials(path: pathlib.Path) -> Credentials:
    if not path.is_file():
        raise CredentialError(f"Credentials file not found: {path}")

    if path.stat().st_mode & 0o077 != 0:
        raise CredentialError(f"Credentials file is not readable: {path}")

    values = {}
    for line in path.read_text().splitlines():
        key, separator, value = line.partition("=")
        if separator:
            values[key.strip()] = value.strip()

    token = values.get("SLACK_TOKEN")
    if not token:
        raise CredentialError("token not found")
    if not token.startswith("xoxc"):
        raise CredentialError("token does not start with xoxc")

    cookie = values.get("SLACK_COOKIE")
    if not cookie:
        raise CredentialError("cookie not found")
    if not cookie.startswith("xoxd"):
        raise CredentialError("cookie does not start with xoxd")

    return Credentials(token, cookie)


# ---------------------------------------------------------------------------
# Slack API requests
# ---------------------------------------------------------------------------


def http_post(url: str, data: dict, headers: dict) -> dict:
    encoded_data = urllib.parse.urlencode(data).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=encoded_data,
        headers={
            **headers,
            "Content-Type": "application/x-www-form-urlencoded",
        },
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        return json.loads(response.read().decode("utf-8"))


def send_message(
    credentials: Credentials,
    channel_id: str,
    message: str,
    http_post,
    thread_ts: str | None = None,
) -> dict:
    data = {
        "token": credentials.token,
        "channel": channel_id,
        "text": message,
    }

    if thread_ts is not None:
        data["thread_ts"] = thread_ts

    response = http_post(
        CHAT_POST_MESSAGE_URL,
        data=data,
        headers={"Cookie": cookie_header(credentials)},
    )

    if not response["ok"]:
        error_code = response.get("error", "unknown_error")
        raise SlackApiError(f"Slack message send failed: {error_code}")

    return {
        "channel": response["channel"],
        "ts": response["ts"],
    }


def fetch_channels(credentials: Credentials, http_post) -> list[dict]:
    channels = []
    cursor = ""

    while True:
        data = {
            "token": credentials.token,
            "types": "public_channel,private_channel",
        }

        if cursor:
            data["cursor"] = cursor

        response = http_post(
            CONVERSATIONS_LIST_URL,
            data=data,
            headers={"Cookie": cookie_header(credentials)},
        )

        if not response["ok"]:
            error_code = response.get("error", "unknown_error")
            raise SlackApiError(f"Slack channel lookup failed: {error_code}")

        channels.extend(response["channels"])
        cursor = response.get("response_metadata", {}).get("next_cursor", "")

        if not cursor:
            break

    return channels


# ---------------------------------------------------------------------------
# Channel resolution
# ---------------------------------------------------------------------------


def resolve_channel(channel_ref: str, channels: list[dict]) -> dict:
    channel_ref = channel_ref.removeprefix("#")

    id_matches = [channel for channel in channels if channel["id"] == channel_ref]

    if id_matches:
        return id_matches[0]

    name_matches = [channel for channel in channels if channel["name"] == channel_ref]
    if len(name_matches) == 1:
        return name_matches[0]

    if len(name_matches) > 1:
        raise ChannelResolutionError("channel name is ambiguous")

    raise ChannelResolutionError(f"channel {channel_ref} not found")


# ---------------------------------------------------------------------------
# CLI definition and entry point
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group()

    parser.add_argument(
        "--channel",
        required=True,
        help="The channel to send the message to",
    )

    parser.add_argument(
        "--message",
        required=True,
        help="The message to send",
    )

    parser.add_argument(
        "--thread-ts",
        required=False,
        help="The timestamp of the thread to reply to",
    )

    mode.add_argument(
        "--dry-run",
        action="store_true",
        help="Preview without sending",
    )

    mode.add_argument(
        "--confirm",
        action="store_true",
        help="Allow the message to be sent",
    )

    return parser


def main(argv=None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit as error:
        if error.code == 0:
            raise
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "invalid_arguments",
                        "message": "Invalid command-line arguments",
                    },
                }
            )
        )
        return 2

    if args.thread_ts and not TIMESTAMP_REGEX.fullmatch(args.thread_ts):
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "invalid_arguments",
                        "message": "Invalid thread timestamp",
                    },
                }
            )
        )
        return 2

    if not args.message.strip():
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "invalid_arguments",
                        "message": "Message cannot be empty",
                    },
                }
            )
        )
        return 2

    if not args.channel.strip():
        print(
            json.dumps(
                {
                    "ok": False,
                    "error": {
                        "code": "invalid_arguments",
                        "message": "Channel cannot be empty",
                    },
                }
            )
        )
        return 2

    dry_run = not args.confirm

    try:
        credentials = load_credentials(DEFAULT_CREDENTIALS_PATH)

        if CHANNEL_ID_REGEX.fullmatch(args.channel):
            channel = {
                "id": args.channel,
                "name": args.channel,
            }
        else:
            channels = fetch_channels(
                credentials,
                http_post,
            )
            channel = resolve_channel(args.channel, channels)

        if dry_run:
            print(
                json.dumps(
                    {
                        "ok": True,
                        "operation": "send_message",
                        "dry_run": True,
                        "channel_id": channel["id"],
                        "channel_name": channel["name"],
                        "message": args.message,
                        "thread_ts": args.thread_ts,
                    }
                )
            )
            return 0

        result = send_message(
            credentials,
            channel["id"],
            args.message,
            http_post,
            args.thread_ts,
        )

        print(
            json.dumps(
                {
                    "ok": True,
                    "operation": "send_message",
                    "dry_run": False,
                    "channel_id": channel["id"],
                    "channel_name": channel["name"],
                    "message_ts": result["ts"],
                    "thread_ts": args.thread_ts,
                }
            )
        )
        return 0

    except CredentialError:
        error_code = "credentials_error"
        error_message = (
            "Unable to load Slack credentials. Check the Slackdump credentials file."
        )
    except ChannelResolutionError:
        error_code = "channel_error"
        error_message = "Slack channel was not found or matched multiple channels."
    except SlackApiError:
        error_code = "slack_api_error"
        error_message = (
            "Slack rejected the request. "
            "Your session may be expired or lack permission."
        )
    except urllib.error.URLError:
        error_code = "network_error"
        error_message = (
            "Unable to reach Slack. Check your network connection and try again."
        )

    print(
        json.dumps(
            {
                "ok": False,
                "error": {
                    "code": error_code,
                    "message": error_message,
                },
            }
        )
    )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
