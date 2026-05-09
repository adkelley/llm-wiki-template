from __future__ import annotations

import subprocess
from datetime import UTC, datetime, timedelta

from errors import CommandError
from models import Envelope, MailConfig, Message
from parsers import (
    parse_account_names,
    parse_envelopes,
    parse_folder_names,
    parse_message,
)


def run_command(args: list[str]) -> str:
    try:
        result = subprocess.run(
            args,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
    except FileNotFoundError as exc:
        raise CommandError(f"Command not found: {args[0]}") from exc
    except subprocess.CalledProcessError as exc:
        message = exc.stderr.strip() or exc.stdout.strip() or str(exc)
        raise CommandError(f"Command failed: {' '.join(args)}\n{message}") from exc

    return result.stdout


def himalaya_version() -> str:
    return run_command(["himalaya", "--version"]).strip()


def himalaya_account_list() -> list[str]:
    output = run_command(["himalaya", "account", "list", "--output", "json"]).strip()
    return parse_account_names(output)


def himalaya_folder_list(account: str) -> list[str]:
    output = run_command(
        [
            "himalaya",
            "folder",
            "list",
            "--account",
            account,
            "--output",
            "json",
        ]
    ).strip()
    return parse_folder_names(output)


def scan_window_after_date(window_days: int, now: datetime | None = None) -> str:
    current = now if now is not None else datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    current = current.astimezone(UTC)

    cutoff = current.date() - timedelta(days=window_days)
    return cutoff.isoformat()


def envelope_list_query(window_days: int | None = None) -> list[str]:
    if window_days is not None:
        return [
            "after",
            scan_window_after_date(window_days),
            "order",
            "by",
            "date",
            "desc",
        ]
    return []


def himalaya_envelope_list(
    config: MailConfig,
    account: str,
    folder: str,
    window_days: int | None = None,
    page_size: int | None = None,
) -> list[Envelope]:
    effective_page_size = page_size or config.max_messages_per_folder

    output = run_command(
        [
            "himalaya",
            "envelope",
            "list",
            "--account",
            account,
            "--folder",
            folder,
            "--page-size",
            str(effective_page_size),
            "--output",
            "json",
            *envelope_list_query(window_days),
        ]
    ).strip()
    return parse_envelopes(output, account, folder)


def himalaya_message_read(account: str, folder: str, message_id: str) -> Message:
    output = run_command(
        [
            "himalaya",
            "message",
            "read",
            "--account",
            account,
            "--folder",
            folder,
            "--preview",
            "--output",
            "json",
            message_id,
        ]
    )
    return parse_message(output, account, folder, message_id)
