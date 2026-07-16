# Analysis Report: /home/budi/dev/prestashop-module/.claude/skills/psm-develop

Generated: 2026-07-16 · Schema: 2

**Grade: Good**

> Good — mature and pattern-complete after 4 fix rounds, but the resume drift-gate's plan.json contract is half-wired (the lone high) and the verify loop can burn its attempt cap on pre-existing module defects.

psm-develop's spine is sound: a five-phase grow-don't-break flow with a hard approval gate, deterministic inventory/validate/reconcile scripts backed by 20 passing tests, and a headless contract whose stop statuses are cross-referenced from every gate. The primary opportunity is closing the plan.json lifecycle — the structured twin of the plan has no canonical path and its statuses are only updated in the markdown, so the 'never trust status blindly' reconcile gate can silently check nothing on resume. Secondary: the verify gate lacks a baseline diff, so a module with pre-existing cross-version defects burns its redesign attempts on errors the new feature never introduced.

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 1 |
| Medium | 6 |
| Low | 10 |

## Themes

### 1. plan.json lifecycle is half-wired

- Root cause: The structured plan artifact that feeds the deterministic --reconcile drift gate has no canonical path (its markdown twin does), and the apply step updates statuses only in the markdown — so on resume the gate either can't locate its input or runs over stale 'rencana' statuses, checks zero items, and returns ok, silently defeating the round-2 safety gate it exists to serve.
- Fix: Canonicalize the JSON twin as <module-path>/.psm-develop-plan.json (declare it in Resolution rules, use it verbatim in On Activation #3 and Rancang), and add one clause in Terapkan: when marking a function's status in the .md, update the same status in the .json — the md stays the narrative for Budi, the json the single structured source --reconcile reads.
- Findings:
  - `determinism-1` Deterministic reconcile gate reads a plan.json the prompt never locates canonically nor keeps status-synced — `SKILL.md:24 (On Activation #3), SKILL.md:43 (Rancang), SKILL.md:55 (Terapkan)`
  - `architecture-2` plan.json has no canonical path and its status lifecycle is mis-wired against --reconcile — `SKILL.md: Rancang fungsi & rencana (line 43), Terapkan (line 55), On Activation #3 (line 24)`
  - `enhancement-1` Add: pin plan.json's path and keep its statuses live, or resume reconciliation silently no-ops (working-state pattern half-wired) — `SKILL.md:43 (Rancang), SKILL.md:24 (On Activation #3), SKILL.md:55 (Terapkan)`

### 2. Resolver mirror exception is unstated

- Root cause: Resolution rules forbid {project-root}/skills/… sibling paths, yet On Activation #1 invokes the psm-setup config resolver via exactly that path — correctly, since the runtime resolver only exists in the skills/ mirror. With the exception unstated, a compliant model may 'fix' the resolver call to <skills-dir>/… and hit a nonexistent path.
- Fix: Add one exception clause to the Resolution rules bullet naming resolve-psm-config.py as the deliberate, only exception ({project-root}/skills/psm-setup/scripts/ is its runtime home); do not change the invocation path.
- Findings:
  - `architecture-1` On Activation resolver call contradicts the skill's own Resolution rule against {project-root}/skills/ sibling paths — `SKILL.md: Resolution rules (line 16) vs On Activation #1 (line 22)`
  - `leanness-2` Stripped why: skills/-mirror prohibition contradicted by On Activation #1 without explanation — `SKILL.md:16,22`

### 3. Inventory extractor has silent coverage gaps

- Root cause: ps-module-inventory.py sells its output as the insert-point map and forbids hand-parsing PHP, but its single-level parent-substring classification misses PS8/9 Symfony admin controllers and indirect ObjectModel inheritance, its table match is file-wide first-match rather than per-class, and the 'is this a real module' composite is left to prose interpretation instead of an emitted boolean.
- Fix: Extend the known-parent list to Symfony admin controller bases across 1.7/8/9 (or emit a detection:'direct-parent-only' flag), scope the table regex to each class body, and emit a derived looks_like_module boolean encoding the Gerbang target rule — each with a fixture in test-ps-module-inventory.py.
- Findings:
  - `determinism-2` Inventory classifier silently misses modern (Symfony) admin controllers and indirect ObjectModel inheritance — `scripts/ps-module-inventory.py:68-76 (build_inventory class classification)`
  - `determinism-3` Table-name association is file-wide first-match, not scoped to the ObjectModel class body — `scripts/ps-module-inventory.py:71-72`
  - `determinism-4` 'Gerbang target' emptiness check is a deterministic composite left to the prompt with an ambiguous conjunction — `SKILL.md:33 (Pahami module existing, Gerbang target)`

### 4. Verify-loop boundaries are underspecified

- Root cause: The verify gate demands an absolute tri-version pass on the whole module with a fuzzy attempt cap ('2-3') and no run-closing step: pre-existing defects in the grown module consume redesign attempts the new feature can't fix, sessions can stop at different attempt counts, and a passed run leaves uncommitted changes that guarantee the next run trips the dirty-tree warning.
- Fix: Use the early ps-static-scan output as a baseline and classify verify errors into pre-existing (surface to Budi as a scope decision without consuming verify_attempts; headless: butuh intervensi) vs introduced (redesign loop as today); fix the cap to a single number (3); after a pass, offer Budi one commit for the run's changes (headless: never commit — memlog the uncommitted state and return it).
- Findings:
  - `enhancement-2` Add: baseline-diff at the verify gate — absolute tri-version pass burns the redesign loop on pre-existing module defects — `SKILL.md:57-63 (Verifikasi)`
  - `determinism-5` Verify-loop cap is a deterministic comparison against a fuzzy constant ('2-3 percobaan') — `SKILL.md:61 (Verifikasi)`
  - `enhancement-3` Add: post-verify commit offer — the undo-net pattern is opened but never closed, so every repeat run starts dirty — `SKILL.md:53 (Terapkan), SKILL.md:65 (Verifikasi close)`

### 5. Headless success status is only implied

- Root cause: The headless contract defines gagal and butuh intervensi precisely but never names the success status, and the vocabulary deviates from the BMad complete/blocked convention — an automating caller must infer completion from the absence of stop values.
- Fix: Name the success status (selesai) in the same sentence that defines the two stop statuses, and add a half-line mapping to the BMad complete/blocked vocabulary (or adopt it family-wide) so generic callers parse one field for all three outcomes.
- Findings:
  - `enhancement-4` Add: name the headless success status — two stop statuses are canonical but 'done' is only implied — `SKILL.md:69-71 (Mode headless)`
  - `architecture-4` Headless stop statuses deviate from the BMad complete/blocked convention — `SKILL.md: Mode headless (lines 69-71)`

## Strengths

- The five-phase spine (pahami → rancang → konfirmasi → terapkan → verifikasi) matches the risk profile of mutating live modules, with a hard approval gate before any file is touched.
- Intelligence placement is largely right: deterministic inventory/--validate-plan/--reconcile scripts (20 passing tests) own the plumbing, psm-validate's JSON verdict is read as-is, and judgment calls are explicitly reserved for the model.
- Headless mode is a real contract: every interactive gate carries a matching headless annotation, assumptions flow to the memlog, and the two stop statuses are centrally defined and cross-referenced.
- The e-commerce function catalog is a well-carved standalone reference — 'what to build' here, 'how to build it safely' delegated to psm-cross-version's version-safe-patterns, with add-to-existing rules colocated at the end.
- All 22 path-scanner flags are noise against builder-owned process artifacts (.memlog.md at root, absolute paths inside .analysis/ run folders) — the skill's own content has no path defects.

## Recommendations

1. Canonicalize <module-path>/.psm-develop-plan.json and keep its statuses in sync at Terapkan so --reconcile always has a located, current input. (resolves: determinism-1, architecture-2, enhancement-1)
2. Add the resolver-path exception clause to Resolution rules (one clause; keep the invocation as written). (resolves: architecture-1, leanness-2)
3. Baseline-diff the verify gate (pre-existing vs introduced errors), fix the attempt cap at 3, and offer a post-pass commit interactively. (resolves: enhancement-2, determinism-5, enhancement-3)
4. Extend ps-module-inventory.py: Symfony admin controller bases, per-class table scoping, looks_like_module boolean — each with a test fixture. (resolves: determinism-2, determinism-3, determinism-4)
5. Name the headless success status (selesai) and map the trio to the BMad complete/blocked vocabulary. (resolves: enhancement-4, architecture-4)
6. Housekeeping: cut the inert psm-develop basename token, drop the two restated parentheticals (route through a variant eval if unsure), and log the customization decline as a memlog decision; accept the 2573-token warn. (resolves: leanness-1, leanness-3, customization-1, architecture-3)

## Experience

- **Grow an existing module** — Invoke psm-develop → config via resolver → inventory + static scan map the module → catalog offers relevant functions → plan written to <module-path>/.psm-develop-plan.md and validated against inventory (--validate-plan) → Budi approves → apply in place → psm-validate must pass 1.7/8/9 → per-version summary.
- **Resume an interrupted run** — Plan artifact detected at activation → --reconcile emits deterministic drift (applied items whose evidence vanished) → model corrects plan statuses → flow continues from last state, verify_attempts persisted across sessions.
- **Headless invocation** — Caller passes module-path, functions, versions → no interactive gates; assumptions logged to memlog → returns one-line summary + plan path + memlog path + per-version verdict, or stops with gagal / butuh intervensi.
- Headless: A genuine headless contract with two canonical stop statuses wired into every gate; its one gap is that success is unnamed and the vocabulary is family-specific rather than BMad-standard.

## Findings

### High (1)

#### determinism-1 — Deterministic reconcile gate reads a plan.json the prompt never locates canonically nor keeps status-synced

- Lens: determinism
- Location: `SKILL.md:24 (On Activation #3), SKILL.md:43 (Rancang), SKILL.md:55 (Terapkan)`
- Evidence: Resume runs `uv run scripts/ps-module-inventory.py <module-path> --reconcile <plan.json>`, and reconcile_plan() only checks items whose plan.json status is 'diterapkan'/'applied'. But the prompt says only "Tulis item rencana terstruktur ke `plan.json`" — no canonical path (the .md plan gets an explicit `<module-path>/.psm-develop-plan.md`; the JSON gets none) — and the apply step instructs status updates only into the markdown: "Tandai status tiap fungsi di `.psm-develop-plan.md` saat diterapkan." Nothing tells the model to flip status in plan.json when applying, so on resume the deterministic drift check either can't find its input or runs over stale 'rencana' statuses, checks zero items, and returns ok=true — the "Rekonsiliasi dulu, jangan percaya status buta" gate silently passes exactly when it matters (e.g. after a git-revert).
- Recommendation: Determinism leak (prompt side): the deterministic check's input contract is left to per-run improvisation. Complete the pre-pass JSON pattern end-to-end: pin a canonical path (e.g. `<module-path>/.psm-develop-plan.json`, named in Resolution rules and used verbatim in On Activation #3), and make the Terapkan step update `status` in that JSON as the single structured source of truth (the .md keeps narrative/rationale, or is rendered from it). Then reconcile has one located, current input and the drift check has one correct answer per run.

### Medium (6)

#### architecture-1 — On Activation resolver call contradicts the skill's own Resolution rule against {project-root}/skills/ sibling paths

- Lens: architecture
- Location: `SKILL.md: Resolution rules (line 16) vs On Activation #1 (line 22)`
- Evidence: Resolution rules state: 'Rujuk sibling lewat `<skills-dir>/psm-validate/…`, bukan `{project-root}/skills/…` — jangan bergantung pada mirror `skills/` di root project', naming psm-* siblings explicitly. The very next section invokes `uv run {project-root}/skills/psm-setup/scripts/resolve-psm-config.py` — a psm-* sibling via the forbidden pattern. The call itself is correct by design (verified: resolve-psm-config.py exists only at /home/budi/dev/prestashop-module/skills/psm-setup/scripts/, NOT under .claude/skills/psm-setup/scripts/, and all four sibling skills use the identical invocation), but the rule as written mis-describes the one exception the skill depends on. A model that 'complies' with the stated rule and rewrites the call to `<skills-dir>/psm-setup/scripts/...` — e.g. during resume or headless self-correction — hits a nonexistent path and config load fails. This is the rule-vs-instruction misalignment the architecture lens names as the most dangerous kind, because it reads correct on a casual pass.
- Recommendation: Add one exception clause to the Resolution rules bullet, e.g.: 'Pengecualian: resolver config psm-setup memang tinggal di `{project-root}/skills/psm-setup/scripts/` (lokasi runtime) — panggil persis seperti tertulis di On Activation #1.' Do not change the invocation path; it is the only one that resolves.

#### architecture-2 — plan.json has no canonical path and its status lifecycle is mis-wired against --reconcile

- Lens: architecture
- Location: `SKILL.md: Rancang fungsi & rencana (line 43), Terapkan (line 55), On Activation #3 (line 24)`
- Evidence: Three sections fail to close a produce/consume loop. (1) 'Tulis item rencana terstruktur ke `plan.json`' gives a bare filename; per the skill's own Resolution rules, bare paths resolve from the installed skill directory — so the working artifact literally lands inside the installed skill, unlike its markdown twin which gets an explicit `<module-path>/.psm-develop-plan.md`. (2) Terapkan directs status updates to the .md only ('Tandai status tiap fungsi di `.psm-develop-plan.md` saat diterapkan'), while ps-module-inventory.py --reconcile reads `status: diterapkan` from the JSON (verified in reconcile_plan(), scripts/ps-module-inventory.py:139). (3) On Activation #3 runs `--reconcile <plan.json>` at resume without saying where plan.json comes from in a fresh session. If a stale plan.json (statuses never updated past 'direncanakan') is reused at resume, reconcile finds zero 'diterapkan' items, returns ok:true, and the drift check silently no-ops — quietly defeating the stated 'Rekonsiliasi dulu, jangan percaya status buta' gate. Recoverable (a model reading the .md first can regenerate the json with current statuses), which is why this is medium rather than high, but the wiring leaves the safety gate's correctness to inference.
- Recommendation: Canonicalize the JSON twin to `<module-path>/.psm-develop-plan.json` wherever plan.json is mentioned, and close the lifecycle with one clause: either 'saat menandai status di .md, perbarui juga .psm-develop-plan.json' in Terapkan, or 'saat resume, regenerasi plan.json dari status terkini di .psm-develop-plan.md sebelum --reconcile' in On Activation #3.

#### enhancement-1 — Add: pin plan.json's path and keep its statuses live, or resume reconciliation silently no-ops (working-state pattern half-wired)

- Lens: enhancement
- Location: `SKILL.md:43 (Rancang), SKILL.md:24 (On Activation #3), SKILL.md:55 (Terapkan)`
- Evidence: The structured-working-artifact pattern is split across two files without a sync rule: 'Rancang' writes structured items to a bare `plan.json` (no location given), 'Terapkan' marks per-function status only in `.psm-develop-plan.md`, yet resume runs `--reconcile <plan.json>` and reconcile_plan() only checks items whose json status is 'diterapkan'. A plan.json persisted pre-apply carries status 'rencana' for everything, so the drift guard — added in round 2 precisely so resume never trusts status blindly — returns ok having checked nothing.
- Recommendation: Pin the machine companion to a named path beside the human plan (e.g. `<module-path>/.psm-develop-plan.json`, dotfile so it can't ship in a module zip) and add one clause at Terapkan: status updates are written to both artifacts (md for Budi, json for --reconcile). Alternatively state at resume that plan.json is regenerated from the md's current statuses before reconciling; either closes the desync, the first is cheaper per run.

#### enhancement-2 — Add: baseline-diff at the verify gate — absolute tri-version pass burns the redesign loop on pre-existing module defects

- Lens: enhancement
- Location: `SKILL.md:57-63 (Verifikasi)`
- Evidence: Missing pattern: regression gate against a captured baseline. 'Pahami' already runs ps-static-scan 'supaya fungsi baru tak menambah masalah lama', but Verifikasi discards that intent: it demands absolute psm-validate pass on the whole module in 1.7/8/9. A running 1.7 module being grown (the skill's stated target: 'sudah ada dan berjalan', not 'sudah lolos validasi') will fail on pre-existing PS8/9 removals the new function never touched; the loop text ('rancang ulang dari artefak') redesigns the new function, which cannot fix them, so 2-3 verify_attempts are consumed and the handoff mis-attributes failure to the feature. psm-validate's JSON has no baseline notion of its own (confirmed in its Vonis section), so the diff must live here.
- Recommendation: Keep the early static-scan output as the baseline. At Verifikasi, classify remaining errors: present in baseline = pre-existing, surface to Budi as a scope decision ('port dulu via psm-cross-version?') without consuming verify_attempts (headless: `butuh intervensi` with reason naming the pre-existing errors); absent from baseline = introduced, enters the redesign loop as today. One or two sentences; the tri-version bar stays for introduced errors.

#### enhancement-3 — Add: post-verify commit offer — the undo-net pattern is opened but never closed, so every repeat run starts dirty

- Lens: enhancement
- Location: `SKILL.md:53 (Terapkan), SKILL.md:65 (Verifikasi close)`
- Evidence: Half-applied pattern: the clean-working-tree gate before apply is the undo net, but nothing after tri-version pass suggests committing, and the Claude Code default is to never commit unasked — so run 1's applied changes are guaranteed uncommitted. For a skill whose premise is a module that grows across runs, run 2 always trips the dirty-tree warning, and if Budi proceeds anyway the undo net can no longer separate run-1 from run-2 changes, degrading the safety story the gate exists for.
- Recommendation: After the per-version pass summary, add one clause: interactively offer Budi a single commit for this run's changes (message naming the functions added) so the next run's undo net is clean; headless, do not commit — append a memlog note that the tree holds uncommitted applied changes and include that in the return so the caller decides. Loses nothing; completes the pattern.

#### determinism-2 — Inventory classifier silently misses modern (Symfony) admin controllers and indirect ObjectModel inheritance

- Lens: determinism
- Location: `scripts/ps-module-inventory.py:68-76 (build_inventory class classification)`
- Evidence: Classification is a single-level parent-substring match: `if "ObjectModel" in parent ... elif "ModuleFrontController" in parent ... elif "ModuleAdminController" in parent`. A PS 8/9-style controller `class FooController extends FrameworkBundleAdminController` (or PS9 `PrestaShopAdminController`) matches nothing, and an entity extending a concrete subclass (`class MyProduct extends Product`) is not counted as an ObjectModel. The skill sells this output as the insert-point map ("Ini peta titik sisip") and forbids the fallback ("jangan parse PHP mentah dengan tangan"), so for a common 8/9 module shape the model plans over a map that silently omits existing controllers/entities.
- Recommendation: This is the lens's critical-example shape — a string-match classifier silently mishandling a common input shape — kept at medium because it under-reports rather than gates. The fix stays deterministic (extraction has one right answer per input): extend the known-parent list to the Symfony admin controller base classes across 1.7/8/9, add a fixture to test-ps-module-inventory.py for each, and either detect one level of indirect inheritance or state the direct-inheritance limitation in the JSON output (e.g. `"detection": "direct-parent-only"`) so the model knows when the map may be partial.

### Low (10)

#### determinism-3 — Table-name association is file-wide first-match, not scoped to the ObjectModel class body

- Lens: determinism
- Location: `scripts/ps-module-inventory.py:71-72`
- Evidence: Inside the per-class loop, `tm = table_re.search(text)` searches the whole file and attaches the first `'table' => '...'` hit to every ObjectModel class found in that file. In a legacy multi-class file (or a file with an earlier non-$definition `'table' =>` array), every class gets the same — possibly wrong — table. That wrong value feeds reconcile_plan's `add_tables` set, producing false drift verdicts.
- Recommendation: Deterministic parsing nicety: scope the table search to the region after each class match (e.g. search `text[cm.end():next_class_start]` or the `$definition` block following the class), and add a two-classes-one-file fixture to the test. Passes the determinism test — same input, one correct table per class — so it belongs in the script, done precisely.

#### determinism-4 — 'Gerbang target' emptiness check is a deterministic composite left to the prompt with an ambiguous conjunction

- Lens: determinism
- Location: `SKILL.md:33 (Pahami module existing, Gerbang target)`
- Evidence: "Bila `<module-path>` bukan module berisi — folder hilang/kosong/tanpa `.php`, atau inventaris tak menemukan versi/hook/ObjectModel — arahkan Budi ke psm-scaffold" — every clause is a check over fields the script already emits (file_count, module_version, registered_hooks, object_models), and the phrasing leaves open whether version/hook/ObjectModel must all be missing or any one. Different runs can gate the same module differently.
- Recommendation: Determinism leak, cheap to absorb but cheaper to settle: have build_inventory emit a derived boolean (e.g. `"looks_like_module": bool` with the exact rule, per the pre-pass JSON pattern) and let the prompt keep only the judgment half — deciding to redirect to psm-scaffold. Unit-testable with an empty-dir fixture (signal verbs present: 'check structure', 'detect').

#### determinism-5 — Verify-loop cap is a deterministic comparison against a fuzzy constant ('2-3 percobaan')

- Lens: determinism
- Location: `SKILL.md:61 (Verifikasi)`
- Evidence: "Batasi loop rancang-ulang → apply → validate ke 2-3 percobaan. Simpan `verify_attempts: N` di `.psm-develop-plan.md`" — the counter is persisted precisely so the cap survives sessions, but the threshold itself is a range, so session A may stop at 2 while session B runs a third attempt. Comparing a persisted counter to a limit has one correct answer only if the limit is one number.
- Recommendation: Not a script candidate — the comparison is trivially absorbable — but the determinism test fails on the constant, not the operation. Fix in prose: pick a single cap (e.g. 3) so the persisted `verify_attempts` gate behaves identically across resumed sessions.

#### enhancement-4 — Add: name the headless success status — two stop statuses are canonical but 'done' is only implied

- Lens: enhancement
- Location: `SKILL.md:69-71 (Mode headless)`
- Evidence: Headless-return pattern is nearly complete: `gagal` and `butuh intervensi` are defined as the two stop statuses with return shapes, but the success case is described only as 'ringkasan satu baris + paths + status lolos per versi' with no machine-readable overall status, so an automating caller must infer completion from the absence of the stop values.
- Recommendation: Name the third status explicitly (e.g. `selesai`) in the same sentence that defines the other two, so the caller parses one field for all three outcomes. One word plus a clause.

#### architecture-3 — SKILL.md in the warn tier: 2573 tokens against desired 2000 (hard 3000)

- Lens: architecture
- Location: `SKILL.md (whole file)`
- Evidence: Pre-pass measures SKILL.md at 2573 tiktoken tokens. Against the resolved org budget (desired 2000 / hard 3000) this is the between-desired-and-budget tier, which per skill-quality-principles warrants a warn naming the most liftable section, not a block. No clean carve exists: every section is core-path except 'Mode headless' (~230 tokens), and its two stop statuses (`gagal`, `butuh intervensi`) are cross-referenced inline from four gate annotations, so carving it would break gate-to-status coherence for below-threshold savings.
- Recommendation: Do not carve. If trimming is wanted, apply the canon's line tests to the Overview (the psm-scaffold differentiation sentence largely repeats what the Gerbang target section already enforces operationally). Otherwise accept the warn — the file is under hard budget.

#### architecture-4 — Headless stop statuses deviate from the BMad complete/blocked convention

- Lens: architecture
- Location: `SKILL.md: Mode headless (lines 69-71)`
- Evidence: The headless contract defines `gagal` and `butuh intervensi` as its stop statuses and names no success status, where skill-quality-principles specify `status` is `complete` or `blocked` with a one-line reason on blocked. The deviation is self-defined, internally consistent (every interactive gate carries a matching headless annotation), and the substance of the convention — memlog absorbs assumptions, return carries paths + reason — is fully honored. It only bites if a BMad-generic orchestrator that expects the standard vocabulary ever calls psm-develop; the psm-family callers read the skill and get the contract.
- Recommendation: Either adopt the standard keys with Indonesian detail text (`blocked` + reason 'butuh intervensi: …' / 'gagal: …', `complete` on success), or add a half-line mapping so generic callers can translate. Family-wide consistency matters more than this one file — change it across the psm skills or not at all.

#### leanness-1 — Inert token definition: `psm-develop` → basename never used as a path

- Lens: leanness
- Location: `SKILL.md:17 (Resolution rules)`
- Evidence: The Resolution rules define `psm-develop` → basename direktori skill, but no path in SKILL.md or references/ecommerce-function-catalog.md uses `psm-develop` as a path token — the only occurrences are the title, the frontmatter name, and the `.psm-develop-plan.md` filename, none of which need the rule. memlog.py takes --workspace/--path, not a skill-name token, so the headless memlog call does not consume it either. The identical line appears in psm-validate and psm-cross-version SKILL.md files, so this is sibling boilerplate carried in rather than wiring this file needs. Fails the canon's core test: it changes no move of the reader.
- Recommendation: Cut the line. (If the parent wants tree-wide consistency, the same cut applies to the sibling skills, but judged on this file it is a dead definition.)

#### leanness-2 — Stripped why: skills/-mirror prohibition contradicted by On Activation #1 without explanation

- Lens: leanness
- Location: `SKILL.md:16,22`
- Evidence: Line 16 instructs 'Rujuk sibling lewat `<skills-dir>/psm-validate/…`, bukan `{project-root}/skills/…` — jangan bergantung pada mirror `skills/` di root project', then line 22 commands exactly that mirror path: `uv run {project-root}/skills/psm-setup/scripts/resolve-psm-config.py`. The resolver is a deliberate exception (it is the runtime resolver that lives in the project mirror), but nothing in the file says so. A reader whose whole world is these files sees a rule and a command that contradict each other, and may 'correct' the resolver path to `<skills-dir>/…` or distrust the mirror rule elsewhere. Both paths currently resolve (resolve-psm-config.py exists in both trees), so this is confusion rather than a wrong action today. Per the canon (test 3), a stripped why is under-writing, not leanness.
- Recommendation: Add one clause naming the exception, e.g. on line 22: '…resolve-psm-config.py (resolver sengaja dipanggil dari mirror runtime skills/psm-setup/scripts — satu-satunya pengecualian atas aturan mirror di Resolution rules)'. One clause, not a paragraph.

#### leanness-3 — Facts restated across sections: add-to-existing rules and scaffold distinction each stated twice

- Lens: leanness
- Location: `SKILL.md:33,55`
- Evidence: Two instances of the canon's 'facts restated across sections' shape. (1) Line 55 (Terapkan) restates the reference's closing rules inline: '(upgrade script untuk hook/tabel baru, cabang versi eksplisit untuk area legacy/modern, GDPR untuk data pelanggan)' — the same rules are already mandated at line 39 ('plus aturan menambah-ke-existing di bagian akhirnya — patuhi itu') and live verbatim as the final section of references/ecommerce-function-catalog.md; the missing-upgrade case is additionally caught deterministically by `--validate-plan` (objectmodel_change_without_upgrade). (2) Line 33 (Gerbang target) restates the Overview's scaffold distinction: '(skill ini menumbuhkan module existing, bukan membuat kerangka baru)' — line 10 already carries this with its why. Roughly 35-40 tokens total whose absence the surrounding mandates already cover.
- Recommendation: Drop both parentheticals: line 55 becomes '…patuhi **Aturan menambah-ke-existing** di `references/ecommerce-function-catalog.md`. Tandai status…'; line 33 becomes 'arahkan Budi ke **psm-scaffold** dan berhenti; jangan merancang di atas ketiadaan.' Route to variant eval to confirm no loss.
- Proposed smallest: Line 55: 'Setelah disetujui, terapkan sesuai rencana pada module di tempat. Tambah, jangan rusak — patuhi **Aturan menambah-ke-existing** di `references/ecommerce-function-catalog.md`. Tandai status tiap fungsi di `.psm-develop-plan.md` saat diterapkan.' Line 33: '…arahkan Budi ke **psm-scaffold** dan berhenti; jangan merancang di atas ketiadaan.'
- Predicted delta: Likely nothing: the add-to-existing rules are mandated at design time and enforced in the reference the model must load, with `--validate-plan` as a deterministic backstop for the upgrade-script case, and the scaffold distinction already lives in the Overview with its why. Worst case is a marginally higher chance of a forgotten GDPR/version-branch consideration at apply time many turns after the reference was read. Route to variant eval to confirm.

#### customization-1 — Customization decline not logged as a memlog decision

- Lens: customization
- Location: `.claude/skills/psm-develop/.memlog.md`
- Evidence: customize-toml-guide.md mandates that the once-per-build customization decision be logged in the memlog as a decision ('Whatever is decided, log it in the memlog as a decision'). The memlog carries (decision) entries for the function catalog and the plan artifact, but no entry recording that end-user customization was declined, even though the skill consistently ships fixed (no customize.toml, no resolver step, hardcoded paths throughout). The sibling psm-agent-expert documents its decline explicitly ('Override surface declined: ...'), so the family convention exists but psm-develop's build log leaves the question open for future rebuild rounds.
- Recommendation: Append one (decision) line to .claude/skills/psm-develop/.memlog.md recording that customization was declined and why (single-operator psm family; config flows through the psm section of {project-root}/_bmad/config.yaml read at activation; catalog extension flows through the {project-root}/_bmad/psm/memory/ecommerce/function-catalog.md augment), so a later round or rebuild treats the absent customize.toml as a conscious choice rather than an omission.
