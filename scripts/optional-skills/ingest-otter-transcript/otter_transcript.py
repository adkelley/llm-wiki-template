import argparse
import json
import os
import re
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class OtterTranscriptError(Exception):
    """Expected user-facing error."""


def utc_now_iso() -> str:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return timestamp.replace("+00:00", "Z")


def slugify(value: str, fallback: str = "otter-transcript") -> str:
    slug = value.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or fallback


def title_matches(conversation: dict[str, Any], title_query: str) -> bool:
    if not title_query:
        return True

    title = str(conversation.get("title") or "")
    return title_query.lower() in title.lower()


def date_matches(conversation: dict[str, Any], date_query: str) -> bool:
    if not date_query:
        return True

    created_at = str(conversation.get("created_at") or "")
    return created_at.startswith(date_query)


def conversation_emails(conversation: dict[str, Any]) -> set[str]:
    emails: set[str] = set()

    owner = conversation.get("owner")
    if isinstance(owner, dict):
        email = owner.get("email")
        if isinstance(email, str):
            emails.add(email.lower())

    for guest in conversation.get("calendar_guests") or []:
        if isinstance(guest, dict):
            email = guest.get("email")
            if isinstance(email, str):
                emails.add(email.lower())

    for shared in conversation.get("shared_emails") or []:
        if isinstance(shared, dict):
            email = shared.get("email")
            if isinstance(email, str):
                emails.add(email.lower())

            user = shared.get("user")
            if isinstance(user, dict):
                user_email = user.get("email")
                if isinstance(user_email, str):
                    emails.add(user_email.lower())

    return emails


def email_matches(conversation: dict[str, Any], email_query: str) -> bool:
    if not email_query:
        return True

    return email_query.lower() in conversation_emails(conversation)


def http_error_message(error: urllib.error.HTTPError) -> str:
    body = error.read().decode("utf-8", errors="replace").strip()

    if error.code in {401, 403}:
        message = (
            f"Otter API returned {error.code}. The API key is missing, invalid, "
            "or not authorized for this workspace or conversation."
        )
    elif error.code == 404:
        message = (
            "Otter API returned 404. The conversation was not found or is not "
            "accessible with this API key."
        )
    elif error.code == 429:
        message = "Otter API returned 429. Rate limit exceeded; retry later."
    else:
        message = f"Otter API returned HTTP {error.code}."

    if body:
        message = f"{message}\nResponse body:\n{body[:500]}"

    return message


