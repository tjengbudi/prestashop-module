# Analysis Report: psm-optimize

Generated: 2026-07-08T14:40:00Z · Schema: 2

**Grade: Excellent**

> Excellent and materially tighter after this fix pass: the no-profiler dead-end is closed for every optimization class (not just N+1), architecture and customization are clean, and only one deferred determinism item remains — a profiler-metric compare script that needs fixture output before it can ship tested.

psm-optimize is a cohesive, authentic evidence-based performance workflow whose one real weakness — a static/no-profiler path that dead-ended at the performance gate — is now fully resolved with a class-split proof (hotspot-delta for N+1/heavy-hook, mechanism-in-diff for cache/service/asset), a stale-invariant-free headless section, and a distinct no-op return shape. The remaining open item is the deferred profiler metric capture+compare script (determinism-1): the live flashlight spin-up is env-bound, but the parse and before/after compare are unit-testable and worth scripting once fixture profiler output exists.

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 0 |
| Medium | 1 |
| Low | 1 |

## Themes

### 1. No-profiler path fully closed across all optimization classes

- Root cause: The prior static-mode fix proved only N+1/heavy-hook fixes via hotspot-scan delta, which silently dead-ended cache/service/asset optimizations (they never move the candidate count) into a redesign loop. The verify gate now splits the static performance proof by fix class and gives cache/service/asset fixes an honest mechanism-in-diff exit with an explicit 'runtime tak terukur' report.
- Fix: Resolved — no action. Verified by enhancement (0 findings) and agent-cohesion (real exit confirmed) on rerun.

### 2. Profiler metric compare remains a prompt-carried scriptable comparison (deferred)

- Root cause: Both the profiler before/after delta and the static hotspot delta are computed by the model reading numbers out of a free-form markdown baseline. The live flashlight+Blackfire spin-up is genuinely env-bound and not unit-testable, but the metric PARSE and the COMPARE are testable against fixture output and were deliberately deferred this pass to avoid shipping an untested profiler parser.
- Fix: When fixture Blackfire/Xdebug output is available, add scripts/ps-profile-metrics.py: a compare mode that reads a machine-readable baseline (JSON sidecar) + fresh metrics and emits a membaik/regresi verdict, covering both profiler numbers and hotspot candidate counts. Store the baseline as JSON so the compare is deterministic on resume/headless. The live spin-up stays prompt orchestration.
- Findings:
  - `determinism-1` Profiler metric capture + before/after compare carried by prompt, no script (deferred) — `SKILL.md: Profil + Verifikasi`

### 3. Inline config.yaml parse is a family-wide low

- Root cause: Every psm sibling parses config.yaml + .user.yaml and extracts psm_target_versions / communication_language inline at activation — deterministic extraction with no script behind it.
- Fix: Family-level, not psm-optimize-specific: a shared config-resolver script emitting resolved psm settings as compact JSON that all psm skills read. Low priority — small, read once — but removes duplicated parsing across the family.
- Findings:
  - `determinism-2` Inline config.yaml + .user.yaml parse/merge/default in On Activation — `SKILL.md: On Activation #1`

## Strengths

- Authentic evidence-based performance-engineer persona and the three pantangan framing — genuine domain investment, preserved.
- Well-drawn script boundary: hotspot-scan over-collects and defers N+1 judgment to the model; psm-validate verdict read 'apa adanya'.
- Class-split static-mode performance proof — an honest exit for cache/service/asset fixes a profiler can't measure, instead of a false 'not improved'.
- Baseline-to-artifact discipline now also carries static candidate counts and pre-opt validate status, so both gates judge a real before/after delta across resume/headless.
- Single-sourced verification invariant: headless points at the Verifikasi gate rather than restating a version that can drift stale.
- First-class headless story with a distinct no-op return shape, and clean family integration.

## Recommendations

1. When fixture profiler output exists, add scripts/ps-profile-metrics.py (parse + before/after compare to a verdict) and store the baseline as JSON — makes the performance gate symmetric with the psm-validate half. (resolves: determinism-1)
2. Family-level: extract the shared config.yaml read into one resolver script emitting JSON, adopted across all psm skills. (resolves: determinism-2)

## Agent Profile

- Name: psm-optimize
- Title: PrestaShop Module Performance Engineer
- Type: stateless
- Mission: Speed up an existing PrestaShop module via cache/service-container without breaking cross-version compatibility or changing behavior, gated by measure-first discipline.

