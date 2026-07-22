#!/usr/bin/env python3

"""
Migrate wiki frontmatter and directory structure to schema v2.

The migration recursively inspects Markdown files under ``wiki/sources``,
``wiki/concepts``, and ``wiki/entities``. For source pages, it replaces
``author`` with the scalar ``attribution`` field, links plain ``source_file``
paths, and adds missing ``renditions`` and ``source_type`` fields without
inferring their values. For concept and entity pages, it replaces ``title``
with ``canonical_name`` and adds any missing name-list fields: ``aliases``,
``abbreviations``, ``known_variants``, and ``known_errors``. Comparison,
synthesis, and trace pages receive the current work-page provenance, status,
relationship, and question fields. Trace ranges are converted to top-level
``ingest_start`` and ``ingest_end`` scalar fields.
Contradiction-resolution pages in their current directory are validated and
receive missing stable IDs.

Preview mode validates and renders all pending changes without writing files.
Apply mode writes changes only after the complete migration plan is valid and
every pending page renders successfully. Existing name-list values, unrelated
frontmatter, Markdown bodies, UTF-8 encoding, and LF or CRLF line endings are
preserved. The migration performs no inference, lookup, normalization, or
reclassification of attribution or name values.
"""

import argparse
import json
import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PagePlan:
    path: Path
    page_type: str
    existing_source_file: str | None
    proposed_source_file: str | None
    missing_source_fields: tuple[str, ...]
    existing_author: str | None
    existing_attribution: str | None
    proposed_attribution: str | None
    existing_title: str | None
    existing_canonical_name: str | None
    proposed_canonical_name: str | None
    missing_name_fields: tuple[str, ...]
    errors: tuple[str, ...]
    proposed_fields: tuple[tuple[str, tuple[str, ...]], ...] = ()
    removed_fields: tuple[str, ...] = ()

    @property
    def needs_change(self) -> bool:
        if self.page_type == "source":
            return not self.errors and (
                self.existing_author is not None
                or self.existing_source_file != self.proposed_source_file
                or bool(self.missing_source_fields)
            )
        if self.page_type in {"entity", "concept"}:
            return not self.errors and (
                self.existing_title is not None
                or self.existing_canonical_name is None
                or bool(self.missing_name_fields)
            )
        return not self.errors and bool(self.proposed_fields or self.removed_fields)


@dataclass(frozen=True)
class MigrationPlan:
    pages: tuple[PagePlan, ...]
    errors: tuple[str, ...]
    create_paths: tuple[Path, ...] = ()

    @property
    def is_valid(self) -> bool:
        return not self.errors


NAME_FIELDS = (
    "aliases",
    "abbreviations",
    "known_variants",
    "known_errors",
)

SOURCE_TYPES = frozenset(
    {
        "article",
        "paper",
        "report",
        "presentation",
        "communication",
        "transcript",
        "recording",
        "book",
        "documentation",
        "dataset",
        "webpage",
        "note",
        "other",
        "unknown",
    }
)

ORIGINS = frozenset({"query", "ingest", "migration", "manual"})
WORK_STATUSES = frozenset({"active", "superseded", "deprecated"})
CONFIDENCES = frozenset({"high", "medium", "low"})
CONTRADICTION_STATUSES = frozenset(
    {"proposed", "open", "in-progress", "resolution-proposed", "resolved", "dismissed"}
)
PRIORITIES = frozenset({"low", "medium", "high"})

EMPTY_VALUES = (
    "",
    '""',
    "''",
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="migrate_v2",
        description=(
            "A preview-first migration that upgrades "
            "`wiki/entities/**/*.md`, `wiki/concepts/**/*.md`, "
            "`wiki/sources/**/*.md`, work pages, and contradiction-resolution "
            "pages, and creates required wiki directories."
        ),
    )
    parser.add_argument(
        "--wiki-dir",
        type=Path,
        default=Path("wiki"),
        help="location of the wiki to inspect and migrate",
    )

    parser.add_argument(
        "--apply",
        action="store_true",
        help="apply changes; otherwise only preview the migration",
    )

    parser.add_argument(
        "--json",
        action="store_true",
        help="emit the migration report as JSON",
    )

    return parser


