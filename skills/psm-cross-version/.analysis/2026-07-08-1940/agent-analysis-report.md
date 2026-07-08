# Analysis Report: skills/psm-cross-version

Generated: 2026-07-08T12:40:27Z · Schema: 2

**Grade: Good**

> Three lenses clean and the prior regression is closed; the explicit totality claim in the headless contract now exposes two escape paths it does not yet cover — a missing-dependency halt and an unsupported target version.

psm-cross-version is structurally clean (architecture, leanness, and customization all pass) with the load-bearing persona preserved as investment. Making the headless return contract explicitly total was the right move — and it raised the bar it must meet: two reachable exits (ps-static-scan not installed; a target version outside the 1.7/8/9 catalog) currently return no contract status, so the totality claim is not yet literally true. Both are small, same-shape fixes.

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 0 |
| Medium | 2 |
| Low | 1 |

## Themes

### 1. Totality claim outruns coverage by two exits

- Root cause: The headless contract now asserts 'kontrak ini total, tiap masuk headless berujung di salah satunya' over passed/partial/blocked. Two reachable branches escape it: (a) ps-static-scan.py not found → 'hentikan' with no status (no operator to tell in headless); (b) a target version outside the 1.7/8/9 catalog returns zero scan findings, slides into the empty-map 'valid' branch, and a green psm-validate that also lacks that version's ruleset reads as a false 'passed'. Making the claim explicit is what surfaced both — a good outcome, but the claim must now be made true.
- Fix: Map both escapes to the contract: (1) the missing-dependency halt → return `blocked` (no risk map can be produced) with reason + memlog, and add it to the blocked bullet's causes; (2) at activation, validate each requested target major against the supported set (1.7/8/9) — if any is outside it, interactive: tell Budi it is unsupported and ask to drop/adjust; headless: return `blocked` with reason 'unsupported target version <x>' + memlog. Then the totality claim holds literally.
- Findings:
  - `cohesion-1` Missing-dependency halt is an unmapped headless terminal state — `SKILL.md:27 (Analisis) vs :56-60 (Mode headless)`
  - `enhancement-1` Add target-version-support guard at activation — `SKILL.md — On Activation (step 2) / Analisis (empty-risk-map branch)`

### 2. Deferred suite-wide config cleanup

- Root cause: The On-Activation config parse remains a determinism leak — the model loads and extracts config.yaml keys every invocation. The fix belongs at the psm-suite level, not this skill: resolve_config.py reads TOML while all 7 psm skills reference config.yaml, so changing one alone would diverge it from 6 siblings.
- Fix: Leave in place; resolve as a shared psm-suite convention cleanup (a config-loader emitting compact JSON, and a decision on TOML vs YAML across the suite).
- Findings:
  - `determinism-1` On-Activation config parse done by prompt (known deferred) — `SKILL.md:On Activation step 1`

## Strengths

- Prior regression closed and three lenses (architecture, leanness, customization) pass clean.
- Load-bearing persona preserved untouched across every pass: careful-migration-engineer voice, 'operator holds decisions' framing, design rationale — investment, not waste.
- Zero rule duplication: ps-static-scan.py is the risk-map engine (now also the resume drift check), psm-validate the final gate; version rules live only in ps-rules.json.
- Safety architecture intact and deepened: approval gate, git nudge, tri-version validation, wrong-path guard, resume reconcile-against-drift.
- Making the return contract explicit is itself a strength — it turned a silent gap into a checkable claim, which is why this rerun could name the two remaining escapes.

## Recommendations

1. Make the totality claim literally true: map the missing-dependency halt to blocked, and add an unsupported-target-version guard at activation that returns blocked (headless) or asks Budi (interactive). (resolves: cohesion-1, enhancement-1)
2. Leave the config parse to the tracked suite-wide cleanup (TOML-vs-YAML decision + shared config-loader across all 7 psm skills). (resolves: determinism-1)

## Agent Profile

- Name: psm-cross-version
- Title: PrestaShop cross-version migration engineer
- Type: stateless
- Mission: Turn one existing PrestaShop module into a single codebase that runs on 1.7.x, 8.x, and 9.x at once, via plan→confirm→apply→verify gated by psm-validate.

## Capabilities

- **Analisis: peta risiko per versi** (external script) — Reuses psm-validate's ps-static-scan.py; empty map distinguishes wrong-path from clean; halts if the script is absent (not yet mapped to a headless status).
- **Rencana perubahan** (prompt) — Designs version-safe fixes from references/version-safe-patterns.md into .psm-cross-plan.md.
- **Konfirmasi (gerbang)** (prompt) — Blocks on Budi's approval before touching any file.
- **Terapkan** (prompt) — version_compare branches; git nudge; stop-and-report partial on apply failure.
- **Verifikasi (gerbang wajib)** (external skill) — psm-validate ×3; blocked-state; plan-artifact cleanup offer at green handoff.
- **Mode headless** (prompt) — Return contract claims totality over passed/partial/blocked — two reachable exits not yet covered.

