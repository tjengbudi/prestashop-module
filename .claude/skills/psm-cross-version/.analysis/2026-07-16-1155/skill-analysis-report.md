# Analysis Report: /home/budi/dev/prestashop-module/.claude/skills/psm-cross-version

Generated: 2026-07-16 · Schema: 2

**Grade: Poor**

> One root cause dominates: the skill's analysis engine, validation-gate pointer, and rule-data path all resolve into the stale skills/ tree while the live tree (.claude/skills/) has moved on — a three-line repoint clears the critical and half the high findings; the remaining substance is headless failure semantics and an unverified undo net.

The skill's plan→confirm→apply→verify spine is sound, lean (1574 tokens, zero waste patterns), and delegates all deterministic work to existing engines without duplicating a single rule. But those delegation pointers target {project-root}/skills/psm-validate — the stale scaffold tree — and the live copies have verifiably diverged, so the workflow's declared factual foundation is wired to an outdated engine. Fixing the three pointers plus adopting the sibling psm-develop headless conventions (typed stop statuses, memlog init, undo-net guard) would return this skill to excellent.

| Severity | Count |
| --- | --- |
| Critical | 1 |
| High | 4 |
| Medium | 6 |
| Low | 7 |

## Themes

### 1. Stale-tree pointers: the deterministic foundation resolves to outdated copies

- Root cause: The live psm skill tree moved to {project-root}/.claude/skills/ but psm-cross-version still points its analysis engine (ps-static-scan.py), its validation-gate reference (psm-validate SKILL.md), and its rule-data path (ps-rules.json) at {project-root}/skills/psm-validate — a stale scaffold. The scanner and gate copies have verifiably diverged (diff confirmed: different default versions 9.0 vs 9.1, different vendor-exclusion walk; live psm-validate gained the E2E browser layer), so the plan is derived from one engine's facts and gated against another's, while the prompt forbids reconciling by hand.
- Fix: Repoint the three references to the live tree: SKILL.md:27 and references/version-safe-patterns.md:9 → {project-root}/.claude/skills/psm-validate/..., and SKILL.md:41 → invoke psm-validate by skill name (or point at {project-root}/.claude/skills/psm-validate/SKILL.md). Leave SKILL.md:20's skills/psm-setup/scripts/resolve-psm-config.py untouched — that is the live runtime resolver, the sole live exception in skills/.
- Findings:
  - `architecture-1` Analysis engine resolves to stale copy of ps-static-scan.py — `SKILL.md:27 (## Analisis: peta risiko per versi)`
  - `architecture-2` Mandatory verification gate routes to stale psm-validate SKILL.md — `SKILL.md:41 (## Verifikasi (gerbang wajib))`
  - `architecture-3` Reference file points ps-rules.json at the stale tree (drift-prone) — `references/version-safe-patterns.md:9`
  - `determinism-1` Analysis and verification phases bind to two divergent copies of the deterministic engine — `SKILL.md:27 (Analisis) + references/version-safe-patterns.md:9 (ps-rules.json path); contrast SKILL.md:41 (Verifikasi)`

### 2. Headless mode defines only the success shape

- Root cause: Mode headless removes every interactive gate but names no failure semantics: no typed stop statuses, no verify-loop cap (a module that cannot go green loops plan→apply→validate forever), no memlog location or init rule (memlog.py append crashes on a nonexistent file), and no distinct status for a module that is already safe. Sibling psm skills carry all of these as named conventions (psm-develop: 'gagal'/'butuh intervensi' + cap; psm-optimize: 'sudah-ramping' no-op status).
- Fix: Mirror the sibling conventions in Mode headless: adopt psm-develop's two stop statuses plus a replan cap (e.g. two cycles), state that the memlog lives at <module-path>/.memlog.md beside .psm-cross-plan.md with init-if-absent, and short-circuit a clean scan straight to the validate gate returning a distinct 'sudah-aman' status.
- Findings:
  - `enhancement-1` Add typed stop statuses and a verify-loop cap to headless mode — `SKILL.md:39-45 (## Verifikasi + ## Mode headless)`
  - `enhancement-3` Add memlog workspace and init to headless mode — `SKILL.md:45 (## Mode headless)`
  - `enhancement-5` Opportunity: clean-scan short-circuit with a distinct no-op status — `SKILL.md:25-33 (## Analisis + ## Rencana perubahan)`

