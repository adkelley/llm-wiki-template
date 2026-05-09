from __future__ import annotations

import json
from datetime import UTC, datetime

from errors import ParseError
from models import Address, Envelope, Message


def parse_account_names(output: str) -> list[str]:
    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ParseError("Account list was not valid JSON") from exc

    if not isinstance(data, list):
        raise ParseError("Account list output must be a JSON list")

    names: list[str] = []
    for item in data:
        if not isinstance(item, dict):
            raise ParseError("Account list items must be JSON objects")

        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise ParseError("Account list item is missing a string name")

        names.append(name)

    return names


def parse_folder_names(output: str) -> list[str]:
    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ParseError("Folder list was not valid JSON") from exc

    if not isinstance(data, list):
        raise ParseError("Folder list output must be a JSON list")

    names: list[str] = []
    for item in data:
        if not isinstance(item, dict):
            raise ParseError("Folder list items must be JSON objects")

        name = item.get("name")
        if not isinstance(name, str) or not name:
            raise ParseError("Folder list item is missing a string name")

        names.append(name)

    return names


def parse_address(value: object) -> Address | None:
    if value is None:
        return None
    if not isinstance(value, dict):
        raise ParseError("Address must be a JSON object")

    name = value.get("name")
    addr = value.get("addr")

    if name is not None and not isinstance(name, str):
        raise ParseError("Name must be a string or null")
    if addr is not None and not isinstance(addr, str):
        raise ParseError("Address must be a string or null")

    return Address(name=name, addr=addr)


def parse_address_list(value: object) -> list[Address]:
    if value is None:
        return []
    if isinstance(value, dict):
        address = parse_address(value)
        return [] if address is None else [address]
    if isinstance(value, list):
        addresses: list[Address] = []
        for item in value:
            address = parse_address(item)
            if address is not None:
                addresses.append(address)
        return addresses
    raise ParseError("Address list must be an object, list, or null")


def parse_envelopes(output: str, account: str, folder: str) -> list[Envelope]:
    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ParseError(f"Envelope list output was not valid JSON: {exc}") from exc

    if not isinstance(data, list):
        raise ParseError("Envelope list output was not a list")

    envelopes: list[Envelope] = []
    for item in data:
        if not isinstance(item, dict):
            raise ParseError("Envelope list items must be JSON objects")

        envelope_id = item.get("id")
        if not isinstance(envelope_id, str) or not envelope_id:
            raise ParseError("Envelope item is missing a string id")

        flags = item.get("flags")
        if not isinstance(flags, list) or not all(
            isinstance(flag, str) for flag in flags
        ):
            raise ParseError("Envelope flags must be a list of strings")

        subject = item.get("subject")
        if subject is not None and not isinstance(subject, str):
            raise ParseError("Envelope subject must be a string or null")

        date = item.get("date")
        if date is not None and not isinstance(date, str):
            raise ParseError("Envelope date must be a string or null")

        has_attachment = item.get("has_attachment")
        if not isinstance(has_attachment, bool):
            raise ParseError("Envelope has_attachment must be a boolean")

        envelopes.append(
            Envelope(
                account=account,
                folder=folder,
                id=envelope_id,
                flags=flags,
                subject=subject,
                date=date,
                from_addr=parse_address(item.get("from")),
                to_addrs=parse_address_list(item.get("to")),
                has_attachment=has_attachment,
            )
        )

    return envelopes


def parse_message(output: str, account: str, folder: str, message_id: str) -> Message:
    try:
        data = json.loads(output)
    except json.JSONDecodeError as exc:
        raise ParseError("Message read output was not valid JSON") from exc

    if not isinstance(data, str):
        raise ParseError("Message read output must be a JSON string")

    return Message(
        account=account,
        folder=folder,
        id=message_id,
        text=data,
    )


def parse_utc_timestamp(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"

    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")

    return parsed.astimezone(UTC)
