# Analysis Report: psm-setup

Generated: 2026-07-09 · Schema: 2

**Grade: Excellent**

> Holds at excellent — architecture, determinism, and customization all pass clean; the remaining findings are one worthwhile headless-return add and four low-severity journey-polish nits, no regressions from the fix pass.

psm-setup stays tight and outcome-shaped: deterministic work is fully scripted, module identity is derived, and the earlier fixes integrated cleanly. The one finding worth acting on is a machine-readable result for the headless automator; the rest are optional low-severity polish (doubled prose, an update-path soft-gate, and two end-of-flow handoff nits).

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 0 |
| Medium | 1 |
| Low | 4 |

## Themes

### 1. Headless machine-readable return

- Root cause: The skill accepts headless invocation and the underlying scripts emit JSON, but the skill's own final message is human prose, leaving an automator without a single parseable success/failure signal to gate the next step on.
- Fix: In Confirm, when invoked headless/with args, surface a compact structured result (install_state, user_keys, legacy_configs_deleted, output_dirs_created) alongside or instead of the prose greeting.
- Findings:
  - `enhancement-1` No machine-readable return for the headless automator — `SKILL.md:Confirm / Outcome`

### 2. End-of-flow polish (optional lows)

- Root cause: A cluster of low-severity nits at the interaction edges: user-key routing stated twice, no explicit keep-all exit on the update path, two overlapping psm-agent-expert handoffs at the end, and the Docker check landing late without being framed as forward-looking. None change behavior.
- Fix: Trim-if-touched: let the planner target own user-key routing; add a one-line keep-all soft-gate on the no-args update path; unify the two psm-agent-expert handoffs into one next action; frame the Docker check as a forward-looking dependency for later workflows.
- Findings:
  - `leanness-1` User-key routing asserted in prose while the planner resolves it authoritatively — `SKILL.md:Overview (12-13) vs Collect Configuration (target)`
  - `enhancement-2` No keep-all soft-gate on the update path — `SKILL.md:Collect Configuration (update state)`
  - `agent-cohesion-1` Two overlapping handoffs to psm-agent-expert at end of setup — `SKILL.md:Seed Knowledge Base step + Confirm (module_greeting)`
  - `agent-cohesion-2` Docker prerequisite checked at end, python3 at start — `SKILL.md:On Activation vs Seed KB & External Deps`

## Strengths

- Deterministic work fully scripted across four Python scripts, each with a matching test (26 tests pass); plan-setup.py imports merge-config.py so priority-merge logic has a single source of truth.
- Read-avoidance: state and defaults are read from planner JSON, not by inspecting config files.
- Anti-zombie merge makes writes idempotent, and the skill tells the user setup is safe to re-run after a partial failure; the temp answers file is mktemp'd, overwritten, and deleted.
- Facilitative collection: all defaults at once, single reply, no 'press enter', split language offered when implied.
- Module identity derived (module_code from planner, {module_code} placeholders) rather than hardcoded; the only literal psm strings live in the explicitly psm-specific section.
- Full preflight gating: python3 and planner-failure both stop before prompting.

## Recommendations

1. Add a compact structured result to Confirm on headless/arg invocation so an automator can verify success programmatically. (resolves: enhancement-1)
2. Optional low-severity polish on next edit: single-source the user-key routing, add a keep-all soft-gate on the no-args update path, unify the psm-agent-expert handoff, and frame the Docker check as forward-looking. (resolves: leanness-1, enhancement-2, agent-cohesion-1, agent-cohesion-2)

## Agent Profile

- Name: psm-setup
- Title: PrestaShop Module Builder installer
- Type: stateless
- Mission: Install and configure the psm BMad module into a project: plan the install, collect preferences, merge config, create output dirs, migrate legacy installs, clean up installer packages.

## Capabilities

- **plan-setup.py** (script) — Read-only pre-pass: classifies install_state, resolves effective core/module defaults (legacy over builtin), derives module_code.
- **Collect Configuration** (prompt) — Facilitative one-shot wizard over the planner's defaults; single-vs-split language judgment.
- **merge-config.py** (script) — Anti-zombie config merge, legacy fallback defaults, and --project-root output-dir creation.
- **merge-help-csv.py** (script) — Registers module capabilities into module-help.csv, deleting the legacy CSV after merge.
- **cleanup-legacy.py** (script) — Removes installer package dirs after verifying each skill is already installed under .claude/skills/.
- **Seed KB & deps hand-off** (prompt) — Defers knowledge-base seeding to psm-agent-expert and checks the Docker dependency.

## Per-Lens Verdicts

