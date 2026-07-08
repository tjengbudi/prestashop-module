# Analysis Report: psm-setup

Generated: 2026-07-08 · Schema: 2

**Grade: Good**

> Solid, well-scoped stateless installer — heavy work correctly scripted; the real leverage is pulling three remaining deterministic operations out of prose and closing the partial-failure recovery gap.

psm-setup is a coherent, cleanly sequenced install workflow that already delegates its heavy lifting to three tested Python scripts and handles headless input well. Its primary opportunity is determinism: install-state classification, default-priority resolution, and output-directory creation are still done by hand in prose on every run, and a mid-flight failure of one parallel merge script leaves partial state with no stated recovery.

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 2 |
| Medium | 6 |
| Low | 3 |

## Themes

### 1. Deterministic work still done in prose

- Root cause: The skill correctly scripts merge and cleanup, but three operations with exactly one right answer per input — install-state classification (file existence truth table), default-priority resolution (already implemented inside merge-config.py), and output-directory selection (schema-declared in module.yaml) — are re-derived by the model on every invocation.
- Fix: Add a pre-pass helper (or extend merge-config.py with --detect-state / --resolve-defaults / dir creation) that emits compact JSON the prompt reads, so the model presents and collects rather than classifying files, merging three sources by hand, and string-scanning config values for path prefixes.
- Findings:
  - `determinism-1` Install-state classification done by hand in prose — `SKILL.md:On Activation (steps 2-3)`
  - `determinism-2` Default-priority merge computed in prose and duplicated in script — `SKILL.md:Collect Configuration (Default priority block)`
  - `determinism-3` Output-directory creation scanned and created by prose — `SKILL.md:Create Output Directories`

### 2. Partial-failure recovery gap

- Root cause: The two merge scripts run in parallel and each deletes its own legacy files on success, but the only failure instruction is 'surface the error and stop.' If one succeeds and the other fails, the project straddles states (config migrated, help CSV not — or vice versa) with legacy fallbacks already gone and no stated next move.
- Fix: State that the flow is safe to re-run from the top (the anti-zombie pattern makes writes idempotent), and note the one-shot nature of legacy deletion — or sequence legacy deletion to occur only after both merges succeed. One sentence turns a dead-end into a next move.
- Findings:
  - `enhancement-2` No recovery next-move when one parallel merge script fails — `SKILL.md:Write Files (43-52)`
  - `agent-cohesion-1` Non-atomic mutation with 'stop' leaves undocumented partial state — `SKILL.md:Write Files (43-54)`

### 3. Hardcoded psm identity leaks past declared sources

- Root cause: Step 1 frames module.yaml's code field as the module identifier and the Outcome step resolves the user's name dynamically, yet two script calls hardcode --module-code psm and the Seed KB section switches to Indonesian and hardcodes 'Budi'. Literals sit where the skill's own declared/dynamic sources should feed.
- Fix: Either derive --module-code from module.yaml's code (and normalize the Seed KB section to the skill's instruction language, replacing 'Budi' with the resolved user_name), or explicitly declare this installer psm-specific so the literals are intentional rather than a latent fork hazard.
- Findings:
  - `customization-1` Module code declared in module.yaml but hardcoded in script commands — `SKILL.md:49,67 vs assets/module.yaml:1 (code: psm)`
  - `agent-cohesion-2` Mid-workflow language switch and hardcoded user name — `SKILL.md:Seed Knowledge Base & External Deps (74-78)`

### 4. Path-reference hygiene against the skill standard

- Root cause: SKILL.md addresses its own scripts and assets with ./scripts/ and ./assets/ (nine sites) and keeps README.md at the skill root. The standard reserves ./ for same-folder use and root for SKILL.md only; bare skill-root-relative paths (scripts/foo.py) are the portable form.
- Fix: Replace every ./scripts/ and ./assets/ with bare scripts/ and assets/ across SKILL.md, and move README.md under references/ (or accept it as a deliberate convention exception).
- Findings:
  - `lint-1` Cross-directory ./ references throughout SKILL.md — `SKILL.md:10,22,35,39,49,54,67,72 (nine sites)`
  - `lint-2` README.md at skill root — `README.md`

## Strengths

- Heavy deterministic work is delegated to three Python scripts, each with a matching test under scripts/tests/ — the merge/cleanup core is scripted and covered.
- The anti-zombie merge pattern makes config writes idempotent, so re-running the skill is inherently safe (a fact worth surfacing to users, per the recovery theme).
- Facilitative config collection: present all defaults, accept a single reply, and an explicit rule never to tell a chat user to 'press enter' — good theory-of-mind for the interface.
- Clean handling of the literal {project-root} token vs resolved filesystem path arguments, taught once and reinforced at command sites.
- Headless path is real: args map to keys, defaults fill the rest, confirmation still shows.

## Recommendations

