#!/usr/bin/env python3

"""
Migrate_v1: Assign stable, type-specific IDs to existing wiki pages without changing substantive knowledge.
"""

import argparse
import json
import re
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PageType:
    directory: str
    frontmatter_type: str
    id_field: str
    id_prefix: str


PAGE_TYPES = (
    PageType(
        directory="sources",
        frontmatter_type="source",
        id_field="source_id",
        id_prefix="source",
    ),
    PageType(
        directory="concepts",
        frontmatter_type="concept",
        id_field="concept_id",
        id_prefix="concept",
    ),
    PageType(
        directory="entities",
        frontmatter_type="entity",
        id_field="entity_id",
        id_prefix="entity",
    ),
    PageType(
        directory="comparisons",
        frontmatter_type="comparison",
        id_field="comparison_id",
        id_prefix="comparison",
    ),
    PageType(
        directory="syntheses",
        frontmatter_type="synthesis",
        id_field="synthesis_id",
        id_prefix="synthesis",
    ),
    PageType(
        directory="traces",
        frontmatter_type="trace",
        id_field="trace_id",
        id_prefix="trace",
    ),
)


@dataclass(frozen=True)
class PagePlan:
    path: Path
    page_type: PageType
    proposed_id: str | None
    existing_id: str | None
    errors: tuple[str, ...]

    @property
    def needs_change(self) -> bool:
        return self.existing_id is None and not self.errors


@dataclass(frozen=True)
class MigrationPlan:
    pages: tuple[PagePlan, ...]
    errors: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.errors


def build_migration_plan(wiki_dir: Path) -> MigrationPlan:
    pages: list[PagePlan] = []
    errors: list[str] = []

    # Validate and collect pages
    if not wiki_dir.is_dir():
        return MigrationPlan(
            pages=(),
            errors=(f"{wiki_dir}: wiki directory does not exist",),
        )

    for page_type in PAGE_TYPES:
        for path in iter_pages(wiki_dir, page_type):
            page = plan_page(path, page_type)
            pages.append(page)
            errors.extend(page.errors)

    # Group effective IDs
    paths_by_id: dict[str, list[Path]] = {}
    for page in pages:
        if page.errors:
            continue

        stable_id = page.existing_id or page.proposed_id
        if stable_id is not None:
            paths_by_id.setdefault(stable_id, []).append(page.path)

    # Report collisions
    for stable_id, paths in sorted(paths_by_id.items()):
        if len(paths) > 1:
            joined_paths = ", ".join(str(path) for path in paths)
            errors.append(f"duplicate ID: {stable_id!r}: {joined_paths}")

    return MigrationPlan(tuple(pages), tuple(errors))


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="migrate_v1",
        description="Assign permanent, type-specific IDs to existing wiki pages.",
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


def iter_pages(wiki_dir: Path, page_type: PageType) -> Iterator[Path]:
    page_dir = wiki_dir / page_type.directory
    if not page_dir.exists():
        return

    for path in sorted(page_dir.rglob("*.md")):
        if path.is_file():
            yield path


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
        if separator:
            frontmatter[key.strip()] = value.strip()

    return frontmatter


def slugify_filename(path: Path) -> str:
    normalized = unicodedata.normalize("NFKD", path.stem)
    ascii_name = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.casefold()).strip("-")

    if not slug:
        raise ValueError(f"{path}: filename does not produce a valid slug")

    return slug


def proposed_id(path: Path, page_type: PageType) -> str:
    return f"{page_type.id_prefix}:{slugify_filename(path)}"


def plan_page(path: Path, page_type: PageType) -> PagePlan:
    errors: list[str] = []

    try:
        candidate_id = proposed_id(path, page_type)
    except ValueError as error:
        errors.append(str(error))
        candidate_id = None

    frontmatter_valid = True
    try:
        frontmatter = read_frontmatter(path)
    except ValueError as error:
        frontmatter = {}
        frontmatter_valid = False
        errors.append(str(error))

    existing_id = None
    if frontmatter_valid:
        actual_type = frontmatter.get("type")
        if actual_type != page_type.frontmatter_type:
            errors.append(
                f"{path}: expected type {page_type.frontmatter_type!r}, "
                f"found {actual_type!r}"
            )

        existing_id = frontmatter.get(page_type.id_field)
        pattern = rf"{re.escape(page_type.id_prefix)}:[a-z0-9]+(?:-[a-z0-9]+)*"
        if existing_id is not None:
            if not re.fullmatch(pattern, existing_id):
                errors.append(
                    f"{path}: expected id pattern {pattern!r}, found {existing_id!r}"
                )

    return PagePlan(
        path=path,
        page_type=page_type,
        proposed_id=candidate_id,
        existing_id=existing_id,
        errors=tuple(errors),
    )


def render_page(plan: PagePlan) -> str:
    if not plan.needs_change:
        raise ValueError(f"{plan.path}: page does not need migration")

    if plan.proposed_id is None:
        raise ValueError(f"{plan.path}: no proposed ID is available")

    with plan.path.open("r", encoding="utf-8", newline="") as file:
        text = file.read()
    newline = "\r\n" if text.startswith("---\r\n") else "\n"
    lines = text.splitlines(keepends=True)

    closing_index = None

    for index, line in enumerate(lines[1:], start=1):
        if line.rstrip("\r\n") == "---":
            closing_index = index
            break

    if closing_index is None:
        raise ValueError(f"{plan.path}: no closing '---' is found")

    type_index = None

    for index in range(1, closing_index):
        line_without_ending = lines[index].rstrip("\r\n")
        if line_without_ending and not line_without_ending[0].isspace():
            key, separator, _ = line_without_ending.partition(":")
            if separator and key.strip() == "type":
                type_index = index
                break

    if type_index is None:
        raise ValueError(f"{plan.path}: no type is specified")

    id_line = f"{plan.page_type.id_field}: {plan.proposed_id}{newline}"
    lines.insert(type_index + 1, id_line)
    return "".join(lines)


def apply_migration(migration: MigrationPlan) -> tuple[Path, ...]:
    if not migration.is_valid:
        raise ValueError("cannot apply an invalid migration")

    rendered_pages: list[tuple[Path, str]] = []
    for page in migration.pages:
        if page.needs_change:
            rendered_pages.append((page.path, render_page(page)))

    for path, rendered_text in rendered_pages:
        path.write_bytes(rendered_text.encode("utf-8"))

    return tuple(path for path, _ in rendered_pages)


def main() -> int:
    parser = build_arg_parser()
    args = parser.parse_args()

    migration = build_migration_plan(args.wiki_dir)
    pending_paths = tuple(page.path for page in migration.pages if page.needs_change)
    changed_paths: tuple[Path, ...] = ()

    if migration.is_valid:
        if args.apply:
            changed_paths = apply_migration(migration)
        else:
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
