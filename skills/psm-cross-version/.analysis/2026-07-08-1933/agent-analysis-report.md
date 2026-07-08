# Analysis Report: skills/psm-cross-version

Generated: 2026-07-08T12:33:18Z · Schema: 2

**Grade: Good**

> The prior fix pass closed the high but left the headless return contract non-total — the newly added already-safe and no-module branches have no passed/partial/blocked status — which is now the thing that matters.

psm-cross-version remains structurally clean (architecture and customization lenses pass) with a complete interactive lifecycle and a preserved load-bearing persona. Its primary opportunity is a self-introduced one: the empty-risk-map guard added interactive branches (report already-safe / report no-module) without pinning headless return statuses, so a headless caller hitting either branch dead-ends; a pre-existing resume gap (stale plan vs. drifted source) also surfaced.

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 0 |
| Medium | 3 |
| Low | 2 |

## Themes

### 1. Headless return contract is not total

- Root cause: The last fix added two interactive-only branches to the analysis step — 'report already-safe' (green empty map) and 'report no PrestaShop module at <path>' (empty map, no structure). Both call for reporting to Budi, but the headless return contract enumerates only passed/partial/blocked and no operator is present headless. So a headless caller (psm-agent-expert is a named consumer) that hits either branch gets no terminal status and the automation dead-ends. This is a regression the empty-map guard introduced.
- Fix: Make the return contract total: map the already-safe green-confirmation branch to `passed` (state it explicitly), and give the no-module/wrong-path branch a terminal headless status — return `blocked` with reason 'no PrestaShop module at <path>' and memlog it instead of asking Budi. Every headless entry then resolves to exactly one status.
- Findings:
  - `cohesion-1` already-safe terminal state absent from headless return contract — `SKILL.md — Analisis (already-safe path, ~line 29) vs Mode headless (return contract, ~line 53)`
  - `enhancement-1` Headless no-module/wrong-path has no terminal return status — `SKILL.md — Analisis: peta risiko per versi + Mode headless`

### 2. Resume does not reconcile against drifted source

- Root cause: Resume reads .psm-cross-plan.md to continue from the last per-change status, but nothing checks whether the source drifted between sessions (Budi hand-edited, another tool ran, a prior partial apply left a mismatched base). Applying a stale plan onto a changed base silently reintroduces the irreversible-edit risk the confirm gate exists to prevent.
- Fix: On resume, add a one-line reconcile nudge: note that plan statuses reflect the last session and, before applying remaining changes, re-run the (cheap, deterministic) ps-static-scan to confirm the risk map still matches the plan — if it diverges, revise from the fresh scan rather than applying blind.
- Findings:
  - `enhancement-2` Resume does not reconcile plan against source changed between sessions — `SKILL.md — On Activation step 3 (Resume)`

### 3. Minor polish

- Root cause: Two low-cost items with no behavior impact: the reference's closing checklist restates catalog facts the reader already holds and duplicates what psm-validate authoritatively gates, and the On-Activation config parse remains a determinism leak.
- Fix: Cut the closing checklist from version-safe-patterns.md (each section already carries its rule; psm-validate is the authority). Leave the config parse to the tracked suite-wide cleanup — resolve_config.py reads TOML while all 7 psm skills reference config.yaml, so fixing this skill alone would diverge it from 6 siblings.
- Findings:
  - `leanness-1` Closing checklist restates catalog facts and duplicates the validator gate — `references/version-safe-patterns.md (closing 'Checklist keluaran cross-version')`
  - `determinism-1` On-Activation config parse is a determinism leak (known, deferred) — `SKILL.md:On Activation #1`

## Strengths

- Prior high stays closed: verify loop has honest terminal states (blocked/partial/already-safe), confirmed across passes.
- Load-bearing persona preserved untouched: careful-migration-engineer voice, 'operator holds decisions' framing, design rationale — investment, not waste.
- Zero rule duplication: ps-static-scan.py is the risk-map engine, psm-validate the final gate; version rules live only in ps-rules.json.
- Clean architecture and customization: correct stateless topology, self-contained reference, deliberate no-customize.toml pattern consistent with sibling psm skills.
- Safety architecture intact: approval gate before irreversible edits, git-checkpoint nudge, mandatory tri-version validation, and now a wrong-path guard on the already-safe shortcut.

