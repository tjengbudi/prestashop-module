# Interim orchestration (until CAP-1)

Companion of `spec-psm-e2e-cap2-cap6-cell-evidence.md`, approved and frozen with it. It holds the orchestrator flow (SKILL.md, `references/run-phases.md`, `references/headless.md`, `references/adversarial-lens.md`, `references/e2e-quickstart.md`) that the docs task writes for this slice. Every rule here is interim: CAP-1 replaces this file as a whole. Amended by `spec-psm-e2e-cap3-failfast-slots.md` (CAP-3) until CAP-1: Fase 2 step 3 (no `--jobs`), Run outcomes and Infra retry (`not-run`, `no-slots`).

## Session and config

- `<t>` is minted once per run by `ps-plan-layers.py --new-session` (interactive: On Activation; headless: per call, before writing the config copy).
- `<cfg>` = `<psm_reports_dir>/psm-config.json` (resolver absent: the orchestrator writes `{}` there, so script defaults apply); headless: the config copy.
- Any `--tag-map`/`--extra-tag-map` goes identically to every plan call, `ps-run-layer.py` (after `--`) and the aggregate.

## Lapis 4 visual review (interactive, as today)

- Every interactive `ps-run-layer.py --layer e2e` call passes `-- --screenshot-dir <psm_reports_dir>/e2e-shots` (all runs this slice are cold full) and reviews `<stamped run dir>/<ver>/` (its `screenshots:` stderr line) for the versions in `appended`.
- A defect judged blocking is held in session state, never written before the wrap-up, and is read-merged there (as today) right after the Layer 3 read-merge, keeping only defects from runs whose output-line `source_fingerprint` equals the last plan's (interim for `tier-matrix.md` > Visual review; `visual-pending.json` deferred), so a visual write never makes stale Layer 3 output look fresh.
- Direct `ps-e2e-run.py` runs stay only in the quickstart.

## Definitions

- **Run scope** = versions × browsers chosen at On Activation step 2 (headless: all configured cells).
- **Scoped e2e entries** = e2e `rerun_matrix` entries inside the run scope.
- **V's scoped browsers** = the browsers of V's scoped e2e entries, in `psm_e2e_browsers` order.
- **V clean** (interim for contract Plan > Phase 1 `clean`): `per_version[V].rerun` holds only `adversarial`/`e2e` and V's per-version Layer 1/2/5 files hold no blocking finding (judged as today).
  - A Layer 2/5 run of V that reported skipped (Docker absent) this session counts as done.
  - Budi declining to fix V's Layer 1/2/5 blocking findings this session (interim for contract Stop convergence) counts V as clean, and the report lists them as open.
  - Headless: clean once its stale layers ran once.
- **E2E loop ended** (session-wide, interim for contract > E2E loop ended), when any of:
  - an E2E run printed `skipped`;
  - an E2E run exited 2 because a child exited 2 (its output line printed with `e2e_status` `ran`; report its stderr);
  - an E2E run was stopped (exit 143; interactive: unless Budi asks to run it again; headless keeps today's rule: a job it stopped returns `blocked` at once, since the contract's `complete` rule is a deferred Headless bullet);
  - `psm_e2e_enabled` false, or `--require` excludes `e2e`;
  - Budi declines to patch an E2E `fail`, or declines an infra retry (below), or an infra retry again left an infra reason.