- **leanness**: Lean and goal-shaped; one minor fact (user-key routing) stated both in Overview and via the planner target.
- **architecture**: Sound stateless installer: clean topology, dependency-honest ordering, explicit merge-script batching, read-avoidance enforced.
- **determinism**: Passes. All deterministic work is delegated to scripts; remaining prose is genuine judgment and JSON-driven reporting.
- **customization**: About right: module.yaml variable defs + config.yaml are the correct surface; identity flows from plan-setup.py, never hardcoded in the generic flow.
- **enhancement**: Lean and well-gated; one headless machine-readable-return gap and one marginal update-path soft-gate worth adding.
- **agent-cohesion**: Coherent installer lifecycle with clear entry and exit; two low end-of-flow handoff/placement nits.
- **path-standards**: Clean (the lone scanner hit is the builder's own .memlog.md, not skill content).

## Experience

- **Fresh install** — python3 preflight → plan-setup classifies fresh → collect config → merge + mkdir output dirs → cleanup installer packages → seed handoff → confirm → greet
- **Legacy migration / update** — plan-setup returns update/legacy_migration with legacy values as defaults → merge → legacy files/dirs removed → confirm migration
- **Headless** — args/inline values map to keys → planner defaults fill the rest → skip prompting → still show full confirmation summary
- Headless: Accepts args/inline values and skips prompting, but the final confirmation is human prose — an automator has no single parseable success signal to gate on (see enhancement-1).

## Findings

### Medium (1)

#### enhancement-1 — No machine-readable return for the headless automator

- Lens: enhancement
- Location: `SKILL.md:Confirm / Outcome`
- Evidence: The skill accepts --headless with inline values and says 'Still display the full confirmation summary at the end,' but that summary is human prose. The merge/cleanup scripts emit JSON to stdout, yet the skill's final message gives an automator no single parseable success/failure signal (install_state, files written, legacy_configs_deleted, output_dirs_created) to gate the next automation step on.
- Recommendation: In Confirm, when invoked headless/with args, surface a compact structured result (or echo the aggregated script JSON fields) alongside or instead of the prose greeting, so success can be verified programmatically.

### Low (4)

#### enhancement-2 — No keep-all soft-gate on the update path

- Lens: enhancement
- Location: `SKILL.md:Collect Configuration (update state)`
- Evidence: A user who re-invokes psm-setup on an already-configured project (install_state update, no args) is presented all defaults and invited to 'respond once with only the values you want to change,' but never offered an explicit 'nothing to change' exit — the wrong-intent user is nudged into a full reconfigure prompt.
- Recommendation: When install_state is update and no args were supplied, add one clause offering 'tell me only what to change, or say nothing to keep everything.' The run stays safe either way via the anti-zombie merge.

#### agent-cohesion-1 — Two overlapping handoffs to psm-agent-expert at end of setup

- Lens: agent-cohesion
- Location: `SKILL.md:Seed Knowledge Base step + Confirm (module_greeting)`
- Evidence: The Seed KB step tells the user to run psm-agent-expert 'once to populate the knowledge base'; the module_greeting shown at Confirm tells the user to call psm-agent-expert 'to consult.' Two distinct reasons to invoke the same skill land back-to-back at the end without one message reconciling them.
- Recommendation: In the Confirm/Outcome handoff, unify the guidance: running psm-agent-expert once both seeds the KB and starts consultation — one clear next action.

#### agent-cohesion-2 — Docker prerequisite checked at end, python3 at start

- Lens: agent-cohesion
- Location: `SKILL.md:On Activation vs Seed KB & External Deps`
- Evidence: python3 is verified in On Activation before any prompting, but the Docker check is deferred to the near-final section. A user completes the full collect/write/cleanup journey before learning Docker (needed for psm-validate/psm-optimize) is missing. Deferral is defensible since Docker is not needed for setup itself.
- Recommendation: Keep the deferred check but frame it explicitly as a forward-looking dependency for later workflows (not a setup blocker), so the late placement reads as intentional.

#### leanness-1 — User-key routing asserted in prose while the planner resolves it authoritatively

- Lens: leanness
- Location: `SKILL.md:Overview (12-13) vs Collect Configuration (target)`
- Evidence: Overview states user_name/communication_language are 'never' written to config.yaml and 'live exclusively' in config.user.yaml; Collect Configuration then says the planner marks each key's target. The planner (and merge-config) is the authoritative runtime source for routing, so the upfront assertions restate a fact the tool already resolves.
- Recommendation: Keep one statement of the data-model intent (user keys are personal/gitignored) and let the planner-target framing own the routing fact; drop the doubled 'never'/'exclusively' emphasis. Defensible as-is — trim-if-touched.
