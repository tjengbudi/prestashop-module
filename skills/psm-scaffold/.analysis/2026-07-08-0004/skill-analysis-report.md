# Analysis Report: skills/psm-scaffold

Generated: 2026-07-08T09:37:00+00:00 · Schema: 2

**Grade: Excellent**

> Skill passes all lenses cleanly; one low-impact script fix (absolute path in JSON output) and the usual artifact false positives.

psm-scaffold is the leanest and cleanest of the psm skills reviewed. The deterministic generator approach is well-executed: same inputs produce the same scaffold, and the Verifikasi gate is correctly enforced. One low finding mirrors the ps-module-inventory.py fix: ps-scaffold.py emits an absolute path in its JSON output.

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 3 |

## Themes

### 1. Absolute path in script JSON output

- Root cause: ps-scaffold.py resolves module_dir to absolute path (line 121) and writes it directly to output JSON (line 147). Saved artifacts will be flagged by scan-path-standards.py, same issue fixed in ps-module-inventory.py.
- Fix: Same fix as ps-module-inventory.py: use module_dir.relative_to(Path.cwd()) with fallback to str(module_dir).
- Findings:
  - `determinism-1` ps-scaffold.py emits absolute module path in JSON output — `scripts/ps-scaffold.py:147`

### 2. Path-scanner false positives on artifacts

- Root cause: scan-path-standards.py scans .analysis/ and .memlog.md. All 12 highs are in generated artifacts and process memory.
- Fix: No skill change needed.
- Findings:
  - `architecture-1` Path-scanner false positives on .analysis/ artifacts and .memlog.md — `.analysis/2026-06-25-1927/, .memlog.md`

## Strengths

- Deterministic generator: same name+author+versions → same scaffold. Model never hand-writes PHP — eliminates whole class of kerangka errors.
- Proven correct: memlog records SKILL.md that kerangka output passes ps-static-scan at all three versions with 0 errors 0 warnings.
- Telanjang-by-design is the right call: scaffold + validate first, then psm-develop adds functions. Clean separation of concerns.
- Headless mode is complete: skip interactive e-commerce offer, memlog assumptions, structured return with psm-validate verdict.
- Soft fallback for e-commerce catalog: 'bila belum, andalkan pengetahuan e-commerce umum' — skill does not dead-end if KB is absent.

## Recommendations

1. In ps-scaffold.py line 147, change '"path": str(module_dir)' to relative path using module_dir.relative_to(Path.cwd()) with fallback to str(module_dir), same pattern as ps-module-inventory.py fix. (resolves: determinism-1)

## Experience

- **Normal flow** — Activation → config load → gather name/author/versions → ps-scaffold.py → composer reminder → offer e-commerce functions → psm-validate → summary
- **Headless flow** — Args parse → ps-scaffold.py → psm-validate → structured return (skip e-commerce offer unless provided)
- Headless: Fully headless-ready — dedicated Mode headless section, memlog.py wiring, structured return with psm-validate verdict path.

## Findings

### Low (3)

#### architecture-1 — Path-scanner false positives on .analysis/ artifacts and .memlog.md

- Lens: architecture
- Location: `.analysis/2026-06-25-1927/, .memlog.md`
- Evidence: 12 highs from scan-path-standards.py — all in generated artifacts and process memory. Source files (SKILL.md, scripts/ps-scaffold.py) are path-clean.
- Recommendation: No skill change. Scope scan-path-standards.py to exclude .analysis/ and .memlog.md.

#### determinism-1 — ps-scaffold.py emits absolute module path in JSON output

- Lens: determinism
- Location: `scripts/ps-scaffold.py:147`
- Evidence: '"path": str(module_dir)' — module_dir is resolved to absolute on line 121. If output is saved as artifact, scan-path-standards.py flags it. Same issue as ps-module-inventory.py line 86, recently fixed.
- Recommendation: Change to: try relative_to(Path.cwd()), fall back to str(module_dir). One-liner, same fix applied to ps-module-inventory.py.

#### customization-1 — No customize.toml — no persistent_facts for project context

- Lens: customization
- Location: `skills/psm-scaffold/ (no customize.toml)`
- Evidence: psm_modules_dir and psm_target_versions are correctly read from config.yaml — right mechanism. No persistent_facts glob to load project-context.md at activation.
- Recommendation: Low priority. Add customize.toml with persistent_facts glob if project context becomes relevant across scaffold invocations.