def read_frontmatter(path: Path) -> dict[str, str]:
    text = path.read_text(encoding="utf-8")
    lines = text.splitlines()
    frontmatter: dict[str, str] = {}
    if not lines or lines[0] != "---":
        raise ValueError(f"{path}: missing opening frontmatter delimiter")

    closing_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line == "---":
            closing_index = index
            break
    if closing_index is None:
        raise ValueError(f"{path}: missing closing frontmatter delimiter")

    frontmatter_lines = lines[1:closing_index]
    for line in frontmatter_lines:
        if not line or line[0].isspace() or line.startswith("#"):
            continue

        key, separator, value = line.partition(":")
        if not separator:
            raise ValueError(f"{path}: malformed frontmatter line: {line!r}")

        key = key.strip()

        if key in frontmatter:
            raise ValueError(f"{path}: duplicate field: {key}")

        if separator:
            frontmatter[key] = value.strip()

    return frontmatter


def iter_pages(entity_dir: Path) -> Iterator[Path]:
    for path in sorted(entity_dir.rglob("*.md")):
        if path.is_file():
            yield path


def block_list_validation_error(path: Path, field_name: str) -> str | None:
    lines = path.read_text(encoding="utf-8").splitlines()
    invalid_list = f"{field_name} must be a list"
    invalid_item = f"{field_name} must contain non-empty scalar values"

    for index, line in enumerate(lines):
        if not line or line[0].isspace():
            continue

        key, separator, value = line.partition(":")
        if not separator:
            continue

        if key.strip() != field_name or value.strip():
            continue

        found_item = False

        for following_line in lines[index + 1 :]:
            if following_line == "---":
                return None if found_item else invalid_list

            if not following_line.strip():
                continue

            # A non-indenting line begins the next top-level frontmatter field
            if not following_line[0].isspace():
                return None if found_item else invalid_list

            stripped = following_line.lstrip()
            if stripped == "-":
                return invalid_item

            if not stripped.startswith("- "):
                return invalid_list

            item = stripped[2:].strip()
            quoted = len(item) >= 2 and item[0] == item[-1] and item[0] in ('"', "'")
            if (
                is_empty_value(item)
                or is_null_value(item)
                or is_collection_value(item)
                or (not quoted and (": " in item or item.endswith(":")))
            ):
                return invalid_item

            found_item = True

        return None if found_item else invalid_list

    return invalid_list


def is_collection_value(value: str | None) -> bool:
    if value is None:
        return False

    return (value.startswith("[") and value.endswith("]")) or (
        value.startswith("{") and value.endswith("}")
    )


def is_empty_value(value: str | None) -> bool:
    if value is None:
        return False

    return value.strip() in EMPTY_VALUES


def is_null_value(value: str | None) -> bool:
    if value is None:
        return False

    stripped = value.strip()
    return stripped == "~" or stripped.casefold() == "null"


def unquote_scalar(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def scalar_error(
    path: Path, field_name: str, value: str | None, *, allow_empty: bool = False
) -> str | None:
    if value is None:
        return None
    if not allow_empty and is_empty_value(value):
        return f"{path}: {field_name} must not be empty"
    if is_null_value(value):
        return f"{path}: {field_name} must not be null"
    if is_collection_value(value) or value == "":
        return f"{path}: {field_name} must be a scalar"
    if value in {">", ">-", ">+", "|", "|-", "|+"} and not allow_empty:
        lines = path.read_text(encoding="utf-8").splitlines()
        for index, line in enumerate(lines):
            key, separator, candidate = line.partition(":")
            if not separator or key.strip() != field_name or candidate.strip() != value:
                continue
            for following in lines[index + 1 :]:
                if following == "---" or (following and not following[0].isspace()):
                    break
                if following.strip():
                    return None
            return f"{path}: {field_name} must not be empty"
    return None


def enum_error(
    path: Path, field_name: str, value: str | None, allowed: frozenset[str]
) -> str | None:
    if value is None:
        return None
    if (
        is_empty_value(value)
        or is_null_value(value)
        or is_collection_value(value)
        or unquote_scalar(value) not in allowed
    ):
        return f"{path}: {field_name} must be one of: " + ", ".join(sorted(allowed))
    return None


def list_error(path: Path, field_name: str, value: str | None) -> str | None:
    if value is None or value == "[]":
        return None
    if value == "":
        error = block_list_validation_error(path, field_name)
        return f"{path}: {error}" if error is not None else None
    return f"{path}: {field_name} must be a list"


def slugify_filename(path: Path) -> str:
    normalized = unicodedata.normalize("NFKD", path.stem)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.casefold()).strip("-")
    if not slug:
        raise ValueError(f"{path}: filename does not produce a valid slug")
    return slug


