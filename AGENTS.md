# LLM Wiki Template - Agent Context

This repository is an app/toolkit for helping users bootstrap their own
LLM-maintained wiki. It is not itself the user's active wiki. Work in this repo
should focus on improving the template, setup scripts, optional skills, and
documentation that users copy into their own projects.

The root `AGENT.md` is for agents helping develop this template repository.
The generated agent instructions for an end-user wiki live in
`scripts/codex/AGENT.md` and `scripts/claude/CLAUDE.md`.

## Product Goal

Help users create and operate a personal or project-specific LLM Wiki with:

- a durable `raw/` source layer
- a maintained `wiki/` synthesis layer
- agent instructions for common LLM coding agents
- optional skills for ingestion, recall, tracing, daily briefings, and closeout
- setup scripts that make the bootstrap flow simple and repeatable

Think of this as a starter kit plus workflow laboratory. New work should make it
easier for users to install, understand, customize, and safely extend their own
LLM Wiki.

## Repository Map

- `README.md` explains the template and user-facing setup flow.
- `raw/` is example/template source-input structure, not active research data.
- `wiki/` is example/template wiki structure, not the maintained knowledge base
  for this repo.
- `scripts/README.md` summarizes supported integrations.
- `scripts/codex/` contains Codex setup and the Codex `AGENT.md` template copied
  into user projects.
- `scripts/claude/` contains Claude Code setup and the `CLAUDE.md` template
  copied into user projects.
- `scripts/obsidian/` contains Obsidian setup helpers.
- `scripts/optional-skills/` contains reusable skill templates that setup
  scripts can install into a user's wiki environment.
- `commit.md` is local/generated commit guidance and is ignored by Git.

## How to Approach Work

When the user asks for help in the root of this repository, assume they are
working on the bootstrap toolkit unless they explicitly say they are operating
an actual wiki.

Good tasks for this repository include:

- designing new optional skills
- improving install/update behavior in setup scripts
- tightening generated `AGENT.md` or `CLAUDE.md` templates
- documenting wiki conventions and onboarding flows
- researching algorithms or implementation options for future features
- adding safeguards against duplicate ingestion, accidental raw edits, or stale
  wiki state
- making the template easier to adapt across agents, editors, and operating
  systems

Do not treat the root `wiki/` as authoritative project memory unless the user
explicitly decides to maintain this repository's own wiki. The files currently
there are placeholders for users.

## Feature Research

The user may ask for research to inform new LLM Wiki features. Examples:

- content hashing to detect duplicate ingests, likely using SHA-256 or another
  stable digest algorithm
- fuzzy matching or semantic similarity to catch near-duplicate sources
- manifests for processed notes, mail, voice memos, or imported files
- frontmatter schemas for source provenance and confidence
- routing logic for deciding which raw sources belong in which wiki
- Obsidian metadata or cache integration
- local search and retrieval tools such as `qmd`

For research tasks:

1. Clarify whether the goal is a design note, implementation patch, or both.
2. Inspect existing scripts and skills before proposing new structure.
3. Prefer small, composable designs that fit the current shell-script and
   Markdown-template style.
4. Separate deterministic safeguards, such as file hashes and manifests, from
   heuristic safeguards, such as semantic duplicate detection.
5. When facts may have changed or require precise current documentation, verify
   with primary sources or official docs.

## Skill Development

Optional skills live under `scripts/optional-skills/{skill-name}/`.

A skill should normally include:

- `SKILL.md` with YAML frontmatter containing `name` and `description`
- clear trigger conditions
- a purpose statement
- required config or manifest files, if any
- step-by-step workflow
- failure modes and permission requirements
- how it writes to `raw/`, `wiki/`, `wiki/index.md`, `wiki/log.md`, or
  `wiki/hot.md`

When editing or creating skills:

- Preserve user-managed config files such as `config.md`, `processed.txt`, and
  `last_scan.txt`.
- Keep generated user-facing workflows agent-agnostic where possible.
- Avoid requiring cloud services when a local path is reasonable.
- Be explicit about macOS GUI automation requirements for Apple Notes, Mail, or
  voice workflows.
- Include safe behavior for missing tools, denied permissions, and empty result
  sets.

## Setup Script Conventions

The setup scripts are intentionally plain Bash. Keep them easy to audit.

- Preserve existing user files where possible.
- Copy starter templates only when the destination does not already exist.
- When updating installed skills, replace `SKILL.md` only unless the user
  explicitly asks to overwrite config/manifests.
- Avoid adding heavyweight dependencies to the setup path.
- Keep prompts clear and reversible.

## Template vs. Installed Files

Be careful about which layer you are editing:

- Edit root docs when improving this repository's documentation.
- Edit `scripts/codex/AGENT.md` when changing what Codex users receive.
- Edit `scripts/claude/CLAUDE.md` when changing what Claude Code users receive.
- Edit `scripts/optional-skills/*/SKILL.md` when changing optional skill
  behavior.
- Do not edit generated local install directories such as `./skills/` unless the
  user is testing installation output.

## Raw and Wiki Directories in This Repo

In an installed user wiki, `raw/` should be treated as immutable source material
and `wiki/` as the maintained synthesis layer.

In this template repository, `raw/` and `wiki/` are scaffolding examples. Keep
them lightweight and generic unless the user asks to turn this repository into a
real active wiki as well.

## Git and Editing

- Check `git status --short` before and after edits.
- Do not revert user changes.
- Keep changes scoped to the user's request.
- Do not stage, commit, or push unless asked.
- Read `commit.md` to understand how to stucture commit messages
- Do not stage `.DS_Store`, `.obsidian/`, `.claude/`, `commit.md`, or transient
  local configuration.
- Use `rg` for repository search.
- Prefer `apply_patch` for manual edits.

## Writing Style

For user-facing docs and templates:

- Write directly and practically.
- Explain the user's workflow, not internal implementation trivia.
- Keep setup instructions copy-pasteable.
- Use concrete examples where they reduce ambiguity.
- Avoid overfitting instructions to one agent unless the file is explicitly
  agent-specific.

For design notes and implementation research:

- Start from the problem and constraints.
- Distinguish recommended path, alternatives, and open questions.
- Include enough detail that the idea can become a skill, script, or template
  change in a later pass.
