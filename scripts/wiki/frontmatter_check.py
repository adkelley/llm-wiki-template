#!/usr/bin/env python3
"""Validate wiki page frontmatter against the schema in AGENT.md.

Two kinds of checks:

1. Universal structural check, independent of page type: no list may
   contain a mapping (dict) item. This catches the silent YAML corruption
   where an unquoted plain-scalar list item (e.g. `- Some label: the rest
   of the sentence`) parses as a one-key mapping instead of a string --
   `yaml.safe_load` raises no error, so a plain "is this valid YAML" check
   misses it entirely. AGENT.md is explicit that `claims:` on
   contradiction-resolution pages must be a flat list of scalar strings,
   same as every other list field, so this rule has no per-type exception.

2. Per-type schema conformance, derived from AGENT.md's documented
   frontmatter block for each `type:` value: required fields, enum-valued
   fields (status/origin/priority/confidence/source_type/entity_type), the
   canonical_name-vs-title rule for concept/entity pages, the
   singular-wikilink shape of `source_file`, the flat `ingest_start`/
   `ingest_end` fields on trace pages, and the conditional
   `resolution`/`dismissal_reason` requirement on contradiction-resolution
   pages. Trace ingestion boundaries are top-level scalar fields;
   the obsolete `ingest_range` representation is rejected.

`issues` are MUST-level violations and cause a nonzero exit. `warnings` are
SHOULD-level recommendations (currently just: a contradiction-resolution
claim with no supporting `[[wikilink]]`) and are reported but don't fail
the check, since a claim may occasionally trace only to the tracker or log
rather than a formal source page yet.
"""

import glob
import re
import sys
from pathlib import Path

import yaml

WIKILINK_RE = re.compile(r"\[\[.+?\]\]")
SINGLE_WIKILINK_RE = re.compile(r"^\[\[.+\]\]$")
NAME_LIST_FIELDS = ("aliases", "abbreviations", "known_variants", "known_errors")

STATUS_VALUES = {"active", "superseded", "deprecated"}
ORIGIN_VALUES = {"query", "ingest", "migration", "manual"}
CONFIDENCE_VALUES = {"high", "medium", "low"}
SOURCE_TYPE_VALUES = {
    "article", "paper", "report", "presentation", "communication",
    "transcript", "recording", "book", "documentation", "dataset",
    "webpage", "note", "other", "unknown",
}
ENTITY_TYPE_VALUES = {"person", "company", "product", "org"}
CR_STATUS_VALUES = {
    "proposed", "open", "in-progress", "resolution-proposed",
    "resolved", "dismissed",
}
CR_PRIORITY_VALUES = {"low", "medium", "high"}


def is_nonempty_str(v):
    return isinstance(v, str) and v.strip() != ""


def is_str_list(v):
    return isinstance(v, list) and all(isinstance(i, str) for i in v)


def is_name_list(v):
    """[] or a block list of nonempty scalar strings."""
    return isinstance(v, list) and all(is_nonempty_str(i) for i in v)


def is_nonempty_scalar(v):
    """Whether a YAML value is a nonempty scalar without restricting its tag."""
    if v is None or isinstance(v, (dict, list)):
        return False
    return not isinstance(v, str) or v.strip() != ""


def check_dict_in_lists(path, data, issues):
    for key, value in data.items():
        if not isinstance(value, list):
            continue
        for item in value:
            if isinstance(item, dict):
                issues.append(
                    f"{path}: '{key}' list contains a mapping {dict(item)!r} "
                    f"-- likely a corrupted scalar (an unquoted 'label: text' "
                    f"list item silently parses as a one-key mapping)"
                )


def require(data, field, issues, path):
    if field not in data or data.get(field) in (None, ""):
        issues.append(f"{path}: missing required field '{field}'")
        return False
    return True


def check_enum(data, field, allowed, issues, path):
    if field not in data:
        issues.append(f"{path}: missing required field '{field}'")
        return
    v = data.get(field)
    if v not in allowed:
        issues.append(f"{path}: '{field}' is {v!r}, must be one of {sorted(allowed)}")


def check_id(data, path, id_field, prefix, issues):
    if not require(data, id_field, issues, path):
        return
    v = data.get(id_field)
    if not is_nonempty_str(v) or not v.startswith(f"{prefix}:"):
        issues.append(f"{path}: '{id_field}' must look like '{prefix}:{{slug}}', got {v!r}")