## Recommendations

1. Make the headless return contract total: map already-safe → passed, and give the no-module/wrong-path branch a terminal blocked status with reason + memlog instead of an interactive-only report. (resolves: cohesion-1, enhancement-1)
2. Add a resume reconcile nudge: re-run ps-static-scan before applying a resumed plan and revise if the risk map diverged from the recorded plan. (resolves: enhancement-2)
3. Cut the closing checklist from version-safe-patterns.md; leave the config parse to the tracked suite-wide cleanup. (resolves: leanness-1, determinism-1)

## Agent Profile

- Name: psm-cross-version
- Title: PrestaShop cross-version migration engineer
- Type: stateless
- Mission: Turn one existing PrestaShop module into a single codebase that runs on 1.7.x, 8.x, and 9.x at once, via plan→confirm→apply→verify gated by psm-validate.

## Capabilities

- **Analisis: peta risiko per versi** (external script) — Reuses psm-validate's ps-static-scan.py; empty map now distinguishes wrong-path from clean module and requires green confirmation before declaring safe.
- **Rencana perubahan** (prompt) — Designs version-safe fixes from references/version-safe-patterns.md into .psm-cross-plan.md, a revisable, resumable artifact.
- **Konfirmasi (gerbang)** (prompt) — Blocks on Budi's approval before touching any file.
- **Terapkan** (prompt) — version_compare branches; git-checkpoint nudge; stop-and-report partial on apply failure.
- **Verifikasi (gerbang wajib)** (external skill) — psm-validate ×3; blocked-state hands irreconcilable findings back to Budi; offers plan-artifact cleanup at green handoff.
- **Mode headless** (prompt) — Return contract enumerates passed/partial/blocked — but not the already-safe or no-module outcomes the analysis branch can now produce.

## Per-Lens Verdicts

- **leanness**: Largely goal-stated prose; the domain catalog is genuine institutional knowledge. One low: the closing checklist in version-safe-patterns.md restates catalog facts and duplicates the validator gate.
- **architecture**: Structurally sound: correct stateless topology, self-contained carved reference, sound plan→apply→verify ordering, script-delegated analysis.
- **determinism**: Clean intelligence placement — deterministic scan and validation are script-delegated; only leak is the known-deferred config parse.
- **customization**: Stateless skill; config.yaml (read at activation) is the sole and correct mechanism; no customize.toml is a deliberate, family-consistent choice.
- **enhancement**: Core flow and terminal handling solid; two gaps — no headless status for the no-module case, and resume does not reconcile a stale plan against source changed between sessions.
- **agent-cohesion**: Pipeline coheres end-to-end; one lifecycle-state gap — the already-safe terminal outcome is unreachable in the headless return contract.

## Experience

- **Interactive migration** — Activate → resolve → scan (empty → structure check → already-safe/no-module) → plan → approve → git nudge → apply (fail → partial) → validate ×3 (irreconcilable → blocked) → summarize + cleanup offer
- **Resume** — Activate → detect .psm-cross-plan.md → continue from last per-change status (gap: does not re-check source drift)
- **Headless** — Args in → scan → plan → apply → validate → passed/partial/blocked (gap: no status for already-safe or no-module)
- Headless: Return contract is passed/partial/blocked referencing guard sites, but is not yet total — the already-safe and no-module branches added by the last fix have no mapped terminal status.

## Findings

### Medium (3)

#### cohesion-1 — already-safe terminal state absent from headless return contract

