# Analysis Report: skills/psm-develop

Generated: 2026-07-08T09:34:00+00:00 · Schema: 2

**Grade: Good**

> Skill is lean and well-structured; one medium finding mirrors psm-cross-version — missing guard for the ps-static-scan.py cross-module dependency leaves users stranded at step one of a destructive workflow.

psm-develop is a clean, well-reasoned workflow with a working ps-module-inventory.py script and matching tests. The plan→confirm→apply→verify invariant is correctly enforced. One medium gap: no guard for the psm-validate dependency in the Pahami section, same pattern as psm-cross-version.

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 0 |
| Medium | 2 |
| Low | 3 |

## Themes

### 1. Undocumented cross-module dependency failure path

- Root cause: ps-static-scan.py lives in psm-validate; psm-develop has no guard for when it is absent. User installing psm-develop standalone hits a Python error at the first substantive step of a destructive workflow.
- Fix: Add one guard sentence after the ps-static-scan.py uv run call in 'Pahami module existing': 'Bila script tidak ditemukan, beri tahu Budi bahwa psm-validate harus terinstal di {project-root}/skills/psm-validate/ lalu hentikan.'
- Findings:
  - `architecture-1` Cross-module script dependency with no missing-dep guard (psm-validate) — `SKILL.md:Pahami module existing — uv run {project-root}/skills/psm-validate/scripts/ps-static-scan.py`
  - `enhancement-1` Missing: dependency-check pattern for cross-module script — `SKILL.md:Pahami module existing`

### 2. Path-scanner false positives on artifacts

- Root cause: scan-path-standards.py scans .analysis/ and .memlog.md. All 8 highs are in generated artifacts and process memory.
- Fix: No skill change needed.
- Findings:
  - `architecture-2` Path-scanner false positives on .analysis/ artifacts and .memlog.md — `.analysis/2026-06-25-2003/, .memlog.md`

## Strengths

- Two-script analysis design is sound: deterministic fact extraction (ps-module-inventory.py + ps-static-scan.py) cleanly separated from judgment (where to insert safely). No model parsing PHP by hand.
- Plan validation against inventory before confirm is a concrete, behavioral gate — not just a suggestion.
- ps-module-inventory.py is correct and well-tested (8 assertions), covers hooks/ObjectModel/controllers/version/upgrade-dir.
- ecommerce-function-catalog.md is self-contained: domain coverage, hook hints, and adding-to-existing rules all in one reference.
- Headless mode is complete: memlog wiring, no interactive gates, structured return documented.

## Recommendations

1. In SKILL.md 'Pahami module existing', after the ps-static-scan.py uv run line, add: 'Bila script tidak ditemukan, beri tahu Budi bahwa psm-validate harus terinstal di {project-root}/skills/psm-validate/ lalu hentikan.' Same guard pattern as psm-cross-version fix. (resolves: architecture-1, enhancement-1)
2. In ps-module-inventory.py line 86, change 'module_path': str(module_dir) to 'module_path': str(module_dir.relative_to(Path.cwd())) with a fallback to str(module_dir) if relative_to fails. Prevents absolute path in JSON output from triggering scan-path-standards.py on saved artifacts. (resolves: determinism-1)

## Experience

- **Normal flow** — Activation → config → module path + feature → resume check → augment KB → inventory scan → static scan → offer functions → plan → validate plan vs inventory → confirm → apply → psm-validate → summary
- **Resume flow** — Activation → detect .psm-develop-plan.md → read last state → continue from last pending function
- **Headless flow** — Args parse → both scans → plan to artifact → apply → psm-validate → structured return with memlog
- Headless: Fully headless-ready — dedicated Mode headless section, memlog.py wiring, structured return documented.

## Findings

### Medium (2)

#### architecture-1 — Cross-module script dependency with no missing-dep guard (psm-validate)

- Lens: architecture
- Location: `SKILL.md:Pahami module existing — uv run {project-root}/skills/psm-validate/scripts/ps-static-scan.py`
- Evidence: The Pahami section requires ps-static-scan.py from psm-validate. No guard or message documents what to do if the script is missing. User installing psm-develop standalone encounters a Python error at step one of a destructive workflow.
- Recommendation: After the ps-static-scan.py uv run line, add: 'Bila script tidak ditemukan, beri tahu Budi bahwa psm-validate harus terinstal di {project-root}/skills/psm-validate/ lalu hentikan.'

#### enhancement-1 — Missing: dependency-check pattern for cross-module script

- Lens: enhancement
- Location: `SKILL.md:Pahami module existing`
- Evidence: Same pattern as psm-cross-version: ps-static-scan.py dependency is load-bearing and undocumented. First-time user without psm-validate gets a traceback at step one of a destructive workflow with no recovery path.
- Recommendation: Same fix as architecture-1: add one guard sentence after the uv run command.

### Low (3)

#### architecture-2 — Path-scanner false positives on .analysis/ artifacts and .memlog.md

- Lens: architecture
- Location: `.analysis/2026-06-25-2003/, .memlog.md`
- Evidence: 8 highs from scan-path-standards.py — all in generated artifacts and process memory. Source files are path-clean.
- Recommendation: No skill change. Scope scan-path-standards.py to exclude .analysis/ and .memlog.md.

#### determinism-1 — ps-module-inventory.py emits absolute module_path in JSON output

- Lens: determinism
- Location: `scripts/ps-module-inventory.py:86`
- Evidence: 'module_path': str(module_dir) — module_dir is resolved to absolute path on line 39. If output is saved as a working artifact, scan-path-standards.py flags it as a portable-path violation.
- Recommendation: Change to relative path where possible: use module_dir.relative_to(Path.cwd()) with fallback to str(module_dir) if outside cwd. Low impact — only affects saved artifact scans.

#### customization-1 — No customize.toml — missing persistent_facts for project context

- Lens: customization
- Location: `skills/psm-develop/ (no customize.toml)`
- Evidence: No customize.toml, so no persistent_facts glob loads project-context.md at activation.
- Recommendation: Low priority. Add customize.toml with [workflow] persistent_facts = ["file:{project-root}/**/project-context.md"] if project context becomes useful across invocations.
