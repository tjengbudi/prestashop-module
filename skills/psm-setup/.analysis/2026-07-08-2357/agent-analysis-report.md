# Analysis Report: psm-setup

Generated: 2026-07-08 · Schema: 2

**Grade: Excellent**

> Excellent after the fix pass — all three prior determinism leaks are genuinely scripted, identity is derived, and the two new gaps this run surfaced were closed in-session; only low-severity point-of-use polish remains.

psm-setup is now a tight, outcome-shaped installer: a read-only plan-setup.py owns install-state classification and three-source default resolution (importing merge-config.py so priority logic has one home), and output-directory creation folded into merge-config via --project-root. Architecture, determinism, and customization all pass clean; the remaining findings are two low-severity, defensible repetitions, not defects.

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 2 |

## Themes

### 1. Point-of-use repetition (low-value polish)

- Root cause: Two facts are taught more than once for point-of-use reinforcement: the literal-token-vs-resolved-path rule appears in Overview and again at two script call sites, and the Docker prerequisite surfaces late in the flow rather than alongside the upfront python3 check. Both are defensible reinforcement, not defects.
- Fix: Optional trim-if-touched: shrink the third literal-token restatement to a back-reference, and optionally consolidate the Docker check into On Activation as a non-blocking deferred prerequisite so all env checks sit in one place.
- Findings:
  - `leanness-1` Literal-token resolution rule restated in three sections — `SKILL.md (Overview, Write Files, Cleanup Legacy)`
  - `agent-cohesion-1` Docker prerequisite check surfaces only late in the flow — `SKILL.md:Seed Knowledge Base & External Deps`

## Strengths

- Heavy deterministic work is fully scripted across four Python scripts, each with a matching test under scripts/tests/ (26 tests pass); plan-setup.py imports merge-config.py so the three-source priority merge has a single source of truth.
- Read-avoidance: the model reads install state and defaults from planner JSON rather than inspecting config files by hand.
- The anti-zombie merge makes config writes idempotent, and the skill now tells the user setup is safe to re-run from the top after a partial failure.
- Facilitative config collection: present all defaults, accept a single reply, never tell a chat user to 'press enter', and offer a split communication/document language when implied.
- Module identity is derived (plan-setup returns module_code; SKILL.md uses {module_code} placeholders) rather than hardcoded.
- Clean separation of the literal {project-root} token in config values from resolved filesystem path arguments, enforced by the scripts' unresolved-token rejection.
- python3 and planner-failure preflights, plus a real headless path.

## Recommendations

1. Optional only: on next edit, shrink the third literal-token restatement to a back-reference and consider moving the Docker check up into On Activation as a non-blocking prerequisite. No blocking work remains. (resolves: leanness-1, agent-cohesion-1)

## Agent Profile

- Name: psm-setup
- Title: PrestaShop Module Builder installer
- Type: stateless
- Mission: Install and configure the psm BMad module into a project: plan the install, collect preferences, merge config, create output dirs, migrate legacy installs, clean up installer packages.

## Capabilities

- **plan-setup.py** (script) — Read-only pre-pass: classifies install_state and resolves effective core/module defaults (legacy over builtin), derives module_code.
- **Collect Configuration** (prompt) — Facilitative one-shot wizard over the planner's defaults; single-vs-split language judgment.
- **merge-config.py** (script) — Anti-zombie config merge into config.yaml / config.user.yaml, legacy fallback defaults, and --project-root output-dir creation.
- **merge-help-csv.py** (script) — Registers module capabilities into module-help.csv, deleting the legacy CSV after merge.
- **cleanup-legacy.py** (script) — Removes installer package dirs after verifying each skill is already installed under .claude/skills/.
- **Seed KB & deps hand-off** (prompt) — Defers knowledge-base seeding to psm-agent-expert and checks the Docker dependency.

## Per-Lens Verdicts

- **leanness**: Lean and outcome-shaped; delegation keeps prose thin. One defensible cross-section restatement of the literal-token rule.
- **architecture**: Structurally sound: correct topology, resolving pointers, dependency-honest ordering, proper parallelization, read-avoidance via planner JSON.
- **determinism**: Passes. The three prior leaks are genuinely scripted with a single source of truth; remaining prose is judgment/interaction, not computation.
- **customization**: About right: no customize.toml needed for a skill; module.yaml is the appropriate config source and identity now flows from plan-setup.py.
- **enhancement**: Well-facilitated; two dead-end/hygiene gaps (planner-failure branch, temp-file location/cleanup) — both closed this session.
- **agent-cohesion**: Coherent end-to-end with prior fixes cleanly integrated; one optional journey-polish note on Docker-check placement.
- **path-standards**: Clean — cross-directory ./ refs removed, README relocated under references/ (the lone remaining scanner hit is the builder's own .memlog.md, not skill content).

## Experience

- **Fresh install** — python3 preflight → plan-setup classifies fresh → collect config → merge + mkdir output dirs → cleanup installer packages → seed handoff → confirm → greet
- **Legacy migration / update** — plan-setup returns update/legacy_migration with legacy values as defaults → merge → legacy files/dirs removed → confirm migration
- **Headless** — args/inline values map to keys → planner defaults fill the rest → skip prompting → still show full confirmation summary
- Headless: Handled: On Activation maps provided args/inline values to keys, uses the planner's resolved defaults for the rest, and still displays the full confirmation summary.

## Findings

### Low (2)

#### leanness-1 — Literal-token resolution rule restated in three sections

- Lens: leanness
- Location: `SKILL.md (Overview, Write Files, Cleanup Legacy)`
- Evidence: The '{project-root} is literal in config values but must be resolved in path arguments' rule is fully taught in Overview, then re-explained at the Write Files call and again at the Cleanup Legacy call. The third restatement adds no new distinction.
- Recommendation: Keep the full teaching in Overview and the one point-of-use reminder at the first script call; shrink the Cleanup restatement to 'resolve {project-root} in the path arguments as above.' Defensible as-is since script rejection is a real scar — trim-if-touched, not a blocking cut.

#### agent-cohesion-1 — Docker prerequisite check surfaces only late in the flow

- Lens: agent-cohesion
- Location: `SKILL.md:Seed Knowledge Base & External Deps`
- Evidence: python3 is checked upfront in On Activation and blocks setup if missing, but the Docker check is deferred to the second-to-last section, bundled with the KB-seeding handoff. A user lacking Docker learns of it only after install completes.
- Recommendation: Reasonable as-is since Docker isn't needed for setup itself (only later psm-validate/psm-optimize). Optional: consolidate python3 + Docker into one upfront prerequisite survey in On Activation, flagging Docker as non-blocking/deferred. Journey polish, not a defect.
