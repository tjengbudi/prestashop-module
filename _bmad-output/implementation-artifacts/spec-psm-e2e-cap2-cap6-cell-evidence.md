---
title: 'psm-validate E2E: per-cell evidence histories (CAP-2) and phase timings (CAP-6)'
type: 'feature'
created: '2026-11-26'
status: 'done'
baseline_commit: '8beb808ca82c7a76497b5ef592046893767f090a'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-psm-e2e-tiered-gate/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-psm-e2e-tiered-gate/cell-contract.md'
  - '{project-root}/_bmad-output/specs/spec-psm-e2e-tiered-gate/brownfield.md'
  - '{project-root}/_bmad-output/specs/spec-psm-e2e-tiered-gate/tier-matrix.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-psm-e2e-cap2-cap6-cell-evidence.interim-orchestration.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Layer 4 freshness is judged per version by image tag only, so a Chromium-only run reads as complete and Firefox is never re-required; `ready` can be true without every configured (version, browser) proven. Phase durations exist only in the truncated progress log, so nobody can see whether boot or browser driving dominates.

**Approach:** First slice of `SPEC-psm-e2e-tiered-gate`: implement the contract's evidence layer — configured cells, append-only per-cell histories, source fingerprint, per-cell state/freshness/gate-grade in plan and aggregate (CAP-2) — plus in-process phase timers carried in every record and surfaced as `e2e_phase_durations` (CAP-6). `cell-contract.md` is authoritative for every rule named here; this spec only fixes the slice boundary.

## Boundaries & Constraints

**Always:**
- Implement these `cell-contract.md` sections as written: Configured cells (shared normalizer in `ps-flashlight-run.py`, exit 2 cases, numeric version order; `psm_e2e_canary` is ignored this slice); Evidence record (Storage, Entry points, Newest, Fields, Producers, incomplete-record rule); State, freshness, gate-grade (incl. `source_fingerprint` and the `newest_source_mtime` bookkeeping skip); Plan's per-cell `rerun_matrix` reasons and browser-keyed `layers.e2e`, plus the Plan > Derivation predicates `failing` and `not-gradeable` (steps, focus, tiers, next cells are not in scope); Phase timings (CAP-6) for the phases this runner emits; Aggregate (`--config`, `--tag-map`/`--extra-tag-map` with `psm_flashlight_tag_map` from `--config` per Config keys > Image tag, removed `unscanned` gate, record selection, `e2e_cells`, `not_run_cells`, per-version `e2e_state`/`reason`, `e2e_phase_durations`, `--e2e` = exit 2, legacy `<module>-e2e*.json` ignored).
- `ps-plan-layers.py --new-session`; `ps-run-layer.py --layer e2e` requires `--session` (exit 2 when missing/malformed) and stamps it on every record; `ps-plan-layers.py` requires `--session` except with `--new-session` (exit 2 when missing/malformed; otherwise unused this slice); aggregate accepts `--session` optionally (validated, unused this slice); `--merge-only --layer e2e` takes no `--session`.
- `ps-run-layer.py --config` for every layer, forwarded to each child; `--config`, `--browsers`, `--engines` join `RESERVED_PASSTHROUGH`. Layer `e2e`: exactly one of `--cells`/`--versions`; input errors and interim runner rules per Design Notes; writes no `<module>-e2e*.json` except `--merge-only` report view; prints the Runner > Output JSON line; exit 3/1/0/2/143 per Runner.
- `ps-e2e-run.py`: per version `boot_phases`, `boot_wall_clock` (Design Notes), `boot_log` (as today), `boot`=`cold`, `boot_id`, `run_id`, `image_tag` (today `tag`), `scenario_notes` (today run level), `browser_mode`=`sequential`, `errors`, `install`; per engine `cells.<engine>` with the remaining per-cell fields (`scenario_set`=`full`, `scenarios_run`, …; Producers); `--engines`; exit codes per Runner: 0 when E2E is skipped, or when at least one cell is emitted and every emitted cell's State-rule state is `pass`; 3 any `fail`; else 1 (so a version with no driven cell is 1). Direct-run legacy fields stay (never evidence).
- Headless config copy (`cell-contract.md` > Headless, first bullet; no canary handling, no canary this slice): after minting `<t>` and before the first plan call, the orchestrator (headless.md; no script) copies the resolved `<psm_reports_dir>/psm-config.json` verbatim to `<psm_reports_dir>/<module>-psm-config.headless.<t>.json`, overwriting only `psm_target_versions` and `psm_e2e_browsers` with the caller's versions and browsers as comma-separated strings (resolver defaults when it passes none), and forwards that file as `--config` to plan, `ps-run-layer.py` and aggregate.
- Honesty law: narrowed, partial, missing, corrupt or stale cells never count; when `--require` includes `e2e`, `ready` is false unless every configured cell has passing gate-grade evidence.