def check_wikilink_list_field(data, field, issues, path, required=False):
    if field not in data:
        if required:
            issues.append(f"{path}: missing required field '{field}'")
        return
    v = data.get(field)
    if not is_str_list(v):
        issues.append(f"{path}: '{field}' must be a list of strings, got {v!r}")


def check_source(data, path, issues):
    check_id(data, path, "source_id", "source", issues)
    require(data, "title", issues, path)
    require(data, "source_file", issues, path)
    sf = data.get("source_file")
    if sf is not None and not (is_nonempty_str(sf) and SINGLE_WIKILINK_RE.match(sf)):
        issues.append(
            f"{path}: 'source_file' must be a single quoted wikilink "
            f"'[[raw/...]]', not a plain path or a list, got {sf!r}"
        )
    if "renditions" in data and not is_str_list(data["renditions"]):
        issues.append(f"{path}: 'renditions' must be a list of strings")
    check_enum(data, "source_type", SOURCE_TYPE_VALUES, issues, path)
    attribution = data.get("attribution")
    if "attribution" not in data:
        issues.append(f"{path}: missing required field 'attribution'")
    elif not is_nonempty_str(attribution):
        issues.append(
            f"{path}: 'attribution' must be a single scalar string, not a "
            f"list -- got {attribution!r}"
        )
    if "key_claims" in data and not is_str_list(data["key_claims"]):
        issues.append(f"{path}: 'key_claims' must be a list of strings")
    check_wikilink_list_field(data, "related", issues, path)
    check_enum(data, "confidence", CONFIDENCE_VALUES, issues, path)


def check_name_fields(data, path, issues):
    for field in NAME_LIST_FIELDS:
        if field not in data:
            continue
        if not is_name_list(data[field]):
            issues.append(
                f"{path}: '{field}' must be [] or a list of nonempty "
                f"strings, got {data[field]!r}"
            )


def check_concept(data, path, issues):
    check_id(data, path, "concept_id", "concept", issues)
    if "title" in data:
        issues.append(f"{path}: concept pages MUST NOT use 'title' -- use 'canonical_name'")
    if require(data, "canonical_name", issues, path) and not is_nonempty_str(data.get("canonical_name")):
        issues.append(f"{path}: 'canonical_name' must be a nonempty string")
    check_name_fields(data, path, issues)
    check_wikilink_list_field(data, "sources", issues, path)
    check_wikilink_list_field(data, "related", issues, path)
    check_enum(data, "confidence", CONFIDENCE_VALUES, issues, path)


def check_entity(data, path, issues):
    check_id(data, path, "entity_id", "entity", issues)
    if "title" in data:
        issues.append(f"{path}: entity pages MUST NOT use 'title' -- use 'canonical_name'")
    if require(data, "canonical_name", issues, path) and not is_nonempty_str(data.get("canonical_name")):
        issues.append(f"{path}: 'canonical_name' must be a nonempty string")
    check_enum(data, "entity_type", ENTITY_TYPE_VALUES, issues, path)
    check_name_fields(data, path, issues)
    check_wikilink_list_field(data, "sources", issues, path)
    check_wikilink_list_field(data, "related", issues, path)


def check_comparison(data, path, issues):
    check_id(data, path, "comparison_id", "comparison", issues)
    require(data, "title", issues, path)
    check_enum(data, "status", STATUS_VALUES, issues, path)
    check_wikilink_list_field(data, "subjects", issues, path)
    check_wikilink_list_field(data, "sources", issues, path)
    check_wikilink_list_field(data, "related", issues, path)
    require(data, "question", issues, path)
    check_enum(data, "origin", ORIGIN_VALUES, issues, path)


def check_synthesis(data, path, issues):
    check_id(data, path, "synthesis_id", "synthesis", issues)
    require(data, "title", issues, path)
    require(data, "question", issues, path)
    check_enum(data, "origin", ORIGIN_VALUES, issues, path)
    check_enum(data, "status", STATUS_VALUES, issues, path)
    check_wikilink_list_field(data, "subjects", issues, path)
    check_wikilink_list_field(data, "sources", issues, path)
    check_wikilink_list_field(data, "related", issues, path)
    check_enum(data, "confidence", CONFIDENCE_VALUES, issues, path)


