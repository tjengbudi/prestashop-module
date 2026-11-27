- source_spec: `_bmad-output/implementation-artifacts/spec-psm-validate-docker-cleanup-own-run.md`
  summary: Force-killed compose runs leave `/tmp/psm-fl-*` mkdtemp directories that no cleanup path reclaims.
  evidence: `ps-flashlight-run.py` creates the dir at bring-up and removes it only on the normal teardown path; `--cleanup-orphans` covers containers and networks only. Pre-existing leak, not introduced by this change; small files under OS tmp reaping. Naming the dir with the owner PID would make it reclaimable by the same ownership rule.
- source_spec: `_bmad-output/implementation-artifacts/spec-psm-validate-docker-cleanup-own-run.md`
  summary: `_teardown()`'s manual (non-compose) path removes containers without `-v`, leaking anonymous DB volumes.
  evidence: The compose path uses `down -v` and the new orphan cleaner now uses `rm -f -v`, but `_teardown()`'s manual branch still uses plain `docker rm -f`. Left alone deliberately — this spec froze `_teardown()` semantics as unchanged. Each force-killed manual run strands a multi-hundred-MB anonymous volume.
- source_spec: `_bmad-output/implementation-artifacts/spec-psm-e2e-cap2-cap6-cell-evidence.md`
  summary: ps-run-layer cannot tell `uv run`'s own exit 2 (resolve/cache/permission failure) from ps-e2e-run's input-error exit 2, so an infra hiccup can end the E2E loop for the session.
  evidence: children start as `uv run ps-e2e-run.py` (PEP 723 dep playwright); uv exits 2 on its own failures; the runner treats any rc 2 as child-originated input error (spec Runner interim). Fix needs a child sentinel (e.g. a marker in its -o file) or a distinct exit code — a contract change.
- source_spec: `_bmad-output/implementation-artifacts/spec-psm-e2e-cap2-cap6-cell-evidence.md`
  summary: On `--stop-job`, ps-run-layer's worker threads still block in `subprocess.run`; a child still in uv env sync is not yet registered and can survive as an orphan.
  evidence: pre-existing ThreadPoolExecutor + subprocess.run pattern (kept in history mode); stop relies on the job registry, which a child joins only after uv finishes resolving. Popen handles + process-group SIGTERM would close it.
- source_spec: `_bmad-output/implementation-artifacts/spec-psm-e2e-cap2-cap6-cell-evidence.md`
  summary: Per-cell E2E histories are append-only and never compacted, so plan/aggregate parse cost grows across sessions.
  evidence: `read_history` reads every line under LOCK_SH on each plan and aggregate call; the contract forbids rewriting lines, so compaction needs a contract-level rotation rule.
- source_spec: `_bmad-output/implementation-artifacts/spec-psm-e2e-cap2-cap6-cell-evidence.md`
  summary: Plan, ps-run-layer and ps-aggregate silently fall back to the script-default configured cells when `--config` is omitted, which can narrow the required set without an error.
  evidence: `configured_cells(None)` returns DEFAULT_TARGET_VERSIONS × DEFAULT_E2E_BROWSERS; a project with extra target versions that forgets `--config` on the aggregate gets `ready` over fewer versions. Contract sanctions the defaults; a warning or exit 2 when `<reports>/psm-config.json` exists would guard it.

- source_spec: none
  summary: Implement CAP-1 of SPEC-psm-e2e-tiered-gate (tiered E2E plan — canary tier 0, release gate tier 1, loop-back steps, focus cell, phase1_reuse/clean, run scope, psm_e2e_canary, runner --tier, aggregate reached, headless stop-at-first-unclean-step, orchestration docs).
  evidence: Split from the combined CAP-1 + CAP-3 request on 2026-11-26 (multi-goal check); Budi chose CAP-3 first so CAP-1's orchestration docs can use --slots directly.

- source_spec: `_bmad-output/implementation-artifacts/spec-psm-e2e-cap3-failfast-slots.md`
  summary: Orphan cleanup runs once per E2E run (inside wait-slots before the first count); containers that leak later in the run are only reaped by the next run.
  evidence: Medium/low review finding (r2 edge-case-2); fixing it needs a change to cell-contract.md > Config keys > psm_e2e_slots.

- source_spec: `_bmad-output/implementation-artifacts/spec-psm-e2e-cap3-failfast-slots.md`
  summary: Slot claims of a ps-run-layer that dies while its child is still booting stop counting until the child's container runs, so another run can briefly exceed the cap.
  evidence: Medium/low review finding (r2 edge-case-9); the contract counts slot_claims only for live ps-run-layer registry entries.

- source_spec: `_bmad-output/implementation-artifacts/spec-psm-e2e-cap3-failfast-slots.md`
  summary: Slot admission has no cross-run FIFO, so one run can repeatedly lose the race for freed slots (starvation).
  evidence: Medium/low review finding (r3 adversarial-1); adding fairness is a contract change and scope expansion.

- source_spec: `_bmad-output/implementation-artifacts/spec-psm-e2e-cap3-failfast-slots.md`
  summary: A child-emitted `not-run` cell's wall_clock spans the whole version run, because started_at is the admission time per Evidence record > Fields.
  evidence: Medium/low review finding (r5 adversarial-3); changing it is a contract change.

- source_spec: `_bmad-output/implementation-artifacts/spec-psm-e2e-cap3-failfast-slots.md`
  summary: Slot admission holds `slots.lock` (blocking flock, no timeout) across the daemon `docker ps` count (up to 120 s), so a slow daemon serialises every session's admission and claim release.
  evidence: Code review 2026-11-26 (Edge Case Hunter + Blind Hunter); the contract mandates count-then-claim under the lock, so moving the count out or adding a lock timeout is a contract change.