**Ask First:** changing any contract rule (rather than deferring it); removing `--jobs` for E2E before slots exist.

**Never (deferred to later slices — keep hooks null/absent, do not half-build):** tiers, `e2e_step`/focus/canary/`phase1_reuse`/`per_version[V].clean`/`blocked-*`/the plan's run scope (`e2e_next_cells` filter), plan `--browsers` and stop convergence (CAP-1; interim scope and decline rules live in the orchestrator, Design Notes); fail-fast, `not-run` production, slots/`--slots`/`wait-slots`/`psm.slots` (CAP-3, `--jobs` stays); `--scenarios`/`requires`/partial production (CAP-4); warm keeper (CAP-5); parallel browsers, locks, `scenario_spans`, `parallel_only`, `snapshot-db` (CAP-7); `--tier` (record `tier: null`); `stopped` records; the other Headless bullets (stop at the first unclean step, `reached`/`not reached`, new return fields); new `PSM_DEFAULTS` keys. Readers must still classify `warm`/`partial`/`not-run` records correctly.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Chromium-only | config 3×2; histories only chromium passes on current fp | plan: firefox `missing` for all 3 versions; aggregate `ready=false` | N/A |
| Narrowed plan | config 3×2, no evidence, `--versions 9.1 --per-version` | e2e `rerun_matrix` lists all six cells; `per_version[9.1].layers.e2e` and `per_version[9.1].rerun` reflect only 9.1's cells | N/A |
| Newer fail | pass then fail, same fp | cell lacks passing evidence, reason `fail`, `ready=false` | N/A |
| Corrupt line | valid, corrupt, valid | two valid records read; corrupt-last → `corrupt-history` | N/A |
| Fingerprint | delete non-newest file / touch `vendor/x` / edit `.psm-develop-plan.json` / append history inside module | stale / stale / fresh / fresh | stat error → exit 2 |
| Bad config | `webkitx`, `9.1`+`9.1.0`, empty list, non-dotted | — | exit 2 |
| Crash child | child exits 1, no output | `inconclusive` `crash` record per admitted cell | exit 1 |
| Install / boot failure | install fails, or bring-up/wait-healthy fails (`install` null), before any engine | one `inconclusive` record per engine, reason `install` resp. `errors` (never `crash`) | exit 1 |
| Child exit 2 | `--cells` over 3 versions, `--jobs 1`, first child exits 2 | no further child starts; nothing appended for that version or unstarted ones | exit 2 |
| Stopped | `--stop-job` while a child runs | records only for children that already exited; no `crash` for the rest | exit 143 |
| Session | plan call without `--new-session`, or `--layer e2e` run, with `--session` missing or not `[a-z0-9]{16}` | — | exit 2 |
| Headless narrowed | caller passes only 9.1, browsers default | headless copy holds `psm_target_versions` = `9.1` (doc-only, no script test); aggregate fed a config with `psm_target_versions` `9.1`: `ready`/`versions` cover only 9.1's cells | N/A |
| Probe drop | firefox binary missing | firefox record `browser-unavailable` | N/A |
| Timings | manual boot, image pulls for PS and DB | `boot_phases` has `pull`, `pull#2`, `wait-healthy`, `wait-healthy#2`; cells hold only `browser:<engine>` | absent phase omitted |

</frozen-after-approval>

## Code Map