def check_trace(data, path, issues):
    check_id(data, path, "trace_id", "trace", issues)
    require(data, "title", issues, path)
    require(data, "question", issues, path)
    check_enum(data, "origin", ORIGIN_VALUES, issues, path)
    check_enum(data, "status", STATUS_VALUES, issues, path)
    check_wikilink_list_field(data, "subjects", issues, path)
    check_wikilink_list_field(data, "sources", issues, path)
    check_wikilink_list_field(data, "related", issues, path)
    check_enum(data, "confidence", CONFIDENCE_VALUES, issues, path)
    for field in ("ingest_start", "ingest_end"):
        if field not in data or data.get(field) in (None, ""):
            issues.append(f"{path}: missing required field '{field}'")
        elif not is_nonempty_scalar(data[field]):
            issues.append(
                f"{path}: '{field}' must be a nonempty scalar, "
                f"got {data[field]!r}"
            )
    if "ingest_range" in data:
        issues.append(
            f"{path}: obsolete field 'ingest_range' is not supported; "
            f"use flat 'ingest_start'/'ingest_end' scalar fields instead, "
            f"got {data['ingest_range']!r}"
        )


def check_contradiction_resolution(data, path, issues, warnings):
    check_id(data, path, "contradiction_resolution_id", "contradiction-resolution", issues)
    require(data, "title", issues, path)
    check_enum(data, "status", CR_STATUS_VALUES, issues, path)
    check_enum(data, "priority", CR_PRIORITY_VALUES, issues, path)
    check_wikilink_list_field(data, "subjects", issues, path)
    check_wikilink_list_field(data, "evidence", issues, path)

    claims = data.get("claims")
    if not isinstance(claims, list) or not claims:
        issues.append(f"{path}: 'claims' must be a non-empty list")
    else:
        for item in claims:
            if not isinstance(item, str) or not item.strip():
                issues.append(f"{path}: 'claims' item must be a non-empty string, got {item!r}")
            elif not WIKILINK_RE.search(item):
                warnings.append(
                    f"{path}: claims item has no [[wikilink]] to supporting "
                    f"evidence: {item!r}"
                )

    if "log_references" in data and not is_str_list(data["log_references"]):
        issues.append(f"{path}: 'log_references' must be a list of strings")

    require(data, "resolution_question", issues, path)

    status = data.get("status")
    if status == "resolved" and not is_nonempty_str(data.get("resolution")):
        issues.append(f"{path}: status is 'resolved' but 'resolution' is missing or empty")
    if status == "dismissed" and not is_nonempty_str(data.get("dismissal_reason")):
        issues.append(f"{path}: status is 'dismissed' but 'dismissal_reason' is missing or empty")


SIMPLE_TYPE_CHECKERS = {
    "source": check_source,
    "concept": check_concept,
    "entity": check_entity,
    "comparison": check_comparison,
    "synthesis": check_synthesis,
    "trace": check_trace,
}


def check_file(path):
    text = Path(path).read_text(encoding="utf-8")
    issues = []
    warnings = []
    if not text.startswith("---\n"):
        return issues, warnings

    try:
        end = text.index("\n---", 4)
    except ValueError:
        return [f"{path}: no closing frontmatter delimiter"], warnings

    fm = text[4:end]
    try:
        data = yaml.safe_load(fm)
    except Exception as e:
        return [f"{path}: YAML parse error: {e}"], warnings

    if not isinstance(data, dict):
        return [f"{path}: frontmatter is not a mapping"], warnings

    check_dict_in_lists(path, data, issues)

    page_type = data.get("type")
    if page_type is None:
        issues.append(f"{path}: missing required field 'type'")
    elif page_type in SIMPLE_TYPE_CHECKERS:
        SIMPLE_TYPE_CHECKERS[page_type](data, path, issues)
    elif page_type == "contradiction-resolution":
        check_contradiction_resolution(data, path, issues, warnings)
    # Unrecognized `type` values are left unvalidated beyond the universal
    # dict-in-list check -- AGENT.md only documents these seven types.

    return issues, warnings


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    root = args[0] if args else "wiki"

    all_issues = []
    all_warnings = []
    for path in sorted(glob.glob(f"{root}/**/*.md", recursive=True)):
        issues, warnings = check_file(path)
        all_issues.extend(issues)
        all_warnings.extend(warnings)

    if all_warnings:
        print(f"{len(all_warnings)} warning(s):")
        for w in all_warnings:
            print(" -", w)

    if all_issues:
        print(f"{len(all_issues)} issue(s) found:")
        for issue in all_issues:
            print(" -", issue)
        sys.exit(1)

    print("OK -- no frontmatter schema issues found.")


if __name__ == "__main__":
    main()
