# Analysis Report: skills/psm-cross-version

Generated: 2026-07-08T12:06:25Z · Schema: 2

**Grade: Good**

> Structurally sound stateless migrator with a rich, load-bearing persona; the one thing that matters is the verify loop has no honest exit when a finding is unresolvable across 1.7/8/9.

psm-cross-version is a tightly cohesive stateless agent: careful-migration-engineer persona drives a clean analyze→plan→confirm→apply→verify pipeline that reuses psm-validate as its risk-map engine and final gate with zero rule duplication — architecture and customization lenses came back clean, and the persona was treated as investment, not waste. Its primary opportunity is closing dead-ends in the lifecycle: the verify loop can spin forever on an irreconcilable API conflict, and two common entry/failure states (already-safe module, mid-apply failure) currently have no defined move.

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 1 |
| Medium | 2 |
| Low | 4 |

## Themes

### 1. Verify loop has no honest exit

- Root cause: When a psm-validate finding is genuinely irreconcilable across the target versions, the Verifikasi loop instructs 'write it back to the plan, re-plan, never declare done' with no termination condition — an infinite re-plan loop interactively, and an unbreakable one headless where no human can intervene. The gate correctly blocks a false pass but offers no honest way out.
- Fix: Add a terminal blocked-state to the verify/plan sections: when the same finding survives re-planning or is judged inherently unresolvable for the requested versions, stop looping and surface it — interactively present the blocker to Budi with options (drop a target version, accept a documented limitation, split codebase); headless, return status 'blocked' with the unresolvable findings and memlog the reason. Preserves 'never declare a false pass' while giving the stuck path a real next move.
- Findings:
  - `enhancement-1` Add a bailout when psm-validate can never pass (unresolvable finding) — `SKILL.md:Verifikasi (gerbang wajib) + Mode headless`
  - `cohesion-1` No escape path when a finding has no cross-version-safe fix — `SKILL.md:Verifikasi (gerbang wajib)`

### 2. Uncovered entry and failure states

- Root cause: The flow is written for the happy path (findings exist, every apply succeeds). It has no defined move for a module that is already cross-version-safe (empty risk map → risks a fabricated plan and a confirmation over nothing) or for a change that fails mid-apply (leaves the module in a partial state; headless could keep applying onto a broken base). Git is the assumed undo path but no checkpoint is secured before the first irreversible edit.
- Fix: Add three guards: (1) after the scan, early-exit if the risk map is empty — report already-safe (optionally confirm with one psm-validate run) and finish without a plan or approval; (2) in Terapkan, stop immediately on a failed/inconsistent apply, mark the change failed, and report the partial state (interactive: ask Budi; headless: return 'partial' + memlog); (3) offer a soft git-checkpoint nudge before the first apply, skipped in headless.
- Findings:
  - `enhancement-2` Add short-circuit when the module is already cross-version-safe — `SKILL.md:Analisis / Rencana perubahan`
  - `enhancement-3` Add mid-apply failure recovery, not just per-change status marking — `SKILL.md:Terapkan`
  - `enhancement-4` Offer a git checkpoint before first apply — `SKILL.md:Terapkan`

### 3. Minor prompt polish

- Root cause: Two low-cost cleanups that do not affect behavior: the Overview restates both gates a second time when the process line plus the operative sections already carry them, and On Activation hand-parses config.yaml keys the model could receive pre-resolved as JSON.
- Fix: Drop the Overview's trailing never/never sentence (gates remain explicit at Rencana, Verifikasi, and headless — route to a variant eval to confirm no emphasis loss matters), and consider a shared resolve step across the psm suite that hands the prompt compact JSON with psm_target_versions pre-split and communication_language resolved instead of parsing YAML by hand.
- Findings:
  - `leanness-1` Gate rules restated within Overview and again at their operative sections — `SKILL.md:Overview (final two sentences)`
  - `determinism-1` Config YAML parsed and key-extracted by prompt — `SKILL.md:On Activation step 1`

## Strengths

- Load-bearing persona: the careful-migration-engineer voice, the 'operator holds decisions, skill holds version-safe knowledge' framing, and the design rationale threaded through each section are investment, not waste — they make every capability prompt able to stay short. Preserve this voice on any fix pass.
- Zero rule duplication by design: reuses psm-validate's ps-static-scan.py as the risk-map engine and psm-validate itself as the final gate, so version rules live in exactly one place (ps-rules.json).
- Determinism discipline: explicitly forbids re-judging deterministic scan output by hand, uses the pre-pass JSON correctly, and delegates scan/validate/memlog to scripts.
- Safety architecture: plan→confirm→apply→verify with an un-skippable approval gate before irreversible source edits and a mandatory tri-version validation gate before declaring done.
- Correct stateless topology and clean customization surface: one SKILL.md, one well-named references/ carve-out, customize.toml appropriately declined in favor of the shared psm config section.

## Recommendations

