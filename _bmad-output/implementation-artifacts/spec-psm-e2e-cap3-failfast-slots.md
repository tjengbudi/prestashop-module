---
title: 'psm-validate E2E: fail-fast, not-run records and host-wide slots (CAP-3)'
type: 'feature'
created: '2026-11-26'
status: 'done'
baseline_commit: '7ca66def43d0d48c8d51fb33c94e18de94c2a2d6'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-psm-e2e-tiered-gate/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-psm-e2e-tiered-gate/cell-contract.md'
  - '{project-root}/_bmad-output/specs/spec-psm-e2e-tiered-gate/tier-matrix.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-psm-e2e-cap2-cap6-cell-evidence.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A multi-cell `ps-run-layer.py --layer e2e` run keeps booting every queued version after a conclusive blocking failure, so Budi waits hours for evidence the first failure already made moot. Concurrency is a per-invocation `--jobs`, blind to other runs on the shared WSL Docker daemon, where saturation shows up as `wait-healthy` stalls.

**Approach:** Second slice of `SPEC-psm-e2e-tiered-gate` (CAP-3). `cell-contract.md` is authoritative for every rule named here: Runner > fail-fast, child exit 2, exit codes; not-run (CAP-3); Config keys > `psm_e2e_slots` (daemon-wide `psm.slots` count, registry `slot_claims`, `slots.lock`, `wait-slots`, `no-slots`, automatic `--cleanup-orphans`); Runner > Child flags `--run-id`, `--slot-cost`, `--progress-append`; Phase timings for `wait-slots`; the sequential-fallback fail-fast rule. This spec fixes only the slice boundary and interim decisions.

## Boundaries & Constraints

