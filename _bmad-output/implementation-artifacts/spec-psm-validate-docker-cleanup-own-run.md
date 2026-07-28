---
title: 'psm-validate: Docker cleanup scoped to the owning run (close arch-9)'
type: 'bugfix'
created: '2026-07-28'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '7fa98ce'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** The orphan-cleanup command in `SKILL.md:35` and `references/e2e-quickstart.md:176-177` selects by name prefix (`docker ps -aq --filter name=psm-fl | xargs -r docker rm -f`), matching **every** psm-validate run on the host. Running it while another session's Layer 2/4 run is in flight force-kills that session — today mitigated only by a prose caveat ("make sure no other run is running"), the open finding arch-9.

**Approach:** Stamp every container and network with run-ownership labels (run id, owner PID, owner host) on both orchestrators, and replace the sweep with a `--cleanup-orphans` mode that removes only artifacts whose owning process is provably dead on this host. Anything it cannot prove dead is left untouched and reported with a reason.

## Boundaries & Constraints

**Always:**
- Both orchestrators (compose and manual) carry an identical label set substituted from single constants in `ps-flashlight-run.py` — never retyped literals. `ps-e2e-run.py` inherits this via its existing sibling import and must not grow its own copy.
- Cleanup defaults to **skip**: any uncertainty (label absent, PID unparsable, foreign host, docker error) is skip-and-report. Under-cleaning is the correct failure direction; killing a live run is not.
- `_teardown()` keeps current semantics — own session only, still the normal path.
- The doc-gate test is rewritten deliberately to lock the new contract and go red if a name-prefix removal sweep reappears in either document.
- The cleanup instruction stays byte-identical across both documents, as the existing gate enforces.

**Ask First:** Any design letting cleanup remove artifacts it cannot prove are dead — including an `--all-sessions` escape hatch or an age/uptime heuristic. Both were considered and rejected during clarification.

**Never:** Selecting containers by name prefix for removal. Touching anything outside psm-validate's own labels. Changing Layer 2/4 verdict semantics or the run's output JSON schema. Adding a background sweeper or interrupt-time teardown handler.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| Normal run ends | Own session finishes or errors | `_teardown()` removes its own artifacts as today; labels never consulted | N/A |
| Orphan from killed run | Labeled, dead PID, this host | Removed; listed under `removed` | Per-item docker failure recorded, exit stays 0 |
| Another session live | Labeled, live PID | Left running; `skipped`, reason `owner-alive` | N/A |
| Foreign host label | `psm.owner-host` ≠ this host | `skipped`, reason `foreign-host` (liveness unknowable) | N/A |
| Legacy unlabeled artifact | Name matches `psm-fl`, no labels | `skipped`, reason `no-owner-label`, plus the exact per-name removal command | N/A |
| Docker unavailable | `docker info` fails | `status: skipped`, honest reason, exit 0 (same degrade contract as main path) | N/A |

</frozen-after-approval>

## Code Map

- `.claude/skills/psm-validate/scripts/ps-flashlight-run.py` -- owns orchestration: `CONTAINER_PREFIX`, `_compose_file_text`, `_bring_up_compose`, `_bring_up_manual`, `_teardown`, `main()`. All new code lands here.
- `.claude/skills/psm-validate/scripts/ps-e2e-run.py:894-912,1008` -- Layer 4 reuses `fl._bring_up_*` / `fl._teardown` with a published port; inherits labels for free. Verify, do not duplicate.
- `.claude/skills/psm-validate/scripts/tests/test-ps-flashlight-run.py:184-284` -- existing doc-gate locking the sweep prose to `CONTAINER_PREFIX`; the gate to rewrite.
- `.claude/skills/psm-validate/SKILL.md:35` -- cleanup prose copy 1. Near its token budget; the replacement should be shorter than what it removes.
- `.claude/skills/psm-validate/references/e2e-quickstart.md:176-177` -- copy 2, must stay identical to copy 1.
- `.claude/skills/psm-validate/.memlog.md` -- project convention: append one round entry.

## Tasks & Acceptance

