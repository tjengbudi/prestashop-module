# Brownfield notes — psm-validate E2E (as of 2026-11-25)

Paths relative to `.claude/skills/psm-validate/scripts/`.

- `ps-e2e-run.py` `run_one_version`: one cold PS+DB boot per version (`bring-up` → `wait-healthy` ≤180 s → `install` → `wait-http` → `warmup-bo`), then `for engine in browsers` runs engines **sequentially** against that container; teardown is in `finally`. `main` loops versions sequentially in-process.
- `DEFAULT_BROWSERS = "chromium,firefox"` (`ps-e2e-run.py:86`); `SUPPORTED_ENGINES` also has `webkit`, and `parse_browsers` silently drops unknown names and falls back to the default (the shared normalizer in `cell-contract.md` makes that exit 2). Browsers share one DB per version; the `{browser}` placeholder is the only isolation mechanism for scenario data.
- `ps-run-layer.py`: `--jobs` (default 3) boots versions concurrently; `--per-version` writes `<module>-e2e-<ver>.json`; `--merge-only` builds canonical file. One Job ID per invocation.
- `ps-plan-layers.py:189` `prov_for`: e2e provenance = expected image tag per version only. **Browser set and scenario completeness are not part of freshness** — gap closed by CAP-2.
- `ps-aggregate.py:922-923`: records `e2e_browsers` (requested) vs `e2e_browsers_run` (from `browsers_available`, the binary probe, not the engines that actually drove; a launch failure still counts as available) but freshness of each browser is not checked. After a merge both fields are unions across versions, so they cannot show per-version narrowing. They are not per-cell truth: CAP-2 uses the per-cell record in `cell-contract.md`.
- No flag exists for scenario subset, fail-fast, warm/keep-alive container, or phase durations. Progress log (`*.progress.log`) has `START`/`END` phase tokens with timestamps — a source for CAP-6.
- Phase 1 (per-version convergence) and Phase 2 (release gate) already exist in `SKILL.md` / `references/run-phases.md`; tiering refines them rather than replacing them.
- Evidence: bankwire run on 2026-09-08 → 2026-09-09 produced six aggregate reports across ~18 h; e2e per-version files and the last aggregate show Chromium-only coverage (`e2e_browsers: ['chromium']`, narrowed on request); aggregate records the narrowing but nothing re-requires Firefox later.
