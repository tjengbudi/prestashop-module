---
id: SPEC-psm-e2e-tiered-gate
companions:
  - tier-matrix.md
  - cell-contract.md
  - brownfield.md
  - ../../../.claude/skills/psm-validate/SKILL.md
  - ../../../.claude/skills/psm-validate/references/run-phases.md
sources: []
---

> **Canonical contract.** This SPEC and the files in `companions:` are the complete, preservation-validated contract for what to build, test, and validate. Source documents listed in frontmatter are for traceability only — consult them only if you need narrative rationale or prose color this contract intentionally omits.

# psm-validate: tiered, faster E2E gate

## Why

Pain. Layer 4 (browser E2E) of psm-validate covers 3 PrestaShop versions (1.7.8, 8.1, 9.1) × 2 browsers (Chromium, Firefox). Each version cold-boots its own PS+DB container, browsers run one after another inside it, and one source patch makes every version's evidence stale. Budi waits roughly a full day per validation. Most of that time goes to re-proving cells that a single cheap canary run could have shown were broken or fine. The work must cut the wait without weakening the release gate's rule that `ready` needs fresh, conclusive evidence for every version × browser.

## Capabilities

- **CAP-1**
  - **intent:** The operator gets E2E feedback in two tiers: a canary cell (default 9.1 × Chromium) during the fix loop, run inside the canary version's Phase 1 loop (its first run cold and full-scenario; the warm container and failed-only reruns only after a failure), then the release gate, where every remaining cell runs: each other version boots cold once with Chromium and Firefox in parallel (CAP-7), and the canary version boots once for its non-canary browsers. The gate (Phase 2) starts only after every version is clean on Layers 1, 2, and 5 and the canary has passing gate-grade evidence or is not-gradeable, unless the E2E loop has ended (`cell-contract.md` > Plan > Phase 2 entry) or the operator stopped convergence (`cell-contract.md` > Plan > Stop convergence; the gate then does not run). A gate failure at (V, browser) sends the loop back to that cell, then re-proves V and the canary cold before the gate resumes.
  - **success:** With a module that has a blocking E2E bug and no failing non-canary cell, no non-canary cell boots until the canary passes. With a clean module, both tiers run and `ready` is true. Tier contents and loop-back steps follow `tier-matrix.md`. `ps-plan-layers.py` computes the tier, step, and next cells (`cell-contract.md` > Plan), and a test asserts that `e2e_next_cells` holds a non-canary cell only when `e2e_step` is `gate`, or when it is `focus` or `cold-version` and the cell is, or shares the version of, `e2e_focus_cell`. A smoke-only module, or one whose specs carry notes, still runs tier 1 once so every configured cell gets the universal smoke; `ready` stays false.
- **CAP-2**
  - **intent:** The planner judges E2E freshness per (version, browser), so evidence that is narrowed or partial never counts as complete.
  - **success:** After a Chromium-only run, the plan marks Firefox `rerun` for every version. The aggregate gives `ready=false` whenever any configured (version, browser) lacks passing gate-grade evidence. The same applies to evidence from a subset of scenarios (CAP-4). "Configured", the evidence record, freshness, conclusiveness, and gate-grade are defined in `cell-contract.md`.
- **CAP-3**
  - **intent:** A multi-cell E2E run stops starting new cells after the first conclusive blocking finding.
  - **success:** With `--slots 1` (the daemon slot count stubbed), three queued cells on three distinct versions, and a conclusive blocking failure in the first, the other two cells are reported as `not-run` (inconclusive, never a pass) and the progress log shows no `bring-up` for them. In the sequential-browsers fallback, the second engine of a version whose first engine fails gets `not-run`. Trigger, scope, and the `not-run` record follow `cell-contract.md`.
- **CAP-4**
  - **intent:** During the fix loop, the operator can re-run only the scenarios that failed in a version's latest evidence.
  - **success:** A rerun touches only the previously failed scenarios of that (version, browser) cell, their transitive prerequisites declared in the scenario spec field `requires` (for a failed scenario without `requires`, every scenario whose file name sorts before it), and the universal smoke. The implementation adds `requires` to bankwire's E2E specs (`modules/bankwire/tests/e2e/*.json`). Its evidence is marked partial, and the plan still requires a full-scenario run for that cell before the gate. Selection rules and fallbacks follow `cell-contract.md`.
