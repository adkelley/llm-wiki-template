from __future__ import annotations

import re

from models import Envelope


def normalized_thread_subject(subject: str | None) -> str:
    if not subject:
        return ""

    value = subject.strip().lower()
    while True:
        updated = re.sub(r"^(re|fw|fwd):\s*", "", value).strip()
        if updated == value:
            return value
        value = updated


def same_thread_subject(left: Envelope, right: Envelope) -> bool:
    left_subject = normalized_thread_subject(left.subject)
    right_subject = normalized_thread_subject(right.subject)
    return bool(left_subject and left_subject == right_subject)


def thread_context_for_envelope(
    envelope: Envelope,
    envelopes: list[Envelope],
    limit: int,
) -> list[Envelope]:
    if limit <= 0:
        return []

    return [
        other
        for other in envelopes
        if other.id != envelope.id and same_thread_subject(envelope, other)
    ][:limit]