- **Pre-spawn exit 2**: an E2E exit 2 before any child is spawned (input error, no output line, e.g. a bad `--cells` or a missing `--session`) does not end the loop. Interactive: fix the input and run again. Headless: return `blocked` with that stderr as `reason`.
- **V's E2E step is due** when the E2E loop has not ended, V has scoped e2e entries, and either no E2E run of V this session printed the plan's current `source_fingerprint` or an infra retry of V is pending.
- **Run outcomes** are read from the next plan call, never from the histories: V's scoped e2e entries with reason `fail` are a failure to patch; with none `fail` but some with reason `inconclusive`, `inconclusive-steps` or `browser-notes`, the run left an infra reason (the cause, e.g. missing image, `browser-unavailable` or `no-slots`, is in its stderr and progress log).
  - (CAP-3) Reason `not-run` is neither a failure nor an infra reason: a cell fail-fast left unstarted. `fail-fast after …` is due again once the source changes (the patch of the `fail`); `input-error after …` once the rejected input is fixed, while a child exit 2 still ends the E2E loop for the session. Fail-fast saves time only for still-queued cells; in-flight children finish and are appended.
  - (CAP-3) `no-slots` (plan reason `inconclusive`) is an infra reason: the daemon-wide slot cap (`psm_e2e_slots`, counted against this run's own N over every running E2E container on the daemon, including a direct `ps-e2e-run.py` run, which counts but bypasses admission) stayed full for the startup timeout. It is fixed by freeing slots or waiting, or by fixing Docker when its `errors` say `docker count failed`, never by an install.
- **Infra retry** (interactive only): after a run that left an infra reason for V, the orchestrator reports the cause and asks Budi to fix the environment (e.g. `--allow-image-pull`, `playwright install`; for `no-slots`: free slots or wait, or fix Docker on `docker count failed`, never an install) or decline. Once he fixed it, an infra retry of V is pending until V's next E2E run (same command, in Fase 1 or the next Fase 2 pass); a decline ends the E2E loop. Headless has no retry: V's step is simply not due and its cells stay unproven.

## Fase 1 (for each in-scope V)

1. Plan `--versions V --per-version --session <t> --config <cfg>`.
2. Run the layers in `per_version[V].rerun` other than `adversarial` and `e2e`.
3. Once V is clean and its E2E step is due, run `ps-run-layer.py --layer e2e --cells V:<V's scoped browsers joined by +> --session <t> --config <cfg>`.
4. Patch blocking findings or an E2E `fail` and repeat as today.

V's loop ends when V is clean, its E2E step is not due, and (interactive, unless the E2E loop ended) the latest plan shows no scoped e2e entry of V with reason `fail`.

## Fase 2

1. One plan call over the in-scope versions with `--per-version --session <t> --config <cfg>`. Any version not clean re-enters its Fase 1 loop first (interim Phase 2 entry check: a patch stales other versions' Layer 1/2/5 files).
2. Layer 3 as today, spawned unless a canonical plan call (the same flags without `--per-version`) shows `layers.adversarial.reuse` true (per-version mode always lists `adversarial`) or lenses spawned under the same plan `source_fingerprint` are still unmerged; judged again each time Fase 2 restarts. Unmerged lens results spawned under another `source_fingerprint` are discarded, never merged (`tier-matrix.md` > Rules).
3. Group the scoped e2e entries of versions whose E2E step is due into one `ps-run-layer.py --layer e2e --cells <ver>:<b>[+<b>],… --session <t> --config <cfg>` call (no `--jobs` and no `--slots`: concurrency is the daemon-wide `psm_e2e_slots` read from `--config`, `--slots` being a manual override only; for a smaller footprint, one version per `--cells` call or a lower `psm_e2e_slots`; no call when none).
4. An appended `fail` re-enters Fase 1 for that version (interactive; its first iteration starts with the patch or Budi's decline), then Fase 2 restarts from its plan call. Headless reports it.

## Wrap-up

Once a Fase 2 pass has no due E2E step and no re-entry, the wrap-up runs once, without any `all_reuse` gate, in contract order (Plan > Phase 2):

1. The Layer 3 read-merge (when spawned; only results spawned under the last plan's `source_fingerprint`).
2. The held Lapis 4 visual defects.
3. Today's `--merge-only` for Layers 2 and 5.
4. `--merge-only --layer e2e` (report view).
5. The cross-version Layer 1 scan to `<module>-static.json` (as today).
6. `ps-aggregate.py --reports-dir … --module … --config <cfg>`.

The report names every configured cell without passing gate-grade evidence as not proven.

## Quickstart TDD verdict

`ps-plan-layers.py --new-session`, `ps-run-layer.py --layer e2e --cells 9.1:chromium --session <t> --config <cfg>`, then `ps-aggregate.py --reports-dir <psm_reports_dir> --module <module-path> --config <cfg>` (static from `<module>-static.json` or `--static`; no `--versions`, `--tier`, `--e2e`). The verdict is `e2e_cells['9.1']['chromium']` (`state`, `gate_grade`, `reason`, `findings`); `ready=false` is expected while other cells are unproven.
