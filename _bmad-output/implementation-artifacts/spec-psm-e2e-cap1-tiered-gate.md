---
title: 'psm-validate E2E: tiered gate — canary fix loop, release gate, loop-back (CAP-1)'
type: 'feature'
created: '2026-11-26'
status: 'done'
baseline_commit: 'c460e10'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-psm-e2e-tiered-gate/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-psm-e2e-tiered-gate/tier-matrix.md'
  - '{project-root}/_bmad-output/specs/spec-psm-e2e-tiered-gate/cell-contract.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-psm-e2e-cap3-failfast-slots.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-psm-e2e-cap2-cap6-cell-evidence.interim-orchestration.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Every E2E pass re-proves all configured cells, so a blocking bug costs one cold boot per version before Budi learns of it, and Fase 1/2 order is judged by prose in the interim orchestration instead of by a script.

**Approach:** Third slice of `SPEC-psm-e2e-tiered-gate` (CAP-1). `ps-plan-layers.py` derives the tier step from the cell histories (tier 0 canary fix loop, tier 1 release gate, loop-back steps) and emits exactly the cells to run next; runner, aggregate and orchestration docs follow it. `cell-contract.md` and `tier-matrix.md` are authoritative for every rule named here; this spec fixes only the slice boundary and the readings in Design Notes.

## Boundaries & Constraints

**Always:**
- Canary `psm_e2e_canary` (contract Config keys): one normalizer in `ps-flashlight-run.py`, `""` in `PSM_DEFAULTS`, validated by plan, aggregate and ps-run-layer (Design Notes > Canary).
- Plan: contract Plan in full — `--browsers` run scope, steps 1–7 first match wins, focus cell, diverge, `blocked-by-scope`, every tier field plus `e2e_focus_recorded_failure`, `phase1_reuse`, per-version `clean` (Design Notes > Plan).
- Runner: `ps-run-layer.py --tier 0|1` required for every non-`--merge-only` `--layer e2e` run and stamped on every record.
- Aggregate: `--session` sets `versions[ver].reached` (Design Notes > Aggregate).
- Docs replace the interim orchestration as a whole (contract > Docs to update, Design Notes > Docs), including the four interim rules Budi kept. The orchestrator runs exactly `e2e_cells_arg` with `--tier <e2e_tier>` and never picks a tier by judgment.
- Honesty law: tiering reorders and gates; it never drops a configured cell from `ready`.

**Ask First:** changing a contract rule rather than deferring it; letting the orchestrator act on `e2e_warm` or `failed-only` before CAP-5/CAP-4 exist.