- `.claude/skills/psm-validate/scripts/ps-flashlight-run.py` -- normalizer, `SUPPORTED_ENGINES`, `phase` timing sink, `CONFIG_KEY_TO_DEST`
- `.claude/skills/psm-validate/scripts/ps-plan-layers.py` -- fingerprint, history I/O, record state/freshness/gate-grade, per-cell plan, `--new-session`
- `.claude/skills/psm-validate/scripts/ps-e2e-run.py` -- `run_one_version` (sequential engines, teardown in `finally`), `run_steps` (step index), `assemble_findings`, `parse_browsers`, `main` exit code
- `.claude/skills/psm-validate/scripts/ps-run-layer.py` -- `main`, `plan_children`, `collect`, `merge_only`, `RESERVED_PASSTHROUGH`
- `.claude/skills/psm-validate/scripts/ps-aggregate.py` -- `e2e_layer`, `merge_version`, `main` (unscanned gate, `--e2e`)
- `.claude/skills/psm-validate/scripts/tests/test-ps-*.py` -- check()-style suites run with `uv run`
- `.claude/skills/psm-validate/{SKILL.md,references/run-phases.md,references/e2e-quickstart.md,references/headless.md,references/adversarial-lens.md}` -- E2E commands

## Tasks & Acceptance

**Execution:**
- [x] `ps-flashlight-run.py` -- add normalizer + configured-cells reader + `version_key`; move `SUPPORTED_ENGINES`; add `DEFAULT_TARGET_VERSIONS`/`DEFAULT_E2E_BROWSERS` as the normalizer's script defaults (existing argparse literals and `ps-e2e-run.py` `DEFAULT_BROWSERS` stay; the drift test in `test-ps-flashlight-run.py` also checks the two new constants against `PSM_DEFAULTS`); make `phase` record `{seconds, outcome}` into an active timing sink with `#n` suffixes -- single owner of cell identity and timings
- [x] `ps-plan-layers.py` -- add `source_fingerprint`, bookkeeping skip in `newest_source_mtime`, `history_path`/`read_history`/`append_record` (flock), `record_state`, freshness/gate-grade/passing predicates, `cell_reason`; replace e2e file planning with per-cell planning in both modes; `--new-session`, required `--session` (exit 2 when missing/malformed, except with `--new-session`), `source_fingerprint` output -- CAP-2 core
- [x] `ps-e2e-run.py` -- per-engine findings/inconclusive/assertions/notes/console/screenshots, `launch_error`, `bo_authed`, `scenarios_run`, findings `action`+`step`, cells on every return path, cell timestamps, boot timing wrapper measured after teardown, `--engines`, normalizer replaces `parse_browsers` fallback, exit 3 -- child shape per Producers
- [x] `ps-run-layer.py` -- e2e history mode (`--cells`/`--versions`, `--session`, `--config`, fingerprint before spawn, tag resolution, record merge + crash/browser-unavailable records, output line, exit codes, stderr line naming the stamped screenshot dir), report-view `--merge-only`, reserved flags -- sole history writer
- [x] `ps-aggregate.py` -- configured versions, history-based E2E layer, new fields, removed gates -- per-cell `ready`
- [x] tests -- rewrite e2e-file tests against histories; add the I/O matrix rows plus the contract tests of Storage (corrupt line), Fresh (four cases) and Gate-grade (assert reason `fail` and `ready=false`, no step); the Configured-cells test seeds 9.1:chromium with passing gate-grade evidence, runs `--versions 9.1 --per-version` (no plan `--browsers`) and expects exactly the other five cells in `rerun_matrix`; every plan test passes `--session`; non-E2E aggregate tests get a `--config` whose `psm_target_versions` matches their static payload, and the unscanned / zero-version exit-2 tests become "configured version missing from static → not conclusive, `ready=false`, exit ≠ 2" (empty configured list stays exit 2); hand-written `warm`/`partial`/`not-run` records give plan reasons `warm-only`/`partial`/`not-run`, are never gate-grade, hide no older gate-grade record, and a newest `not-run` appears in `not_run_cells`
- [x] docs -- per Design Notes > Interim orchestration: SKILL.md (mint the token once per run via `--new-session` and pass it to every plan call; resolver absent → write `{}` as `psm-config.json`; On Activation step 2 scope = the interim run scope, cells left out stay unproven and `ready` false; Lapis 4, Fase 1/2 paragraphs; Vonis fields; aggregate command gains `--config`; the general "exit 2 = input error, fix and repeat" sentence excepts a child-originated E2E exit 2, which ends the E2E loop), run-phases.md (e2e row of the layer table, Fase 1/2 commands and end conditions, ungated `--merge-only` for Layers 2/5 and the e2e view (no `--versions`), `--config` as ps-run-layer flag, `--session <t>` on every plan call, tag-map forwarding), e2e-quickstart.md TDD verdict step, adversarial-lens.md (Layer 3 spawned again when Fase 2 restarts and the canonical plan does not reuse it; unmerged lens results from another `source_fingerprint` are discarded; Lapis 4 visual defects are merged after the lenses; it holds no plan command), headless.md (token minted per call and passed to every plan call and E2E run; a pre-spawn E2E exit 2 returns `blocked`, a child-originated one ends the E2E loop; a job stopped under the silent-log rule still returns `blocked` at once, as today; the headless config copy forwarded as `--config` to plan, ps-run-layer and aggregate), `ps-run-layer.py` docstring (e2e writes histories, not canonical files; exit 3/143; the JSON output line; no `--browsers` after `--`); `docs/psm/README.md` unchanged (no ps-run-layer command there, no new keys this slice)