- **CAP-5**
  - **intent:** In interactive runs, once the focus cell has a recorded failure, the fix-loop container (tier 0 focus cell) stays up across iterations, so an iteration skips bring-up and wait-healthy. Headless runs never use it.
  - **success:** The first focus-cell run without a recorded failure is cold. Every warm iteration after the one that started the keeper shows no `bring-up` or `wait-healthy` phase in the progress log. Each warm iteration starts from a DB restored to the baseline captured before the first install, with every file added since that baseline removed, and a freshly copied and installed module, so DB rows and added files from the previous iteration cannot cause a finding. Files that existed before install and were modified are not restored; the cold runs catch them. A keeper process owns the container under a warm Job ID: it stops via `--stop-job <warm-id>`, tears down after an idle TTL (default 60 minutes), and `--cleanup-orphans` removes it only after the keeper is dead. Ownership, reset, and teardown follow `cell-contract.md`.
- **CAP-6**
  - **intent:** Each E2E run records how long each phase took, per version and browser.
  - **success:** Each cell's evidence record holds the duration of every logged phase: the shared boot phases (`pull`, `bring-up`, `wait-healthy`, `install`, `wait-http`, `warmup-bo`, `snapshot-db` when the boot drives more than one browser, `teardown`) once per boot, and the cell's own `browser:<engine>`, plus wall-clock for both. The aggregate report surfaces them as `e2e_phase_durations`, counting each boot once, so the operator can see whether boot or browser driving dominates. Format follows `cell-contract.md`.