def block_mapping_values(path: Path, field_name: str) -> dict[str, str] | None:
    lines = path.read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        key, separator, value = line.partition(":")
        if not separator or key.strip() != field_name or value.strip():
            continue
        result: dict[str, str] = {}
        for following in lines[index + 1 :]:
            if following == "---" or (following and not following[0].isspace()):
                break
            if not following.strip():
                continue
            nested_key, nested_separator, nested_value = following.strip().partition(":")
            if not nested_separator or nested_key in result:
                return None
            result[nested_key] = nested_value.strip()
        return result
    return None


def plan_work_page(
    path: Path, page_type: str, frontmatter: dict[str, str], errors: list[str]
) -> tuple[tuple[tuple[str, tuple[str, ...]], ...], tuple[str, ...]]:
    proposed: list[tuple[str, tuple[str, ...]]] = []
    removed: list[str] = []

    origin = frontmatter.get("origin")
    filed = frontmatter.get("filed_from_query")
    if origin is not None:
        error = enum_error(path, "origin", origin, ORIGINS)
        if error:
            errors.append(error)
    else:
        if filed is not None and unquote_scalar(filed).casefold() not in {"true", "false"}:
            errors.append(f"{path}: filed_from_query must be true or false")
        else:
            migrated_origin = (
                "query"
                if filed is not None
                and unquote_scalar(filed).casefold() == "true"
                else "manual"
            )
            proposed.append(("origin", (f"origin: {migrated_origin}",)))
    if filed is not None:
        removed.append("filed_from_query")

    status = frontmatter.get("status")
    if status is None:
        proposed.append(("status", ("status: active",)))
    else:
        error = enum_error(path, "status", status, WORK_STATUSES)
        if error:
            errors.append(error)

    for field_name in ("subjects", "sources", "related"):
        value = frontmatter.get(field_name)
        if value is None:
            if field_name == "sources":
                errors.append(f"{path}: missing sources")
            else:
                proposed.append((field_name, (f"{field_name}: []",)))
        else:
            error = list_error(path, field_name, value)
            if error:
                errors.append(error)

    if page_type in {"comparison", "synthesis"}:
        title = frontmatter.get("title")
        if title is None:
            errors.append(f"{path}: missing title")
        else:
            error = scalar_error(path, "title", title)
            if error:
                errors.append(error)

    question = frontmatter.get("question")
    if question is None:
        proposed.append(("question", ('question: ""',)))
    else:
        error = scalar_error(path, "question", question, allow_empty=True)
        if error:
            errors.append(error)

    if page_type in {"synthesis", "trace"}:
        confidence = frontmatter.get("confidence")
        if confidence is None:
            proposed.append(("confidence", ("confidence: low",)))
        else:
            error = enum_error(path, "confidence", confidence, CONFIDENCES)
            if error:
                errors.append(error)

    if page_type == "trace":
        concept = frontmatter.get("concept")
        title = frontmatter.get("title")
        if concept is not None:
            error = scalar_error(path, "concept", concept)
            if error:
                errors.append(error)
        if title is None:
            if concept is None:
                errors.append(f"{path}: missing title or concept")
            else:
                if scalar_error(path, "concept", concept) is None:
                    proposed.append(("title", (f"title: {concept}",)))
        else:
            error = scalar_error(path, "title", title)
            if error:
                errors.append(error)

        if concept is not None:
            removed.append("concept")
            if "subjects" not in frontmatter and not any(
                name == "subjects" for name, _ in proposed
            ):
                concept_text = unquote_scalar(concept)
                proposed.append(
                    ("subjects", ("subjects:", f'  - "[[{concept_text}]]"'))
                )
            elif "subjects" not in frontmatter:
                proposed = [item for item in proposed if item[0] != "subjects"]
                concept_text = unquote_scalar(concept)
                proposed.append(
                    ("subjects", ("subjects:", f'  - "[[{concept_text}]]"'))
                )

        ingest_range = frontmatter.get("ingest_range")
        flat_range_fields = ("ingest_start", "ingest_end")
        existing_flat_fields = {
            field_name for field_name in flat_range_fields if field_name in frontmatter
        }

        if ingest_range is not None and existing_flat_fields:
            errors.append(
                f"{path}: ingest_range must not coexist with ingest_start or ingest_end"
            )
        elif ingest_range is not None:
            if ingest_range == "":
                mapping = block_mapping_values(path, "ingest_range")
                if mapping is None or set(mapping) != {"start", "end"}:
                    errors.append(f"{path}: ingest_range must contain start and end")
                    mapping = None
                parts = None if mapping is None else (mapping["start"], mapping["end"])
            else:
                range_value = unquote_scalar(ingest_range)
                split_parts = [part.strip() for part in range_value.split("→")]
                if len(split_parts) != 2 or not all(split_parts):
                    errors.append(f"{path}: ingest_range must be START → END")
                    parts = None
                else:
                    parts = (split_parts[0], split_parts[1])

            if parts is not None:
                range_errors = [
                    scalar_error(path, field_name, value, allow_empty=True)
                    for field_name, value in zip(flat_range_fields, parts)
                ]
                errors.extend(error for error in range_errors if error)
                if not any(range_errors):
                    removed.append("ingest_range")
                    proposed.extend(
                        (
                            (field_name, (f"{field_name}: {value}",))
                            for field_name, value in zip(flat_range_fields, parts)
                        )
                    )
        else:
            for field_name in flat_range_fields:
                value = frontmatter.get(field_name)
                if value is None:
                    proposed.append((field_name, (f'{field_name}: ""',)))
                else:
                    error = scalar_error(path, field_name, value, allow_empty=True)
                    if error:
                        errors.append(error)

    return tuple(proposed), tuple(removed)