def list_conversations(api_key: str) -> list[dict[str, Any]]:
    request = urllib.request.Request(
        "https://api.otter.ai/v1/conversations",
        headers={
            "Authorization": f"Bearer {api_key}",
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")

    except urllib.error.HTTPError as error:
        raise OtterTranscriptError(http_error_message(error)) from error
    except urllib.error.URLError as error:
        raise OtterTranscriptError(
            f"Could not reach Otter API: {error.reason}"
        ) from error

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise OtterTranscriptError(
            f"Otter API response was not valid JSON: {error}"
        ) from error

    data = payload.get("data")

    if not isinstance(data, list):
        raise OtterTranscriptError("Otter list response missing data list")

    return data


def fetch_conversation(api_key: str, conversation_id: str) -> dict[str, Any]:
    url = f"https://api.otter.ai/v1/conversations/{conversation_id}?include=transcript"
    headers = {"Authorization": f"Bearer {api_key}"}
    request = urllib.request.Request(
        url,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        raise OtterTranscriptError(http_error_message(error)) from error
    except urllib.error.URLError as error:
        raise OtterTranscriptError(
            f"Could not reach Otter API: {error.reason}"
        ) from error

    try:
        payload = json.loads(body)
    except json.JSONDecodeError as error:
        raise OtterTranscriptError(
            f"Otter API response was not valid JSON: {error}"
        ) from error

    data = payload.get("data")

    if not isinstance(data, dict):
        raise OtterTranscriptError("Otter conversation response missing data object")

    return data


def date_from_created_at(created_at: str | None) -> str:
    if not created_at:
        return "undated"

    match = re.match(r"^(\d{4}-\d{2}-\d{2})", created_at)
    if match:
        return match.group(1)

    return "undated"


def raw_output_path(conversation: dict[str, Any], raw_output_dir: Path) -> Path:
    created_date = date_from_created_at(conversation.get("created_at"))
    title_slug = slugify(str(conversation.get("title", "") or "Otter transcript"))
    id_slug = slugify(
        str(conversation.get("id", "") or "unknown-id"), fallback="unknown-id"
    )

    filename = f"{created_date}-otter-{title_slug}-{id_slug}.md"
    return raw_output_dir / filename


def transcript_from_conversation(conversation: dict[str, Any]) -> dict[str, Any]:
    relationships = conversation.get("relationships")
    if not isinstance(relationships, dict):
        raise OtterTranscriptError("Otter response missing relationships object")
    transcript = relationships.get("transcript")
    if not isinstance(transcript, dict):
        raise OtterTranscriptError("Otter response missing transcript object")

    content = transcript.get("content")
    if not isinstance(content, str) or not content.strip():
        raise OtterTranscriptError("Otter response missing transcript content")

    return transcript


def raw_markdown(conversation: dict[str, Any]) -> str:
    transcript = transcript_from_conversation(conversation)
    participant_emails = sorted(conversation_emails(conversation))
    participant_email_text = ", ".join(participant_emails) or "unknown"

    return (
        f"Title: {conversation.get('title') or 'Otter transcript'}\n"
        "Source: Otter.ai Public API\n"
        f"URL: {conversation.get('url') or 'unknown'}\n"
        f"Conversation ID: {conversation.get('id') or 'unknown'}\n"
        f"Created: {conversation.get('created_at') or 'unknown'}\n"
        f"Participant emails: {participant_email_text}\n"
        f"Transcript format: {transcript.get('format') or 'txt'}\n"
        f"Captured: {utc_now_iso()}\n"
        "\n"
        f"{transcript['content']}\n"
    )


def write_raw_markdown(output_path: Path, markdown: str) -> None:
    if output_path.exists():
        raise OtterTranscriptError(
            f"refusing to overwrite existing file: {output_path}"
        )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(markdown, encoding="utf-8")


def main(argv: list[str] | None = None) -> int:

    parser = argparse.ArgumentParser(description="Ingest Otter transcript")
    parser.add_argument(
        "--conversation-id",
        type=str,
        help="Conversation ID",
    )
    parser.add_argument(
        "--title",
        type=str,
        help="Case-insensitive text to match in the conversation title",
    )
    parser.add_argument(
        "--date",
        type=str,
        help="Conversation date to match, YYYY-MM-DD",
    )
    parser.add_argument(
        "--email-address",
        type=str,
        help="Participant/owner/shared email address to match",
    )
    parser.add_argument(
        "--raw-output-dir",
        type=Path,
        default=Path("raw"),
        help="Directory for generated raw Markdown output",
    )
    args = parser.parse_args(argv)

    if not any(
        [
            args.conversation_id,
            args.title,
            args.date,
            args.email_address,
        ]
    ):
        parser.error(
            "provide at least one of --conversation-id, --title, --date, or --email-address"
        )

    try:
        api_key = os.environ.get("OTTER_API_KEY")
        if not api_key:
            raise OtterTranscriptError("OTTER_API_KEY environment variable not set")

        if args.conversation_id:
            full_conversation = fetch_conversation(api_key, args.conversation_id)
            markdown = raw_markdown(full_conversation)
            output_path = raw_output_path(full_conversation, args.raw_output_dir)
            write_raw_markdown(output_path, markdown)
            print(f"Created: {output_path}")
            return 0

        conversations = list_conversations(api_key)
        matches = [
            conversation
            for conversation in conversations
            if title_matches(conversation, args.title)
            and date_matches(conversation, args.date)
            and email_matches(conversation, args.email_address)
        ]
        print("match count: ", len(matches))

        if not matches:
            print("No matching conversations found")
            raise OtterTranscriptError("no matching conversations found")

        if len(matches) > 1:
            print(f"Multiple matching conversations found: {len(matches)}")
            for conversation in matches:
                print(
                    conversation["created_at"],
                    conversation["title"],
                    conversation["id"],
                )
            raise OtterTranscriptError(
                "narrow the search or rerun with --conversation-id"
            )

        conversation = matches[0]
        conversation_id = conversation["id"]
        full_conversation = fetch_conversation(api_key, conversation_id)
        markdown = raw_markdown(full_conversation)
        output_path = raw_output_path(full_conversation, args.raw_output_dir)
        write_raw_markdown(output_path, markdown)
        print(f"Created: {output_path}")
        return 0

    except OtterTranscriptError as error:
        print(f"otter_transcript: {error}")
        return 1



if __name__ == "__main__":
    raise SystemExit(main())
