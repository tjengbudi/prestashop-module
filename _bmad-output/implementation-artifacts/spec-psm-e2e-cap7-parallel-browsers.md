---
title: 'psm-validate E2E: parallel browsers in one boot — workers, cross-engine lock, lockstep, sequential confirmation (CAP-7)'
type: 'feature'
created: '2026-11-27'
status: 'done'
baseline_commit: '8f75c71'
review_loop_iteration: 0
context:
  - '{project-root}/_bmad-output/specs/spec-psm-e2e-tiered-gate/SPEC.md'
  - '{project-root}/_bmad-output/specs/spec-psm-e2e-tiered-gate/cell-contract.md'
  - '{project-root}/_bmad-output/specs/spec-psm-e2e-tiered-gate/tier-matrix.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-psm-e2e-cap3-failfast-slots.md'
  - '{project-root}/_bmad-output/implementation-artifacts/spec-psm-e2e-cap1-tiered-gate.md'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** A version that needs both browsers drives them one after another inside one boot (CAP-3 interim: every version admitted at cost 1 with `--sequential-browsers`), so the release gate's browser time is the sum of both engines, and later engines inherit the shop state the earlier engine left (shared DB, no reset).

**Approach:** Last slice of `SPEC-psm-e2e-tiered-gate` (CAP-7). `cell-contract.md` > Parallel browsers (CAP-7) is authoritative for every rule named here — engine workers, cross-engine lock, lockstep barrier, BO-login fallback, parallel-only confirmation (`snapshot-db`, full reset, `rerun-seq`, `parallel_only`, `parallel-unconfirmed`), Slots (cost n vs cost 1 + `--sequential-browsers`, reset before later engines, `sequential-reset`), Identical findings — plus Phase timings for the new phases and Evidence record for the new reasons. This spec fixes only the slice boundary and interim decisions.

## Boundaries & Constraints