1. Add a terminal blocked-state to the verify loop for irreconcilable findings (interactive: hand the decision to Budi; headless: return 'blocked' + memlog). Closes the only true dead-end and the single high-severity finding. (resolves: enhancement-1, cohesion-1)
2. Guard the entry and failure states: empty-risk-map early exit, mid-apply failure stop-and-report, and a soft git-checkpoint nudge before first apply. (resolves: enhancement-2, enhancement-3, enhancement-4)
3. Trim the Overview's duplicate gate sentence and pre-resolve config to JSON at activation — low-cost polish, no behavior change. (resolves: leanness-1, determinism-1)

## Agent Profile

- Name: psm-cross-version
- Title: PrestaShop cross-version migration engineer
- Type: stateless
- Mission: Turn one existing PrestaShop module into a single codebase that runs on 1.7.x, 8.x, and 9.x at once, via plan→confirm→apply→verify gated by psm-validate.

## Capabilities

- **Analisis: peta risiko per versi** (external script) — Reuses psm-validate's ps-static-scan.py as the deterministic per-version risk-map engine; reads source only for fix-design context.
- **Rencana perubahan** (prompt) — Designs version-safe fixes from references/version-safe-patterns.md, written to .psm-cross-plan.md as a revisable, resumable artifact.
- **Konfirmasi (gerbang)** (prompt) — Presents the plan and blocks on Budi's approval before touching any file — the un-skippable gate for irreversible source edits.
- **Terapkan** (prompt) — Applies approved changes in place with explicit version_compare branches, marking per-change status in the plan artifact.
- **Verifikasi (gerbang wajib)** (external skill) — Calls psm-validate across all three target versions; module is cross-version-safe only when green on 1.7/8/9.
- **Mode headless** (prompt) — Non-interactive path for workflow/agent callers: args instead of questions, no confirm gate, assumptions logged to memlog.

## Per-Lens Verdicts

- **leanness**: Lean and goal-framed throughout; one minor in-paragraph restatement of the plan/validate gates in the Overview.
- **architecture**: Stateless agent is structurally sound — correct one-SKILL topology with a single well-named carve-out, sound stateless activation, genuine step dependencies, guarded external refs, and no subagent/read-avoidance violations.
- **determinism**: Strong determinism discipline; scan/validate/memlog all delegated to scripts and pre-pass JSON used correctly. One low-severity config-parse leak.
- **customization**: Clean — customize.toml appropriately declined for a Claude Code SKILL; shared psm-section config read at activation is the sole, allowed config mechanism.
- **enhancement**: Core flow and headless are well-formed, but the verify loop has no escape hatch for unresolvable findings, and two common entry states (already-safe module, mid-apply failure) dead-end the user.
- **agent-cohesion**: Persona and capabilities cohere tightly; lifecycle is complete end-to-end with one minor unhandled outcome (irreconcilable conflict) in the verify loop.

## Experience

- **Interactive migration** — Activate → resolve module+versions → risk-map scan → draft plan → Budi approves → apply → psm-validate on 1.7/8/9 → summarize
- **Resume** — Activate → detect .psm-cross-plan.md → continue from last state instead of re-analyzing
- **Headless (workflow/agent caller)** — Args in → scan → plan → apply without confirm gate → validate → one-line summary + plan/memlog paths + per-version pass status
- Headless: Well-formed: args replace questions, confirm gate delegated to caller, assumptions logged to memlog, structured return with per-version pass status.

## Findings

### High (1)

#### enhancement-1 — Add a bailout when psm-validate can never pass (unresolvable finding)

- Lens: enhancement
- Location: `SKILL.md:Verifikasi (gerbang wajib) + Mode headless`
- Evidence: Verify says: if errors remain, write them back to .psm-cross-plan.md and re-plan from the artifact, and 'jangan menyatakan selesai'. There is no termination condition. If a finding is genuinely unresolvable for the target set (e.g. an API with no viable cross-version shim, or a dependency that cannot be bundled), the agent is trapped between 'cannot declare done' and 'cannot fix' — an infinite re-plan loop interactively, and worse headless where no human can break it.
- Recommendation: Add a blocked-state move: when the same finding survives re-planning (or is judged inherently unresolvable for the requested versions), stop looping and surface it — interactively present the blocker(s) to Budi with options (drop a target version, accept a documented limitation, or abandon); headless, return status 'blocked' with the unresolvable findings and memlog the reason. Preserves 'never declare a false pass' while giving the stuck path a real next move.

### Medium (2)

#### enhancement-2 — Add short-circuit when the module is already cross-version-safe

- Lens: enhancement
- Location: `SKILL.md:Analisis / Rencana perubahan`
- Evidence: A user may run this on a module that is already clean. The analysis engine can return zero risky findings, but the flow marches straight into 'Rencana perubahan' which is written for the case where findings exist. Nothing tells the agent to recognize an empty risk map and stop — risking a fabricated or empty plan and a confusing confirmation gate over nothing.
- Recommendation: After the risk map, add an explicit early exit: if the scan returns no cross-version findings, report to Budi that the module already passes across the target versions (optionally run psm-validate once to confirm) and finish without producing a plan or asking for approval.