- source_spec: `_bmad-output/implementation-artifacts/spec-psm-e2e-cap3-failfast-slots.md`
  summary: `daemon_slot_usage` counts only running containers; a direct `ps-e2e-run.py` compose boot (no claim) whose `ps` container sits in `created` while waiting for DB health is not counted, so ps-run-layer can over-admit briefly.
  evidence: Code review 2026-11-26 (Blind Hunter); contract wording is "every running container", so counting created/restarting states needs a contract amendment.

- source_spec: `_bmad-output/implementation-artifacts/spec-psm-e2e-cap3-failfast-slots.md`
  summary: When ps-run-layer itself raises while children run, `shutdown(wait=False)` leaves the children running unsupervised and the temp dir holding their `-o` outputs is removed.
  evidence: Code review 2026-11-26 (Edge Case Hunter); same pattern as the pre-CAP-3 runner (run_children + rmtree in finally), not introduced by this change.

- source_spec: `_bmad-output/implementation-artifacts/spec-psm-e2e-cap1-tiered-gate.md`
  summary: Produce `stopped` records in ps-run-layer (cell-contract.md > Evidence record > Storage) for admitted cells of a SIGTERM'd child and of children in flight when the run is stopped.
  evidence: Deferred from CAP-1 on Budi's request (2026-11-27) while slimming the spec; review rounds showed it needs its own SIGTERM handler with critical sections (reap vs stop races). Readers (plan blocked-infra, aggregate reached) already handle `stopped` records; until then a stopped job's cells keep their earlier records, never a pass.

- source_spec: `_bmad-output/implementation-artifacts/spec-psm-e2e-cap1-tiered-gate.md`
  summary: Produce the SPEC success-signal bankwire timing report (before/after tiered gate), with commit `c460e10` as the "before" baseline.
  evidence: CAP-1 keeps the timing report out of scope (Never list); review-loop round 5 noted it had no deferred-work entry or baseline.

- source_spec: `_bmad-output/implementation-artifacts/spec-psm-e2e-cap1-tiered-gate.md`
  summary: Decide in cell-contract.md whether a corrupt-tail cell whose last record is a smoke-only pass should stay `not-gradeable` (literal contract) or be rerun so the tail gets repaired.
  evidence: Review-loop round 5 found the literal not-gradeable rule leaves such a tail unrepaired forever; changing it is a contract rule change (Ask First), so CAP-1 keeps the literal reading.

- source_spec: `_bmad-output/implementation-artifacts/spec-psm-e2e-cap1-tiered-gate.md`
  summary: Pin one meaning of "newest record" in the plan predicates (append order vs `started_at`) and test histories where the two disagree.
  evidence: CAP-1 step-04 review — `_focus_cell` picks each cell's failing record by append order (`_newest`, inherited from CAP-2/6) but ranks cells by `started_at`; with daemon-wide slots (CAP-3) concurrent jobs for one cell can append out of `started_at` order, so the focus cell could point at an older run.

- source_spec: `_bmad-output/implementation-artifacts/spec-psm-e2e-cap7-parallel-browsers.md`
  summary: Decide in cell-contract.md whether a parallel finding may move to non-blocking `parallel_only` when the `rerun-seq` pass left that same step inconclusive (failed BO login, aborted scenario) instead of running it conclusively.
  evidence: CAP-7 step-04 review — per the contract the rerun is judged like a cold single-engine run, so a BO finding demoted by a rerun whose BO login failed leaves the cell `pass` (BO steps only in `inconclusive`); this matches today's single-engine semantics but lets a real defect pass when the rerun's login flakes.

- source_spec: `_bmad-output/implementation-artifacts/spec-psm-e2e-cap7-parallel-browsers.md`
  summary: Decide whether engines that hit `launch_error`/`crash` in the parallel pass (or whose `rerun-seq` cannot launch) should get a sequential retry in the same run and/or force cost-1 sequential admission next run, like `parallel-unconfirmed`.
  evidence: CAP-7 step-04 review — launch failures caused by two browsers starting at once (RAM) are never retried sequentially and `_unconfirmed_versions` reacts only to `parallel-unconfirmed`, so such a cell can stay inconclusive run after run.

- source_spec: `_bmad-output/implementation-artifacts/spec-psm-e2e-cap7-parallel-browsers.md`
  summary: Make `reset-files` restore the module directory as it was at snapshot time (e.g. tar it in `snapshot-db`) instead of copying fresh source from `/ps-module-src`.
  evidence: CAP-7 step-04 review — files a module's install() writes inside its own directory are lost by the reset while the DB still says installed, so confirmation and sequential-fallback passes can see a state no cold boot produces (bankwire is unaffected).

- source_spec: `_bmad-output/implementation-artifacts/spec-psm-e2e-cap7-parallel-browsers.md`
  summary: Make the shared reset routine fail on a post-reset 5xx that the first boot did not have, and retry the single health check briefly, so a reset-broken shop maps to `parallel-unconfirmed`/`sequential-reset` instead of confirmed findings.
  evidence: CAP-7 step-04 review — the contract keeps 5xx best-effort and health checked once; a reset that breaks the shop would turn into a blocking `fail` blamed on the module, and a transient `unknown` health forces an unneeded sequential next run.

- source_spec: `_bmad-output/implementation-artifacts/spec-psm-e2e-cap7-parallel-browsers.md`
  summary: Harden lockstep setup/teardown against filesystem errors — `mkdtemp`/mkdir OSError in `run_parallel_workers` and swallowed marker writes on a full /tmp that leave `barrier_wait` (no deadline) waiting forever.
  evidence: CAP-7 step-04 review — both paths are unhandled; unlikely on a healthy host but they crash the version or hang until `--stop-job`.