def plan_contradiction_page(
    path: Path, frontmatter: dict[str, str], errors: list[str]
) -> tuple[tuple[tuple[str, tuple[str, ...]], ...], tuple[str, ...]]:
    proposed: list[tuple[str, tuple[str, ...]]] = []
    stable_id = frontmatter.get("contradiction_resolution_id")
    try:
        expected_id = f"contradiction-resolution:{slugify_filename(path)}"
    except ValueError as error:
        errors.append(str(error))
        expected_id = None
    if stable_id is None and expected_id is not None:
        proposed.append(
            ("contradiction_resolution_id", (f"contradiction_resolution_id: {expected_id}",))
        )
    elif stable_id is not None and not re.fullmatch(
        r"contradiction-resolution:[a-z0-9]+(?:-[a-z0-9]+)*", stable_id
    ):
        errors.append(f"{path}: invalid contradiction_resolution_id: {stable_id!r}")

    for field_name, allowed in (
        ("status", CONTRADICTION_STATUSES),
        ("priority", PRIORITIES),
    ):
        value = frontmatter.get(field_name)
        if value is None:
            errors.append(f"{path}: missing {field_name}")
        else:
            error = enum_error(path, field_name, value, allowed)
            if error:
                errors.append(error)

    for field_name in ("subjects", "claims", "evidence", "log_references"):
        value = frontmatter.get(field_name)
        if value is None:
            errors.append(f"{path}: missing {field_name}")
        else:
            error = list_error(path, field_name, value)
            if error:
                errors.append(error)

    for field_name in ("title", "resolution_question", "created", "updated"):
        value = frontmatter.get(field_name)
        if value is None:
            errors.append(f"{path}: missing {field_name}")
        else:
            error = scalar_error(path, field_name, value)
            if error:
                errors.append(error)

    status = unquote_scalar(frontmatter.get("status", ""))
    if status == "resolved" and "resolution" not in frontmatter:
        errors.append(f"{path}: resolution is required when status is resolved")
    if status == "dismissed" and "dismissal_reason" not in frontmatter:
        errors.append(f"{path}: dismissal_reason is required when status is dismissed")
    for field_name in ("resolution", "dismissal_reason"):
        if field_name in frontmatter:
            error = scalar_error(path, field_name, frontmatter[field_name])
            if error:
                errors.append(error)

    return tuple(proposed), ()