**Always:**
- Fail-fast: once a reaped child has appended a `fail` record (completion order), start no further queued cell, cancel `wait-slots` waits, let in-flight children finish; every unstarted cell gets a `not-run` record `fail-fast after <ver>:<browser>` (that child's first failing engine in `psm_e2e_browsers` order). A child exit 2 does the same with `input-error after <ver>` and still exits 2; nothing is appended for the exit-2 version itself. A version none of whose cells started: once its `not-run` records are appended, its progress log is truncated to one `DONE rc=not-run <reason>` line. Children reaped in one batch are handled in plan order; the first trigger fixes the reason for every unstarted cell (a child exit 2 still makes the run exit 2); `not-run` records are appended at the trigger. An append error stops admission as today: no `not-run`/`no-slots` record follows, in-flight children are still reaped and their records attempted, open waits end `cancelled`.
- Slots: `ps-run-layer.py --slots N` (else `psm_e2e_slots` from `--config`, validated in `read_e2e_config` (non-`--merge-only` `--layer e2e` runs only) even when `--slots` is given, empty = default; else 6; < 1 or non-integer = exit 2); `--jobs` defaults to `None` (`DEFAULT_JOBS` for Layers 2/5) and any `--jobs` with layer `e2e` (`--merge-only` included) = exit 2 naming `--slots`; `--slots` with another layer or `--merge-only` = exit 2. Admission per contract and Design Notes > Admission/Claims (daemon-wide `psm.slots` sum, live registry claims, `slots.lock`, failed docker count = cap full); every queued version's `wait-slots` opens as soon as its progress log is truncated, and the `--cleanup-orphans` routine runs once per run inside it, before the first docker count, every mode (result summarised on stderr; its errors never fail the run); timeout → `no-slots` (`inconclusive`) for every still-queued cell, with what filled the cap in `errors`.
- Child (`ps-e2e-run.py`): `--run-id` (`[0-9a-f]{12}`, else exit 2; set as `fl.RUN_ID` before progress, job registration or labels), `--slot-cost n` (integer ≥ 1, else exit 2; absent = 1, so a direct `ps-e2e-run.py` run is counted too; `ps-e2e-run.py` always stamps `psm.slots=n` on its PS container only, compose `ps:` service or manual `docker run`; Layers 2/5 (`ps-flashlight-run.py`, `ps-scenario-run.py`) stamp no `psm.slots`), `--progress-append` (no truncation), `--sequential-browsers` (after an engine's `fail`, that version's remaining probed engines (probe-dropped ones stay `browser-unavailable`) get cells `state: not-run`, `conclusive: false`, `reason: fail-fast after <ver>:<engine>`, every `_new_cell` key `null`, `scenario_set`/`browser_notes`/`phase_durations` included, which `run_one_version`'s timing copy skips; never started; with more than one engine the child logs the fallback once on stderr (as the interim cost-1 admission, not a slot shortage), never in `browser_notes`/`errors`). The child judges an engine's `fail` with `cell_state` after copying that engine's `browser:<engine>` timing into the cell (the sink is copied only after `_run_one_version_inner` returns, so without it every cell reads `not-driven`). ps-run-layer keeps a child `not-run` cell's `state`/`conclusive`/`reason` (no `derive_state`) and fills the rest as for a cell no engine ran.
- `psm_e2e_slots: "6"` in `PSM_DEFAULTS`, `DEFAULT_E2E_SLOTS = 6` in ps-run-layer with a drift check; `RESERVED_PASSTHROUGH` gains `--run-id`, `--slot-cost`, `--progress-append`, `--sequential-browsers` (so the prefix `--slo` becomes exit 2).
- Honesty law: `not-run`/`no-slots` cells are never gate-grade, never a pass. ps-run-layer's existing `--layer e2e` exit rules are unchanged; `not-run`/`no-slots` records count as not `pass` under them (so 1, unless a `fail` makes it 3).

**Ask First:** changing a contract rule rather than deferring it; making engine fail-fast apply to direct `ps-e2e-run.py` runs without `--sequential-browsers`.

**Never (later slices — keep absent, do not half-build):** CAP-1 (`--tier`, plan tiers/steps, canary, run scope, `reached`); CAP-7 parallel admission at cost n, `snapshot-db`/resets between sequential engines, workers, locks; CAP-5 keeper (`keeper-wait`, warm slot reuse); CAP-4 `--scenarios`; `stopped` records; aggregate/plan changes (they already read `not-run`).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| AC fail-fast | `--slots 1`, stubbed daemon count 0, `--cells 9.1:chromium,8.1:chromium,1.7.8:chromium`, 9.1 child fails | 8.1 and 1.7.8 never spawned; `not-run` `fail-fast after 9.1:chromium`; their logs = one `DONE rc=not-run` line, no `bring-up` | exit 3 |
| Fail in flight | `--slots 2`, 9.1 fails while 8.1 runs, 1.7.8 queued | 8.1 finishes and is appended; 1.7.8 `not-run` | exit 3 |
| Exit 1 child | first child inconclusive | no fail-fast, rest run | exit 1 |
| Child exit 2 | `--slots 1`, first child exits 2 | queued cells `not-run` `input-error after <ver>`; nothing for that version | exit 2, line `ran` |
| Foreign full | daemon count = slots forever, passthrough `-- --startup-timeout 1` | every cell `no-slots`, no child spawned | exit 1 |
| Own queue | `--slots 1`, two versions, child takes longer than the startup timeout | second waits past it, then runs | — |
| Count error | docker ps fails | treated as full → `no-slots` after timeout | — |
| Sequential child | `--sequential-browsers`, chromium fails | firefox cell `not-run`, never driven | child exit 3 |
| Labels | `--slot-cost 2` compose / manual; no `--slot-cost` compose / manual; Layer 2 / Layer 5 boot | `psm.slots` sums 2 / 2; 1 / 1; 0 / 0 | — |
| Bad input | `--slots 0`, `psm_e2e_slots: "x"`, `--jobs 2 --layer e2e`, child `--run-id XYZ` | — | exit 2 |

</frozen-after-approval>

## Code Map

- `.claude/skills/psm-validate/scripts/ps-run-layer.py` -- `run_e2e`, `run_children` (replaced by slot admission), `build_record`/`records_for_child`, `read_e2e_config`, `RESERVED_PASSTHROUGH`, `main` (`--jobs`/`--slots`)
- `.claude/skills/psm-validate/scripts/ps-flashlight-run.py` -- `progress`/`progress_init`, `job_register` (registry entry), `owner_labels`, `_compose_file_text`, `_bring_up_compose`/`_bring_up_manual`(`_inner`), `cleanup_orphans`, `entry_state`, `_registry_entries`
- `.claude/skills/psm-validate/scripts/ps-e2e-run.py` -- `main` (child flags), `run_one_version`, `_run_one_version_inner` engine loop and `note`, `_new_cell`, `cell_state`, `exit_code`
- `.claude/skills/psm-validate/scripts/ps-scenario-run.py` -- Layer 5 `_bring_up_manual` caller (no `psm.slots`)
- `.claude/skills/psm-setup/scripts/resolve-psm-config.py` -- `PSM_DEFAULTS`
- `.claude/skills/psm-validate/scripts/tests/test-ps-{run-layer,e2e-run,flashlight-run,scenario-run}.py` -- `_run_full`/`E2EChild` harness, drift test
- `.claude/skills/psm-validate/{SKILL.md,references/run-phases.md,references/headless.md}`, `docs/psm/README.md` -- `--jobs` → `--slots`, `wait-slots`, `not-run`/`no-slots`, automatic cleanup

## Tasks & Acceptance

**Execution:**
- [x] `ps-flashlight-run.py` -- path+version progress helper (`progress` delegates to it), a wait-phase helper on it (START/ALIVE/END to the given log, never `SLOW` whatever `slow_after`, returns `{seconds, outcome}`), `progress_init(truncate=)`, `job_update(**fields)` rewriting the own registry entry atomically (temp `.<pid>.json.tmp` in the same dir, never matching `*.json`, + `os.replace`; `job_register` too), `LOCK_DIR` (`<tmp>/psm-locks`), slot-cost label on the PS container only (stamped only when the caller gives a cost: `ps-e2e-run.py` always, Layers 2/5 never; keyword-only `slot_cost=None` from `_bring_up_compose`/`_bring_up_manual` down to `_compose_file_text`, so positional callers and stubs stay valid), `daemon_slot_usage()` -> (used, counted `[{job, host, run, cost}]`, error) from one `docker ps` (`error` `None`, else the failure tail: stderr, or the exception text on timeout/`OSError`; ps-run-layer prefixes `docker count failed: `) -- shared plumbing both scripts use
- [x] `ps-e2e-run.py` -- `--run-id`, `--slot-cost` (default 1), `--progress-append`, `--sequential-browsers` with engine fail-fast and `not-run` cells -- child side of CAP-3
- [x] `ps-run-layer.py` -- `--slots`, config key, slot admission loop with claims/lock/cleanup/`wait-slots` heartbeat and phase entry, fail-fast and exit-2 `not-run`, `no-slots`, every child gets `--run-id <claim> --slot-cost 1 --progress-append --sequential-browsers`, docstring -- runner side
- [x] `resolve-psm-config.py` + drift test (drift block in `test-ps-flashlight-run.py`) -- `psm_e2e_slots`
- [x] tests -- every I/O row; rewrite e2e tests that pass `--jobs` to `--slots` (`test_e2e_merge_only_view` drops `--jobs`; merge-only with `--jobs`/`--slots` = exit 2); the old "child exit 2 → nothing appended" expectation becomes `not-run` for queued cells; harness stubs `daemon_slot_usage`, `cleanup_orphans`, points `JOB_REGISTRY`/`fl.LOCK_DIR` at a fresh temp dir per `_run_full` call (with a hook seeding registry entries there for AC 2) and patches `SLOT_POLL`/`PROGRESS_HEARTBEAT` small; also: an exit-3 child with unreadable output → `crash`, no fail-fast; a `fail` (earlier in plan order) and an exit 2 reaped in one batch (both exit while a stubbed count blocks, a third version queued) → `fail-fast after <fail ver>:…`, exit 2; a cancelled wait's `outcome: cancelled` in the `not-run` record; claim counting (claim + its PS or DB container = 1, claim of a dead/foreign entry = 0); cleanup called exactly once per run, after every queued log shows `START wait-slots` and before the first count, both in the Own queue row and when slots suffice; a version admitted on the first pass has `wait-slots` (outcome `ok`) in its records' `phase_durations`; a `ps-e2e-run.py` boot without `--slot-cost` stamps `psm.slots=1`, a Layer 5 (`ps-scenario-run.py`) boot stamps none (labels read from the rendered compose text and captured `docker run` argv); each new `RESERVED_PASSTHROUGH` flag is exit 2; no wait phase writes `SLOW`; child `--run-id` lands in `psm.run`, its registry entry and progress lines, and `--progress-append` keeps the log; ps-run-layer keeps a child `not-run` cell without `derive_state`
- [x] docs -- SKILL.md and run-phases.md: E2E commands drop `--jobs` and pass no `--slots` (N = `psm_e2e_slots` via `--config`; `--slots` documented only as a manual override), the daemon-wide count checked against this run's own N (equal `psm_e2e_slots` everywhere gives one shared ceiling; claims from another temp dir count only once their containers run) (for E2E, per-run advice such as `--jobs 1` or "lower `--jobs`" becomes one version per `--cells` call / lower `psm_e2e_slots`; Layer 2/5 advice keeps `--jobs`, their containers are never counted), `wait-slots` in phase list (opened for every queued version as soon as the run starts, ends at admission; never `SLOW`), `not-run`/`no-slots` meaning and Run outcomes (fail-fast saves time only for still-queued cells; a direct `ps-e2e-run.py` run counts against every run's slots but bypasses admission; `not-run`: neither a failure nor an infra reason, `fail-fast after …` due again once the source changes, `input-error after …` once the rejected input is fixed, while a child exit 2 still ends the E2E loop for the session; `no-slots`: infra reason, fixed by freeing slots or waiting, or by fixing Docker when `errors` says `docker count failed`, never by an install), run-phases.md DONE table gains `rc=not-run <reason>`/`rc=no-slots`/`rc=stopped`, automatic `--cleanup-orphans` once per run inside `wait-slots`, before the first count, removing only provably-dead owners (also next to SKILL.md "Hentikan hanya secara terarah"); headless.md: it also runs headless (exception to "never touch a job you did not start"); `spec-psm-e2e-cap2-cap6-cell-evidence.interim-orchestration.md` (this spec amends that frozen companion until CAP-1): step 3 drops `--jobs` (as above), Run outcomes/Infra retry gain `not-run`/`no-slots` as above; README config table `psm_e2e_slots` and its `ps-run-layer.py --jobs` concurrency mentions (`--slots` for E2E)

**Acceptance Criteria:**
- Given the AC fail-fast row, when the run ends, then the output line `appended` lists all three cells and each history holds exactly one record.
- Given `--slots 1`, a large `--startup-timeout`, and a pre-seeded `alive` registry entry (`fl.OWNER_*` host/boot/ns, pid of a live test subprocess, no `script`) holding one claim, when the run starts, then it waits in `wait-slots` (`ALIVE wait-slots` lines naming `claim:<job>/<run>=1`) and is admitted once that claim is removed.

## Design Notes

- **Interim cost/mode (until CAP-7):** every version is admitted at cost 1 with `--sequential-browsers`, so `browser_mode` stays `sequential` and engine fail-fast always applies under ps-run-layer; the reset to a `snapshot-db` before later engines is deferred (browsers share one DB as today; such records lack the `#2` reset phases in `boot_phases`, which tells them apart from CAP-7 ones).
- **Trigger** is an appended `fail` record, not the bare exit code, as `cell-contract.md` > Runner > Fail-fast states: an exit-3 child whose output crashed has no conclusive finding and does not trigger fail-fast.
- **Admission:** the existing `docker_available()` skip stays first (before job registration, any truncation, `wait-slots` or cleanup: a skipped run touches no progress log). The queue is `--cells`/`--versions` written order. Before the first pass ps-run-layer truncates every queued version's progress log and right after it opens `wait-slots` in that log (`START wait-slots`, then the `ALIVE wait-slots` heartbeat, never `SLOW`; `ALIVE` detail `cleanup-orphans running`, then `first count pending` until the first count), so a queued version's log is never silent; the phase ends at admission (`END wait-slots ok`, before spawn) or at `no-slots`/`not-run`. With these phases open, the `--cleanup-orphans` routine runs once on the loop thread (off the `no-slots` clock), then the first pass starts; every docker count runs inside the open phases. The loop wakes on a child exit (reaping stays in completion order) or after `SLOT_POLL` (module constant, 5 s). Each pass first reaps every finished child (after a trigger the loop only reaps: no lock, count or admission), then holds `slots.lock` (blocking `flock` held for one count, so bounded by `DOCKER_CMD_TIMEOUT`; an `OSError` on it is ps-run-layer raising), reads claims, counts once, and admits the head while it fits, spawning each admitted version at once (claim written first; `_spawn` stays a blocking runner on a worker thread, the loop waiting with `wait(..., timeout=SLOT_POLL, return_when=FIRST_COMPLETED)`; one that raises an `Exception` is reaped as rc `None`: claim removed, `crash` records, no fail-fast; `JobStopped` still stops the run as today); every queued version it cannot admit stays in `wait-slots` (`ALIVE` detail recomputed each pass). The `no-slots` clock is one run-wide `time.monotonic` accumulator: it advances only while a version waits and no own child is in flight, never resets, and is checked after each pass's admissions, firing only while no own child is in flight; its limit is the contract's startup timeout, and a passthrough `--startup-timeout` that is not an integer is exit 2 before spawn (≤ 0 is accepted as today: no budget). `errors` holds one string per counted container `<psm.job>@<host>=<cost>` and claim `claim:<job>/<run>=<cost>` (own included), or `docker count failed: <stderr tail>` (last 200 chars, whitespace collapsed to one space); `ALIVE` details join the same tokens with `, `, then `; own queue` while an own child is in flight, else `; budget <n>s left`, and `; last pass <n>s ago`. A `psm.slots` label or claim `cost` that is not an integer ≥ 1 counts 1, shown as `=?`. `wait-slots` outcomes: `ok`, `no-slots`, `cancelled` (fail-fast, exit 2, append error, ps-run-layer's own exception or Ctrl-C), `stopped`; every outcome joins the heartbeat before `END`. On fail-fast or exit 2 a cancelled wait is closed (heartbeat joined) before its log is truncated to the `DONE` line, so `cancelled` survives only in the record's `phase_durations`.
- **Claims:** one `{run, cost}` per admitted version in the own registry entry, added before spawn and removed when its child is reaped, both under `slots.lock`. Claims (`slot_claims`, written only by ps-run-layer, so no script/layer filter) of every registry entry not its own (own = `pid == fl.OWNER_PID`) whose `entry_state` is `alive`, plus the run's own claims held in memory (never re-read from its own file), count unless a container returned by the `psm.slots` count carries that `psm.run` (never the DB container, which has no `psm.slots`). A failed registry write warns on stderr and never fails the run; other runs then see its claims only once its containers run (a failed removal leaves a stale claim until the next write, which rewrites the in-memory list).
- **Records:** `run_id` = the claim id for every record of an admitted version (crash included), ps-run-layer's own for `not-run`/`no-slots`; timestamps per contract Evidence record > Fields. Every queued version goes through `wait-slots`, so it is recorded like any phase: a record without a child cell has `phase_durations` = `{"wait-slots": …}`, and every record of a spawned version gets that entry merged (into a new dict when `null`; outcome `ok` when admitted on the first pass; a version with no record, i.e. skipped, `STOPPED_CODES` or exit 2, keeps it only in its log); a `no-slots` version's log ends `END wait-slots no-slots` + `DONE rc=no-slots`. When ps-run-layer exits, a log it truncated that lacks `DONE` gets one only when no child of that version is still running (an in-flight child writes its own): after a reaped child `rc=stopped` for `STOPPED_CODES`, `rc=crash` for rc `None` or a signal death (rc < 0, or > 128 as `uv run` reports it), else `rc=<child exit code>`; otherwise `rc=stopped` on a stop, `rc=crash` when ps-run-layer raises (exception or Ctrl-C: open waits end `cancelled` first, then it re-raises), else `rc=<run exit code>`.

## Verification

**Commands:**
- `for f in .claude/skills/psm-validate/scripts/tests/test-ps-*.py; do uv run "$f" >/dev/null || echo "FAILED $f"; done` -- expected: no FAILED line
- `uv run .claude/skills/psm-setup/scripts/tests/test-resolve-psm-config.py` -- expected: exit 0

## Suggested Review Order

**Slot admission and fail-fast (runner)**

- Entry point: one run's queue, claims, wait phases and trigger state in one object.
  [`ps-run-layer.py:918`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L918)

- One pass under slots.lock: foreign claims + one daemon count, admit the head while it fits.
  [`ps-run-layer.py:1175`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L1175)

- Reap: release claim, append records, a `fail` record (not exit 3) fires fail-fast.
  [`ps-run-layer.py:1131`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L1131)

- Fail-fast/exit-2: cancel waits, `not-run` for every unstarted cell, log reduced to DONE.
  [`ps-run-layer.py:1095`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L1095)

- Run-wide no-slots clock, advancing only while nothing of ours is in flight.
  [`ps-run-layer.py:1110`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L1110)

- Loop: reap in completion order, poll every SLOT_POLL, cleanup once inside wait-slots.
  [`ps-run-layer.py:1225`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L1225)

- DONE lines for every truncated log, whatever way the run ends.
  [`ps-run-layer.py:1263`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L1263)

- Claims of other live runs; unreadable registry warns instead of crashing.
  [`ps-run-layer.py:1025`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L1025)

- Shared lock in /tmp, made writable for other users.
  [`ps-run-layer.py:999`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L999)

**Shared plumbing (flashlight)**

- Daemon-wide `psm.slots` sum; a failed count is reported, the caller treats it as full.
  [`ps-flashlight-run.py:1403`](../../.claude/skills/psm-validate/scripts/ps-flashlight-run.py#L1403)

- `psm.slots` label stamped on the PS container only.
  [`ps-flashlight-run.py:1027`](../../.claude/skills/psm-validate/scripts/ps-flashlight-run.py#L1027)

- Wait phase: START/ALIVE/END to a given log, never SLOW, bounded join.
  [`ps-flashlight-run.py:377`](../../.claude/skills/psm-validate/scripts/ps-flashlight-run.py#L377)

- Registry entry rewritten atomically to publish `slot_claims`.
  [`ps-flashlight-run.py:669`](../../.claude/skills/psm-validate/scripts/ps-flashlight-run.py#L669)

**Child (ps-e2e-run)**

- Sequential engines: after a `fail` the rest become `not-run` cells, never driven.
  [`ps-e2e-run.py:1138`](../../.claude/skills/psm-validate/scripts/ps-e2e-run.py#L1138)

- Engine verdict judged with its browser timing copied in first.
  [`ps-e2e-run.py:1207`](../../.claude/skills/psm-validate/scripts/ps-e2e-run.py#L1207)

- Record merge keeps a child `not-run` cell's state as is.
  [`ps-run-layer.py:771`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L771)

**Config, docs, tests**

- `psm_e2e_slots` default 6 (drift-checked against the runner constant).
  [`resolve-psm-config.py:55`](../../.claude/skills/psm-setup/scripts/resolve-psm-config.py#L55)

- wait-slots, not-run/no-slots and automatic cleanup for the operator.
  [`run-phases.md:53`](../../.claude/skills/psm-validate/references/run-phases.md#L53)

- AC: `--slots 1`, first of three versions fails, others `not-run` with no bring-up.
  [`test-ps-run-layer.py:1683`](../../.claude/skills/psm-validate/scripts/tests/test-ps-run-layer.py#L1683)

- AC: a foreign live claim holds the run in wait-slots until removed.
  [`test-ps-run-layer.py:2054`](../../.claude/skills/psm-validate/scripts/tests/test-ps-run-layer.py#L2054)

- Sequential child fail-fast between engines.
  [`test-ps-e2e-run.py:571`](../../.claude/skills/psm-validate/scripts/tests/test-ps-e2e-run.py#L571)
