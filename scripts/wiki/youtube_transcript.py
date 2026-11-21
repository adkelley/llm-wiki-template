#!/usr/bin/env python3

import argparse
import html
import json
import re
import shutil
import subprocess
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse


class TranscriptError(Exception):
    """Expected failure that should be shown without python traceback."""


def clean_vtt_text(vtt: str) -> str:
    cleaned_lines: list[str] = []
    previous_line: str | None = None

    for line in vtt.splitlines():
        line = line.strip()

        if not line:
            continue

        if line == "WEBVTT" or line.startswith("WEBVTT"):
            continue

        if "-->" in line:
            continue

        if line.isdigit():
            continue

        if line.startswith(("Kind:", "Language:")):
            continue

        line = re.sub(r"<\d{2}:\d{2}:\d{2}\.\d{3}>", "", line)
        line = re.sub(r"<\d{2}:\d{2}\.\d{3}>", "", line)
        line = re.sub(r"</?c(?:\.[^>]*)?>", "", line)
        line = re.sub(r"<[^>]+>", " ", line)
        line = html.unescape(line)
        line = re.sub(r"\s+", " ", line).strip()

        if not line:
            continue

        if line == previous_line:
            continue

        cleaned_lines.append(line)
        previous_line = line
    return "\n".join(cleaned_lines)


def utc_now_iso() -> str:
    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return timestamp.replace("+00:00", "Z")


def slugify(value: str, fallback: str = "youtube-video") -> str:
    slug = value.lower()
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug or fallback


def extract_video_id(url: str) -> str:
    parsed = urlparse(url)

    if parsed.hostname in {"www.youtube.com", "youtube.com", "m.youtube.com"}:
        query = parse_qs(parsed.query)
        if "v" in query and query["v"]:
            return query["v"][0]

        parts = parsed.path.strip("/").split("/")
        if len(parts) >= 2 and parts[0] in {"embed", "shorts"}:
            return parts[1]

    if parsed.hostname == "youtu.be":
        return parsed.path.strip("/").split("/")[0]

    return "unknown-id"


def format_upload_date(upload_date: str | None) -> str:
    if not upload_date:
        return "undated"

    if re.fullmatch(r"\d{8}", upload_date):
        return f"{upload_date[0:4]}-{upload_date[4:6]}-{upload_date[6:8]}"

    return "undated"


def require_yt_dlp() -> str:
    executable = shutil.which("yt-dlp")
    if executable is None:
        raise TranscriptError(
            "yt-dlp was not found on PATH. Install yt-dlp using the official "
            "instructions for your operating system, then confirm `yt-dlp --version` "
            "works in this shell."
        )

    return executable


def fetch_metadata(yt_dlp: str, url: str) -> dict[str, Any]:
    result = subprocess.run(
        [yt_dlp, "--dump-single-json", "--skip-download", url],
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise TranscriptError(f"yt-dlp failed while reading metadata:\n{message}")

    try:
        metadata = json.loads(result.stdout)
    except json.JSONDecodeError as error:
        raise TranscriptError(f"yt-dlp output is not valid JSON: {error}") from error

    if not isinstance(metadata, dict):
        raise TranscriptError("yt-dlp returned unexpected metadata")

    return metadata


def find_vtt_file(directory: Path) -> Path:
    candidates = sorted(directory.glob("*.vtt"))
    if not candidates:
        raise TranscriptError("yt-dlp did not produce a .vtt subtitle file.")
    return candidates[0]


def download_vtt(
    yt_dlp: str,
    url: str,
    temp_dir: Path,
    lang: str,
    sub_format: str,
) -> Path:
    output_template = temp_dir / "subs.%(ext)s"
    result = subprocess.run(
        [
            yt_dlp,
            "--skip-download",
            "--write-auto-subs",
            "--sub-langs",
            lang,
            "--sub-format",
            sub_format,
            "-o",
            output_template.as_posix(),
            url,
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        message = result.stderr.strip() or result.stdout.strip()
        raise TranscriptError(f"yt-dlp failed while downloading subtitles:\n{message}")

    return find_vtt_file(temp_dir)


def raw_markdown(
    title: str,
    url: str,
    video_id: str,
    published: str,
    transcript: str,
) -> str:
    return (
        f"Title: {title}\n"
        "Source: YouTube\n"
        f"URL: {url}\n"
        f"Video ID: {video_id}\n"
        f"Published: {published}\n"
        f"Captured: {utc_now_iso()}\n"
        "\n"
        f"{transcript}\n"
    )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create a raw Markdown transcript from a WebVTT file or YouTube URL."
    )
    parser.add_argument("source", help="input .vtt file path or YouTube URL")
    parser.add_argument(
        "--output", type=Path, help="optional file to write raw Markdown output"
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("raw"),
        help="directory for generated raw Markdown output",
    )
    parser.add_argument(
        "--title", default="YouTube video", help="title for raw Markdown output"
    )
    parser.add_argument("--url", default="unknown", help="source YouTube URL")
    parser.add_argument(
        "--published",
        default="undated",
        help="published date for raw Markdown metadata, ideally YYYY-MM-DD",
    )
    parser.add_argument("--lang", default="en", help="subtitle language to download")
    parser.add_argument(
        "--sub-format", default="vtt", help="subtitle format to request"
    )

    args = parser.parse_args()

    try:
        title = args.title
        url = args.url
        video_id = extract_video_id(url)
        published = args.published

        source_path = Path(args.source)
        if source_path.exists():
            vtt = source_path.read_text(encoding="utf-8")
        else:
            url = args.source
            video_id = extract_video_id(url)

            yt_dlp = require_yt_dlp()
            metadata = fetch_metadata(yt_dlp, url)

            title = str(metadata.get("title") or title)
            url = str(metadata.get("webpage_url") or url)
            video_id = str(metadata.get("id") or video_id)

            metadata_published = format_upload_date(metadata.get("upload_date"))
            if metadata_published != "undated":
                published = metadata_published

            with tempfile.TemporaryDirectory() as temp_name:
                vtt_path = download_vtt(
                    yt_dlp=yt_dlp,
                    url=url,
                    temp_dir=Path(temp_name),
                    lang=args.lang,
                    sub_format=args.sub_format,
                )
                vtt = vtt_path.read_text(encoding="utf-8")

        transcript = clean_vtt_text(vtt)
        if not transcript:
            raise TranscriptError(
                "subtitle file was read, but cleaned transcript is empty"
            )

        output_path = args.output
        if output_path is None:
            filename = (
                f"{slugify(published, 'undated')}-"
                f"{slugify(title)}-"
                f"{slugify(video_id, 'unknown-id')}.md"
            )
            output_path = args.output_dir / filename

        if output_path.exists():
            print(
                f"youtube_transcript: refusing to overwrite existing file: {output_path}"
            )
            return 1

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(
            raw_markdown(title, url, video_id, published, transcript),
            encoding="utf-8",
        )

        print(f"Created: {output_path}")
        return 0
    except TranscriptError as error:
        print(f"youtube_transcript: {error}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