**Never (later slices — keep absent):** producing `stopped` records (deferred-work; CAP-1 readers handle them per contract — gradeability skips them, aggregate `reached` counts them — and tests use hand-written ones); CAP-4 `--scenarios-from-failed`/`requires`; CAP-5 keeper, `--warm`, warm `--list-jobs` fields; CAP-7 parallel admission, `snapshot-db`, workers; the bankwire timing report (deferred-work, "before" baseline `c460e10`). Interim until then: the plan emits `e2e_warm`/`e2e_scenarios` per contract, and the orchestrator always runs cells cold and full (one boot per version, browsers sequential as CAP-3 admits them).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Fresh module | config 3×2, no history | `focus`, tier 0, next `[9.1:chromium]`, `e2e_scenarios` full, `e2e_warm` false | — |
| Canary blocking bug | canary cold fail, no other record | `focus` on canary only, `e2e_warm` true, `e2e_scenarios` failed-only | — |
| Clean canary | canary passing gate-grade | `gate`, tier 1, `e2e_cells_arg` `1.7.8:chromium+firefox,8.1:chromium+firefox,9.1:firefox` | — |
| Loop-back | tier-1 fail 8.1:firefox; patch; warm pass 8.1:firefox; both 8.1 cells cold pass; canary cold pass | `focus` → `cold-version` [8.1 ×2] → `cold-canary` [9.1:chromium] → `gate` [1.7.8 ×2, 9.1:firefox] | — |
| Interim loop-back | as above, fix-loop run cold full pass | `cold-canary` directly, then `gate` incl. 8.1:chromium | — |
| Two failing | one tier-1 run fails 1.7.8:chromium and 8.1:firefox; fix-loop runs cold full pass | `focus` 1.7.8:chromium → `focus` 8.1:firefox → `cold-canary` → `gate`; a warm pass on 1.7.8:chromium instead gives `cold-version` [1.7.8 ×2] | — |
| Promote order | focus cell, one fp: cold fail then warm pass / warm pass then cold fail | non-canary `cold-version`, canary `cold-canary` / `focus` with `e2e_warm` false, `full` | — |
| Diverge | one fp: cold fail, warm pass, cold fail / cold fail, warm pass, warm fail | cold full `focus` / `focus`, `e2e_warm` true | — |
| Smoke-only | every record `authored_assertions` 0 | `gate` with five cells after canary, then `blocked-not-gradeable`, tier null, `ready` false | — |
| Clean module | canary then five gate cells cold full pass | `done`, tier null, next `[]`, `e2e_cells_arg` null; aggregate `ready` true | — |
| Infra twice | one session, one fp: `no-slots`,`no-slots` / `no-slots`,`crash` / `no-slots`,`stopped`,`crash` / `no-slots`,clean pass,`crash` | `blocked-infra` ×3 / not blocked | — |
| Scope | `--versions 9.1 --browsers chromium`, step `gate` | `blocked-by-scope`, tier 1, required = five cells, causes `out-of-scope` | — |
| Hosted in 8.1 | loop-back at `cold-canary`, default scope / `--versions 8.1` | next `[9.1:chromium]` / `blocked-by-scope`, tier 0 | — |
| Bad input | canary `9.1:webkit` not configured; `--browsers safari` or `""`; e2e run without `--tier`; `--tier 2`; `--tier` with another layer or `--merge-only` | — | exit 2 |

</frozen-after-approval>

## Code Map

- `.claude/skills/psm-validate/scripts/ps-plan-layers.py` -- `main`, `plan_e2e_cells` (name/shape kept), `per_version_rollup`, predicates `is_failing`/`is_not_gradeable`/`has_passing_evidence`/`newest_gate_grade`/`record_state`; new pure `derive_e2e_step(histories, cells, canary, scope_versions, scope_browsers, fingerprint, tag_map, session)` (`histories` = `{cell: [records]}` already read; returns every tier field; no I/O), which `main` and AC 1 call
- `.claude/skills/psm-validate/scripts/ps-flashlight-run.py` -- `configured_cells` (signature kept; drop its "canary diabaikan" note), `normalize_engines`, `version_key`, `CONFIG_KEY_TO_DEST` (unchanged; `psm_e2e_browsers` → `browsers` already maps)
- `.claude/skills/psm-validate/scripts/ps-run-layer.py` -- `main` args, `_e2e_input`, `read_e2e_config`, `RESERVED_PASSTHROUGH`, `build_record` (`tier=None`)
- `.claude/skills/psm-validate/scripts/ps-aggregate.py` -- `read_aggregate_config`, `main` (`--session`), `versions` assembly; `static_layer`/`flashlight_layer`/`scenario_layer`/`validate_layer_shape` (reused by plan)
- `.claude/skills/psm-setup/scripts/resolve-psm-config.py` -- `PSM_DEFAULTS`
- `.claude/skills/psm-validate/scripts/tests/test-ps-{plan-layers,run-layer,aggregate,flashlight-run}.py`, `.claude/skills/psm-setup/scripts/tests/test-resolve-psm-config.py`
- `.claude/skills/psm-validate/{SKILL.md,references/{run-phases,headless,adversarial-lens,e2e-quickstart}.md}`, `.claude/skills/psm-{develop,cross-version,scaffold,optimize}/SKILL.md`, `docs/psm/README.md`, the interim-orchestration companion (superseded note)

## Tasks & Acceptance