#### enhancement-3 — Add mid-apply failure recovery, not just per-change status marking

- Lens: enhancement
- Location: `SKILL.md:Terapkan`
- Evidence: Terapkan marks each change's status in .psm-cross-plan.md and relies on Resume to pick up, which handles a clean interruption. But it does not say what to do when applying a change itself fails (edit doesn't fit, file moved, an applied change breaks the module) — leaving the module in a partial state with some changes done and no defined stop point. Headless makes this worse: the loop could continue applying downstream changes onto a broken base.
- Recommendation: Add: if applying a change fails or leaves the module inconsistent, stop immediately, mark that change as failed in .psm-cross-plan.md, and report the partial state — interactively ask Budi how to proceed; headless return a 'partial' status with the failed change and memlog it. State clearly that already-applied changes remain (git is the undo path) so the operator knows the module is mid-transformation.

### Low (4)

#### enhancement-4 — Offer a git checkpoint before first apply

- Lens: enhancement
- Location: `SKILL.md:Terapkan`
- Evidence: Terapkan only 'assumes Budi uses git' and mentions it if unclear, but does nothing to secure a rollback point before irreversible source edits begin. A user without a clean working tree, or on a dirty branch, loses the easy undo the whole design leans on.
- Recommendation: Just before the first apply, offer a one-line checkpoint suggestion (e.g. confirm a clean working tree or suggest a branch/commit) so the operator has a guaranteed rollback point. Keep it a soft nudge, not a hard gate; skip in headless where the caller owns the workspace.

#### leanness-1 — Gate rules restated within Overview and again at their operative sections

- Lens: leanness
- Location: `SKILL.md:Overview (final two sentences)`
- Evidence: Overview states the process 'rencana → konfirmasi → terapkan → verifikasi' and then closes with an emphatic restatement of the same two gates ('Tidak pernah menerapkan perubahan tanpa rencana yang disetujui, dan tidak pernah menyatakan selesai sebelum lolos psm-validate di 1.7.x + 8.x + 9.x'). Both gates are already carried at their point of use: the approval gate in 'Rencana perubahan' and the validate gate in 'Verifikasi (gerbang wajib)' and again in 'Mode headless'. The closing sentence adds no new constraint.
- Recommendation: Drop the Overview's closing never/never sentence; let the process line carry the mission and the 'Rencana'/'Verifikasi' sections carry the enforceable gates at their decision points.
- Proposed smallest: End the Overview after 'Konsumen hasil: Budi ... dan psm-agent-expert yang merangkai sesi.' Remove the trailing sentence 'Tidak pernah menerapkan perubahan tanpa rencana yang disetujui, dan tidak pernah menyatakan selesai sebelum lolos psm-validate di 1.7.x + 8.x + 9.x.'
- Predicted delta: Likely nothing — both gates remain explicit at their operative sections ('gerbang yang tak boleh dilewati', 'gerbang wajib') and in headless mode. Emphasis loss is marginal. Route to variant eval to confirm.

#### determinism-1 — Config YAML parsed and key-extracted by prompt

- Lens: determinism
- Location: `SKILL.md:On Activation step 1`
- Evidence: 'Muat config dari {project-root}/_bmad/config.yaml (+ .user.yaml bila ada). Ambil versi target dari section psm (psm_target_versions, default 1.7.8,8.1,9.0)... communication_language (default Indonesia).' — model reads the config file, extracts two keys, splits a comma-separated version list, and applies defaults by hand.
- Recommendation: Determinism leak (signal-verb 'Muat'/'Ambil' = parse/extract of a known format with schema-known keys and defaults). Have a resolve step hand the prompt compact JSON with psm_target_versions already list-split and communication_language resolved, so the model reasons over values instead of parsing YAML. Low because the file is tiny; note this is a shared-convention cleanup across the psm suite rather than this skill alone.

#### cohesion-1 — No escape path when a finding has no cross-version-safe fix

- Lens: agent-cohesion
- Location: `SKILL.md:Verifikasi (gerbang wajib)`
- Evidence: Verify loop instructs: on remaining psm-validate errors, re-write findings to .psm-cross-plan.md and re-plan from the artifact — never declare done. There is no branch for the case where an API genuinely has no version-safe path (e.g., a hard 1.7-vs-9 conflict), so the plan→apply→verify loop implies indefinite retry with no defined termination or decision hand-back.
- Recommendation: Add a terminal outcome in the verify/plan sections: when a finding is irreconcilable across the target versions, surface it back to Budi as a decision (drop a version, accept a limitation, or split codebase) rather than looping. In-persona for a careful engineer who leaves decisions to the operator, and closes the only dead-end in the journey.