def plan_page(path: Path, expected_type: str) -> PagePlan:
    errors: list[str] = []
    missing_name_fields: list[str] = []
    missing_source_fields: list[str] = []

    frontmatter_valid = True
    try:
        frontmatter = read_frontmatter(path)
    except ValueError as error:
        frontmatter = {}
        frontmatter_valid = False
        errors.append(str(error))

    page_type = frontmatter.get("type", expected_type)

    existing_source_file = None
    proposed_source_file = None

    existing_author = None
    existing_attribution = None
    proposed_attribution = None

    existing_title = None
    existing_canonical_name = None
    proposed_canonical_name = None
    proposed_fields: tuple[tuple[str, tuple[str, ...]], ...] = ()
    removed_fields: tuple[str, ...] = ()

    if frontmatter_valid:
        actual_type = frontmatter.get("type")
        if actual_type != expected_type:
            errors.append(
                f"{path}: expected type: {expected_type}, found {actual_type!r}"
            )
        if page_type == "source":
            existing_source_file = frontmatter.get("source_file")
            if existing_source_file is not None:
                source_value = existing_source_file
                if (
                    len(source_value) >= 2
                    and source_value[0] == source_value[-1]
                    and source_value[0] in ("'", '"')
                ):
                    source_value = source_value[1:-1]

                if source_value.startswith("[[") and source_value.endswith("]]"):
                    proposed_source_file = existing_source_file
                else:
                    proposed_source_file = f'"[[{source_value}]]"'

            renditions = frontmatter.get("renditions")
            if renditions is None:
                missing_source_fields.append("renditions")
            elif renditions == "[]":
                pass
            elif renditions == "":
                validation_error = block_list_validation_error(path, "renditions")
                if validation_error is not None:
                    errors.append(f"{path}: {validation_error}")
            else:
                errors.append(f"{path}: renditions must be a list")

            source_type = frontmatter.get("source_type")
            if source_type is None:
                missing_source_fields.append("source_type")
            elif (
                is_empty_value(source_type)
                or is_null_value(source_type)
                or is_collection_value(source_type)
                or unquote_scalar(source_type) not in SOURCE_TYPES
            ):
                errors.append(
                    f"{path}: source_type must be one of: "
                    + ", ".join(sorted(SOURCE_TYPES))
                )

            existing_author = frontmatter.get("author")
            if is_empty_value(existing_author):
                errors.append(f"{path}: author must not be empty")
            if is_null_value(existing_author):
                errors.append(f"{path}: author must not be null")
            if is_collection_value(existing_author):
                errors.append(f"{path}: author must be a scalar")
            existing_attribution = frontmatter.get("attribution")
            if is_empty_value(existing_attribution):
                errors.append(f"{path}: attribution must not be empty")
            if is_null_value(existing_attribution):
                errors.append(f"{path}: attribution must not be null")
            if is_collection_value(existing_attribution):
                errors.append(f"{path}: attribution must be a scalar")

            if existing_author is None and existing_attribution is None:
                errors.append(f"{path}: missing author or attribution")
            elif existing_attribution is None and existing_author is not None:
                proposed_attribution = existing_author
            else:
                proposed_attribution = existing_attribution
        elif page_type in {"entity", "concept"}:
            existing_title = frontmatter.get("title")
            if is_empty_value(existing_title):
                errors.append(f"{path}: title must not be empty")

            if is_null_value(existing_title):
                errors.append(f"{path}: title must not be null")

            if is_collection_value(existing_title):
                errors.append(f"{path}: title must be a scalar")

            existing_canonical_name = frontmatter.get("canonical_name")
            if is_empty_value(existing_canonical_name):
                errors.append(f"{path}: canonical_name must not be empty")

            if is_null_value(existing_canonical_name):
                errors.append(f"{path}: canonical_name must not be null")

            if is_collection_value(existing_canonical_name):
                errors.append(f"{path}: canonical_name must be a scalar")

            if existing_title is None and existing_canonical_name is None:
                errors.append(f"{path}: missing title or canonical_name")
            elif existing_canonical_name is None and existing_title is not None:
                proposed_canonical_name = existing_title
            else:
                proposed_canonical_name = existing_canonical_name
            for name_field in NAME_FIELDS:
                if name_field not in frontmatter:
                    missing_name_fields.append(name_field)
                    continue

                value = frontmatter[name_field]
                if value == "[]":
                    continue

                if value == "":
                    validation_error = block_list_validation_error(path, name_field)
                    if validation_error is None:
                        continue
                    errors.append(f"{path}: {validation_error}")
                    continue

                errors.append(f"{path}: {name_field} must be a list")
        elif page_type in {"comparison", "synthesis", "trace"}:
            proposed_fields, removed_fields = plan_work_page(
                path, page_type, frontmatter, errors
            )
        elif page_type == "contradiction-resolution":
            proposed_fields, removed_fields = plan_contradiction_page(
                path, frontmatter, errors
            )

    return PagePlan(
        path=path,
        page_type=page_type,
        existing_source_file=existing_source_file,
        proposed_source_file=proposed_source_file,
        missing_source_fields=tuple(missing_source_fields),
        existing_author=existing_author,
        existing_attribution=existing_attribution,
        proposed_attribution=proposed_attribution,
        existing_canonical_name=existing_canonical_name,
        proposed_canonical_name=proposed_canonical_name,
        existing_title=existing_title,
        missing_name_fields=tuple(missing_name_fields),
        errors=tuple(errors),
        proposed_fields=proposed_fields,
        removed_fields=removed_fields,
    )