**Execution:**
- [x] `ps-flashlight-run.py` + `resolve-psm-config.py` -- canary normalizer, `psm_e2e_canary: ""` -- one owner of the canary
- [x] `ps-plan-layers.py` -- pure step derivation, `--browsers`, tier fields, `phase1_reuse`/`clean`, docstring -- CAP-1 core
- [x] `ps-run-layer.py` -- `--tier`, canary validation, docstring -- runner side
- [x] `ps-aggregate.py` -- canary validation, `reached` -- headless `not reached`
- [x] tests -- every I/O row; the ACs; existing e2e runs gain `--tier`; `per_version[V].clean` true and false; a scenario-notes not-gradeable cell → `blocked-not-gradeable`; `reached` true from only a session `not-run`/`no-slots`/`stopped` record and true with no session record when every cell of V passes from an earlier session, false without one while a cell lacks passing evidence (contract Aggregate); per derived step `e2e_next_cells` equals the contract's step set (`done`: `[]`, `e2e_cells_arg` null); a canary-version loop-back (9.1:firefox fails → `cold-version` [9.1 ×2] satisfies the canary, then `gate`); a non-default canary (`8.1:firefox`); a config without chromium (default canary = newest target × first browser); the Clean-module aggregate runs with `--require e2e` plus a minimal conclusive, passing Layer 1 static fixture (`--static` and the `conclusive` floor hold whatever `--require`), so `ready` true does not depend on Layer 2/5 fixtures; `tier` is a JSON integer on every record kind ps-run-layer writes (child, `crash`, `no-slots`, `not-run`); `--browsers chromium,firefox` given explicitly beats a config `psm_e2e_browsers` of `chromium`; a canary shape table (`" 9.1 : Chromium "` ok, `9.1`, `9.1:chromium:x`, `:chromium`, `9.1:`, `7.0:chromium`, `9.1:webkit`, non-string → exit 2); `--ti 30` after `--` still reaches the child as `--timeout`
- [x] docs -- Design Notes > Docs

**Acceptance Criteria:**
- Given generated histories over config 3×2 (every combination per cell of: none, a cold full `pass`, a cold full `fail`, or an inconclusive `crash` record, all on the current fingerprint, each with its own `job_id`, `started_at` rising in configured order, current session and tag; plus per combination three variants of the focus cell F: F's records on another fingerprint, a warm full `pass` appended to F, a warm full `fail` appended to F; `crash` records carry `boot`/`scenario_set` null as the runner writes them), when the pure step derivation derives each in-process (`pass` records passing gate-grade), then `e2e_next_cells` holds a non-canary cell only when `e2e_step` is `gate`, or `focus`/`cold-version` with the cell being or sharing the version of `e2e_focus_cell`.
- Given config 3×2 with no history, when the plan runs `--per-version` with and without `--versions 9.1 --browsers chromium`, then both e2e `rerun_matrix`s list the same six cells.
- Given a headless call for 9.1 only whose canary is `8.1:chromium`, when `headless.md`'s config-copy rule applies, then the copy's `psm_e2e_canary` is empty and an assumption is logged (docs criterion).

## Design Notes

**Canary.** A present, non-`null` value that is not a string = exit 2 naming the key. Value trimmed; absent, `null` or empty = newest target × chromium (first configured browser when chromium is not configured). Otherwise it must split at exactly one `:` into a trimmed version equal to a configured string and a trimmed browser lower-cased as `normalize_engines` does, inside the configured set; anything else = exit 2 naming the key, whatever `psm_e2e_enabled`. ps-run-layer checks it in `read_e2e_config` (non-`--merge-only` `--layer e2e` runs only).

**Plan.**
- `--browsers` is normalized like `psm_e2e_browsers`; argparse default `None` (so an explicit `chromium,firefox` beats `apply_config_file`), then `--config`, else `chromium,firefox`; empty or outside the configured browsers = exit 2. `--versions` gets the same argparse default `None` (else `1.7.8,8.1,9.1`), so an explicit value equal to the script default stays the run scope.
- Fields in both modes: `e2e_cells_arg` is `null` when `e2e_next_cells` is empty; `e2e_focus_cell` is always one `"<ver>:<browser>"` string (the canary when nothing fails); additive field `e2e_focus_recorded_failure` (bool: `e2e_focus_cell` has a recorded failure, contract Plan; Budi, round 4); `e2e_warm` false and `e2e_scenarios` `full` on every step but `focus` (`blocked-by-scope` included, even in place of a derived `focus`); for `failed-only` the plan only tests the focus cell's failed set (contract Failed-only rerun) for emptiness, counting only non-empty string `scenario` values (`null`/non-strings ignored, so a set of only those is empty → `full`). `e2e_blocked_causes` is `{}` outside `blocked-*`; values `not-gradeable`, the newest non-`stopped` record's infra cause, `out-of-scope`.
- Top-level `phase1_reuse`: per-version mode = AND over `--versions`; canonical mode = no layer other than `e2e`/`adversarial` in `rerun`. `per_version[V].phase1_reuse`/`clean` only in `--per-version` mode. Every plan call whose E2E fields or `rerun_matrix` are read is a run-scope `--per-version` call (`rerun_matrix` exists only there).
- `clean`: false without loading files when `phase1_reuse` is false for V; otherwise V's per-version Layer 1, 2, 5 files are loaded through ps-aggregate (lazy import; it brings its own `ps_plan_layers` instance), and a file that does not load, fails `validate_layer_shape` (static with keys `id`, `severity`, `message`; flashlight with none) or is a scenario payload failing `validate_layer_shape(payload, ())` or whose `versions[V].scenarios` (or a scenario's `steps`), when present, is not a list of objects = exit 2 naming it. Blocking = a finding with severity `error` from the layer functions; an inconclusive layer without one is clean.
- Derivation: "fresh conclusive" includes warm and partial records, so step 5 precedes step 7's diverge as numbered. Focus-cell tie on highest `started_at` across runs breaks as inside a run; a null `job_id` is a run of its own.
- Diverge (Budi, round 1): a cold full `fail` on the current fingerprint later in the cell's history than a warm or partial `pass` on it (`source_fingerprint` only).
- Interim consequence (interactive until CAP-4/5; permanent in headless): a cold full fix-loop pass clears `failing`, so `cold-version` is skipped and V's other browsers are re-proved in tier 1 — reordered, never dropped. Tests reach step 5 with hand-written warm/partial records.

