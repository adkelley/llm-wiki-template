Commit Style Guide (Jeremy Chone–Inspired)

A concise, high-signal commit message format designed for fast scanning in `git log --oneline` while preserving semantic meaning.

---

## Format

```
<symbol> <scope> - <summary>
```

### Components

- **symbol** — denotes the type of change (required)
- **scope** — subsystem, module, or concern (optional but recommended)
- **summary** — short, present-tense description (required)

---

## Symbols

| Symbol | Meaning     | When to Use                                          |
| ------ | ----------- | ---------------------------------------------------- |
| `+`    | Addition    | New feature, capability, or support                  |
| `-`    | Fix         | Bug fix or correction                                |
| `^`    | Improvement | Enhancing existing functionality                     |
| `!`    | Important   | Breaking change, API change, or major behavior shift |
| `>`    | Refactor    | Internal restructuring without changing behavior     |
| `.`    | Minor       | Maintenance, docs, cleanup, version bumps            |

> Note: Older variants may use `*` instead of `>` for refactor.

---
## Examples

auth - add GitHub OAuth login
parser - fix panic on empty input
cli - improve error messages for invalid flags
config - change default pull behavior to rebase
db - refactor query builder into separate module
docs - fix typos in installation guide
`
---

## Scope Guidelines

Scopes help localize the change. Keep them short and consistent.

**Common scopes:**

- `cli`
- `git`
- `docs`
- `config`
- `parser`
- `api`
- `db`
- `ui`
- `tests`
- `deps`
- `macos`

**Examples:**

```
+ git - add support for shallow clone
- macos - fix path resolution issue
^ docs - improve rebase explanation
```

---
## Summary Guidelines
Write summaries that are:
- **Concise** — ideally under ~72 characters
- **Present tense** — “add”, not “added”
- **Specific** — describe *what* changed, not just “update”
### Good
```
+ git - add explanation for detached HEAD
```
### Avoid
```
+ stuff - updated things
```
---

## Decision Heuristics

When choosing a symbol:

- Use `+` if something **new exists**
- Use `-` if something **was broken and is now fixed**
- Use `^` if something **got better but already existed**
- Use `!` if the change **affects users or breaks expectations**
- Use `>` if you **restructured code without changing behavior**
- Use `.` if it's **low-impact maintenance**

## Practical Examples (Git Learning

```
+ gitignore - add .tool-versions to ignored files
- clone - fix incorrect branch checkout example
^ docs - improve merge vs rebase explanation
! config - change default pull strategy to rebase
> examples - refactor setup walkthrough into sections
. docs - typo fixes
```

## 

This system optimizes

- **Scanability** — quickly understand history at a glance
- **Signal over noise** — minimal verbosity, maximum meaning
- **Consistency** — predictable structure across

It is intentionally lightweight compared to systems like Conventional Commits, while still conveying semantic

## Optional

If needed, you can extend

- Multiple scopes:
  `^ cli/db - improve

- Breaking-change detail (paired with `!`):
  `! api - rename Response.content to

## Final

Before

- [ ] Did I choose the correct symbol?
- [ ] Is the scope accurate and concise?
- [ ] Is the summary clear and in present tense?
- [ ] Would this make sense in `git log