def build_migration_plan(entities_dir: Path) -> MigrationPlan:
    pages: list[PagePlan] = []
    errors: list[str] = []
    create_paths: list[Path] = []

    # Validate and collect pages
    if not entities_dir.is_dir():
        return MigrationPlan(
            pages=(),
            errors=(f"{entities_dir}: entities directory does not exist",),
        )

    wiki_dir = entities_dir.parent
    concepts_dir = wiki_dir / "concepts"
    sources_dir = wiki_dir / "sources"
    page_directories: list[tuple[Path, str]] = [
        (entities_dir, "entity"),
        (concepts_dir, "concept"),
        (sources_dir, "source"),
        (wiki_dir / "comparisons", "comparison"),
        (wiki_dir / "syntheses", "synthesis"),
        (wiki_dir / "traces", "trace"),
        (
            wiki_dir / "tasks" / "contradiction-resolutions",
            "contradiction-resolution",
        ),
    ]
    for page_dir, page_type in page_directories:
        for path in iter_pages(page_dir):
            page = plan_page(path, page_type)
            pages.append(page)
            errors.extend(page.errors)

    contradiction_ids: dict[str, list[Path]] = {}
    for page in pages:
        if page.page_type != "contradiction-resolution" or page.errors:
            continue
        frontmatter = read_frontmatter(page.path)
        stable_id = frontmatter.get("contradiction_resolution_id")
        if stable_id is None:
            stable_id = f"contradiction-resolution:{slugify_filename(page.path)}"
        contradiction_ids.setdefault(stable_id, []).append(page.path)
    for stable_id, paths in sorted(contradiction_ids.items()):
        if len(paths) > 1:
            joined = ", ".join(str(path) for path in paths)
            errors.append(f"duplicate ID: {stable_id!r}: {joined}")

    for directory in (
        wiki_dir / "traces",
        wiki_dir / "tasks" / "contradiction-resolutions",
    ):
        if directory.exists() and not directory.is_dir():
            errors.append(f"{directory}: required directory path is not a directory")
        elif not directory.exists() or not any(directory.iterdir()):
            create_paths.append(directory / ".gitkeep")

    return MigrationPlan(
        pages=tuple(pages),
        errors=tuple(errors),
        create_paths=tuple(create_paths),
    )


def add_missing_name_fields(
    lines: list[str], insert_index: int, missing_fields: tuple[str, ...], ending: str
) -> None:
    for field in missing_fields:
        lines.insert(insert_index, f"{field}: []{ending}")
        insert_index += 1
    return None


def add_missing_source_fields(
    lines: list[str], insert_index: int, missing_fields: tuple[str, ...], ending: str
) -> None:
    values = {
        "renditions": "[]",
        "source_type": "unknown",
    }
    for field in missing_fields:
        lines.insert(insert_index, f"{field}: {values[field]}{ending}")
        insert_index += 1