**Runner.** `--tier`: missing or not `0`/`1` = exit 2; with `--merge-only` or another layer = exit 2; joins `RESERVED_PASSTHROUGH` but `reserved_in_passthrough` matches it only as `--tier` or a prefix of at least `--tie`, so `--ti` (the child's `--timeout` abbreviation) still passes; stamped as JSON integer `tier`.

**Aggregate.** `reached` is emitted for every configured version only when `--session` is given; any record of that session counts (`not-run`, `no-slots`, `stopped` included), so an E2E loop that ended before any run leaves every version lacking passing evidence `reached: false`. Docs pass `--session` to the aggregate in headless only. A version stopped at `blocked-not-gradeable` with no session record reports `reached: false` per contract; the headless return's `stopped at blocked-not-gradeable` explains it. A malformed `--session` = exit 2, as in plan (`valid_session`).

**Docs** (contract > Docs to update; CAP-4/5/7 items — `requires`, keepers, warm stop, `ALIVE idle`, `snapshot-db`/`lock-wait`/`barrier-wait`, `parallel_only` — stay absent):
- Orchestration per contract Plan and tier-matrix: hosting version (from one run-scope `--per-version` plan call at session start and at each loop-back; out-of-scope → first in-scope version, numeric order; its loop runs first), Phase 1 loop gated by `clean` and `e2e_step`, Phase 2 entry check, Phase 2 loop and wrap-up, stop convergence (offered when V is not clean or `e2e_focus_recorded_failure` of the newest run-scope plan call is true; only E2E runs change it, so it holds in a non-hosting V loop), E2E loop ended, Layer 3 reuse (canonical plan call shows `layers.adversarial.reuse`; unmerged lens results discarded on every loop-back), `visual-pending.json` (an interim cold full `focus` run counts as cold full-scenario). A scope leaving out the step's cells shows only as `blocked-by-scope` with `e2e_required_cells`.
- Interim rules Budi kept (round 1, round 3): a run that exited 2 with an output line (child exit 2) ends the E2E loop; a pre-spawn or append-error exit 2 (no output line) does not — interactive: fix and rerun; headless: return `blocked` with the stderr at once, no wrap-up. Interactive exit 143 ends the E2E loop unless Budi reruns. An infra cause (short of `blocked-infra`) is carried per version V: a run left one for V when the next plan's e2e `rerun_matrix` reason is `inconclusive`, `inconclusive-steps` or `browser-notes` for a cell of V in the run's output-line `appended` (runs without an output line leave none; `not-run` and `fail` never are one; the cause is named from stderr and progress log). Before the first later run whose `e2e_next_cells` include a cell of V, interactive asks Budi to fix the environment or decline; a decline ends the E2E loop. The carried cause for V is cleared when Budi answers "fixed" or a later plan shows no such reason for a cell of V. Any rerun is a fresh run-scope plan call and its `e2e_cells_arg`. Exit 0, 1 or 3 with an output line is read through the next plan call as above (a stopped child included: its cells get no record while `stopped` is deferred and keep their earlier records). Any other ps-run-layer exit (130, or 1 without an output line, e.g. a traceback): interactive shows stderr and asks Budi to rerun or end the E2E loop; headless returns `blocked` with the stderr, no wrap-up.
- No Docker (Budi, round 5): a Layer 2/5 run that reported `skipped` counts that layer as done; the orchestrator itself judges V clean from V's Layer 1 file (no finding with severity `error`), as in the interim orchestration. The plan's `clean` stays false there (`phase1_reuse` false); the docs override it.
- Headless (contract Headless): config copy resets the canary only when it is well-formed (trimmed, exactly one `:`, two non-empty parts) and, normalized as Design Notes > Canary, outside the caller's set, logging an assumption that names the dropped value (the model applies this rule by hand; no script mode in CAP-1); any other value is kept so the plan's exit 2 returns `blocked`. Stop at the first unclean step: after each E2E run one plan call with the same flags; the step is clean iff none of its `e2e_next_cells` has an e2e `rerun_matrix` entry other than reason `not-gradeable`. A child exit 2 or exit 143 is a step not clean (`complete`); until `stopped` records exist, a stopped job's cells keep their earlier records. `e2e_tier_reached` and `stopped at <step>` come from the last run-scope plan call, or, when headless stops after a run found not clean, from the call that chose that run (contract "last plan call" read per tier-matrix Rules as the step stopped at); return gains `versions` and `not_run_cells` from the aggregate with `--session`; `complete`/`blocked` rule. The four headless callers' SKILL.md per contract > Docs to update (psm-optimize Profil/Verifikasi included).
- Files: SKILL.md, `run-phases.md` ("Istilah E2E (interim, sampai CAP-1)" rewritten; every non-`--merge-only` e2e command carries `--tier`), `headless.md`, `adversarial-lens.md` (Layer 3 respawned after a loop-back), `e2e-quickstart.md` (TDD verdict gains `--tier 0`), README config table (`psm_e2e_canary`; a malformed value is exit 2 even with `psm_e2e_enabled` false), superseded note on the interim-orchestration companion.

## Verification

**Commands:**
- `for f in .claude/skills/psm-validate/scripts/tests/test-ps-*.py; do uv run "$f" >/dev/null || echo "FAILED $f"; done` -- expected: no FAILED line
- `uv run .claude/skills/psm-setup/scripts/tests/test-resolve-psm-config.py` -- expected: exit 0
- Manual: `headless.md` states AC 3's canary reset; every non-`--merge-only` `ps-run-layer.py --layer e2e` command in the docs carries `--tier`; no `--merge-only` command carries `--tier`; the interim rules of Design Notes > Docs are present; `git diff c460e10` of the docs adds none of the CAP-4/5/7 items.

## Suggested Review Order

**Tier derivation (plan core)**

- Entry point: pure step derivation, steps 1–7 first match wins, then run-scope filter.
  [`ps-plan-layers.py:709`](../../.claude/skills/psm-validate/scripts/ps-plan-layers.py#L709)

- Step ladder: done → blocked-not-gradeable → blocked-infra → gate → cold-version → cold-canary → focus.
  [`ps-plan-layers.py:756`](../../.claude/skills/psm-validate/scripts/ps-plan-layers.py#L756)

- Focus cell: failing cells of the newest run, tie by version then browser order.
  [`ps-plan-layers.py:672`](../../.claude/skills/psm-validate/scripts/ps-plan-layers.py#L672)

- Diverge (Budi r1): cold full fail newer than a warm/partial pass forces cold full focus.
  [`ps-plan-layers.py:636`](../../.claude/skills/psm-validate/scripts/ps-plan-layers.py#L636)

- Warm/scenarios only on focus; scope-blocked steps keep tier; fields emitted in one place.
  [`ps-plan-layers.py:786`](../../.claude/skills/psm-validate/scripts/ps-plan-layers.py#L786)

- Infra cause per record, feeding blocked-infra and the carried interim cause.
  [`ps-plan-layers.py:597`](../../.claude/skills/psm-validate/scripts/ps-plan-layers.py#L597)

**Phase 1 gates**

- `clean` via ps-aggregate layer functions; bad layer file = exit 2 naming it.
  [`ps-plan-layers.py:1060`](../../.claude/skills/psm-validate/scripts/ps-plan-layers.py#L1060)

- `phase1_reuse`/`clean` per version and top-level AND in main.
  [`ps-plan-layers.py:1296`](../../.claude/skills/psm-validate/scripts/ps-plan-layers.py#L1296)

**Canary (one owner)**

- Single normalizer: trim, one colon, configured version, lower-cased in-set browser.
  [`ps-flashlight-run.py:1660`](../../.claude/skills/psm-validate/scripts/ps-flashlight-run.py#L1660)

- Aggregate validates canary in every mode, whatever `psm_e2e_enabled`.
  [`ps-aggregate.py:877`](../../.claude/skills/psm-validate/scripts/ps-aggregate.py#L877)

**Runner `--tier`**

- Strict `0`/`1`; required except merge-only; rejected with other layers.
  [`ps-run-layer.py:746`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L746)

- Every record kind stamped through one builder.
  [`ps-run-layer.py:800`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L800)

- Passthrough reserves `--tier` only from `--tie`, so `--ti` stays the child's `--timeout`.
  [`ps-run-layer.py:148`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L148)

**Aggregate `reached`**

- Any session record, or every cell passing from any session, counts as reached.
  [`ps-aggregate.py:884`](../../.claude/skills/psm-validate/scripts/ps-aggregate.py#L884)

- `--session` without a history source is exit 2, not a false "not reached".
  [`ps-aggregate.py:947`](../../.claude/skills/psm-validate/scripts/ps-aggregate.py#L947)

**Orchestration docs**

- Interim E2E terms replaced by tier rules, exit-code handling, No-Docker override.
  [`run-phases.md:114`](../../.claude/skills/psm-validate/references/run-phases.md#L114)

- Hosting version and loop order from the session-start run-scope plan call.
  [`run-phases.md:215`](../../.claude/skills/psm-validate/references/run-phases.md#L215)

- Headless canary reset (AC 3) and stop at the first unclean step.
  [`headless.md:22`](../../.claude/skills/psm-validate/references/headless.md#L22)
  [`headless.md:41`](../../.claude/skills/psm-validate/references/headless.md#L41)

**Tests and config**

- Tier derivation tests: I/O rows, AC 1 invariant, AC 2, corrupt-tail literal reading.
  [`test-ps-plan-layers.py:579`](../../.claude/skills/psm-validate/scripts/tests/test-ps-plan-layers.py#L579)

- Runner tier bad input, stamping, passthrough.
  [`test-ps-run-layer.py:2245`](../../.claude/skills/psm-validate/scripts/tests/test-ps-run-layer.py#L2245)

- Aggregate `reached` cases.
  [`test-ps-aggregate.py:1499`](../../.claude/skills/psm-validate/scripts/tests/test-ps-aggregate.py#L1499)

- `psm_e2e_canary` default `""`.
  [`resolve-psm-config.py:59`](../../.claude/skills/psm-setup/scripts/resolve-psm-config.py#L59)