**Execution:**
- [x] `scripts/ps-flashlight-run.py` -- add ownership constants (label keys, this process's run id/PID/host) and stamp them onto compose services, the compose network, and the manual `docker run` / `docker network create` -- one source of truth so both orchestrators answer "who owns this" identically.
- [x] `scripts/ps-flashlight-run.py` -- add `cleanup_orphans()` and a `--cleanup-orphans` CLI mode (module path optional in that mode only) emitting a JSON report of `removed` / `skipped` with per-item reasons, exit 0 -- the safe replacement for the sweep.
- [x] `scripts/tests/test-ps-flashlight-run.py` -- extend: labels derived from constants on both orchestrators; the full I/O decision table against a monkeypatched docker inventory and PID-liveness probe; rewritten doc-gate requiring the new command in both docs and failing if a prefix removal sweep returns -- mutation-test the new gate rather than trusting it.
- [x] `SKILL.md` + `references/e2e-quickstart.md` -- replace the sweep with the `--cleanup-orphans` invocation and drop the now-unnecessary "no other run is running" caveat -- keep both copies identical.
- [x] `.memlog.md` -- append a round entry closing arch-9 and recording the rejected alternatives.

**Acceptance Criteria:**
- Given another session's flashlight container is running, when `--cleanup-orphans` executes, then it is still running afterwards and appears under `skipped` with reason `owner-alive`.
- Given a run killed with SIGKILL left labeled artifacts, when `--cleanup-orphans` executes, then exactly that run's container and network are removed and the command exits 0.
- Given the label key constants are renamed in code without updating the documents, when the suite runs, then the doc-gate goes red.
- Given either document reintroduces a `--filter name=psm-fl` removal sweep, when the suite runs, then the doc-gate goes red.
- Given a normal Layer 2 and Layer 4 run, when it completes, then the emitted JSON schema and teardown behavior are unchanged.

## Spec Change Log

- **Review round 1 (Blind Hunter + Edge Case Hunter, 2026-07-28).** Both reviewers independently
  attacked the same three leaf predicates the verdict rests on. Triage: 0 intent_gap, 0 bad_spec
  (the architecture — labels + decision table + report — was validated by both; every finding hit a
  leaf predicate, so re-deriving 300 verified lines would have reproduced the same shape), 15 patch,
  2 defer, 1 reject.
  - **Amended (design):** hostname was treated as proof of a shared PID namespace. It is not — two
    WSL2 distros share the Windows hostname and one Docker daemon but have separate PID namespaces,
    so a live sibling run's PID is invisible and would have been judged `owner-dead` and killed:
    the exact failure this spec exists to close, through another door. Ownership now also carries
    `psm.owner-boot` (kernel boot-id) and `psm.owner-ns` (PID-namespace inode). Different namespace
    → `foreign-pid-ns`, skip. Different boot → `owner-boot-gone`, remove (the owner cannot be alive,
    and its PID may since have been reused — which also reclaims orphans that PID reuse would
    otherwise strand forever).
  - **Amended (robustness):** `isdigit()`→`isdecimal()` plus a `pid > 0` guard (`int("²")` raised
    ValueError, `os.kill(0,0)` always succeeds); `OverflowError` added to the liveness guard; a
    per-artifact try/except so one malformed record cannot abort a sweep mid-flight; labels read
    per-key via `{{.Label "k"}}` instead of parsing comma-joined `{{.Labels}}`; strict prefix filter
    (docker's `name=` is a substring match); `docker rm -f -v`; `already-gone` for the teardown race;
    `status: partial` when errors occurred; `manual_command` for every non-removable reason except
    `owner-alive`; `--cleanup-orphans` made exclusive of `module_path` and `-o`; `--cleanup-orphans`
    added to `ps-run-layer`'s reserved-passthrough gate.
  - **Known-bad state avoided:** a cleanup that proves ownership by PID alone, which is only an
    identity within one boot and one PID namespace.
  - **KEEP:** default-deny decision table with one removing verdict and named reasons for every
    refusal; the positive control that the prose ban is non-vacuous; `owner-alive` never being handed
    a kill command; exit 0 for artifacts that merely could not be proven dead.
  - **Rejected:** non-zero exit when `errors` is non-empty — the frozen I/O matrix approves exit 0;
    machine consumers get `status: partial` instead.

## Design Notes

PID liveness is the ownership probe because it fails safe: an uncertain probe makes cleanup skip an
artifact it could have removed (harmless leftover), never remove one belonging to a live run. But a
PID is only an identity *within one boot and one PID namespace* — hostname alone does not establish
either, so boot-id and namespace are labelled and checked before the PID is trusted at all.

```
labels on every artifact:
  psm.run=<uuid>  psm.owner-pid=<pid>  psm.owner-host=<hostname>
  psm.owner-boot=<kernel boot-id>  psm.owner-ns=<pid-namespace inode>
  (the last two only where the platform can produce them; the completeness
   check demands exactly what this platform writes, never more)

cleanup decision — one removing verdict, every refusal named:
  no psm.run label              -> skip (not ours to judge)
  host != this host             -> skip (foreign-host)
  boot label missing            -> skip (incomplete-owner-labels)
  boot != this boot             -> REMOVE (owner-boot-gone: its whole boot is gone)
  ns label missing              -> skip (incomplete-owner-labels)
  ns != this namespace          -> skip (foreign-pid-ns: PID unreadable from here)
  pid not decimal, or <= 0      -> skip (bad-owner-pid)
  PID alive (or probe uncertain) -> skip (owner-alive)
  otherwise                     -> REMOVE (owner-dead)
```

## Verification

**Commands:**
- `uv run .claude/skills/psm-validate/scripts/tests/test-ps-flashlight-run.py` -- expected: all checks pass, rewritten doc-gate included
- `uv run .claude/skills/psm-validate/scripts/tests/test-ps-e2e-run.py` -- expected: all checks pass (Layer 4 inherits labels, no regression)
- `python3 .claude/skills/bmad-workflow-builder/scripts/scan-scripts.py .claude/skills/psm-validate` -- expected: 0 findings
- Real-Docker check: one labeled container with a dead owner PID, one with a live PID; run `--cleanup-orphans` -- expected: only the dead-owner one is removed

**Manual checks (if no CLI):**
- Confirm `SKILL.md` did not grow past its token budget after the prose swap.

## Suggested Review Order

**The ownership rule (start here)**

- One decision function, one removing verdict, every refusal named — the whole safety property.
  [`ps-flashlight-run.py:553`](../../.claude/skills/psm-validate/scripts/ps-flashlight-run.py#L553)

- Why hostname alone is not identity: boot-id and PID-namespace are labelled too.
  [`ps-flashlight-run.py:364`](../../.claude/skills/psm-validate/scripts/ps-flashlight-run.py#L364)

- Uncertainty reads as "alive" — including OverflowError, which is not an OSError.
  [`ps-flashlight-run.py:534`](../../.claude/skills/psm-validate/scripts/ps-flashlight-run.py#L534)

**Stamping both orchestrators**

- Single source of ownership labels; compose and manual both substitute from it.
  [`ps-flashlight-run.py:402`](../../.claude/skills/psm-validate/scripts/ps-flashlight-run.py#L402)

- Compose network is labelled too — a killed run leaves it, and unlabelled means unreclaimable.
  [`ps-flashlight-run.py:351`](../../.claude/skills/psm-validate/scripts/ps-flashlight-run.py#L351)

**Sweeping safely**

- Labels read per-key; comma-joined `{{.Labels}}` would let ownership be forged.
  [`ps-flashlight-run.py:596`](../../.claude/skills/psm-validate/scripts/ps-flashlight-run.py#L596)

- One malformed record cannot abort the sweep; `status: partial` when anything errored.
  [`ps-flashlight-run.py:661`](../../.claude/skills/psm-validate/scripts/ps-flashlight-run.py#L661)

- `rm -f -v` mirrors `compose down -v`, so anonymous DB volumes are reclaimed.
  [`ps-flashlight-run.py:637`](../../.claude/skills/psm-validate/scripts/ps-flashlight-run.py#L637)

**Blast-radius guards**

- Mode is exclusive: with `-o` it would overwrite layer evidence and fake a "no Docker" verdict.
  [`ps-flashlight-run.py:827`](../../.claude/skills/psm-validate/scripts/ps-flashlight-run.py#L827)

- Passthrough gate: otherwise every child runs destructive cleanup instead of validating.
  [`ps-run-layer.py:69`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L69)

**Gates and tests**

- Prose ban now catches both writing directions, whitespace-normalised, across collected docs.
  [`test-ps-flashlight-run.py:279`](../../.claude/skills/psm-validate/scripts/tests/test-ps-flashlight-run.py#L279)

- Full decision table, including the WSL2 cross-namespace case that would kill a live run.
  [`test-ps-flashlight-run.py:344`](../../.claude/skills/psm-validate/scripts/tests/test-ps-flashlight-run.py#L344)

- Listing tested by behaviour of the built command, not by counting source text.
  [`test-ps-flashlight-run.py:473`](../../.claude/skills/psm-validate/scripts/tests/test-ps-flashlight-run.py#L473)

- Closes a proven-vacuous spot: the race branch was only ever exercised through a stub.
  [`test-ps-flashlight-run.py:513`](../../.claude/skills/psm-validate/scripts/tests/test-ps-flashlight-run.py#L513)

**Operator-facing prose**

- The command operators actually run; the "make sure no other run is running" caveat is gone.
  [`SKILL.md:35`](../../.claude/skills/psm-validate/SKILL.md#L35)

- Second copy, kept identical by the doc gate.
  [`e2e-quickstart.md:176`](../../.claude/skills/psm-validate/references/e2e-quickstart.md#L176)