def render_source_page(plan: PagePlan) -> str:
    with plan.path.open("r", encoding="utf-8", newline="") as file:
        text = file.read()

    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise ValueError(f"{plan.path}: missing opening frontmatter delimiter")

    closing_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.rstrip("\r\n") == "---":
            closing_index = index
            break
    if closing_index is None:
        raise ValueError(f"{plan.path}: missing closing frontmatter delimiter")

    author_index = None
    attribution_index = None
    source_file_index = None
    for index in range(1, closing_index):
        content = lines[index].rstrip("\r\n")
        key, separator, _ = content.partition(":")
        if not separator:
            continue

        key = key.strip()

        if key == "author":
            author_index = index
        elif key == "attribution":
            attribution_index = index
        elif key == "source_file":
            source_file_index = index

    if source_file_index is not None:
        source_line = lines[source_file_index]
        source_content = source_line.rstrip("\r\n")
        source_ending = source_line[len(source_content) :]
        lines[source_file_index] = (
            f"source_file: {plan.proposed_source_file}{source_ending}"
        )

    if author_index is not None:
        author_line = lines[author_index]
        author_content = author_line.rstrip("\r\n")
        author_ending = author_line[len(author_content) :]
        if attribution_index is None:
            lines[author_index] = (
                f"attribution: {plan.proposed_attribution}{author_ending}"
            )
            attribution_index = author_index
        else:
            del lines[author_index]
            if attribution_index > author_index:
                attribution_index -= 1

    if plan.missing_source_fields:
        closing_index = next(
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.rstrip("\r\n") == "---"
        )
        source_file_index = next(
            (
                index
                for index in range(1, closing_index)
                if lines[index].partition(":")[0].strip() == "source_file"
            ),
            None,
        )
        insert_index = (
            source_file_index + 1
            if source_file_index is not None
            else closing_index
        )
        reference_index = source_file_index if source_file_index is not None else 0
        reference_line = lines[reference_index]
        reference_content = reference_line.rstrip("\r\n")
        ending = reference_line[len(reference_content) :] or "\n"
        add_missing_source_fields(
            lines,
            insert_index,
            plan.missing_source_fields,
            ending,
        )

    if attribution_index is None:
        raise ValueError(f"{plan.path}: missing attribution in frontmatter")

    return "".join(lines)


def render_structured_page(plan: PagePlan) -> str:
    with plan.path.open("r", encoding="utf-8", newline="") as file:
        text = file.read()
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise ValueError(f"{plan.path}: missing opening frontmatter delimiter")
    closing_index = next(
        (
            index
            for index, line in enumerate(lines[1:], start=1)
            if line.rstrip("\r\n") == "---"
        ),
        None,
    )
    if closing_index is None:
        raise ValueError(f"{plan.path}: missing closing frontmatter delimiter")

    ranges: dict[str, tuple[int, int]] = {}
    index = 1
    while index < closing_index:
        content = lines[index].rstrip("\r\n")
        if content and not content[0].isspace():
            key, separator, _ = content.partition(":")
            if separator:
                end = index + 1
                while end < closing_index:
                    following = lines[end].rstrip("\r\n")
                    if following and not following[0].isspace():
                        break
                    end += 1
                ranges[key.strip()] = (index, end)
                index = end
                continue
        index += 1

    for field_name in plan.removed_fields:
        field_range = ranges.get(field_name)
        if field_range is None:
            continue
        start, end = field_range
        del lines[start:end]
        removed_count = end - start
        closing_index -= removed_count
        ranges = {
            key: (
                value_start - removed_count if value_start >= end else value_start,
                value_end - removed_count if value_start >= end else value_end,
            )
            for key, (value_start, value_end) in ranges.items()
            if key != field_name
        }

    reference_line = lines[closing_index - 1] if closing_index > 1 else lines[0]
    reference_content = reference_line.rstrip("\r\n")
    ending = reference_line[len(reference_content) :] or "\n"
    additions: list[str] = []
    for _, field_lines in plan.proposed_fields:
        additions.extend(f"{line}{ending}" for line in field_lines)
    lines[closing_index:closing_index] = additions
    return "".join(lines)


