# Raw

This directory stores the repository’s source material and other immutable inputs.

## Subdirectories

- `articles/` — clipped web articles, such as captures created with Obsidian Web Clipper
- `assets/` — downloaded images and other attached media
- `data/` — structured data files such as CSV, JSON, and benchmark results
- `papers/` — PDFs and other academic paper sources
- `repos/` — repository source materials such as `README.md` files and architecture notes from codebases
- `transcripts/` — meeting notes and podcast or video transcripts

## Guidelines

- Treat files in `raw/` as source inputs, not working documents.
- Avoid editing these files after ingest unless you are correcting a bad import.
- Store derived notes, summaries, and syntheses under `wiki/`, not `raw/`.