**Acceptance Criteria:**
- Given config 3×2, a conclusive static file for the three versions, and histories with passing gate-grade records for all six cells on the current fingerprint and tags, when aggregating with `--require static,e2e`, then `ready=true`, every `e2e_cells` entry has `gate_grade: true`, and each `e2e_phase_durations[ver].boots` has exactly one key per distinct `boot_id` of the selected records.
- Given the AC1 setup (config 3×2, conclusive static, `--require static,e2e`) with five cells passing, when the sixth cell's newest gate-grade record is not passing, or it has no gate-grade record, then `ready=false` and `e2e_cells` names that cell with reason `fail` when its newest gate-grade record is a `fail`, `missing` when it has no record.
- Given `ps-run-layer.py --layer e2e --versions 9.1 --session <t>`, when the child succeeds, then exactly one record per configured browser of 9.1 is appended and no `<module>-e2e*.json` is written.

## Design Notes

Slice decisions where the contract leaves a gap or depends on a deferred piece:

- **Plan shape**: `per_version[V].layers.e2e[<browser>]` = `{reuse, reason, path}` (`path` = the cell's history, `reason` null when `reuse`); canonical `layers.e2e` = `{<browser>: {<ver>: {reuse, reason, path}}}` over configured versions. `rerun_matrix` stays a `--per-version` output; its e2e entries add `browser` and `reason`. Per-version `rerun` lists `e2e` when any of its browser entries has `reuse: false`; canonical top-level `rerun` lists `e2e` when any cell entry of `layers.e2e` has `reuse: false`. `all_reuse` = every `per_version[V].rerun` (V in `--versions`) is empty, not `not rerun_matrix`; it is informational (per-version `rerun` always holds `adversarial`), so no interim loop gates on it. A plan `--versions` entry that is not exactly a configured string is exit 2 naming the configured set.
- **Reasons**: with no fresh record, judge the newest valid record: fingerprint matches but tag differs → `stale-tag`, else `stale-source`. `_e2e_scenario_notes(module_dir)` is only the current-notes comparator for `not-gradeable`/`scenario-notes`, in plan and aggregate alike; the emitted aggregate field `e2e_scenario_notes` comes from the selected records (contract Aggregate).
- **Record**: ps-run-layer computes `state`/`conclusive`/`reason` at merge (State rules; not driven = no `browser:<engine>` entry in the cell's `phase_durations`); readers trust the stored state and apply only the corrupt-line and incomplete-record rules. A record holds exactly the Fields keys plus `boot_wall_clock` and `boot_log` (Budi-approved addition to the contract whitelist: the container log tail the child emits today on a boot failure, `null` otherwise; the aggregate keeps appending `_log_tail(boot_log)` to the E2E reason as today); deferred hooks (`tier`, `keeper_boot`, `scenario_spans`, `parallel_only`) are `null`. The child's `image_tag` is stored as emitted. Version-level child fields (`run_id`, `boot`, `boot_id`, `boot_phases`, `boot_wall_clock`, `boot_log`, `image_tag`, `browser_mode`, `errors`, `install`, `scenario_notes`) go into every record of that version, `browser-unavailable` included; without usable child output they are `null`, except `run_id` = ps-run-layer's RUN_ID and `image_tag` = the resolved tag. An OS error reading or appending a history file is exit 2 naming the path (plan, aggregate; ps-run-layer after in-flight children finish). Timestamps are written as `datetime.now(timezone.utc).isoformat(timespec='microseconds')` (`+00:00`); readers also accept `Z` and no fractional seconds.
- **Child output in history mode**: the child emits `cells.<engine>` for every engine it kept after the probe, on every return path (boot or install failure included, with `started_at`/`finished_at` null, which ps-run-layer fills with admission and write time). The probe-drop note is keyed to the dropped engine, so it lands in no emitted cell. Output with `status: skipped` appends nothing for its cells; the following rules apply only to other output. An admitted engine missing from the child's `browsers_available` → `browser-unavailable`; any other admitted engine without a cell, or output that does not parse or fails the shape check → `crash`. Shape check: a JSON object whose `versions[<requested ver>]` is an object holding a `cells` object of objects; anything else (a stray version included) → `crash`, not exit 2; a missing per-cell field is stored `null` (incomplete-record rule). Cells outside the admitted set are not appended (stderr note).
- **Runner interim**: `fl.docker_available()` false before spawning → `skipped` output line, nothing appended, exit 0. A child reporting `status: skipped` → `skipped`, exit 0, unless an appended record is `fail` (`ran`, exit 3). ps-run-layer starts children itself and appends each child's records as soon as it is reaped, in completion order. A child exit 2 → no further child starts, in-flight children finish and their records append, nothing is appended for that version or unstarted cells, exit 2 (no `not-run`). Stop (`--stop-job`) → records already appended stay, nothing (no `crash`) for in-flight or unstarted cells, no output line, exit 143; a child reaped with returncode 143 or −15 counts as stopped, never `crash`. The output line is printed on every other exit except pre-spawn input errors; its `reason` is `null` for `ran`, for `skipped` the docker-check message, else the first skipped child's `reason`; a child exit 2 overrides `skipped` and `fail` (`ran`, exit 2). Exit 2 input errors: `--cells` or `--session` with another layer; and for layer `e2e`: neither or both of `--cells`/`--versions`; a `--cells` token not of the form `<ver>:<browser>[+<browser>]…`, an empty token, or a browser repeated inside one cell; a version repeated in `--cells`; a cell outside the configured set (so a `--versions` entry must equal a configured string); `--per-version`; `psm_reports_dir` equal to the module root; a passthrough `--screenshot-dir` inside the module but outside `psm_reports_dir`. The `RESERVED_PASSTHROUGH` check (any listed flag or a prefix abbreviation of it, ≥ 4 chars, loop over the whole tuple) applies to every layer, as today's code does. Not checked: `--tier`, `--warm`, `--scenarios-from-failed` (no such flags; argparse rejects them); `--jobs` stays and bounds concurrent versions. With a passthrough `--screenshot-dir`, ps-run-layer prints `screenshots: <stamped run dir>` on stderr before spawning (the output line keeps the contract shape). `--versions` is required except for layer `e2e`. ps-run-layer reads `--config` through its own key map, not `apply_config_file`: configured set, `psm_flashlight_tag_map`, `psm_flashlight_startup_timeout`. Configured-set validation and the reports-dir/screenshot-dir checks apply to layer `e2e` only (`--merge-only --layer e2e`: configured set only); other layers forward `--config` without validating it. `--merge-only --layer e2e` takes only `--module`, `--reports-dir`, `--config` (`--cells`, `--versions`, `--session`, `--per-version` or a passthrough → exit 2; `--jobs` ignored); a configured cell without a valid record shows `null`; the view overwrites a legacy `<module>-e2e.json`; exit 0 once written (all-`null` included), 2 on a failed write.
- **Normalizer input**: a comma-separated string (as the resolver writes) or a list of strings, items stripped, browser items lowercased before validation (versions as written); key absent or `null` → script default; a config file that is unreadable or not a JSON object → exit 2.
- **Aggregate**: the derived-file loop in `main` skips `e2e`; histories need `--reports-dir` + `--module`, and without them every cell reads `missing`. A `--versions` that differs = set inequality after normalization. A cell with no valid record: `e2e_cells` entry `{state: null, gate_grade: false, reason, findings: [], parallel_only: null}`, reason `corrupt-history` when the file's last line is corrupt, else `missing`. `corrupt-history` overrides the selected record's reason and the cell lacks passing evidence. `e2e_cells[…].reason` = the plan reason (with `stale-fail` per contract Aggregate), `null` for a cell with passing evidence. `versions[ver].reason`: `e2e_state` `fail` → the literal `fail` (`e2e_cells` keeps each cell's plan reason); `inconclusive` → the reason of the first cell lacking passing evidence, in `psm_e2e_browsers` order; `pass` → `null`.
- **Timing**: one sink per `run_one_version` call, inactive by default (Layer 2/5 phases unchanged). `phase.__exit__` records every phase whatever the outcome: `seconds` = monotonic float rounded to 3 decimals, `outcome` = the END status string. `browser:<engine>[#n]` goes to that engine's `phase_durations`, everything else to `boot_phases`; any phase repeated in one boot gets `#n` (`pull#2` for the DB image, `bring-up#2`/`teardown#2` after the port retry). `boot_wall_clock` (per version in the child, copied into each record) = seconds from `run_one_version` entry until `_teardown` returns (container lifetime, browsers included), measured by an outer wrapper so the inner function keeps its `finally`; record `wall_clock` = `finished_at` − `started_at`. Aggregate `boots[…].wall_clock` reads `boot_wall_clock`, `browsers[…].wall_clock` reads `wall_clock`; a record with `boot_id` null adds nothing to `boots`. No container started → `boot_phases` holds only phases that ran (`{}` if none); `boot_id` is still set.
- **Interim orchestration (until CAP-1)**: the orchestrator flow (session token, `<cfg>`, run scope, V clean, E2E loop ended, Fase 1/2, wrap-up, visual review, quickstart) lives in the companion `spec-psm-e2e-cap2-cap6-cell-evidence.interim-orchestration.md`, approved and frozen with this spec; the docs task writes it into the skill docs.

## Verification

**Commands:**
- `for f in .claude/skills/psm-validate/scripts/tests/test-ps-*.py; do uv run "$f" || echo "FAILED $f"; done` -- expected: no FAILED line
- `uv run .claude/skills/psm-setup/scripts/tests/test-resolve-psm-config.py` -- expected: exit 0

## Suggested Review Order

**Cell evidence: state, freshness, reasons (the core of CAP-2)**

- Entry point: per-cell reason in contract order, the single judgment that plan and aggregate share.
  [`ps-plan-layers.py:460`](../../.claude/skills/psm-validate/scripts/ps-plan-layers.py#L460)

- State rules plus incomplete-record downgrade; the runner writes them, readers trust them.
  [`ps-plan-layers.py:337`](../../.claude/skills/psm-validate/scripts/ps-plan-layers.py#L337)

- Gate-grade = fresh, conclusive, cold, full; the gate that drives `ready`.
  [`ps-plan-layers.py:390`](../../.claude/skills/psm-validate/scripts/ps-plan-layers.py#L390)

- Fingerprint: size+mtime_ns walk, bookkeeping and an in-module reports dir excluded.
  [`ps-plan-layers.py:149`](../../.claude/skills/psm-validate/scripts/ps-plan-layers.py#L149)

- Append-only history: LOCK_SH read, corrupt-line rules, one LOCK_EX write.
  [`ps-plan-layers.py:272`](../../.claude/skills/psm-validate/scripts/ps-plan-layers.py#L272)
  [`ps-plan-layers.py:305`](../../.claude/skills/psm-validate/scripts/ps-plan-layers.py#L305)

- Plan: every configured cell judged, whatever `--versions` says.
  [`ps-plan-layers.py:499`](../../.claude/skills/psm-validate/scripts/ps-plan-layers.py#L499)

**Configured cells (single owner)**

- Shared normalizer: exit-2 cases, numeric order, ASCII digits only.
  [`ps-flashlight-run.py:1349`](../../.claude/skills/psm-validate/scripts/ps-flashlight-run.py#L1349)

- The required set is read straight from `--config`, never narrowed by run flags.
  [`ps-flashlight-run.py:1403`](../../.claude/skills/psm-validate/scripts/ps-flashlight-run.py#L1403)

**Runner: the only history writer**

- E2E history mode: input gates, fingerprint before spawn, reap-and-append, exit codes.
  [`ps-run-layer.py:847`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L847)

- Child output to records: shape check, crash and browser-unavailable fallbacks.
  [`ps-run-layer.py:745`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L745)

- One record = contract Fields + `boot_wall_clock` + `boot_log`; state derived at write time.
  [`ps-run-layer.py:714`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L714)

- `--cells` grammar; browsers are lowercased and ordered by `psm_e2e_browsers`.
  [`ps-run-layer.py:595`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L595)

- Report view only, never evidence.
  [`ps-run-layer.py:989`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L989)

**Aggregate: per-cell `ready`**

- Record selection per cell: newest gate-grade, else newest.
  [`ps-aggregate.py:426`](../../.claude/skills/psm-validate/scripts/ps-aggregate.py#L426)

- Per-version E2E layer; a gate-grade `fail` always blocks, even with unreadable findings.
  [`ps-aggregate.py:518`](../../.claude/skills/psm-validate/scripts/ps-aggregate.py#L518)

- CAP-6 surface: each `boot_id` counted once, browsers per engine.
  [`ps-aggregate.py:581`](../../.claude/skills/psm-validate/scripts/ps-aggregate.py#L581)

**Child shape and timings (CAP-6)**

- Timing sink: inactive by default, `#n` suffixes, records failed phases too.
  [`ps-flashlight-run.py:348`](../../.claude/skills/psm-validate/scripts/ps-flashlight-run.py#L348)

- Boot wrapper measures wall-clock after teardown; cells emitted on every return path.
  [`ps-e2e-run.py:910`](../../.claude/skills/psm-validate/scripts/ps-e2e-run.py#L910)

- Per-engine cell fill; a launch error claims no scenarios.
  [`ps-e2e-run.py:894`](../../.claude/skills/psm-validate/scripts/ps-e2e-run.py#L894)

- Exit 0/3/1 from the shared state rule.
  [`ps-e2e-run.py:1167`](../../.claude/skills/psm-validate/scripts/ps-e2e-run.py#L1167)

**Orchestration docs (interim until CAP-1)**

- Fase 1/2, wrap-up (merge only in-scope versions), session and config.
  [`run-phases.md:1`](../../.claude/skills/psm-validate/references/run-phases.md#L1)

- Lapis 4, session minting, Vonis fields.
  [`SKILL.md:47`](../../.claude/skills/psm-validate/SKILL.md#L47)

- Headless config copy and the two kinds of exit 2.
  [`headless.md:1`](../../.claude/skills/psm-validate/references/headless.md#L1)

**Tests**

- Plan: fingerprint cases, corrupt line, reasons, configured-cells narrowing.
  [`test-ps-plan-layers.py:1`](../../.claude/skills/psm-validate/scripts/tests/test-ps-plan-layers.py#L1)

- Runner: AC3, input-error table, stop/exit-2/append-error paths.
  [`test-ps-run-layer.py:1`](../../.claude/skills/psm-validate/scripts/tests/test-ps-run-layer.py#L1)

- Aggregate: AC1, AC2, Chromium-only, headless narrowed, phase durations.
  [`test-ps-aggregate.py:1`](../../.claude/skills/psm-validate/scripts/tests/test-ps-aggregate.py#L1)
