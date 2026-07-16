# Analysis Report: .claude/skills/psm-setup

Generated: 2026-07-16 · Schema: 2

**Grade: Good**

> A well-scripted, correctly-shaped installer held back by two things: an update run that trusts the model to preserve existing config values (determinism-1), and a drifted inline recap of psm-agent-expert's seed recipe pointing at the stale scaffold tree (leanness-3/architecture-1).

psm-setup's script layer is its strength — four unit-tested scripts with anti-zombie merges, unresolved-token guards, and idempotent cleanup, wrapped in a clean linear flow that passes workflow integrity. The opportunity is ownership: SKILL.md restates facts that the scripts and a sibling skill already own (one restatement has drifted to stale paths), and the 'existing config wins' tier of default resolution lives only in the prompt, so update runs depend on the model echoing every value back.

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 1 |
| Medium | 11 |
| Low | 7 |

## Themes

### 1. SKILL.md restates facts owned elsewhere

- Root cause: Belt-and-suspenders prose repeats what the scripts already guard (the {project-root} token rule at four sites, user-key routing at three, mkdir mechanics) and recaps psm-agent-expert's seed recipe inline — where the copy has already drifted to the stale skills/ scaffold paths. The repetition costs tokens (2124, above the 1500 desired tier); the drifted recap actively misleads.
- Fix: One editing pass on SKILL.md: replace the Seed section with the minimal hand-off (leanness-3's proposed_smallest), keep the Overview token paragraph as the single authority plus the one unguarded reminder in Create Output Directories, state user-key routing once, and drop the mkdir tool-teaching sentence — seven findings and the token overage fall out of one edit.
- Findings:
  - `leanness-1` {project-root} dual-semantics rule restated at four sites — `SKILL.md:18 (Overview), :43-45 (Write Files), :58 (Create Output Directories), :64 (Cleanup Legacy Directories)`
  - `leanness-2` User-key routing fact stated three times — `SKILL.md:12-13 (Overview) and :37 (Collect Configuration)`
  - `leanness-3` Seed section recaps another skill's mechanics — downstream mechanics in the wrong file, already drifted — `SKILL.md:76 (Seed Knowledge Base & External Deps)`
  - `leanness-4` Tool mechanics re-teach: 'Use mkdir -p or equivalent' — `SKILL.md:58 (Create Output Directories)`
  - `enhancement-1` Remove drifted restatement of psm-agent-expert's seed recipe (delegation already applied) — `SKILL.md:74-76 (## Seed Knowledge Base & External Deps)`
  - `architecture-1` Seed section restates another skill's seed logic with drifted paths — `SKILL.md:74-78 (## Seed Knowledge Base & External Deps)`
  - `architecture-6` SKILL.md between desired and budget token tier — `SKILL.md`

### 2. Update runs trust the model to preserve existing config

- Root cause: merge-config.py's anti-zombie delete rebuilds the module section purely from the answers JSON, while the 'existing new config values win' tier of default resolution exists only as a prompt instruction — so on an update run, any value the model does not echo back silently resets to defaults. The same prompt-side pattern covers install-type classification and output-directory creation, and module.yaml's directories: list is created by no instruction at all.
- Fix: Extend merge-config.py to own default resolution end-to-end: treat existing module-section values as fallback defaults exactly as apply_legacy_defaults treats legacy values, emit a resolve/--show-defaults pre-pass JSON (resolved defaults with provenance plus install_type), and create module.yaml's directories: entries itself, reporting directories_created.
- Findings:
  - `determinism-1` Default-priority resolution is prompt-side while the script implements only two of its three tiers — `/home/budi/dev/prestashop-module/.claude/skills/psm-setup/SKILL.md:35 (Collect Configuration) + /home/budi/dev/prestashop-module/.claude/skills/psm-setup/scripts/merge-config.py:271-293`
  - `determinism-2` Prompt-side string-prefix classification and creation of output directories; module.yaml directories list falls through the stated rule — `/home/budi/dev/prestashop-module/.claude/skills/psm-setup/SKILL.md:56-58 (Create Output Directories) + /home/budi/dev/prestashop-module/.claude/skills/psm-setup/assets/module.yaml:39-42`
  - `determinism-3` Install-type classification (fresh install / update / legacy migration) is a deterministic three-way check done in the prompt — `/home/budi/dev/prestashop-module/.claude/skills/psm-setup/SKILL.md:20-27 (On Activation)`

### 3. Duplicated sources with no drift guard

- Root cause: resolve-psm-config.py exists in two identical copies — consumers execute the scaffold-tree copy at skills/psm-setup/scripts/ while the test suite lives beside this skill's non-executed copy — and PSM_DEFAULTS hardcodes the same defaults as assets/module.yaml with no cross-check. Both pairs stay in sync by convention only; this is the known multi-layer defaults-sync burden growing new limbs.
- Fix: Pick one canonical resolver copy (point consumers at the installed skill's scripts/ and delete the scaffold copy, or move the tests beside the executed copy), and add a unit test asserting each shared key's default in PSM_DEFAULTS equals assets/module.yaml.
- Findings:
  - `architecture-5` scripts/resolve-psm-config.py is unreachable from this skill and shadowed by the copy consumers execute — `scripts/resolve-psm-config.py; scripts/tests/test-resolve-psm-config.py`
  - `determinism-4` PSM_DEFAULTS duplicates module.yaml defaults with no automated drift check — `/home/budi/dev/prestashop-module/.claude/skills/psm-setup/scripts/resolve-psm-config.py:39-55 vs /home/budi/dev/prestashop-module/.claude/skills/psm-setup/assets/module.yaml:19-37`

### 4. README is a drifting, misplaced doc surface

- Root cause: The root-level README (flagged by path-standards; the bmb template ships none) documents the stale scaffold layout, lists 8 config keys while the runtime resolver honors 10 (both E2E keys missing), and tells users to 'press accept' — an interaction SKILL.md itself forbids.
- Fix: Relocate the README out of the skill root (module docs home, e.g. docs/), refreshing it in transit: structure section updated to the installed .claude/skills/ tree, config table gains psm_e2e_enabled and psm_e2e_browsers plus a source-of-truth note pointing at PSM_DEFAULTS in resolve-psm-config.py, and the accept-defaults instruction reworded to a typed reply.
- Findings:
  - `architecture-4` README.md at skill root, with a stale structure section — `README.md (root); stale content at README.md:129-147`
  - `enhancement-2` Add the two undocumented E2E keys to the README config table (documented escape hatch is incomplete) — `README.md:41-54 (### Konfigurasi table)`
  - `enhancement-4` Reword 'tekan terima saja' — README tells the user to press accept, which the skill itself forbids — `README.md:31`

### 5. Hardcoded 'Budi' defeats the personalization the skill just configured

- Root cause: The Seed section says 'Beri tahu Budi' twice and module.yaml's module_greeting says 'membantu Budi', while the Outcome section promises to address the user by their configured user_name (default BMad) — an implicit instruction that contradicts the skill's own stated rule and blocks portability to any other installer.
- Fix: Replace 'Budi' with the configured user_name (or 'the user') in SKILL.md and make module_greeting name-neutral.
- Findings:
  - `architecture-2` Hardcoded user name contradicts the skill's own Outcome rule — `SKILL.md:76,78 (Seed section); assets/module.yaml:6-10 (module_greeting)`
  - `enhancement-5` Hardcoded 'Budi' bypasses the user_name the skill just collected — `SKILL.md:76-78 (seed/deps section); assets/module.yaml module_greeting`

## Strengths

- Script layer is exemplary: four unit-tested Python scripts (scan-scripts 0/0/0) with anti-zombie merges, reject_unresolved_paths guards on every path argument, and idempotent legacy cleanup — the destructive step verifies skills are installed before it deletes.
- Shape matches the job: a linear simple-workflow that passes integrity checks, clean two-part frontmatter with quoted triggers, zero waste patterns and back-references, SKILL.md within its token budget.
- Correct customization posture: no customize.toml, matching the default-no for a one-shot installer whose install questions, module.yaml, and written config files are its product, not its configuration surface.
- Chat-interface realities are encoded: values collected in one combined prompt, never 'press enter', and argument mapping makes the input side headless-ready.
- Legacy migration is genuinely engineered: three-way fresh/update/migration detection, legacy values as schema-filtered fallback defaults, post-merge cleanup with verification and idempotent re-runs.

## Recommendations

1. Run the theme-1 editing pass on SKILL.md: swap in the proposed_smallest Seed hand-off, dedupe the {project-root} token rule and user-key routing to single authorities, and drop the mkdir sentence. (resolves: leanness-1, leanness-2, leanness-3, leanness-4, enhancement-1, architecture-1, architecture-6)
2. Extend merge-config.py to own default resolution: existing module-section values as fallback defaults, a --show-defaults pre-pass JSON with install_type and provenance, and creation of module.yaml's directories: entries. (resolves: determinism-1, determinism-2, determinism-3)
3. De-duplicate resolve-psm-config.py (one canonical copy, tests beside the executed one) and add a PSM_DEFAULTS-vs-module.yaml sync test. (resolves: architecture-5, determinism-4)
4. Relocate the README out of the skill root and refresh it: live .claude/skills/ structure, +psm_e2e_enabled/+psm_e2e_browsers rows with a source-of-truth note, typed-reply wording for accepting defaults. (resolves: architecture-4, enhancement-2, enhancement-4)
5. Neutralize the hardcoded name: 'the user' (or configured user_name) in SKILL.md's Seed section, name-neutral module_greeting in assets/module.yaml. (resolves: architecture-2, enhancement-5)
6. Stamp the canonical Resolution rules block into SKILL.md and define the headless return contract (assumptions appended via _bmad/scripts/memlog.py plus a minimal JSON result). (resolves: architecture-3, enhancement-3)

## Experience

- **Fresh install** — module.yaml read → core + module values collected in one combined prompt → merge-config.py and merge-help-csv.py run in parallel → output directories created → cleanup-legacy.py removes installer packages → confirmation summary + module greeting → hand-off: run psm-agent-expert once to seed the knowledge base, check Docker.
- **Update (re-run)** — Existing psm section detected → user informed this is an update → same collect/merge flow; risk: any existing value the model does not echo into the answers JSON silently resets to defaults (determinism-1).
- **Legacy migration** — Per-module _bmad/psm/config.yaml or _bmad/core/config.yaml detected alongside existing config → legacy values become schema-filtered fallback defaults → consolidated write → legacy files deleted and installer directories cleaned with verification.
- Headless: Input side is ready (--headless and inline values map to config keys, prompting skipped) but the return is undefined — the flow ends in a prose summary with no JSON contract or memlog'd assumptions (enhancement-3).

## Findings

### High (1)

#### determinism-1 — Default-priority resolution is prompt-side while the script implements only two of its three tiers

- Lens: determinism
- Location: `/home/budi/dev/prestashop-module/.claude/skills/psm-setup/SKILL.md:35 (Collect Configuration) + /home/budi/dev/prestashop-module/.claude/skills/psm-setup/scripts/merge-config.py:271-293`
- Evidence: SKILL.md instructs the model: '**Default priority** (highest wins): existing new config values > legacy config values > assets/module.yaml defaults... Only keys that match the current schema are carried forward — changed or removed keys are ignored.' — i.e. parse up to four YAML files, filter keys against the schema, and compute a priority merge inline. merge-config.py already implements the legacy and module.yaml tiers deterministically (load_legacy_values/apply_legacy_defaults with schema filtering) but NOT the 'existing new config values' tier: its anti-zombie step (del config[module_code]) rebuilds the module section solely from metadata + answers, so preserving previously configured module values across an update depends entirely on the model re-reading config.yaml correctly and echoing every value back into the answers JSON. If it echoes only changed values, user customizations silently reset to defaults.
- Recommendation: Determinism leak. All three tiers pass the determinism test (identical input -> identical resolved defaults; trivially unit-testable). Apply the pre-pass JSON pattern: add a resolve/--show-defaults mode to merge-config.py (or a small pre-pass script) that reads existing config.yaml + legacy configs + module.yaml and emits compact JSON of resolved defaults with per-key provenance for the model to present; and/or make merge_config treat existing module-section values as fallback defaults exactly as apply_legacy_defaults treats legacy values, so update runs cannot lose values regardless of what the model echoes back.

### Medium (11)

#### leanness-1 — {project-root} dual-semantics rule restated at four sites

- Lens: leanness
- Location: `SKILL.md:18 (Overview), :43-45 (Write Files), :58 (Create Output Directories), :64 (Cleanup Legacy Directories)`
- Evidence: The literal-token-in-values vs resolved-path-in-arguments rule is stated in full in Overview (line 18), then restated before the Write Files commands (lines 43 and 45), again in Create Output Directories (line 58, including 'The paths stored in the config files must continue to use the literal {project-root} token' — a step that never touches config files), and again before the cleanup command (line 64: 'As with the merge scripts, replace {project-root}...'). This is the canon's 'facts restated across sections' shape. Three of the four use-sites are also script-guarded: merge-config.py, merge-help-csv.py, and cleanup-legacy.py all reject an unresolved token with a loud error (reject_unresolved_paths, merge-config.py:342), so a forgotten resolution there recovers in one turn. The only unguarded site is the mkdir step, where 'mkdir -p {project-root}/...' would silently create a junk directory.
- Recommendation: Keep the Overview paragraph as the single authority and keep the resolve instruction inside Create Output Directories (the one site with no script guard). Cut the reminders at lines 45 and 64 and the 'config files must continue to use the literal token' sentence at line 58 — the scripts' own errors cover those cases, per the canon's core test (a line earns its place only by preventing a failure that would otherwise happen).

#### leanness-3 — Seed section recaps another skill's mechanics — downstream mechanics in the wrong file, already drifted

- Lens: leanness
- Location: `SKILL.md:76 (Seed Knowledge Base & External Deps)`
- Evidence: The only actions this skill takes are: do not seed, and tell the user to run psm-agent-expert once. Yet the parenthetical recaps psm-agent-expert's entire seed procedure — source paths ({project-root}/skills/reports/prestashop-module-builder-plan.md, {project-root}/skills/psm-cross-version/references/version-safe-patterns.md, {project-root}/skills/psm-develop/references/ecommerce-function-catalog.md, devdocs fallback). None of it changes a move in this skill, and it has already drifted: the authoritative psm-agent-expert/references/maintain-knowledge.md now resolves catalog paths via a '<skills-dir>' convention, while this recap points into the {project-root}/skills/ tree — the stale scaffold. The recap fails the defend-against-absence test: no dimension exists on which relaying these mechanics beats a two-line hand-off, and the stale copy can only mislead the user it is relayed to.
- Recommendation: Replace the recap with the hand-off only; the seed mechanics stay in psm-agent-expert's maintain-knowledge.md where they execute. Route to variant eval to confirm.
- Proposed smallest: Setelah direktori dibuat, knowledge base di `{project-root}/_bmad/psm/memory/` (`tech/`, `ecommerce/`, `projects/`) masih kosong. Jangan men-seed-nya di sini — itu tugas first-run `psm-agent-expert` (lihat `references/maintain-knowledge.md` skill tersebut). Beri tahu Budi: jalankan `psm-agent-expert` sekali untuk mengisinya.

Periksa juga dependensi eksternal: **Docker** wajib untuk uji `psm-validate`/`psm-optimize` di `prestashop-flashlight`. Cek `docker --version`; bila tak ada, beri tahu Budi cara memasang (jangan instal otomatis) dan bahwa image flashlight ditarik saat workflow uji pertama dijalankan.
- Predicted delta: Nothing lost — the model is explicitly told not to seed, so the source-path details drive no action here, and cutting them removes a copy that is already stale relative to the authoritative file. Route to variant eval to confirm.

#### architecture-1 — Seed section restates another skill's seed logic with drifted paths

- Lens: architecture
- Location: `SKILL.md:74-78 (## Seed Knowledge Base & External Deps)`
- Evidence: The section explicitly says seeding is psm-agent-expert's job ('Jangan men-seed-nya di sini'), then restates that skill's seed sources anyway — naming {project-root}/skills/psm-cross-version/references/version-safe-patterns.md and {project-root}/skills/psm-develop/references/ecommerce-function-catalog.md (the stale skills/ scaffold tree), while the authoritative logic in psm-agent-expert's references/maintain-knowledge.md (lines 18-19) resolves them via <skills-dir>/..., i.e. the installed .claude/skills/ tree. The parenthetical 'lihat references/maintain-knowledge.md skill tersebut' also reads as a bare path, which by convention resolves from this skill's root where no references/ directory exists. It is additionally the only Indonesian-language section in an otherwise English SKILL.md — a seam showing it was bolted onto the bmb template.
- Recommendation: Cut the restated source list: keep only 'tell the user to run psm-agent-expert once to seed the knowledge base — its first-run seed logic (psm-agent-expert's references/maintain-knowledge.md) owns the sources.' This removes the drift surface, fixes the bare-path ambiguity, and lets the authoritative file be the single owner. Normalize the section's language to match the rest of the file.

#### architecture-2 — Hardcoded user name contradicts the skill's own Outcome rule

- Lens: architecture
- Location: `SKILL.md:76,78 (Seed section); assets/module.yaml:6-10 (module_greeting)`
- Evidence: The Outcome section promises: once user_name is known, 'address the user by their configured name'. The Seed section instructs 'Beri tahu Budi: jalankan psm-agent-expert...' and 'beri tahu Budi cara memasang' — a specific hardcoded name (the default is 'BMad'), and module.yaml's module_greeting, displayed verbatim in Confirm, says 'membantu Budi'. This is the implicit-instruction-violates-stated-principle misalignment the architecture bar names as the most dangerous kind, and it makes the skill non-portable to any other user.
- Recommendation: Replace 'Budi' with 'the user' in SKILL.md and make the greeting name-neutral (or interpolate the configured user_name), so the Outcome rule actually governs every user-facing line.

#### architecture-3 — Multi-file SKILL.md missing the canonical Resolution rules block

- Lens: architecture
- Location: `SKILL.md`
- Evidence: SKILL.md references multiple internal files by bare path (assets/module.yaml, assets/module-help.csv, scripts/merge-config.py, scripts/merge-help-csv.py, scripts/cleanup-legacy.py) and invokes them bare in bash (python3 scripts/merge-config.py ...), where the executing shell's cwd is not guaranteed to be the skill root. The Overview paragraph covers {project-root} token semantics thoroughly, but nothing states that bare paths resolve from the skill's installed directory — the exact gap the canonical Resolution rules block exists to close, and the principles file requires it in any SKILL.md that references multiple internal files.
- Recommendation: Stamp the canonical Resolution rules block (bare paths / {project-root} / {skill-name}) into SKILL.md; the existing {project-root}-literal-token paragraph then reads as the skill-specific extension of it.

#### architecture-4 — README.md at skill root, with a stale structure section

- Lens: architecture
- Location: `README.md (root); stale content at README.md:129-147`
- Evidence: Path-standards flags README.md at skill root (only SKILL.md belongs there); the official template bmad-bmb-setup ships no root README. Judged down from the scanner's high because it is human-facing module documentation, never loaded at runtime — not workflow content. But it is drifting: the 'Struktur' section documents the stale skills/ scaffold layout rather than the installed .claude/skills/ tree, and its config table lists 8 psm keys while module.yaml prompts only 4, implying setup manages keys it never writes.
- Recommendation: Move the module README out of the skill (e.g. docs/ or the module's distribution root) since it is not agent-consumed content, and refresh the structure section and config-key table while relocating.

#### architecture-5 — scripts/resolve-psm-config.py is unreachable from this skill and shadowed by the copy consumers execute

- Lens: architecture
- Location: `scripts/resolve-psm-config.py; scripts/tests/test-resolve-psm-config.py`
- Evidence: This SKILL.md never references resolve-psm-config.py; its consumers (e.g. psm-validate SKILL.md line 20) execute the other copy at {project-root}/skills/psm-setup/scripts/resolve-psm-config.py in the otherwise-stale scaffold tree. The two copies are currently identical (verified by diff), but the test suite lives beside this non-executed copy — an engineer can edit here, pass tests, and change nothing at runtime. A file no path in the skill reaches is a silent-drift trap in the topology.
- Recommendation: Pick one canonical copy: point consumers at the installed skill's scripts/ (then delete the scaffold-tree copy), or if the scaffold tree must stay authoritative, remove this duplicate and move the tests beside the executed copy.

#### determinism-2 — Prompt-side string-prefix classification and creation of output directories; module.yaml directories list falls through the stated rule

- Lens: determinism
- Location: `/home/budi/dev/prestashop-module/.claude/skills/psm-setup/SKILL.md:56-58 (Create Output Directories) + /home/budi/dev/prestashop-module/.claude/skills/psm-setup/assets/module.yaml:39-42`
- Evidence: SKILL.md: 'create each path-type value from config.yaml that does not yet exist — this includes output_folder and any module variable whose value starts with {project-root}/' — a scan-for/detect-pattern operation (string-prefix classification) plus token resolution and mkdir, done by the model each run. Meanwhile module.yaml declares a directories: list (_bmad/psm/memory/tech|ecommerce|projects) that no SKILL.md instruction creates — the config-value prefix rule cannot catch it — yet the Seed section assumes those directories exist ('Setelah direktori dibuat... masih kosong').
- Recommendation: Determinism leak (signal verbs: scan for, detect pattern, transform). merge-config.py already holds every input needed — module.yaml (including directories:), resolved answers, and the written config — so have it create the directories (resolving the token from a --project-root it can derive from --config-path) and report directories_created in its JSON, or emit a directories_to_create list the model just mkdirs verbatim. This closes the memory-dirs gap deterministically instead of relying on the model to generalize past the stated rule.

#### enhancement-1 — Remove drifted restatement of psm-agent-expert's seed recipe (delegation already applied)

- Lens: enhancement
- Location: `SKILL.md:74-76 (## Seed Knowledge Base & External Deps)`
- Evidence: The section correctly applies delegation ('Jangan men-seed-nya di sini — itu tugas psm-agent-expert') and names the authority (references/maintain-knowledge.md of that skill), then restates the recipe inline anyway — and the restatement has already drifted: psm-setup points the catalogs at {project-root}/skills/psm-cross-version/... and {project-root}/skills/psm-develop/... (the stale scaffold tree), while the authoritative maintain-knowledge.md resolves them via <skills-dir> (the live installed sibling tree at .claude/skills/). Duplicated downstream logic drifting is the exact failure delegation exists to prevent.
- Recommendation: Cut the parenthetical recipe (source paths + devdocs fallback) and keep only the delegation, the pointer to psm-agent-expert's references/maintain-knowledge.md, and the one-line user instruction to run psm-agent-expert once. Loss from the removal: nothing — the authoritative reference is already named in the same sentence.

#### enhancement-2 — Add the two undocumented E2E keys to the README config table (documented escape hatch is incomplete)

- Lens: enhancement
- Location: `README.md:41-54 (### Konfigurasi table)`
- Evidence: README's config table is the only discovery surface for keys setup never prompts for (module.yaml asks 4, table documents 8), and its stated escape hatch is 'sunting _bmad/config.yaml'. But the runtime resolver scripts/resolve-psm-config.py honors 10 keys — psm_e2e_enabled and psm_e2e_browsers (Lapis 4 browser E2E gate and Playwright engines) are absent from the table, so an expert user wanting to skip or tune E2E dead-ends. MEMORY already tracks this family's multi-layer defaults-sync risk; this is a fifth drift point.
- Recommendation: Add psm_e2e_enabled and psm_e2e_browsers rows to the README table, and annotate the table with its source of truth (PSM_DEFAULTS in scripts/resolve-psm-config.py) so future keys land in both places.

#### enhancement-3 — Opportunity: define the headless return contract (assumptions to memlog, minimal JSON back)

- Lens: enhancement
- Location: `SKILL.md:29 (On Activation args paragraph) and SKILL.md:80-82 (## Confirm)`
- Evidence: Headless readiness verdict: input-side ready (arguments map to keys, defaults fill the rest, prompting is skipped) and easily adaptable to full headless. The gap is the return: '--headless' is an accepted argument but the flow ends only in a human confirmation summary, while the principles' Headless mode pattern calls for assumptions logged as typed entries via {project-root}/_bmad/scripts/memlog.py (which exists in this project) and a minimal JSON return (status, files written, directories created) so an automator bootstrapping psm in CI gets a usable result.
- Recommendation: Add two lines to the headless branch: append 'assumption' entries (defaults used, legacy values carried forward) through _bmad/scripts/memlog.py, and end with a small JSON return of status plus the paths written (config.yaml, config.user.yaml, module-help.csv, directories created) in place of — or alongside — the prose summary.

### Low (7)

#### leanness-2 — User-key routing fact stated three times

- Lens: leanness
- Location: `SKILL.md:12-13 (Overview) and :37 (Collect Configuration)`
- Evidence: That user_name and communication_language live exclusively in config.user.yaml is stated in Overview bullet 1 ('are never written here'), Overview bullet 2 ('These values live exclusively here'), and again in Collect Configuration ('Of these, user_name and communication_language are written exclusively to config.user.yaml'). The routing is enforced by merge-config.py (_CORE_USER_KEYS, line 299) — the model never writes these files by hand, so one statement (with the gitignore why) is all the Confirm step and user explanation need.
- Recommendation: State the routing once in Overview with its why (personal, gitignored) and drop the other two restatements; the Collect Configuration sentence can shrink to nothing since the script does the split.

#### leanness-4 — Tool mechanics re-teach: 'Use mkdir -p or equivalent'

- Lens: leanness
- Location: `SKILL.md:58 (Create Output Directories)`
- Evidence: 'Use `mkdir -p` or equivalent to create the full path' teaches a tool the model drives fluently — the canon's core test cuts it: a capable model told to create directories that do not yet exist already does this correctly.
- Recommendation: Delete the sentence; the section's remaining instruction (create each not-yet-existing path-type value with the token resolved) fully specifies the outcome.

#### architecture-6 — SKILL.md between desired and budget token tier

- Lens: architecture
- Location: `SKILL.md`
- Evidence: 2124 tiktoken tokens against the configured tier [1500 desired, 2500 budget] — the principles file defines this band as warn-and-name-the-section, not a hard finding. Nothing is branch-specific enough to carve (every section fires on every run), so a references/ split would be the wrong fix.
- Recommendation: Take the reduction from architecture-1's cut (the restated seed-source detail is the heaviest non-load-bearing prose); the {project-root} gotcha paragraph stays inline as a gotcha that cannot carve.

#### determinism-3 — Install-type classification (fresh install / update / legacy migration) is a deterministic three-way check done in the prompt

- Lens: determinism
- Location: `/home/budi/dev/prestashop-module/.claude/skills/psm-setup/SKILL.md:20-27 (On Activation)`
- Evidence: Steps 2-3 have the model derive a three-way classification from file existence plus section presence: 'Check if {project-root}/_bmad/config.yaml exists — if a section matching the module's code is already present... Check for per-module configuration at {project-root}/_bmad/psm/config.yaml and {project-root}/_bmad/core/config.yaml...' with fresh-install vs legacy-migration branching on the combination.
- Recommendation: Determinism leak, cheap but unit-testable (given the same files, the classification is always the same). Fold an install_type field and legacy_configs_found list into the same defaults pre-pass JSON proposed in determinism-1 — one script run then hands the model install type, legacy inventory, and resolved defaults together, and the prompt keeps only the user-facing messaging judgment.

#### determinism-4 — PSM_DEFAULTS duplicates module.yaml defaults with no automated drift check

- Lens: determinism
- Location: `/home/budi/dev/prestashop-module/.claude/skills/psm-setup/scripts/resolve-psm-config.py:39-55 vs /home/budi/dev/prestashop-module/.claude/skills/psm-setup/assets/module.yaml:19-37`
- Evidence: PSM_DEFAULTS hardcodes 'psm_target_versions': '1.7.8,8.1,9.1', 'psm_flashlight_tag_map': '1.7.8=1.7.8.11,...', psm_modules_dir, psm_reports_dir — the same defaults declared in assets/module.yaml. They currently agree, but nothing verifies it: tests/test-resolve-psm-config.py never cross-references module.yaml, so the sync is maintained by convention (a known multi-layer sync burden).
- Recommendation: Comparison-category script opportunity: comparing two files for drift is exactly the deterministic work the lens says should never be manual. Add a unit test in scripts/tests/test-resolve-psm-config.py that loads assets/module.yaml and asserts each shared key's default equals PSM_DEFAULTS, so divergence fails a test run instead of surfacing at runtime.

#### enhancement-4 — Reword 'tekan terima saja' — README tells the user to press accept, which the skill itself forbids

- Lens: enhancement
- Location: `README.md:31`
- Evidence: README step 1 says defaults are sensible — 'tekan terima saja bila cocok' (just press accept) — but SKILL.md's Collect Configuration explicitly encodes the chat-interface reality: never tell the user to press enter or leave blank, because they must type something. A first-timer following the README looks for an accept button that does not exist.
- Recommendation: Reword to match the skill's actual interaction, e.g. 'balas "pakai default semua" bila cocok'.

#### enhancement-5 — Hardcoded 'Budi' bypasses the user_name the skill just collected

- Lens: enhancement
- Location: `SKILL.md:76-78 (seed/deps section); assets/module.yaml module_greeting`
- Evidence: The skill collects user_name (default BMad) and the Outcome section instructs addressing the user by the configured name, yet the seed/deps section hardcodes 'Beri tahu Budi' twice and module.yaml's greeting says 'membantu Budi'. This is the same failure shape as a hardcoded value beside a declared scalar: the personalization mechanism the skill just configured is silently no-oped for any other installer of a module whose stated goal is 'siap dipakai siapa pun'.
- Recommendation: Replace 'Budi' with 'the user' (or the collected user_name) in SKILL.md, and make module_greeting name-neutral.