- Lens: agent-cohesion
- Location: `SKILL.md — Analisis (already-safe path, ~line 29) vs Mode headless (return contract, ~line 53)`
- Evidence: The Analisis empty-risk-map path defines a fourth terminal outcome: module already cross-version-safe → confirm once with psm-validate, 'hanya bila hijau laporkan ke Budi bahwa module sudah lolos... selesai tanpa rencana atau gerbang persetujuan.' The Mode headless return contract enumerates only 'passed, partial, atau blocked', each pinned to a pipeline trigger ('Terapkan untuk partial, Verifikasi untuk blocked, gerbang wajib untuk passed'). The already-safe path never reaches the 'gerbang wajib' gate (it exits early), so a headless caller (psm-agent-expert, a named consumer) receiving an already-safe module has no defined return status — and 'laporkan ke Budi' has no operator present headless.
- Recommendation: Map the already-safe green confirmation to the existing `passed` status (state explicitly that an already-safe module returns `passed`), or add `already-safe` as a fourth headless status pinned to the Analisis confirm-green branch, so the four terminal states and the headless return contract match 1:1.

#### enhancement-1 — Headless no-module/wrong-path has no terminal return status

- Lens: enhancement
- Location: `SKILL.md — Analisis: peta risiko per versi + Mode headless`
- Evidence: The empty-risk-map guard resolves the wrong-path/no-module case interactively ('laporkan tidak ada module ... minta Budi konfirmasi path'). But the headless contract mandates exactly one of passed | partial | blocked per invocation, and none maps to 'target path is not a PrestaShop module.' A headless caller pointed at a bad path gets an interactive-style report and no terminal status, dead-ending the automation.
- Recommendation: In the empty-risk-map guard, add a headless branch: when structure is absent and no operator is present, return `blocked` (or a distinct terminal status) with reason 'no PrestaShop module at <path>' and log to memlog, instead of asking Budi to confirm. Keeps the return contract total for every headless entry.

#### enhancement-2 — Resume does not reconcile plan against source changed between sessions

- Lens: enhancement
- Location: `SKILL.md — On Activation step 3 (Resume)`
- Evidence: Resume reads .psm-cross-plan.md to 'melanjutkan dari keadaan terakhir alih-alih menganalisis ulang.' Prior passes cover failure DURING apply, but not the gap where source drifted between sessions — Budi hand-edited files, ran another tool, or a prior partial apply left a base that no longer matches the recorded per-change statuses. Applying a stale plan onto a changed base silently reintroduces the irreversible-edit risk the confirm-gate exists to prevent.
- Recommendation: On resume, add a one-line reconcile nudge: note that plan statuses reflect the last session and, before applying remaining changes, re-run ps-static-scan (cheap, deterministic) to confirm the risk map still matches the plan — if it diverges, revise the plan from the fresh scan rather than applying blind.

### Low (2)

#### leanness-1 — Closing checklist restates catalog facts and duplicates the validator gate

- Lens: leanness
- Location: `references/version-safe-patterns.md (closing 'Checklist keluaran cross-version')`
- Evidence: The closing checklist repeats items already stated in the sections above: 'ps_versions_compliancy terisi' (composer.json section), 'prepend-autoloader: false' (composer.json section), 'variabel Smarty di-escape' (Templates section), 'cabang versi pakai _PS_VERSION_/version_compare' (Deteksi versi + Konstanta sections). The final item 'Lolos psm-validate di 1.7.x, 8.x, dan 9.x' duplicates SKILL.md's verification gate — a hand-checklist over exactly what the deterministic psm-validate scan already verifies.
- Recommendation: Cut the checklist. Each catalog section already carries its rule at the point of use, and psm-validate is the authoritative gate — removing the recap changes no model move. If a single closing pointer is wanted, one line suffices, but even that repeats SKILL.md.

#### determinism-1 — On-Activation config parse is a determinism leak (known, deferred)

- Lens: determinism
- Location: `SKILL.md:On Activation #1`
- Evidence: 'Muat config dari {project-root}/_bmad/config.yaml (+ .user.yaml bila ada). Ambil versi target dari section psm (psm_target_versions, default 1.7.8,8.1,9.0)' — the model loads/merges two YAML files, extracts the psm section, reads a key, applies a default, and splits a comma list. Every operation has one correct answer for a given input, so it fails the determinism test.
- Recommendation: Push config resolution into a pre-pass script that hands the model compact JSON. KNOWN DEFERRED: repo's resolve_config.py reads TOML while all 7 psm skills reference config.yaml; fixing this skill alone would diverge it from 6 identical siblings. Raised at low for completeness only — resolve as a shared psm-suite convention cleanup, not in this skill in isolation.