### 3. Irreversible apply rests on an assumed, not verified, undo net

- Root cause: Terapkan rewrites module source in place. Interactively the skill merely assumes Budi uses git ('asumsikan Budi memakai git untuk pembatalan'); in headless there is no operator, no approval gate, and no check at all — a module outside git or with a dirty tree gets rewritten with no undo path, contradicting the Overview's unqualified 'never apply without an approved plan' invariant.
- Fix: Before the first file edit, check git status on <module-path>: dirty or non-git interactively → warn and offer a folder backup; headless → auto-backup and memlog the path, or stop with 'butuh intervensi' (copy psm-develop's clause nearly verbatim). Qualify the Overview invariant with one clause naming the headless delegation of approval.
- Findings:
  - `enhancement-2` Add an undo-net guard before Terapkan — `SKILL.md:35-37 (## Terapkan)`
  - `architecture-4` Overview's absolute 'never apply without approved plan' contradicted by headless mode — `SKILL.md:10 (Overview) vs SKILL.md:45 (Mode headless)`

### 4. The closing checklist duplicates the engine and leaks two hand-checks

- Root cause: The 'Checklist keluaran cross-version' section restates rules the model just read ~100 lines earlier and that the mandatory psm-validate gate checks mechanically — except two items (ps_versions_compliancy range correctness, composer prepend-autoloader) that no engine rule covers, silently demoting deterministic checks to per-run hand-verification. Only one fact in the checklist (index.php stub per folder) exists nowhere else.
- Fix: Delete the checklist section, relocate the index.php stub fact into the composer.json & autoload section, and extend psm-validate's ps-rules.json with the two missing rules (prepend-autoloader === false; compliancy-range expect variant) so coverage moves engine-side; keep SKILL.md's psm-validate pass as the single definition of done.
- Findings:
  - `leanness-1` Closing checklist restates the file it ends and the psm-validate gate — `references/version-safe-patterns.md:## Checklist keluaran cross-version (lines 104-113)`
  - `determinism-2` Cross-version checklist leaves two unit-testable checks to the model that the delegated engine does not perform — `references/version-safe-patterns.md:104-113 (Checklist keluaran cross-version)`

## Strengths

- The plan→confirm→apply→verify spine with psm-validate as the single mandatory gate is stated once at point of use and never softened — the definition of done is unambiguous across interactive and headless paths.
- Zero duplication of deterministic assets: rule data, scan logic, and config resolution are all borrowed from their owning skills (ps-rules.json, ps-static-scan.py, resolve-psm-config.py), and the customization lens confirms config.yaml-via-resolver is a sound single mechanism with no parallel config surface.
- Intelligence placement is right-way-round: scan facts are declared non-negotiable ('jangan menilai ulang dengan tangan') while genuinely contextual choices (Mail::send vs custom, ObjectModel vs Doctrine) stay model judgment guided by the pattern catalog.
- The .psm-cross-plan.md working artifact carries resume and failure-writeback ('tulis temuan kembali... jangan analisis ulang dari nol'), so validate failures iterate the plan instead of restarting analysis.
- Prose is lean and in budget: 1574 SKILL.md tokens, 0 waste patterns, 0 back-references, and the pattern catalog carries non-inferable institutional knowledge with its why attached.

## Recommendations

1. Repoint the three psm-validate references from {project-root}/skills/ to the live {project-root}/.claude/skills/ tree (SKILL.md:27, SKILL.md:41, references/version-safe-patterns.md:9), leaving the live resolve-psm-config.py reference untouched — three one-line edits that clear the critical, two highs, and a medium. (resolves: architecture-1, architecture-2, architecture-3, determinism-1)
2. Adopt the sibling psm-develop/psm-optimize headless conventions in Mode headless: typed stop statuses ('gagal', 'butuh intervensi') with a replan cap, memlog location + init-if-absent clause, and a 'sudah-aman' no-op status for clean scans. (resolves: enhancement-1, enhancement-3, enhancement-5)
3. Add the undo-net guard before Terapkan (git-status check → warn/backup interactively, auto-backup + memlog or stop in headless) and qualify the Overview's absolute approval invariant for headless delegation. (resolves: enhancement-2, architecture-4)
4. Delete the closing checklist in references/version-safe-patterns.md, move its one unique fact (index.php stub per folder) into the composer section, and extend ps-rules.json engine-side with the two rules the checklist currently hand-checks. (resolves: leanness-1, determinism-2)
5. Add a wrong-intent routing line (no existing module → psm-scaffold, stop) and sharpen the description's first clause toward conversion ('Ubah module PrestaShop existing...') to reduce trigger collision with psm-scaffold. (resolves: enhancement-4)
6. Minor polish pass: collapse the version_compare code block to two prose clauses, cut the Overview's restated gates sentence, convert On Activation numbering to bullets, add the missing why to the wildcard-exclude WAJIB, restore the {skill-name} placeholder form. (resolves: leanness-2, leanness-3, leanness-4, leanness-5, architecture-5)

## Experience

- **Interactive conversion (primary)** — Budi invokes with a module path → config resolved via psm-setup resolver → ps-static-scan builds the per-version risk map → per-version change plan written to .psm-cross-plan.md → Budi approves → version-safe patterns applied → psm-validate gates all three versions → summary of changes per area and pass status per version.
- **Resume after interruption or validate failure** — Re-invocation finds .psm-cross-plan.md beside the module and continues from the artifact; validate failures are written back into the plan as new/updated changes and redesigned from there — never re-analyzed from scratch.
- **Headless (called by workflow or psm-agent-expert)** — Module path and versions come from arguments; no interactive gates; assumptions logged to memlog; returns a one-line summary + .psm-cross-plan.md path + memlog path + per-version pass status.
- Headless: Headless runs end-to-end without gates and logs assumptions to a memlog, but defines only the success shape — no typed failure statuses, no verify-loop cap, no memlog init rule, and no no-op status for an already-safe module.

## Findings

### Critical (1)

#### architecture-1 — Analysis engine resolves to stale copy of ps-static-scan.py

- Lens: architecture
- Location: `SKILL.md:27 (## Analisis: peta risiko per versi)`
- Evidence: The section runs `uv run {project-root}/skills/psm-validate/scripts/ps-static-scan.py` and declares the output 'fakta deterministik; jangan menilai ulang dengan tangan'. The live psm tree is {project-root}/.claude/skills/; skills/psm-validate/scripts/ps-static-scan.py is verified by diff to DIFFER from the live scanner (stale copy dated Jul 8, live updated Jul 13). Every downstream stage — plan, Budi's approval, irreversible source edits — consumes this risk map, and the skill forbids second-guessing it, so a stale engine silently corrupts the factual basis of the whole workflow with no name-resolution safety net (it is a direct script invocation, not a Skill-tool call).
- Recommendation: Repoint line 27 to the live tree: `{project-root}/.claude/skills/psm-validate/scripts/ps-static-scan.py`. Do NOT change line 20's `{project-root}/skills/psm-setup/scripts/resolve-psm-config.py` in the same sweep — that one correctly targets the live runtime resolver, the sole live exception in skills/.

### High (4)

#### architecture-2 — Mandatory verification gate routes to stale psm-validate SKILL.md

- Lens: architecture
- Location: `SKILL.md:41 (## Verifikasi (gerbang wajib))`
- Evidence: The gate says 'lihat `{project-root}/skills/psm-validate/SKILL.md`' — verified to differ from the live .claude/skills/psm-validate/SKILL.md (stale: 5.5KB, Jun 25; live: 9.7KB, Jul 14, which includes the later-built E2E browser layer). The Overview promises 'tidak pernah menyatakan selesai sebelum lolos psm-validate di 1.7.x + 8.x + 9.x'; an agent that follows this pointer and executes the outdated validation procedure certifies less than the live gate requires, yielding a false 'selesai'. Partially mitigated because invoking psm-validate by skill name resolves to the live skill — the defect fires when the agent reads the referenced file, which the line explicitly invites.
- Recommendation: Repoint to `{project-root}/.claude/skills/psm-validate/SKILL.md`, or drop the file pointer entirely and instruct invocation of the psm-validate skill by name so name resolution always lands on the live definition.

#### determinism-1 — Analysis and verification phases bind to two divergent copies of the deterministic engine

- Lens: determinism
- Location: `SKILL.md:27 (Analisis) + references/version-safe-patterns.md:9 (ps-rules.json path); contrast SKILL.md:41 (Verifikasi)`
- Evidence: Analisis invokes `uv run {project-root}/skills/psm-validate/scripts/ps-static-scan.py` and declares its output 'Ini fakta deterministik; jangan menilai ulang dengan tangan', but that path is the stale scaffold copy — verified diff vs the live .claude/skills/psm-validate engine: default `--versions` 1.7.8,8.1,9.0 vs 9.1, different vendor-exclusion file walk (`part == "vendor"` vs substring `"vendor/"`), different module_path emission. Verifikasi then calls psm-validate as a skill, whose bare paths resolve to the LIVE engine. So the plan is derived from one engine's facts and gated against another's, while the prompt forbids reconciling by hand ('jangan menilai ulang', 'jangan analisis ulang dari nol'). ps-rules.json copies are identical today, which caps current blast radius, but nothing guards the drift.
- Recommendation: Determinism defect at the delegation boundary: a deterministic fact source must be single-sourced or the 'trust the scan' contract is void — same input must yield the same facts at analysis and at the validate gate. Point both phases at one canonical engine+ruleset location (the concrete path/tree correction is the paths/architecture lane's to specify; this lane's requirement is one engine, not which tree). The explicit `--versions <target>` argument mitigates the default-version divergence but not the file-walk or future rule drift.

#### enhancement-1 — Add typed stop statuses and a verify-loop cap to headless mode

- Lens: enhancement
- Location: `SKILL.md:39-45 (## Verifikasi + ## Mode headless)`
- Evidence: Pattern: headless return contract (skill-quality-principles 'Headless mode': status complete|blocked with reason; sibling precedent psm-develop SKILL.md:71 defines 'gagal' and 'butuh intervensi' including 'cap verify tercapai'). psm-cross-version's headless return names only 'ringkasan satu baris + path plan + path memlog + status lolos per versi'. The Verifikasi section loops failures back into .psm-cross-plan.md with no iteration cap, and headless removes all confirmation gates — a module that cannot go green loops plan→apply→validate indefinitely with no defined exit. Unrecoverable failures have no named shape either: if ps-static-scan.py or psm-validate errors, the skill forbids both hand-analysis ('jangan menilai ulang dengan tangan') and declaring done without green, boxing the model with no legal move.
- Recommendation: Adopt psm-develop's two stop statuses in Mode headless: 'gagal' (unrecoverable — scan/validate engine errors, target not a module) returns status + one-line reason + memlog path; 'butuh intervensi' (verify-loop cap reached, e.g. two replan cycles without going green) returns status + plan path + memlog so the caller decides. One or two sentences, mirroring the sibling wording.

#### enhancement-2 — Add an undo-net guard before Terapkan

- Lens: enhancement
- Location: `SKILL.md:35-37 (## Terapkan)`
- Evidence: Pattern: undo-net guard, already a named convention in sibling psm-develop SKILL.md:53 (verify clean git working tree before touching files; headless: auto-backup + memlog the path, or stop with 'butuh intervensi'). psm-cross-version performs the same shape of irreversible in-place source rewriting but only assumes the net exists: 'asumsikan Budi memakai git untuk pembatalan (sebutkan ini bila belum jelas)' — an assumption, not a check. In headless there is no operator and no gate, so a module outside git (or with a dirty tree) gets rewritten with no undo path.
- Recommendation: Before the first file edit, check `git status` on <module-path>: dirty or non-git interactively → warn and offer a folder backup; headless → create the backup automatically and memlog its path, or stop with 'butuh intervensi'. Copy the psm-develop clause nearly verbatim to keep the module convention uniform.

### Medium (6)

#### architecture-3 — Reference file points ps-rules.json at the stale tree (drift-prone)

- Lens: architecture
- Location: `references/version-safe-patterns.md:9`
- Evidence: The carved catalog directs detection to `{project-root}/skills/psm-validate/assets/ps-rules.json`. That file is verified identical in both trees today, so nothing breaks yet — but rule updates land in the live .claude/skills/ tree, and this pointer will silently drift the next time ps-rules.json changes. Same wrong-tree convention as architecture-1/2.
- Recommendation: Repoint to `{project-root}/.claude/skills/psm-validate/assets/ps-rules.json` in the same fix pass as architecture-1 and architecture-2.

#### determinism-2 — Cross-version checklist leaves two unit-testable checks to the model that the delegated engine does not perform

- Lens: determinism
- Location: `references/version-safe-patterns.md:104-113 (Checklist keluaran cross-version)`
- Evidence: Checklist items '`ps_versions_compliancy` terisi range yang benar' and 'composer `prepend-autoloader: false`, autoload benar' gate the module being 'dianggap cross-version-safe', but ps-rules.json has no composer.json rule at all, and its struct-compliancy rule checks presence only (`expect: present`), not range correctness against the target versions. Every other checklist item (forbidden deps, removed APIs/hooks/constants, index.php per folder, Smarty escape) is engine-covered; these two fall back to the model hand-verifying a JSON key equality and a version-range comparison on every run — both pass the determinism test (identical input → identical output, trivially unit-testable).
- Recommendation: Determinism leak in the prompt layer; the fix is a script-side rule, not a new script: extend psm-validate's ps-rules.json with a composer structure rule (prepend-autoloader === false) and a compliancy-range expect variant — scan_structure_rule already provides the machinery — then let the checklist cite scan coverage instead of implying hand-checks. Signal verbs present: 'terisi range yang benar' (validate against expected), 'autoload benar' (check structure). Note the transformation-planning side is correctly placed as judgment: the deterministic finding→fix join already lives in ps-rules.json `fix` fields, and the remaining pattern choices ('prefer Mail::send bila cukup', 'ObjectModel bila module sederhana') genuinely turn on context.

#### enhancement-3 — Add memlog workspace and init to headless mode

- Lens: enhancement
- Location: `SKILL.md:45 (## Mode headless)`
- Evidence: Pattern: memlog workspace rule (working-state-patterns.md: the log sits beside the primary artifact; init creates it). The headless section says append assumptions 'via memlog.py append' and promises 'path memlog' in the return, but never names where the memlog lives or that it must exist first. Verified in {project-root}/_bmad/scripts/memlog.py: append requires --workspace|--path and does path.read_text() — the first append against a nonexistent file raises an unhandled FileNotFoundError, so a headless run crashes or improvises a location the caller cannot predict.
- Recommendation: One clause: memlog lives at <module-path>/.memlog.md beside .psm-cross-plan.md — 'init bila belum ada, append selanjutnya' — and that is the path returned to the caller.

#### enhancement-4 — Opportunity: redirect the no-existing-module arrival to psm-scaffold

- Lens: enhancement
- Location: `SKILL.md:3 (description) and SKILL.md:18-23 (## On Activation)`
- Evidence: Pattern: wrong-intent routing (the accident-arrival user walk). The description leads with 'Buat module PrestaShop kompatibel 1.7/8/9 sekaligus' and trigger 'buat module compatible 1.7 8 9' — 'buat' reads as create-new, but the skill only converts an existing module ('Ubah satu module PrestaShop existing'). A user who triggers it wanting a new module dead-ends at 'tentukan module yang dikerjakan (path folder)' with no route to psm-scaffold, whose triggers ('bikin module PrestaShop baru cross-version') overlap this phrasing.
- Recommendation: One line in On Activation step 2: bila tidak ada module existing (Budi ingin module baru), arahkan ke psm-scaffold dan berhenti. Optionally sharpen the description's first clause toward conversion ('Ubah module PrestaShop existing jadi kompatibel 1.7/8/9 sekaligus') to reduce trigger collision.

#### enhancement-5 — Opportunity: clean-scan short-circuit with a distinct no-op status

- Lens: enhancement
- Location: `SKILL.md:25-33 (## Analisis + ## Rencana perubahan)`
- Evidence: Pattern: distinct no-op return, precedented in sibling psm-optimize SKILL.md:47 ('sudah-ramping' status so the caller can distinguish successful no-op from a broken run). If ps-static-scan.py reports no per-version risks (module already safe — a technically valid, unexpected input), the flow still marches through writing an empty .psm-cross-plan.md and asking Budi to approve nothing, and the headless return cannot distinguish 'nothing needed changing' from a normal transform run.
- Recommendation: On a clean scan, skip plan/apply and go straight to the psm-validate gate; report 'module sudah cross-version-safe' with per-version status, and in headless return a distinct status (e.g. 'sudah-aman') without plan-change fields.

#### leanness-1 — Closing checklist restates the file it ends and the psm-validate gate

- Lens: leanness
- Location: `references/version-safe-patterns.md:## Checklist keluaran cross-version (lines 104-113)`
- Evidence: Six of the seven checklist items restate rules already stated above in the same file (ps_versions_compliancy, forbidden PS9 deps, version branches via version_compare, prepend-autoloader:false, Smarty escaping); item 7 restates SKILL.md's binding definition of done ('hanya bila lolos psm-validate di 1.7.x, 8.x, dan 9.x'). The model has just read all of these rules ~100 lines earlier, and psm-validate — the skill's declared gate — checks every item anyway. Only 'index.php di tiap folder' is a fact stated nowhere else in the skill. Canon core test: facts restated across sections; the section also creates a second, softer 'dianggap cross-version-safe bila' definition alongside the authoritative one in SKILL.md Verifikasi.
- Recommendation: Delete the checklist section and relocate its one unique fact into the composer.json & autoload section; keep SKILL.md's psm-validate pass as the single definition of done. Route to variant eval to confirm.
- Proposed smallest: Remove '## Checklist keluaran cross-version' entirely. Add one bullet under '## composer.json & autoload': '- Sertakan `index.php` stub di tiap folder module (persyaratan keamanan, diperiksa Validator).'
- Predicted delta: Likely nothing — psm-validate remains the mandatory gate and mechanically checks every listed item, so the worst case is one extra validate iteration on a module the model would otherwise have self-caught. Route to variant eval to confirm.

### Low (7)

#### leanness-2 — Version-detection code block re-teaches standard PHP the model writes unprompted

- Lens: leanness
- Location: `references/version-safe-patterns.md:## Deteksi versi (lines 13-25)`
- Evidence: An 8-line PHP block demonstrates `if (version_compare(_PS_VERSION_, '8.0.0', '>=')) {...} else {...}` — a branching idiom any capable model produces without instruction once told to branch by version (which SKILL.md Terapkan already mandates with the exact function named). Canon core-test shape: mechanics for a tool the model already drives fluently. The only non-inferable content in the section is two clauses: `_PS_VERSION_` is available from module load, and the keep-branches-in-a-private-helper convention.
- Recommendation: Collapse the code block into two prose lines that keep the two non-inferable clauses. Route to variant eval to confirm.
- Proposed smallest: Replace the section body with: 'Cabangkan runtime dengan `version_compare(_PS_VERSION_, ''8.0.0'', ''>='')` — `_PS_VERSION_` tersedia sejak module di-load; pakai `''9.0.0''` untuk jalur PS9 spesifik. Bungkus dalam helper privat (mis. `isPs8Plus()`) agar cabang konsisten, bukan pengecekan tersebar.'
- Predicted delta: Nothing expected — the idiom is standard PHP and every later section's example code re-demonstrates it in context anyway; the retained clauses preserve the availability fact and the helper convention. Route to variant eval to confirm.

#### leanness-3 — Overview's final sentence restates gates stated one sentence earlier and enforced in their own sections

- Lens: leanness
- Location: `SKILL.md:## Overview (final sentence, line 10)`
- Evidence: 'Tidak pernah menerapkan perubahan tanpa rencana yang disetujui, dan tidak pernah menyatakan selesai sebelum lolos psm-validate di 1.7.x + 8.x + 9.x' is the negative restatement of the 'rencana → konfirmasi → terapkan → verifikasi' process sentence immediately preceding it. Both gates are then enforced at point of use — Rencana perubahan ('gerbang yang tak boleh dilewati'), Verifikasi ('hanya bila lolos psm-validate'), and Mode headless ('Tetap berlaku: jangan menyatakan lolos...'). That makes three statements of the validate gate and three of the approval gate in a 1574-token file. Canon core test: restated facts / defensive padding. (The headless restatement is not duplication — it disambiguates which gate survives '--headless' — and stays.)
- Recommendation: Cut the Overview's final sentence; the process sentence plus the section-level gates carry both invariants at their points of use. Saves ~35 tokens with no behavior change.

#### leanness-4 — On Activation numbering is decorative — steps are mostly independent obligations

- Lens: leanness
- Location: `SKILL.md:## On Activation (lines 20-23)`
- Evidence: Steps 1 (load config), 2 (determine module/versions), and 4 (augment patterns) are independent obligations with no feed-forward between them; only 3 (resume check) depends on 2, and that dependency is self-evident (the resume file lives under the module path determined in 2). Canon test 5: numbering tells the reader order matters and it will march the steps in order; where they are independent obligations, use bullets.
- Recommendation: Convert the four numbered steps to bullets. No goal-sentence collapse needed — each bullet is a real, distinct obligation; only the sequence signal is false.

#### leanness-5 — Bare WAJIB without its why on wildcard resource exclusion (under-writing)

- Lens: leanness
- Location: `references/version-safe-patterns.md:## Services / Dependency Injection (line 91)`
- Evidence: 'Wildcard resource WAJIB exclude `index.php`' is the only shouted rule in the file that carries no failure clause — every other WAJIB/caps directive has its consequence inline ('kalau true, dependency module override core dan merusak PrestaShop'; 'divalidasi Validator'; 'PS8+ dev mode lempar exception'). Per the canon, a reader handed a rule without its reason cannot apply it to the unforeseen case and may optimize it away; this is under-writing to fix by adding the why, not a line to cut.
- Recommendation: Reframe the shout as the failure it guards against, one clause: e.g. 'exclude `index.php` dari wildcard resource — stub keamanan itu bukan kelas service, dan container gagal saat mencoba me-registrasi-nya.' (Verify the exact failure mode against the PrestaShop docs the file cites before wording it.)

#### architecture-4 — Overview's absolute 'never apply without approved plan' contradicted by headless mode

- Lens: architecture
- Location: `SKILL.md:10 (Overview) vs SKILL.md:45 (Mode headless)`
- Evidence: The Overview states an unqualified invariant: 'Tidak pernah menerapkan perubahan tanpa rencana yang disetujui.' Headless mode runs the flow 'tanpa gerbang konfirmasi interaktif', applying irreversible source edits against a plan no one saw — the caller 'bertanggung jawab atas persetujuan' but never sees the plan before apply. The contradiction is explicit and self-acknowledged (memlog absorbs assumptions, psm-validate still gates 'selesai'), so it will not mislead an executing model — but the stated principle and the mode disagree as written.
- Recommendation: Qualify the Overview invariant with one clause ('kecuali mode headless, di mana persetujuan didelegasikan ke pemanggil dan tercatat di memlog'), or have headless pause after writing .psm-cross-plan.md unless the caller passes an explicit pre-approval flag.

#### architecture-5 — Resolution-rules block literalizes the {skill-name} placeholder into a tautology

- Lens: architecture
- Location: `SKILL.md:16 (## Resolution rules)`
- Evidence: The canonical block's third line is '`{skill-name}` → the skill directory's basename'; here it reads '`psm-cross-version` → basename direktori skill', defining the literal name as resolving to itself. Inert (nothing in the skill uses {skill-name}), but it deviates from the stamped canonical block and carries no information.
- Recommendation: Restore the placeholder form (`{skill-name}` → basename direktori skill) or drop the bullet since the token is unused.

#### customization-1 — Terminal stage produces artifacts and stops — on_complete is the one credible opt-in point

- Lens: customization
- Location: `SKILL.md: Verifikasi (gerbang wajib) / Mode headless`
- Evidence: The workflow ends after psm-validate passes with a summary to Budi (or a one-line return in headless mode), leaving onward actions (git commit, release packaging, sprint logging) to the operator. The skill has zero hardcoded templates and no org-redirectable output path (.psm-cross-plan.md is a resume artifact colocated with the module by design), so this is the only customization point that could ever earn a surface; the guide's high-opportunity opt-in threshold (two or more hardcoded templates) is not met, and the interactive session plus psm-agent-expert orchestration already own onward routing, so the forced-fork risk is minimal.
- Recommendation: Keep the ships-fixed decision as logged. Revisit opting in — a minimal customize.toml carrying only the universal four defaults, with on_complete as the point that earns it — only if a recurring post-verification action emerges across runs; do not add the surface preemptively. If the skill ever opts in, fold the hardwired optional read of {project-root}/_bmad/psm/memory/tech/cross-version-patterns.md into persistent_facts rather than keeping a parallel hand-rolled load.