1. Move install-state detection, default resolution, and output-dir creation into scripts (extend merge-config.py or add a small pre-pass), leaving the prompt to present/collect only. (resolves: determinism-1, determinism-2, determinism-3)
2. Add one recovery sentence to the Write Files stop instruction: safe to re-run from the top (anti-zombie), with legacy fallbacks being one-shot — or defer legacy deletion until both merges succeed. (resolves: enhancement-2, agent-cohesion-1)
3. Normalize hardcoded psm identity: derive --module-code from module.yaml, translate the Seed KB section to English, and replace 'Budi' with resolved user_name. (resolves: customization-1, agent-cohesion-2)
4. Fix path-reference hygiene: swap ./scripts/ and ./assets/ for bare relative paths and relocate README.md out of the skill root. (resolves: lint-1, lint-2)
5. Optional polish: add a python3 preflight alongside the Docker check, offer a split communication/document language, and trim the two low-value prose lines the leanness lens flagged. (resolves: enhancement-3, enhancement-1, leanness-1, leanness-2)

## Agent Profile

- Name: psm-setup
- Title: PrestaShop Module Builder installer
- Type: stateless
- Mission: Install and configure the psm BMad module into a project: collect preferences, merge config, migrate legacy installs, clean up installer packages.

## Capabilities

- **Collect Configuration** (prompt) — Facilitative one-shot wizard: present all defaults, accept a single reply changing only what the user wants.
- **merge-config.py** (script) — Anti-zombie merge of core + module config into config.yaml / config.user.yaml, with legacy fallback defaults.
- **merge-help-csv.py** (script) — Registers module capabilities into module-help.csv, deleting the legacy CSV after merge.
- **cleanup-legacy.py** (script) — Removes installer package dirs after verifying every skill is already installed under .claude/skills/.
- **Seed KB & deps hand-off** (prompt) — Defers knowledge-base seeding to psm-agent-expert and preflights the Docker dependency.

## Per-Lens Verdicts

- **leanness**: Largely lean and load-bearing; one full re-teach of the token rule and one script-internals note are the only trimmable prose.
- **architecture**: Sound stateless topology: single SKILL.md, coherent linear activation with genuine dependencies, correct parallelization of the two merge scripts.
- **determinism**: Core merge/cleanup correctly scripted; three deterministic operations remain in prose that a pre-pass script should own.
- **customization**: About right: a skill registers via SKILL.md frontmatter, so no customize.toml is warranted; config handled appropriately.
- **enhancement**: Well-scoped with good defaults and headless handling; a few edge-case and next-move gaps worth adding.
- **agent-cohesion**: Coherent, well-sequenced workflow with clear hand-off; blemished by a partial-failure gap and a mid-file language/name inconsistency.
- **path-standards**: Cross-directory ./ references throughout SKILL.md violate the bare-relative-path standard; README.md sits at skill root.

## Experience

- **Fresh install** — activate → collect config → write files → mkdir output dirs → cleanup installer packages → confirm → greet
- **Legacy migration / update** — activate detects existing module section + legacy per-module config → legacy values become fallback defaults → merge → legacy files/dirs removed → confirm migration
- **Headless** — args like --headless or inline values map to keys → defaults for the rest → skip prompting → still show final confirmation summary
- Headless: Handled: On Activation maps provided args/inline values to keys, uses defaults for the rest, and still displays the full confirmation summary.

## Findings

### High (2)

#### lint-1 — Cross-directory ./ references throughout SKILL.md

- Lens: path-standards
- Location: `SKILL.md:10,22,35,39,49,54,67,72 (nine sites)`
- Evidence: Deterministic path-standards scanner: ./scripts/ and ./assets/ are used to address the skill's own subdirectories. Per the standard, ./ means the same folder only; the portable form is a bare skill-root-relative path (scripts/foo.py, assets/module.yaml). They function for this skill but violate the standard.
- Recommendation: Replace every ./scripts/ and ./assets/ occurrence with bare scripts/ and assets/.

#### lint-2 — README.md at skill root

- Lens: path-standards
- Location: `README.md`
- Evidence: Deterministic path-standards scanner: only SKILL.md belongs at the skill root; all other prose/progressive-disclosure content should live under references/. README.md sits at the root.
- Recommendation: Move README.md under references/, or accept it as a deliberate top-level convention exception if the project standardizes on root READMEs.

### Medium (6)

#### determinism-1 — Install-state classification done by hand in prose

- Lens: determinism
- Location: `SKILL.md:On Activation (steps 2-3)`
- Evidence: Model is told to check whether config.yaml has a section for the module and whether _bmad/psm/config.yaml / _bmad/core/config.yaml exist to decide 'fresh install' vs 'legacy migration' vs 'consolidated'. This is a truth table over two booleans re-derived from raw YAML on every run.
- Recommendation: Add a pre-pass detect-install-state.py returning compact JSON ({install_state, module_section_present, legacy_configs_found}) so the model reads state instead of re-deriving it.