## Capabilities

- **Profil** (prompt + script) — Batch-run inventory + hotspot-scan, capture baseline (metrics/static candidate counts/pre-opt validate status); clean 'already lean' exit keyed on model judgment.
- **Identifikasi & rencana** (prompt + reference) — Pick opportunities from optimization-catalog, design version-safe fixes, write revisable plan, gate on approval.
- **Terapkan** (prompt) — Apply approved plan in place, version-branch legacy/modern, preserve behavior.
- **Verifikasi** (prompt + external skill) — Dual gate: psm-validate delta (no new failures) + class-split performance proof; static path has a real exit for every fix class.
- **ps-hotspot-scan.py** (script) — Mechanical over-collection of query-in-loop / heavy-hook candidates as JSON; N+1 judgment deferred to model.
- **Mode headless** (prompt) — Non-interactive path with distinct no-op 'sudah-ramping' return; verification gate survives, only confirmation is skipped.

## Per-Lens Verdicts

- **leanness**: Lean; prior duplications removed (delta rule single-sourced, catalog Pagar wajib deleted, headless condition-restatement dropped). Added Verifikasi coverage is warranted, not ceremony.
- **architecture**: Clean — frontmatter, progressive disclosure, dependency-real ordering, and the newly-batched profil scripts all wire correctly. Zero findings.
- **determinism**: Clean intelligence placement (scripts collect sites, model judges N+1); one standing leak — profiler capture+compare has no script (deferred, medium) — plus a family-wide inline config parse (low).
- **customization**: Clean — no build-time config surface exists and none is abused; customize.toml absence is the deliberate psm-family convention, shared config read at activation is the allowed path. Zero findings.
- **enhancement**: All four prior gaps confirmed closed; no add/subtract gaps survive a real run. Zero findings.
- **agent-cohesion**: Coherent and purposeful; the static non-N+1 path now has a class-appropriate exit closing the prior dead-end. Zero findings after the Overview alignment trim.

## Experience

- **Interactive optimize** — Budi names module → batched profil measures hotspots + baseline (metrics/static/validate status) → plan shown → approve → applied → dual gate (validate delta + class-split perf proof) → summary.
- **Already-lean no-op** — Profil finds no real hotspot after judging candidates → clean 'sudah ramping' exit before the plan gate, reported as success.
- **Headless (called by workflow/agent)** — Args instead of questions → confirm gate skipped, verification survives → assumptions logged → structured return, distinct no-op shape when already lean.
- Headless: First-class: dedicated section, distinct no-op return, single-sourced verification invariant that points at the gate instead of restating it.

## Findings

### Medium (1)

#### determinism-1 — Profiler metric capture + before/after compare carried by prompt, no script (deferred)

- Lens: determinism
- Location: `SKILL.md: Profil + Verifikasi`
- Evidence: Baseline capture records profiler numbers into a prose block and Verifikasi has the model 'bandingkan dengan blok baseline ... syaratnya metrik membaik'; the static branch likewise compares candidate counts by hand. The before/after delta is a Comparison-category computation that is deterministic and unit-testable given the same inputs. The live flashlight/Blackfire spin-up is env-bound and correctly stays prompt orchestration, but the parse and compare are not — they were deferred this pass to avoid shipping an untested profiler parser.
- Recommendation: Add scripts/ps-profile-metrics.py with a compare mode reading a JSON baseline + fresh metrics and emitting an improved/regressed verdict (covering both profiler numbers and hotspot candidate counts), tested against fixture profiler output; store the baseline as machine-readable JSON so the compare is deterministic on resume/headless.

### Low (1)

#### determinism-2 — Inline config.yaml + .user.yaml parse/merge/default in On Activation

- Lens: determinism
- Location: `SKILL.md: On Activation #1`
- Evidence: 'Muat config dari {project-root}/_bmad/config.yaml (+ .user.yaml bila ada). Ambil versi target dari section psm (psm_target_versions, default 1.7.8,8.1,9.0).' The model parses two known-format YAML files, overlays .user.yaml, extracts one key, and applies a default — all deterministic. Family-wide across psm skills.
- Recommendation: Family-level fix: a shared pre-pass config-resolver script that loads config.yaml, overlays .user.yaml, and emits resolved psm settings as compact JSON. Low severity — config is small and read once — but consolidating removes the parse duplicated across the psm family.
