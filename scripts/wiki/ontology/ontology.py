import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class WikiPage:
    path: Path
    page_type: str
    stable_id: str
    title: str


@dataclass(frozen=True)
class WikiCatalog:
    pages: tuple[WikiPage, ...]
    pages_by_id: dict[str, WikiPage]
    errors: tuple[str, ...]

    @property
    def is_valid(self) -> bool:
        return not self.errors


PAGE_DIRECTORIES = {
    "sources": ("source", "source_id"),
    "concepts": ("concept", "concept_id"),
    "entities": ("entity", "entity_id"),
    "comparisons": ("comparison", "comparison_id"),
    "syntheses": ("synthesis", "synthesis_id"),
    "traces": ("trace", "trace_id"),
}


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


def build_catalog(wiki_dir: Path) -> WikiCatalog:
    pages: list[WikiPage] = []
    pages_candidates_by_id: dict[str, list[WikiPage]] = {}
    pages_by_id: dict[str, WikiPage] = {}
    errors: list[str] = []

    for dir_name, (page_type, stable_id_field) in PAGE_DIRECTORIES.items():
        dir_path = wiki_dir / dir_name
        if not dir_path.is_dir():
            errors.append(f"Directory not found: {dir_path}")
            continue
        for file_path in sorted(dir_path.rglob("*.md")):
            if not file_path.is_file():
                continue

            try:
                frontmatter = read_frontmatter(file_path)
                stable_id = frontmatter[stable_id_field]

                title = frontmatter["title"]
                page = WikiPage(
                    path=file_path,
                    page_type=page_type,
                    stable_id=stable_id,
                    title=title,
                )
                pages.append(page)
                pages_candidates_by_id.setdefault(stable_id, []).append(page)
            except Exception as error:
                errors.append(f"Error reading file {file_path}: {error}")

    for stable_id, candidates in sorted(pages_candidates_by_id.items()):
        if len(candidates) == 1:
            pages_by_id[stable_id] = candidates[0]
            continue

        paths = ", ".join(
            str(page.path) for page in sorted(candidates, key=lambda page: page.path)
        )
        gg

    return WikiCatalog(
        pages=tuple(pages),
        pages_by_id=pages_by_id,
        errors=tuple(errors),
    )


def main():
    wiki_dir = Path("/tmp/llm-wiki-codex-test.pOMo55/wiki")
    catalog = build_catalog(wiki_dir)
    print(catalog)


if __name__ == "__main__":
    main()