**Always:**
- Child (`ps-e2e-run.py`): a version process driving one probed engine drives it in-process (`browser_mode: sequential`). With ≥ 2 probed engines and no `--sequential-browsers` (direct runs included) it runs in parallel mode (`browser_mode: parallel`) and drives no browser itself during the lockstep pass: it captures `snapshot-db` after `warmup-bo`, spawns one `--engine-worker` subprocess per engine (same interpreter, registered under the same Job ID and `--run-id`, own `ctx`, screenshots in `<shots>/<ver>/<engine>`, lines appended to the version's progress log, never `DONE`), forwards SIGTERM, reaps workers in completion order (polling all of them) and creates `<engine>.done` as each exits, reads each worker's result file, then gives each engine (in `psm_e2e_browsers` order) at most one sequential pass per contract before teardown (a `rerun-seq` also for an engine without findings that drove a scenario in which any engine's parallel pass has a finding), and deletes the lock file, holders dir and step dir after all workers exit. A worker that leaves no parseable result (Design Notes > Worker interface) → its cell `inconclusive`, reason `crash`, exit code in `browser_notes`. Without `--slot-cost` (a direct run) the child stamps `psm.slots` = the number of engines it drives in parallel, else 1 (one engine or `--sequential-browsers`).
- In an engine worker only (in-process passes — single engine, sequential fallback, `rerun-seq`, BO-login fallback — take no lock and write no marker), every scenario holds `fcntl.flock` on `<LOCK_DIR>/<job>-<ver>.bo.lock` (`LOCK_EX` when it has a BO `goto`, else `LOCK_SH`) and releases it (fd closed) when the scenario ends, before writing its step marker; while holding it the worker keeps the marker `<LOCK_DIR>/<job>-<ver>.bo.holders/<engine>` (created after acquiring, removed before release). `_bo_login` runs outside it. Waiting (opened only when a non-blocking try fails) = phase `lock-wait:<engine>` naming the engines in the holders dir. Lockstep barrier per contract (`<LOCK_DIR>/<job>-<ver>.step/<engine>.<k>`, k = 0-based index in the driven list: the universal smoke is step 0, then discovery order), waiting = `barrier-wait:<engine>` naming the engines not done. Both waits poll, have no timeout, never `SLOW`. A cell's first pass records `scenario_spans` (Design Notes).
- Reset (`reset-db`, `reset-files` with a fresh module copy and no install, `reset-opcache`, then `wait-http`, `warmup-bo`) is one shared routine, used by the parallel confirmation passes and by the sequential fallback before each engine after the first; its phases land in `boot_phases` suffixed by `TimingSink` (a name's first occurrence in the boot is bare, so the first reset records `reset-db`, `reset-files`, `reset-opcache`, `wait-http#2`, `warmup-bo#2`). Commands and failures: Design Notes.
- Child-set cell states are kept as emitted (no `derive_state`) by `cell_state` and by ps-run-layer's `build_record`: `not-run`, and `inconclusive` with reason `crash`, `parallel-unconfirmed` or `sequential-reset`. Only a `parallel-unconfirmed` or `sequential-reset` cell carries a cell-level `errors` list (the failing sub-phase; `_new_cell` gains no `errors` key); `build_record` writes version-level `errors` followed by it, never replacing them and never copying it to sibling cells.
- Runner (`ps-run-layer.py`): admits a version driving n engines at cost n (child without `--sequential-browsers`) when n slots are free, else at cost 1 with `--sequential-browsers` when n > 1; a version any of whose configured cells has a newest record with reason `parallel-unconfirmed` (read once before admission) is always admitted at cost 1 sequential. The child argv, `--slot-cost` and the slot claim carry the admitted cost. `RESERVED_PASSTHROUGH` gains `--engine-worker`.
- Honesty law: a parallel finding blocks only when the sequential rerun reproduces it; a rerun failure always blocks (state `fail`); unconfirmable findings never pass silently: a snapshot, health or reset failure gives `parallel-unconfirmed`; a degraded rerun (launch error, failed BO login) keeps the state Design Notes > Confirmation merge gives it, judged exactly like a single-engine run (a failed BO login leaves its authed BO steps inconclusive). Child exit code and fail-fast see only the confirmed result.

**Ask First:** changing a contract rule rather than deferring it; adding CAP-4 `requires`/topological order or CAP-5 keeper code to make a test pass.

**Never (later slices — keep absent):** CAP-4 (`--scenarios`, `--scenarios-from-failed`, `requires`, Kahn order — lockstep uses today's discovery order); CAP-5 keeper/warm flags (`--warm`, `--use-warm`, `--keep-warm`, `--warm-owner`, `--warm-ttl`, `keeper-wait`, warm `baseline`) — the reset routine is written so CAP-5 can reuse it, but no warm path exists; producing `stopped` records; the bankwire timing report (both deferred-work).

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Parallel clean | 2 engines, no findings | one boot, `snapshot-db`, no sequential pass; both cells `parallel`, `started_at`/`finished_at` overlap; FO-only scenarios' spans overlap across engines, BO scenarios' never | exit 0 |
| Parallel-only failure | chromium finding F in scenario X not reproduced in `rerun-seq`; firefox no finding, its rerun clean | chromium `pass`, F in `parallel_only`; firefox also gets `rerun-seq:firefox` (it drove X), `pass`; `boot_phases` gains `reset-db`, `reset-files`, `reset-opcache`, `wait-http#2`, `warmup-bo#2`, then `reset-db#2`, `reset-files#2`, `reset-opcache#2`, `wait-http#3`, `warmup-bo#3` | exit 0 |
| Masked on other engine | chromium finding in X; firefox no finding, its rerun fails G | firefox findings = {G}, `fail`, `parallel_only` empty | exit 3 |
| Confirmed + new | finding F reproduced, rerun also fails G | findings = {F, G} (rerun's), `fail` | exit 3 |
| Unconfirmable | finding, `reset-db` fails (or container unhealthy) | `inconclusive`, `parallel-unconfirmed`, F in `parallel_only`, sub-phase in cell `errors` | exit 1 |
| BO-login fallback | chromium login ok, firefox login fails | firefox first pass discarded; `browser:firefox#2` after reset counts, no confirmation | — |
| All BO logins fail, FO finding | 2 engines, both BO logins fail; chromium FO finding F in scenario X, reproduced by its rerun | no `browser:<engine>#2`; `rerun-seq:chromium` and `rerun-seq:firefox` (it drove X) still run; chromium findings = {F}, `fail`; authed BO steps stay in `inconclusive` on both cells | exit 3 |
| Worker crash | firefox worker exits 1, no result | firefox `crash` (rc in `browser_notes`), chromium unaffected; barrier never hangs | exit 1 |
| Sequential fallback | `--sequential-browsers`, 2 engines, both pass | `snapshot-db`, then before firefox `reset-db`, `reset-files`, `reset-opcache`, `wait-http#2`, `warmup-bo#2`; both cells driven, `browser_mode: sequential` | exit 0 |
| Sequential fail-fast | `--sequential-browsers`, 2 engines, chromium `fail` | firefox `not-run`; no reset phase in `boot_phases` | exit 3 |
| Sequential reset fails | reset before firefox fails | firefox `inconclusive`, `sequential-reset`, sub-phase in its `errors`; chromium's record clean | exit 1 |
| Direct run label | `ps-e2e-run.py` without `--slot-cost`: 2 probed engines / one engine / `--sequential-browsers` | `psm.slots` = 2 / 1 / 1 (compose and manual) | — |
| Admission | `--slots 6`, `--cells 9.1:chromium+firefox,8.1:chromium+firefox,1.7.8:chromium+firefox`, count 0 | three children, cost 2 each, no `--sequential-browsers` | — |
| Admission short | `--slots 3`, same cells | 9.1 cost 2 parallel; 8.1 cost 1 `--sequential-browsers`; 1.7.8 waits | — |
| Unconfirmed history | 8.1:firefox newest reason `parallel-unconfirmed` | 8.1 cost 1 `--sequential-browsers` whatever the free slots | — |

</frozen-after-approval>

## Code Map

- `.claude/skills/psm-validate/scripts/ps-e2e-run.py` -- `__main__` (worker dispatch), `_run_one_version_inner` (mode choice, snapshot, parallel driver, confirmation passes, sequential fallback resets), `_drive_page`/`drive_engine` (per-scenario hook, spans), `substitute` (`{browser}` token), `_new_cell`, `_fill_cell`, `cell_state`, `_engine_failed`, `exit_code`, `main` (`--sequential-browsers` stderr text; `--slot-cost` default absent → n in parallel mode, else 1)
- `.claude/skills/psm-validate/scripts/ps-flashlight-run.py` -- `TimingSink.record` (route `lock-wait:`/`barrier-wait:`/`rerun-seq:` to the cell), `phase`, `progress_*` (new `progress_attach`), `job_register`, `JOB_STOP_GRACE`, `LOCK_DIR`, `_exec`, `_health_status`
- `.claude/skills/psm-validate/scripts/ps-scenario-run.py` -- `DB_PRELUDE` (read only, unchanged)
- `.claude/skills/psm-validate/scripts/ps-run-layer.py` -- `_SlotRun.__init__`/`_pass` (cost n admission, argv at admission), `build_record` (child-set states, cell `errors`), `RESERVED_PASSTHROUGH`, docstring
- `.claude/skills/psm-validate/scripts/ps-plan-layers.py` -- `read_history`, `history_path` (read by the runner; unchanged)
- `.claude/skills/psm-validate/scripts/tests/test-ps-{e2e-run,run-layer,flashlight-run}.py` -- unit tests; new `tests/live/test-cap7-live.py`
- `.claude/skills/psm-validate/{SKILL.md,references/run-phases.md,references/e2e-quickstart.md}`, `docs/psm/README.md` -- docs

## Tasks & Acceptance

**Execution:**
- [x] `ps-flashlight-run.py` -- `TimingSink.record` routes `browser:`, `lock-wait:`, `barrier-wait:`, `rerun-seq:` phases to `phase_durations[<engine>]` through a new `CELL_PHASE_PREFIXES` tuple; `CELL_PHASE_PREFIX = "browser:"` stays unchanged (ps-plan-layers `_driven` reads it: only `browser:<engine>` marks a cell driven); `TimingSink.events` = `[(name, seconds, outcome)]` unsuffixed in record order; `progress_attach(path, version, slow_after)` -- cell phases per contract Phase timings
- [x] `ps-e2e-run.py` -- engine worker (`--engine-worker <spec.json>`, Design Notes > Worker interface), cross-engine lock + holder markers, step barrier, `scenario_spans` in each cell's first pass, snapshot + reset routine, parallel driver (spawn/reap/`.done`/SIGTERM forwarding/crash cells/worker timings re-recorded into the version sink as each worker is reaped), sequential passes (BO-login fallback, `rerun-seq` confirmation, `parallel-unconfirmed`), sequential-fallback resets (`sequential-reset`), child-set states in `cell_state`, docstring -- child side of CAP-7
- [x] `ps-run-layer.py` -- cost n / cost 1 admission, `parallel-unconfirmed` forcing, argv built at admission, `build_record` child-set states + cell `errors`, `--engine-worker` reserved, docstring -- runner side
- [x] `tests/test-ps-e2e-run.py`, `tests/test-ps-run-layer.py`, `tests/test-ps-flashlight-run.py` -- every I/O row (child rows with a stubbed parallel driver / stubbed container execs; the worker spawn path once with a real stub worker subprocess (`WORKER_CMD` set to a wrapper script that loads ps-e2e-run.py, stubs `drive_engine` and calls the real `worker_main`, so stamping, result write, `progress_attach` and `job_register` run; the `--engine-worker` argv dispatch gets its own test); the lock and barrier helpers (explicit paths, no phase, sink or progress use) with real `flock`/files across threads, their `lock-wait:`/`barrier-wait:` phases covered by the stub-worker subprocess test; stub driven lists have ≥ 2 steps and stub FO-only scenarios last ≥ 5 × `LOCKSTEP_POLL`, so overlap claims are deterministic); existing expectations updated: two-engine `_rov` tests without `sequential_browsers` go through the stubbed parallel driver, and "tanpa --sequential-browsers (run langsung): engine lain tetap jalan" asserts parallel mode (no in-process drive, workers spawned through the seam); two-engine `sequential_browsers=True` tests stub the snapshot/reset execs; incl. CAP-3's Labels test (no `--slot-cost` → 1 now only for one engine or `--sequential-browsers`) -- unit coverage
- [x] `tests/live/test-cap7-live.py` -- skips unless Docker, both browsers, the default-tag flashlight images and the DB image are local; never pulls; runs on a plain temp copy of `modules/bankwire`; (a) concurrent same-admin BO sessions (A logs in, then B, each loads `AdminModules` still authed) per target version; (b) Identical findings per contract with the step-55 fault (non-empty confirmed set; a mismatch reruns once; every attempt, retry included, uses a fresh empty reports dir, so admission is never history-forced) plus AC1's live overlap; (c) from (b)'s parallel records: no BO-scenario span overlaps the other engine's spans, and every step k+1 span starts after every step k span ends; `PSM_LIVE_VERSIONS` may narrow the versions; (b) and (c) assert `browser_mode: parallel` on both records of each version and fail, naming the counted slots, when admission fell back to sequential; a skip prints one `SKIPPED: <reason>` line (missing images named) and exits 0 -- contract live tests
- [x] docs -- `SKILL.md` ("Vonis dan output": `parallel_only`; "Pantau run Docker": `snapshot-db`, `reset-*`, `lock-wait:`/`barrier-wait:` (never SLOW), `rerun-seq:`, `browser:<e>#2`; Lapis 4: "CAP-4/5/7" → "CAP-4/5", visual review reads the `screenshots` of the newest line of `<reports>/<module>-e2e-<ver>-<browser>.jsonl` for each driven cell in `appended` — in parallel mode under `<ver>/<engine>/` or `<ver>/<engine>-seq/`; the one sanctioned history read, path pattern from `ps-run-layer.py --help`, named as the exception in SKILL.md "namanya diturunkan skrip, tak diketik" and run-phases.md "Hasil run … tak pernah dari histori"), `references/run-phases.md` (cost n vs cost 1 admission, `parallel-unconfirmed` → sequential next run, the new phases, worker lines; the interim sentence "Interim sampai CAP-4/5/7 … browser berurutan sesuai admisi slot" rewritten for CAP-4/5 (browsers parallel at cost n, sequential at cost 1 with a reset between engines); Istilah E2E gains `parallel-unconfirmed`, `sequential-reset` and worker `crash` (meaning, infra cause, remediation: rerun — after `parallel-unconfirmed` the next run is admitted at cost 1 sequential — and check container health, the child's stderr and the `snapshot-db`/`reset-*`/`rerun-seq:` END lines of the progress log); "Tinjauan visual" same source as SKILL.md), `references/e2e-quickstart.md` (a direct two-engine run is parallel and counts 2 slots; `{browser}` = `<engine>-seq` only in the confirmation passes after a parallel run (`rerun-seq`, BO-login fallback); rewrite the "DB bersama antar-browser" gotcha (lockstep + reset; `{browser}` still needed within a step) and the screenshot-path example (`<ver>/<engine>/` in parallel mode)), `docs/psm/README.md` (next to the `psm_e2e_slots` row: a parallel version costs n slots) -- operator docs

**Acceptance Criteria:**
- Given a two-engine version admitted at cost 2 with a driven list of ≥ 2 steps, when it runs (unit: the real stub-worker spawn test, no findings; live: (b)), then both cells (unit: the child's `cells` under one version-level `boot_id`) or records (live) share `boot_id` and have `browser_mode: parallel`, and the browser phases overlap: unit, max(`started_at`) < min(`finished_at`) (worker-stamped); live, where a rerun supplies `finished_at`, each engine's earliest `scenario_spans` start < the other engine's latest span end.
- Given the live suite on this host, when `uv run .claude/skills/psm-validate/scripts/tests/live/test-cap7-live.py` runs, then (a), (b) and (c) pass on every default target version.

## Design Notes

- **Mode:** parallel only with ≥ 2 probed engines and no `--sequential-browsers`; the probe may drop an engine after admission at cost n (cost stays stamped, contract). Snapshot only when the boot drives > 1 engine.
- **`scenario_spans`** = `{<scenario name>: [start_ns, end_ns]}` from `time.monotonic_ns()` (host-wide clock, comparable across processes), recorded only by a cell's first pass (the lockstep worker pass, or the engine's only pass in single-engine and sequential-fallback mode); `rerun-seq` and BO-login fallback passes record none. In a worker each scenario runs: acquire the lock (after any `lock-wait`), `start_ns`, run, `end_ns`, remove the holder marker, close the fd, write the step marker; after the last step's marker the worker leaves `browser:<engine>` with no barrier wait. Release runs in a `finally` (holder marker removed best-effort, fd closed); a holder-marker create/remove error is ignored; the step marker is written only after a scenario that returned (an exception aborts the drive, and `<engine>.done` releases the barrier); the version process also deletes a reaped worker's holder marker best-effort. Lock and barrier polls sleep `LOCKSTEP_POLL` = 0.25 s. In-process passes stamp just around the run.
- **Phases:** only the worker records the lockstep `browser:<engine>` (re-recorded once into the version sink); the version process wraps no `browser:` phase around workers. `rerun-seq:<engine>` wraps the health check, reset and drive, with no `browser:` phase inside; the BO-login fallback runs the reset, then `browser:<engine>#2`. Phase names always use the engine name. Only the confirmation passes (`rerun-seq`, BO-login fallback) set `ctx['browser_token']` = `<engine>-seq` (read only by `substitute` for `{browser}`) and `ctx['screenshot_dir']` = `<shots>/<ver>/<engine>-seq` (created best-effort like the version dir); findings, `inconclusive` and the launch keep the engine name. Worker passes, single-engine runs and every engine of the sequential fallback set no token (`{browser}` = the engine name); their screenshots go to `<shots>/<ver>/<engine>` (worker) or today's `<shots>/<ver>`.
- **Sequential fallback, snapshot failure:** no engine has run yet, so every engine gets `sequential-reset` naming `snapshot-db` (contract Slots).
- **Confirmation passes (parallel mode):** BO login failed = a result is present, `launch_error` is null, the driven list needs BO (`_needs_bo`) and `bo_authed` is false; succeeded = `bo_authed` true. A `crash` or `launch_error` engine is neither: it gets no pass, its partial spans do not count as driven, and it is ignored for "every engine's login failed". An engine needs a fallback pass when its login failed and another's succeeded, or a `rerun-seq` when it has findings or a scenario in its lockstep `scenario_spans` has a finding in any engine's parallel pass (a discarded first pass included). Every engine needing a pass gets one, in order, whatever an earlier pass found; each starts with the shared reset routine (Snapshot and reset). After the first failure of the snapshot or of any reset-routine sub-phase (health check, `reset-db`, `reset-files`, `reset-opcache`, `wait-http`) no further reset runs: that engine and every later engine needing a pass get `parallel-unconfirmed`, `findings: []`, their parallel findings in `parallel_only` (a BO-login-fallback engine: its discarded first pass's), the sub-phase in cell `errors`, and keep every other field of that parallel pass. The failure prints its `errors` entry on stderr and, inside `rerun-seq:<engine>`, sets that phase's END outcome to `<sub-phase>-failed`; a later engine skipped for it opens no phase, and its cell `errors` repeats that entry verbatim. These failures never enter version-level `errors` (sequential fallback included). In parallel mode a `snapshot-db` failure does not stop the lockstep pass: its `errors` entry is printed on stderr once, at snapshot time, no engine opens `rerun-seq:`, every engine needing a pass gets `parallel-unconfirmed` with that entry, and engines needing none keep their parallel result. When every engine's BO login failed, no BO-login fallback pass runs, but an engine needing a `rerun-seq` still gets it.
- **Confirmation merge:** the counting pass supplies `scenarios_run`, `authored_assertions`, `bo_authed`, `launch_error`, `console_errors`, `screenshots`, `finished_at`; `started_at` and `scenario_spans` always stay from the lockstep pass. Rerun: `findings` = the rerun's own finding objects; parallel findings whose `(scenario, step, action)` is absent from them move to `parallel_only` (an engine rerun only for another engine's finding has none, so its rerun's failures are its findings); `inconclusive` = first pass's ∪ rerun's (dedup on that key). BO-login fallback: `findings` and `inconclusive` are that pass's alone. A rerun that cannot launch thus leaves the cell `inconclusive` (`launch-error`); one whose BO login fails leaves its BO steps inconclusive. Each pass whose `launch_error` is set (worker included) adds today's launch-failure note to that engine's `browser_notes`. The version-level legacy fields (`findings`, `inconclusive`, `pass`, `browsers`, `screenshots`, `console_errors`, `authored_assertions`, `skipped_browser`) are rebuilt from the final cells in every mode, where today's code computes them (earlier returns keep today's values): `browsers` = engines whose counting pass ran without `launch_error` (never a `crash`, `sequential-reset` or `not-run` cell); `findings`, `inconclusive`, `screenshots`, `console_errors`, `authored_assertions` from those engines' final cells; `pass` = `browsers` non-empty, no findings and no `parallel-unconfirmed` cell; `skipped_browser` = `browsers` empty (today's meaning: no engine tested). `parallel_only` = `[]` on every cell of a parallel-mode version whose worker left a parseable result (`launch_error` included) unless filled above, else `null` (`_new_cell`).
- **Worker interface:** the version process spawns module-level `WORKER_CMD` (default `[sys.executable, __file__, '--engine-worker']`) plus the spec.json path; `__main__` dispatches `argv[1] == '--engine-worker'` to `worker_main(spec_path)` before `run_main_with_progress` (so no `DONE`); the worker starts with `fl.RUN_ID` = `run_id`, then a new `fl.progress_attach(path, version, slow_after)` (sets the progress path, version and slow-after; no truncate; never `progress_init`), then `job_register(job_id, module=ctx['mod'], layer='e2e', versions=version)`, then `timing_activate()`, and sets `ctx['screenshot_dir']` = spec.json's `screenshot_dir` (null when that dir could not be created: screenshots skipped); each progress line names its engine in the phase field. Before spawning, the version process creates a private work dir (`tempfile.mkdtemp()`, mode 0700) holding `<engine>.spec.json` and `<engine>.result.json`, plus the holders dir, the step dir and each `<shots>/<ver>/<engine>` (best-effort like the version dir); it deletes the work dir with the lock file, holders dir and step dir after all workers exit (its `finally`, stop path included). spec.json = `{version, engine, engines, scenarios, ctx, job_id, run_id, parent_pid, progress_file, slow_after, lock, holders_dir, step_dir, screenshot_dir, headed, result}` (`ctx` JSON-safe). Workers run with stdout `DEVNULL` and inherit stderr. The result file, written atomically (temp + `os.replace`), = `{engine, started_at, finished_at, result: <drive_engine's return>, scenario_spans, timings: [[name, seconds, outcome], ...]}`: `started_at`/`finished_at` = `utc_now()` stamped by the worker just inside and at the end of its `browser:<engine>` phase and copied into the cell (a `crash` cell leaves both null; ps-run-layer fills them per contract); `timings` = the worker sink's `events`, re-recorded into the version sink when that worker is reaped, so the version sink's suffixes continue and every lockstep phase precedes the sequential passes'. Parseable = a JSON object with those keys and `engine` = the worker's; a parseable result is used whatever the exit code or signal, and a worker without one is a `crash` unless the version process itself was stopped. A worker that cannot be spawned (spec write or `Popen` error): its `<engine>.done` is created at once, its cell is `crash` with the error in `browser_notes`, and the other workers go on. In the lock and barrier polls a worker whose `os.getppid()` differs from spec.json's `parent_pid` (the version process's `os.getpid()`) removes its holder marker best-effort, writes no result and exits 1. A worker that gets `JobStopped` ignores further SIGTERM, writes no result and exits 143. Every exit of the version process while workers are alive (its `finally` before teardown, stop path included) uses one reap: SIGTERM the live workers, wait at most 10 s in total, SIGKILL the rest, then wait for them (well inside `stop_job`'s `JOB_STOP_GRACE`). On its own SIGTERM (`JobStopped`) the version process forwards it, reaps so, skips every sequential pass and exits 143 as today.
- **Logging:** the sequential-mode notice and the BO-login fallback go to stderr and, in the progress log, only as the detail of a `START` line (no new token): the notice on the first `browser:<engine>` START, the fallback on the fallback pass's `browser:<engine>` START; never `browser_notes`/`errors`; the `--sequential-browsers` stderr text drops "admisi interim cost 1".
- **Snapshot and reset in shell (inside the PS container):** `DB_PRELUDE` comes from ps-scenario-run.py loaded lazily by path like `_plan_layers` (only `DB_PRELUDE` is read; ps-e2e-run's own `fl` runs `_exec`/`phase`; any load error, `SystemExit` included, is a `snapshot-db` failure). Each of `snapshot-db`, `reset-db`, `reset-files`, `reset-opcache` is one `fl._exec` with timeout `--timeout` and env `{"MOD_NAME": mod_name}`, running a `set -e` script with no pipe whose status matters and no process substitution (`sh` may be dash), starting with `: "${MOD_NAME:?}"` and `export LC_ALL=C` (so `sort` and `comm` agree) and ending with `echo PSM_<SUB_PHASE>_OK` (e.g. `PSM_RESET_DB_OK`); failure = timeout, exception, non-zero exit or missing sentinel, and sets the phase's `ph.status` = `timeout` on timeout, else `gagal` (as `pull`), so its END line and `boot_phases` outcome show it. The shared reset routine (every confirmation pass, and every later engine of the sequential fallback) is: health check (`_health_status` must be `healthy`), `reset-db`, `reset-files`, `reset-opcache`, `wait-http` (no response fails the routine and sets its `ph.status` = `gagal`; a 5xx answer and `warmup-bo` stay best-effort as on first boot); both use first boot's helpers, URLs and `--startup-timeout`. A failure's `errors` entry = `<sub-phase>: <reason, ≤ 200 chars>` (`health: <status>` for the health check, `wait-http: no response`). Docroot listing (one shared snippet, run in the docroot): `find . \( -path ./var/cache -o -path "./modules/$MOD_NAME" \) -prune -o -print > <tmp>`, then `sort <tmp> > <list>` (files and directories; names containing a newline are unsupported). `snapshot-db` = `$MYSQLDUMP_BIN -h $DBH -P $DBPORT -u $DBU -p$DBPW --single-transaction --routines --databases $DBN > /tmp/psm-e2e-snapshot.sql` plus the listing into `/tmp/psm-e2e-snapshot.files` (outside the docroot, apart from Layer 5's `/tmp/psm-scenario-baseline.sql`). `reset-db` = `$MYSQL_BIN` with the same creds and no database argument: `DROP DATABASE`, then load the dump (it recreates the DB). `reset-files` = `rm -rf modules/$MOD_NAME`, the listing into `/tmp/psm-e2e-current.files`, `comm -13 /tmp/psm-e2e-snapshot.files /tmp/psm-e2e-current.files > /tmp/psm-e2e-new.files`, `while IFS= read -r p; do rm -rf -- "$p"; done < /tmp/psm-e2e-new.files`, empty `var/cache` (keep the dir), `cp -r /ps-module-src modules/$MOD_NAME`. `reset-opcache` = `kill -USR2` the php-fpm master, the one process whose `/proc/<pid>/comm` starts with `php-fpm` while its parent's (`PPid:` from `/proc/<pid>/status`) does not (PPid 0 or an unreadable parent counts as not php-fpm; a candidate whose own `comm`/`status` vanishes or cannot be read is skipped, e.g. `c=$(cat /proc/$p/comm 2>/dev/null) || continue`; php-fpm running but not exactly one such process = fail); without php-fpm `apachectl -k graceful`; else fail.

## Verification

**Commands:**
- `for f in .claude/skills/psm-validate/scripts/tests/test-ps-*.py; do uv run "$f" >/dev/null || echo "FAILED $f"; done` -- expected: no FAILED line
- `uv run .claude/skills/psm-setup/scripts/tests/test-resolve-psm-config.py` -- expected: exit 0
- `uv run .claude/skills/psm-validate/scripts/tests/live/test-cap7-live.py` -- expected: exit 0 and no `SKIPPED` line, with `PSM_LIVE_VERSIONS` unset (long: about a dozen boots; run in the background)

## Suggested Review Order

**Parallel driver (child, version process)**

- Entry point: lockstep pass, then per-engine confirmation passes, then rebuild legacy fields.
  [`ps-e2e-run.py:1648`](../../.claude/skills/psm-validate/scripts/ps-e2e-run.py#L1648)

- Spawns one worker per engine, reaps in completion order, writes `<engine>.done`.
  [`ps-e2e-run.py:1317`](../../.claude/skills/psm-validate/scripts/ps-e2e-run.py#L1317)

- One reap path: SIGTERM, 10 s grace, SIGKILL — shared by stop and normal exit.
  [`ps-e2e-run.py:1289`](../../.claude/skills/psm-validate/scripts/ps-e2e-run.py#L1289)

- Parseable-result check decides `crash` vs used result, whatever the exit code.
  [`ps-e2e-run.py:1260`](../../.claude/skills/psm-validate/scripts/ps-e2e-run.py#L1260)

**Engine worker, lock and lockstep**

- Worker entry: attach progress, register job, drive under `LockstepHook`, atomic result.
  [`ps-e2e-run.py:1202`](../../.claude/skills/psm-validate/scripts/ps-e2e-run.py#L1202)

- Review patch: first SIGTERM ignores repeats so cleanup is never cut.
  [`ps-e2e-run.py:1196`](../../.claude/skills/psm-validate/scripts/ps-e2e-run.py#L1196)

- Per scenario: barrier for step k−1, flock EX/SH, span, release, step marker.
  [`ps-e2e-run.py:1124`](../../.claude/skills/psm-validate/scripts/ps-e2e-run.py#L1124)

- Barrier polls markers / `.done`; parent-gone check prevents orphan workers.
  [`ps-e2e-run.py:1090`](../../.claude/skills/psm-validate/scripts/ps-e2e-run.py#L1090)

- Non-blocking try first; `lock-wait:` opened only on contention, never SLOW.
  [`ps-e2e-run.py:1028`](../../.claude/skills/psm-validate/scripts/ps-e2e-run.py#L1028)

**Confirmation (honesty law)**

- Who gets BO-login fallback vs `rerun-seq` (drove a scenario with any finding).
  [`ps-e2e-run.py:1621`](../../.claude/skills/psm-validate/scripts/ps-e2e-run.py#L1621)

- Rerun findings replace parallel ones; unreproduced move to `parallel_only`.
  [`ps-e2e-run.py:1601`](../../.claude/skills/psm-validate/scripts/ps-e2e-run.py#L1601)

- Legacy version fields rebuilt from final cells; `parallel-unconfirmed` blocks `pass`.
  [`ps-e2e-run.py:1771`](../../.claude/skills/psm-validate/scripts/ps-e2e-run.py#L1771)

**Snapshot and reset (inside container)**

- mysqldump + docroot listing after `warmup-bo`; dash-safe `set -e` with sentinel.
  [`ps-e2e-run.py:1408`](../../.claude/skills/psm-validate/scripts/ps-e2e-run.py#L1408)

- Shared routine: health, reset-db/files/opcache, wait-http, warmup-bo; first failure stops.
  [`ps-e2e-run.py:1532`](../../.claude/skills/psm-validate/scripts/ps-e2e-run.py#L1532)

- Sequential fallback resets before each later engine; failure → `sequential-reset`.
  [`ps-e2e-run.py:1723`](../../.claude/skills/psm-validate/scripts/ps-e2e-run.py#L1723)

- Live-found fix: wait for redirect off AdminLogin (Firefox 8.1 false login failure).
  [`ps-e2e-run.py:826`](../../.claude/skills/psm-validate/scripts/ps-e2e-run.py#L826)

**Runner admission and records**

- Cost n when n slots free, else cost 1 + `--sequential-browsers`.
  [`ps-run-layer.py:1065`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L1065)

- Newest `parallel-unconfirmed` (or unreadable history) forces sequential.
  [`ps-run-layer.py:1034`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L1034)

- argv, `--slot-cost` and claim built at admission with the same cost.
  [`ps-run-layer.py:693`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L693)

- Child-set states kept as emitted; cell `errors` appended after version errors.
  [`ps-run-layer.py:820`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L820)

- Child side mirrors it in `cell_state`.
  [`ps-e2e-run.py:2015`](../../.claude/skills/psm-validate/scripts/ps-e2e-run.py#L2015)

**Phase plumbing**

- New cell-phase prefixes routed to `phase_durations[<engine>]`; `CELL_PHASE_PREFIX` untouched.
  [`ps-flashlight-run.py:460`](../../.claude/skills/psm-validate/scripts/ps-flashlight-run.py#L460)

- Worker joins the version's progress log without truncating it.
  [`ps-flashlight-run.py:335`](../../.claude/skills/psm-validate/scripts/ps-flashlight-run.py#L335)

**Tests and docs**

- Real stub-worker subprocess through `WORKER_CMD`; AC1 overlap asserted.
  [`test-ps-e2e-run.py:1545`](../../.claude/skills/psm-validate/scripts/tests/test-ps-e2e-run.py#L1545)

- Real flock/barrier across threads.
  [`test-ps-e2e-run.py:1273`](../../.claude/skills/psm-validate/scripts/tests/test-ps-e2e-run.py#L1273)

- Live suite: concurrent BO sessions, Identical findings, span lock/lockstep checks.
  [`test-cap7-live.py:421`](../../.claude/skills/psm-validate/scripts/tests/live/test-cap7-live.py#L421)

- Operator docs: phases, cost n/1, new reasons, stall exception for parallel waits.
  [`run-phases.md:46`](../../.claude/skills/psm-validate/references/run-phases.md#L46)