#### determinism-2 — Default-priority merge computed in prose and duplicated in script

- Lens: determinism
- Location: `SKILL.md:Collect Configuration (Default priority block)`
- Evidence: Prose asks the model to apply 'existing new config > legacy config > module.yaml defaults' and to carry forward only schema-matching keys. merge-config.py (load_legacy_values, apply_legacy_defaults) already implements exactly this three-source priority merge — the model re-does it by hand just to present defaults.
- Recommendation: Add a --resolve-defaults mode (or thin resolve-defaults.py) that emits [{key, prompt, effective_default}] so the prompt only presents and collects; schema-match filtering is already k in module_yaml inside the script.

#### determinism-3 — Output-directory creation scanned and created by prose

- Lens: determinism
- Location: `SKILL.md:Create Output Directories`
- Evidence: Prose tells the model to find path-type config values by string prefix ({project-root}/), resolve the token, and mkdir -p each. The directory set is already declared deterministically in module.yaml (directories list plus output_folder).
- Recommendation: Fold directory creation into a script that already knows the resolved paths and the module.yaml directories list (merge-config, or a create-dirs.py); the prompt should not enumerate/filter config values by prefix.

#### enhancement-2 — No recovery next-move when one parallel merge script fails

- Lens: enhancement
- Location: `SKILL.md:Write Files (43-52)`
- Evidence: The two merge scripts run in parallel; instruction is only 'if either exits non-zero, surface the error and stop.' If merge-config succeeds but merge-help-csv fails, the project is left half-configured with no stated next move. The anti-zombie pattern makes a full re-run idempotent, but the skill never tells the user that.
- Recommendation: Add one sentence: after surfacing the error, tell the user setup is safe to re-run from the top once the cause is fixed (anti-zombie removes partial entries).

#### agent-cohesion-1 — Non-atomic mutation with 'stop' leaves undocumented partial state

- Lens: agent-cohesion
- Location: `SKILL.md:Write Files (43-54)`
- Evidence: Each merge script deletes its own legacy files on success. If merge-config succeeds (new config written, legacy config deleted) but merge-help-csv fails, the workflow stops with config migrated and legacy config gone but the help CSV not migrated — and a retry lands in the 'already has a section' branch with legacy fallbacks already deleted. No rollback or re-run guidance is given.
- Recommendation: Document that the combined flow is safe to re-run (writes are idempotent; legacy fallbacks are one-shot), or sequence legacy deletion to happen only after both merges succeed. Add one line on what to do after a mid-flow failure.

#### enhancement-1 — Communication and document language forced equal

- Lens: enhancement
- Location: `SKILL.md:Collect Configuration (Core config, 37)`
- Evidence: communication_language and document_output_language are asked 'as a single language question, both keys get the same answer.' The actual user writes in Indonesian while PrestaShop docs are English — a common case for wanting to converse in one language and generate documents in another. Collapsing the keys silently removes that choice.
- Recommendation: Keep the single-question default for speed, but add one clause offering to collect the two languages separately if the user's answer implies a split or they ask.

### Low (3)

#### customization-1 — Module code declared in module.yaml but hardcoded in script commands

- Lens: customization
- Location: `SKILL.md:49,67 vs assets/module.yaml:1 (code: psm)`
- Evidence: Step 1 frames module.yaml's code field as the module identifier, but the merge-help-csv and cleanup-legacy invocations hardcode --module-code psm. Works today (code == psm and the skill is psm-specific throughout), but a fork editing module.yaml's code would leave these commands pointing at the wrong module.
- Recommendation: Derive --module-code from module.yaml's code, or explicitly state in SKILL.md that this installer is psm-specific. Low because it is not intended to be generic.

#### agent-cohesion-2 — Mid-workflow language switch and hardcoded user name

- Lens: agent-cohesion
- Location: `SKILL.md:Seed Knowledge Base & External Deps (74-78)`
- Evidence: Every step is English until this section, which is entirely Indonesian and repeatedly hardcodes 'Budi' ('Beri tahu Budi ...'). This contradicts the Outcome step (86), which resolves the user's name dynamically from user_name and instructs addressing the user by their configured name.
- Recommendation: Normalize the section to the skill's instruction language (English) and replace hardcoded 'Budi' with the resolved user_name (or a neutral 'the user').

#### enhancement-3 — No python3 preflight despite it being the hard runtime dep

- Lens: enhancement
- Location: `SKILL.md:78 (external deps) vs 47-49/67 (script invocations)`
- Evidence: The skill carefully checks for Docker (an optional downstream dep) but never checks for python3, which every script requires. Without it the user hits a raw 'command not found' at Write Files rather than a clear message.
- Recommendation: Add a quick python3 --version preflight in On Activation; if absent, tell the user how to install it and stop before prompting, matching the graceful Docker guidance.