def render_page(plan: PagePlan) -> str:
    if not plan.needs_change:
        raise ValueError(f"{plan.path}: page does not need migration")

    if plan.page_type == "source":
        return render_source_page(plan)

    if plan.page_type not in {"entity", "concept"}:
        return render_structured_page(plan)

    if plan.proposed_canonical_name is None:
        raise ValueError(f"{plan.path}: no canonical name is available")

    with plan.path.open("r", encoding="utf-8", newline="") as file:
        text = file.read()

    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != "---":
        raise ValueError(f"{plan.path}: missing opening frontmatter delimiter")

    closing_index = None
    for index, line in enumerate(lines[1:], start=1):
        if line.rstrip("\r\n") == "---":
            closing_index = index
            break
    if closing_index is None:
        raise ValueError(f"{plan.path}: missing closing frontmatter delimiter")

    title_index = None
    canonical_name_index = None
    for index in range(1, closing_index):
        content = lines[index].rstrip("\r\n")
        key, separator, _ = content.partition(":")
        if not separator:
            continue

        key = key.strip()

        if key == "title":
            title_index = index
        elif key == "canonical_name":
            canonical_name_index = index

    if title_index is not None:
        title_line = lines[title_index]
        title_content = title_line.rstrip("\r\n")
        title_ending = title_line[len(title_content) :]

        if canonical_name_index is None:
            lines[title_index] = (
                f"canonical_name: {plan.proposed_canonical_name}{title_ending}"
            )
            canonical_name_index = title_index
        else:
            del lines[title_index]
            if canonical_name_index > title_index:
                canonical_name_index -= 1

    if canonical_name_index is None:
        raise ValueError(f"{plan.path}: missing canonical_name in frontmatter")

    canonical_line = lines[canonical_name_index]
    canonical_content = canonical_line.rstrip("\r\n")
    ending = canonical_line[len(canonical_content) :]
    add_missing_name_fields(
        lines,
        canonical_name_index + 1,
        plan.missing_name_fields,
        ending,
    )
    return "".join(lines)


def apply_migration(migration: MigrationPlan) -> tuple[Path, ...]:
    if not migration.is_valid:
        raise ValueError("cannot apply an invalid migration")

    rendered_pages = [
        (page.path, render_page(page)) for page in migration.pages if page.needs_change
    ]

    for path in migration.create_paths:
        if path.exists():
            raise ValueError(f"cannot create existing path: {path}")

    for path, rendered in rendered_pages:
        path.write_bytes(rendered.encode("utf-8"))

    for path in migration.create_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"")

    return tuple(path for path, _ in rendered_pages) + migration.create_paths


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    entities_dir = args.wiki_dir / "entities"
    migration = build_migration_plan(entities_dir)
    pending_page_paths = tuple(
        page.path for page in migration.pages if page.needs_change
    )
    pending_paths = pending_page_paths + migration.create_paths
    changed_paths: tuple[Path, ...] = ()

    # Ensure every pending page can render during preview
    if migration.is_valid:
        if args.apply:
            changed_paths = apply_migration(migration)
        else:
            # Validate rendering without writing.
            for page in migration.pages:
                if page.needs_change:
                    render_page(page)

    report: dict[str, object] = {
        "wiki_dir": str(args.wiki_dir),
        "apply": args.apply,
        "page_count": len(migration.pages),
        "pending_count": len(pending_paths),
        "changed_count": len(changed_paths),
        "error_count": len(migration.errors),
        "valid": migration.is_valid,
        "errors": list(migration.errors),
        "pending_paths": [str(path) for path in pending_paths],
        "changed_paths": [str(path) for path in changed_paths],
    }

    if args.json:
        print(json.dumps(report, sort_keys=True))
    else:
        print(f"pages={len(migration.pages)}")
        print(f"errors={len(migration.errors)}")
        print(f"valid={migration.is_valid}")
        print(f"pending={len(pending_paths)}\n")

        for error in migration.errors:
            print(f"error: {error}")

        if migration.is_valid:
            paths = changed_paths if args.apply else pending_paths

            for path in paths:
                is_creation = path in migration.create_paths
                if args.apply:
                    label = "created" if is_creation else "updated"
                else:
                    label = "would create" if is_creation else "would update"
                print(f"{label}: {path}")

    return 0 if migration.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
