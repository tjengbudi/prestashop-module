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