## Per-Lens Verdicts

- **leanness**: Passes; the explicit headless enumeration earns its keep as a totality contract (pointer-recaps, not restated trigger logic), and the redundant checklist was cut.
- **architecture**: Structurally sound — correct single-SKILL topology, one clean carve, resolving progressive disclosure, dependency-ordered linear pipeline.
- **determinism**: Clean script delegation throughout; only the known-deferred On-Activation config parse leaks, raised at low.
- **customization**: Stateless skill, about right — customize.toml deliberately declined, sole mechanism is shared config.yaml section psm; org pattern override exists via memory augment hook.
- **enhancement**: Lifecycle near-complete; one uncovered path where an unsupported target-version request can slip through the empty-risk-map guard into a false 'safe' claim.
- **agent-cohesion**: Terminal-state to contract mapping is sound except for one reachable headless exit (missing psm-validate dependency) that returns no status, contradicting the stated totality.

## Experience

- **Interactive migration** — Activate → resolve → scan (absent script → halt) → empty-map guard → plan → approve → apply → verify → summarize + cleanup offer
- **Resume** — Activate → detect plan → re-run ps-static-scan to reconcile drift → continue or revise
- **Headless** — Args in → ... → passed/partial/blocked (gaps: absent script and unsupported version have no mapped status)
- Headless: Return contract is explicitly total over passed/partial/blocked, but two reachable exits — ps-static-scan absent and target version out of catalog — are not yet mapped, so the totality claim is aspirational until they are.

## Findings

### Medium (2)

#### cohesion-1 — Missing-dependency halt is an unmapped headless terminal state

- Lens: agent-cohesion
- Location: `SKILL.md:27 (Analisis) vs :56-60 (Mode headless)`
- Evidence: Line 27: bila ps-static-scan.py tidak ditemukan (psm-validate belum terinstal), skill 'beri tahu Budi ... lalu hentikan'. This branch is reachable in headless mode, yet the headless contract asserts totality — 'kontrak ini total, tiap masuk headless berujung di salah satunya' — over passed/partial/blocked only. None cover 'psm-validate not installed': blocked is defined solely as 'temuan tanpa jalur version-safe' atau 'path bukan module PrestaShop'. In headless there is no Budi to tell, so this halt returns no contract status, leaving the caller (psm-agent-expert) without a terminal state.
- Recommendation: Map the missing-dependency halt to a headless return status (blocked is the natural fit — no risk map can be produced) and add it to the blocked bullet's causes, or add a fourth explicit status. Log the reason to memlog like the other headless exits so the contract stays genuinely total.

#### enhancement-1 — Add target-version-support guard at activation

- Lens: enhancement
- Location: `SKILL.md — On Activation (step 2) / Analisis (empty-risk-map branch)`
- Evidence: Valid-but-unexpected-input archetype: config psm_target_versions (or a Budi request like 'juga PS 1.6' / 'PS 10') can name a major the pattern catalog and ps-static-scan ruleset never cover. ps-static-scan then returns zero findings for that unknown version, which lands in the empty-risk-map branch → 'struktur valid' → confirm-once via psm-validate. If psm-validate likewise lacks that version's ruleset, a green confirm gets read as cross-version-safe for a version that was never actually checked — a silent false 'passed'. The existing empty-map guard only distinguishes already-safe vs wrong-path; it does not catch 'target version out of supported range'.
- Recommendation: At activation, after resolving target versions, validate each requested major against the supported/covered set (1.7/8/9). If any target falls outside it, don't proceed silently: interactive — tell Budi the version is unsupported by the pattern catalog/ruleset and ask to drop or adjust it; headless — return status `blocked` with reason 'unsupported target version <x>' and log to memlog. This keeps the verify gate from being fed a version it can't actually assess.

### Low (1)

#### determinism-1 — On-Activation config parse done by prompt (known deferred)

- Lens: determinism
- Location: `SKILL.md:On Activation step 1`
- Evidence: 'Muat config dari {project-root}/_bmad/config.yaml (+ .user.yaml bila ada). Ambil versi target dari section psm (psm_target_versions, default 1.7.8,8.1,9.0).' — the model loads two YAML files, merges the overlay, and extracts a typed section value, all deterministic parse/merge/extract work with one correct answer per input.
- Recommendation: A resolve_config helper should hand back compact JSON (resolved psm_target_versions, communication_language). KNOWN DEFERRED: resolve_config.py currently reads TOML while all 7 psm skills reference config.yaml, so fixing this one skill alone diverges it from 6 siblings — resolve as a shared psm-suite convention cleanup, not a per-skill edit. Not a new defect.
