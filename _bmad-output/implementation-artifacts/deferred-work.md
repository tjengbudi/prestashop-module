- source_spec: `_bmad-output/implementation-artifacts/spec-psm-validate-docker-cleanup-own-run.md`
  summary: Force-killed compose runs leave `/tmp/psm-fl-*` mkdtemp directories that no cleanup path reclaims.
  evidence: `ps-flashlight-run.py` creates the dir at bring-up and removes it only on the normal teardown path; `--cleanup-orphans` covers containers and networks only. Pre-existing leak, not introduced by this change; small files under OS tmp reaping. Naming the dir with the owner PID would make it reclaimable by the same ownership rule.
- source_spec: `_bmad-output/implementation-artifacts/spec-psm-validate-docker-cleanup-own-run.md`
  summary: `_teardown()`'s manual (non-compose) path removes containers without `-v`, leaking anonymous DB volumes.
  evidence: The compose path uses `down -v` and the new orphan cleaner now uses `rm -f -v`, but `_teardown()`'s manual branch still uses plain `docker rm -f`. Left alone deliberately — this spec froze `_teardown()` semantics as unchanged. Each force-killed manual run strands a multi-hundred-MB anonymous volume.