- **CAP-7**
  - **intent:** When a version needs both browsers, they drive concurrently against one booted container in lockstep (scenario k+1 starts on any engine only after every engine has finished scenario k, in the same deterministic order on all engines), except that a scenario with a BO step runs while the other engine runs nothing.
  - **success:** A release-gate version with both browsers stale boots once, and its two `browser:<engine>` phases overlap in time (by the cells' `started_at`/`finished_at`, both start before either ends). A cross-engine lock is exclusive for scenarios with a BO step: while one engine runs a BO scenario, no scenario of any kind runs on another engine; FO-only scenarios run in parallel only with other FO-only scenarios, so a BO scenario cannot mask another engine's failure. The engines run in lockstep (scenario k+1 starts on any engine only after every engine has finished scenario k, same order on all engines), so one engine's scenario cannot change shop state that another engine's earlier scenario depends on; the browser phase therefore lasts roughly the sum over scenarios of the slower engine (both engines in turn for a BO scenario). An engine with a failure in parallel mode reruns its full scenario set sequentially after a full reset to the snapshot taken after `warmup-bo` (DB, module files, `var/cache`, opcache), and the cell's findings are that rerun's failures: a parallel failure that does not reproduce there does not block, and every failure of the rerun blocks (the cell fails; never inconclusive, never an infra cause), so findings are identical to those of one cold single-engine run per engine on the same module (baseline, comparison key and fixture in `cell-contract.md` > Parallel browsers > Identical findings). When slots are too few for parallel browsers, the sequential fallback resets to the same snapshot before each later engine, so each engine that runs starts from the same state whatever the free slots (fail-fast may still leave later engines `not-run`, CAP-3). Mechanism, lock, and fallbacks follow `cell-contract.md`.

## Constraints

- Honesty law stays intact. A (version, browser) cell that was not tested, was narrowed, ran only partially, or was stopped is never reported as a pass, and it drops `ready`.
- Release-gate evidence comes only from cold boots with the full scenario set. Warm-container (CAP-5) and failed-only (CAP-4) evidence serve convergence only.
- Every configured cell (`psm_target_versions` × `psm_e2e_browsers`, default all target versions × both browsers; in headless runs, the caller's versions × browsers) remains mandatory for `ready`. Run-time narrowing never shrinks that set. It only filters the cells the plan says to run next, and when it filters out all of them, nothing runs and the plan reports `blocked-by-scope` with the required cells (`cell-contract.md`). Tiering reorders and gates the work but drops nothing.
- Every container, including the warm canary, is owned by a Job ID. Stop it only with `--stop-job`, and remove dead leftovers only with `--cleanup-orphans`, which ps-run-layer also runs automatically inside its slot wait (`wait-slots`), before the first slot count, in every mode, headless included (only containers whose owner is provably dead; implementing this changes `references/headless.md`). Killing by name, prefix, or `prune` stays forbidden.
- E2E concurrency (containers, including a warm one, plus CAP-7 browsers) respects one configurable host-wide cap, `psm_e2e_slots` (default 6), counted over every running E2E container on the Docker daemon, cold and warm, from every client of the daemon (container label `psm.slots`). A cell queued behind its own run's cells waits its turn; one blocked only by other runs waits up to the startup timeout, then is reported inconclusive (`no-slots`) (`cell-contract.md` > Config keys). The cap exists because the host is a shared WSL Docker daemon where saturation shows up as stalls at `wait-healthy`.
- Layer 4 visual review looks only at cold full-scenario runs, reports blocking defects through `<module>-adversarial.json` as today, and never triggers an E2E loop-back (`tier-matrix.md`).
- A source patch still stales every version (E2E through `source_fingerprint`; Layers 1, 2, 5 through today's `newest_source_mtime`, `cell-contract.md` > Fresh). Tiering must not use per-version file relevance to skip versions.
- Headless callers (psm-develop, psm-cross-version, psm-scaffold, psm-optimize) keep their per-version verdict contract: the versions and browsers they pass become the configured set for that run (`cell-contract.md` > Headless). Tiering is internal to psm-validate and applies to headless runs too, with two differences: a headless run never uses a warm container (always cold), and it stops at the first tier step that is not clean.

## Non-goals

- Reducing the target version or browser set, or making Firefox optional for `ready`.
- Speeding up Layers 1, 2, 3, or 5 (static, flashlight, adversarial, scenario).
- Distributed or CI runners and remote Docker hosts.
- Writing new E2E scenarios for any module.
- Skipping versions based on which files a patch touched.

## Success signal

On bankwire (fixture in `cell-contract.md`) with the fault injected: a cold canary run (fail), one warm iteration (fail; it starts the keeper and is not measured), the one-line revert patch, then the measured fix-loop iteration, a warm canary run with no `pull`, `bring-up` or `wait-healthy` phase and no non-canary cell. On a clean module the canary version boots twice (the cold canary run, then its gate boot for the non-canary browsers) and every other version boots once in the release gate (tier 1), with its stale browsers in parallel. CAP-6 timings in the cell histories show both, and a test asserts that `ready` is false whenever any version × browser cell lacks fresh, full, cold-boot evidence. Success is these structural criteria plus a mandatory before/after timing report on bankwire (same host, images already pulled). It measures E2E runs only (Layers 1, 2, 5 are not sped up, Non-goals), all on the module with the injected fault reverted: one fix-loop iteration, the one right after the one-line revert patch (before: `ps-run-layer.py --layer e2e --versions 9.1 --per-version` with the configured browsers; after: the warm canary run), and the full release gate over all six cells (before: `--versions 1.7.8,8.1,9.1 --per-version --jobs 3`; after: the cold canary run plus the tier-1 run). "Before" runs first, on the scripts of the commit preceding the first script change; each progress log is copied right after its run (logs are truncated per run), and its phase seconds come from `START`/`END` timestamps. "After" phase seconds come from the `boot_phases`, `keeper_boot` and `phase_durations` of the records those runs appended, not from the aggregate's `e2e_phase_durations`. A measurement's wall-clock is the elapsed time of its invocations, timed around the commands the same way before and after. The report, `<psm_reports_dir>/bankwire-e2e-timing.md`, states each measurement's module state and lists wall-clock plus per-phase seconds per boot and per cell. The numeric wall-clock target is set later from it.

## Assumptions

- The canary defaults to the newest target (9.1) × Chromium and is configurable. Budi named "9 + Chrome".
- Fail-fast (CAP-3) stops only unstarted cells. In-flight cells finish, to avoid orphaned state.
- Release-gate evidence is never taken from a warm container, because warm state can mask install-path bugs.

## Open Questions

None.
