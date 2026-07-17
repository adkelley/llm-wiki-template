#!/usr/bin/env python3

"""
Migrate entity-page frontmatter from the legacy title schema to naming schema v2.

The migration recursively inspects Markdown files under ``wiki/entities``.
It replaces ``title`` with ``canonical_name`` and adds any missing entity-name
list fields: ``aliases``, ``abbreviations``, ``known_variants``, and
``known_errors``.

Preview mode validates and renders all pending changes without writing files.
Apply mode writes changes only after the complete migration plan is valid and
every pending page renders successfully. Existing name-list values, unrelated
frontmatter, Markdown bodies, UTF-8 encoding, and LF or CRLF line endings are
preserved. The migration performs no inference, lookup, or normalization of
entity names.
"""

import argparse
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PagePlan:
    path: Path
    existing_title: str | None
    existing_canonical_name: str | None
    proposed_canonical_name: str | None
    missing_name_fields: tuple[str, ...]
    errors: tuple[str, ...]

    @property
    def needs_change(self) -> bool:
        return not self.errors and (
            self.existing_title is not None
            or self.existing_canonical_name is None
            or bool(self.missing_name_fields)
        )


@dataclass(frozen=True)
class MigrationPlan:
    pages: tuple[PagePlan, ...]
    errors: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.errors


NAME_FIELDS = (
    "aliases",
    "abbreviations",
    "known_variants",
    "known_errors",
)

EMPTY_VALUES = (
    "",
    '""',
    "''",
)


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="migrate_v2",
        description="A preview-first migration that upgrades only `wiki/entities/**/*.md`.",
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
            quoted = (
                len(item) >= 2
                and item[0] == item[-1]
                and item[0] in ('"', "'")
            )
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


def plan_entity_page(path: Path) -> PagePlan:
    errors: list[str] = []
    missing_name_fields: list[str] = []

    frontmatter_valid = True
    try:
        frontmatter = read_frontmatter(path)
    except ValueError as error:
        frontmatter = {}
        frontmatter_valid = False
        errors.append(str(error))

    existing_title = None
    existing_canonical_name = None
    proposed_canonical_name = None

    if frontmatter_valid:
        actual_type = frontmatter.get("type")
        if actual_type != "entity":
            errors.append(f"{path}: expected type: entity, found {actual_type!r}")

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

    return PagePlan(
        path=path,
        existing_canonical_name=existing_canonical_name,
        proposed_canonical_name=proposed_canonical_name,
        existing_title=existing_title,
        missing_name_fields=tuple(missing_name_fields),
        errors=tuple(errors),
    )


def build_migration_plan(entity_dir: Path) -> MigrationPlan:
    pages: list[PagePlan] = []
    errors: list[str] = []

    # Validate and collect pages
    if not entity_dir.is_dir():
        return MigrationPlan(
            pages=(),
            errors=(f"{entity_dir}: entity directory does not exist",),
        )

    for path in iter_pages(entity_dir):
        page = plan_entity_page(path)
        pages.append(page)
        errors.extend(page.errors)

    return MigrationPlan(
        pages=tuple(pages),
        errors=tuple(errors),
    )


def add_missing_name_fields(
    lines: list[str], insert_index: int, missing_fields: tuple[str, ...], ending: str
) -> None:
    for field in missing_fields:
        lines.insert(insert_index, f"{field}: []{ending}")
        insert_index += 1
    return None


def render_page(plan: PagePlan) -> str:
    if not plan.needs_change:
        raise ValueError(f"{plan.path}: page does not need migration")

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

    for path, rendered in rendered_pages:
        path.write_bytes(rendered.encode("utf-8"))

    return tuple(path for path, _ in rendered_pages)


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()
    entities_dir = args.wiki_dir / "entities"
    migration = build_migration_plan(entities_dir)
    pending_paths = tuple(page.path for page in migration.pages if page.needs_change)
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
            label = "updated" if args.apply else "would update"

            for path in paths:
                print(f"{label}: {path}")

    return 0 if migration.is_valid else 1


if __name__ == "__main__":
    raise SystemExit(main())
