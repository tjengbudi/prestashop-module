# Analysis Report: /home/budi/dev/prestashop-module/.claude/skills/psm-optimize

Generated: 2026-07-16 · Schema: 2

**Grade: Fair**

> Lean, well-gated flow whose two real risks are silent staleness (three sibling routes read the outdated skills/ mirror) and success-shaped failure (a wrong target or a crashed validator can exit as success).

psm-optimize keeps its profil→rencana→konfirmasi→terapkan→verifikasi spine tight: token budget respected, zero waste patterns, intelligence placement sound, and the no-customize.toml decision holds. But the skill has drifted behind its family: three cross-skill references still route through the stale skills/ mirror (diverged content confirmed by diff), and the hardening gates psm-develop gained — target proof before a clean exit, bounded verify loops, fail-closed verdict reading, undo-net before apply — were never inherited, so several failure modes currently exit looking like success.

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 4 |
| Medium | 4 |
| Low | 7 |

## Themes

### 1. Sibling routes read the stale skills/ mirror

- Root cause: SKILL.md and the catalog route ps-module-inventory.py, version-safe-patterns.md, and psm-validate through {project-root}/skills/, but the live tree is .claude/skills/ and the mirror has diverged (old 3-layer validator, inventory missing plan-validation, patterns missing the cross-version checklist). Every run silently profiles and verifies against superseded contracts. psm-develop already codified the fix as the <skills-dir> resolution token.
- Fix: Add the <skills-dir> rule to Resolution rules (copy psm-develop SKILL.md:16 wording) and reroute the three sibling content references in SKILL.md (Profil, Identifikasi, Verifikasi) and references/optimization-catalog.md line 7 through it. Leave only the resolve-psm-config.py call on {project-root}/skills/ — that runtime resolver legitimately lives there.
- Findings:
  - `architecture-1` Sibling routes target the stale skills/ mirror instead of the live tree — `SKILL.md:27,33,43; references/optimization-catalog.md:7`
  - `enhancement-3` Add: <skills-dir> sibling-resolution pattern — three cross-skill references currently resolve to the stale skills/ mirror — `SKILL.md:Resolution rules (lines 12-17), Profil (line 27), Identifikasi & rencana (line 33), Verifikasi (line 43)`

### 2. Failure paths undefined — failures exit shaped like success

- Root cause: The skill defines only happy-path behavior. An existing-but-wrong target (typo, empty folder, shop root) yields an empty hotspot scan that SKILL.md labels a success ('sudah ramping'); an unrunnable or non-JSON psm-validate verdict has no defined reading; the redesign loop has no attempt cap; and Terapkan edits files in place on an unchecked git assumption. psm-develop carries the guard for each of these (target gate, fail-closed verdict, verify_attempts cap, clean-tree/backup gate) — none were inherited.
- Fix: Port psm-develop's four guards: (1) before the 'sudah ramping' exit, require the inventory to have proven a real module and stop on script non-zero exits; (2) rule that an unrunnable/unreadable psm-validate verdict counts as not-pass; (3) persist verify_attempts in the plan artifact, cap at 2-3, then hand off to Budi; (4) confirm a clean git tree before Terapkan, offering backup otherwise. Add the matching headless failure statuses (gagal, butuh intervensi) to Mode headless, which today defines only success-shaped returns.
- Findings:
  - `enhancement-1` Add: target gate before the 'sudah ramping' clean exit (psm-develop 'Gerbang target' pattern) — `SKILL.md:Profil (line 27) and Mode headless (line 47)`
  - `enhancement-2` Add: bounded verify loop and fail-closed verdict (psm-develop verify_attempts + unreadable-verdict patterns) — `SKILL.md:Verifikasi (line 43) and Mode headless (line 47)`
  - `enhancement-4` Add: undo-net gate before Terapkan (psm-develop clean-working-tree/backup pattern) — `SKILL.md:Terapkan (line 39)`

### 3. Baseline evidence chain has weak links at write, extraction, and resume

- Root cause: The mandatory Verifikasi gate compares before/after evidence, but the chain producing that evidence is fragile: Profil never names the artifact path at the moment the baseline must be written (it is only bound later in Identifikasi), profiler metrics are hand-extracted from raw Blackfire/Xdebug output and round-tripped through free-form markdown with no guarantee of method-identical extraction, and resume trusts plan statuses blindly after possible git reverts.
- Fix: Name <module-path>/.psm-optimize-plan.md at first use in Profil; add scripts/ps-profile-summary.py that converts raw profiler output (cachegrind for Xdebug, CLI/JSON for Blackfire) into compact JSON embedded verbatim in both the baseline block and the Verifikasi re-measure, keeping the improve/trade-off verdict in the prompt; on resume with an existing plan, re-run the hotspot scan and spot-check items marked 'diterapkan' against the code, writing corrections back to the plan.
- Findings:
  - `architecture-2` Baseline artifact unnamed at the point it must be written — `SKILL.md:29`
  - `determinism-1` Profiler metric extraction and baseline round-trip are unscripted measurement plumbing — `SKILL.md: Profil (lines 27-29, baseline metrics) + Verifikasi (line 43, re-measure & compare)`
  - `enhancement-5` Add: reconcile-on-resume — resume trusts plan statuses blindly (psm-develop --reconcile pattern) — `SKILL.md:On Activation #3 (line 23)`

### 4. Restatement and dead-wiring trims

- Root cause: Small core-test failures accumulated: gate rules restated up to four times across sections, two resolution tokens defined but never used, an evidence taxonomy recapped inside its own section, a batch-your-calls instruction the harness already mandates, and generic performance-101 bullets diluting the PrestaShop-specific catalog.
- Fix: One trim pass over SKILL.md and the catalog: keep each gate's single statement in the section that enforces it, delete the {skill-root} and basename resolution lines, truncate the Verifikasi recap, drop the batch instruction, and cut the generic SQL/JS-hygiene bullets while keeping every PrestaShop-mechanism bullet.
- Findings:
  - `leanness-1` Measure-first / gate rules restated up to four times in SKILL.md — `SKILL.md:10 (Overview, 'Tiga pantangan...') and SKILL.md:27 (Profil, '(jangan optimasi spekulatif)')`
  - `leanness-2` Resolution rules define two tokens the skill never uses — `SKILL.md:14-16 (Resolution rules)`
  - `leanness-3` Verifikasi re-lists its own evidence taxonomy as a summary definition — `SKILL.md:43 (Verifikasi, 'Module teroptimasi bila...' sentence)`
  - `leanness-4` Batch-your-tool-calls clause re-teaches harness behavior — `SKILL.md:27 (Profil)`
  - `leanness-5` Catalog carries generic performance-101 bullets alongside its PrestaShop-specific value — `references/optimization-catalog.md:25, 30, 35-36`
  - `architecture-3` Tautological resolution rule for an unused token — `SKILL.md:16`

## Strengths

- Gated spine is sound and enforced where it acts: measure-before-change, plan approval before touching files, and a double verification gate (compatibility + class-appropriate performance evidence) — workflow-integrity pre-pass passes clean.
- Intelligence placement is correct in both directions: ps-hotspot-scan.py surfaces candidates while every verdict stays with the model, and config/memlog/validate plumbing is scripted with read-as-is guards.
- Leanness fundamentals hold: SKILL.md at 2361 tokens inside budget, zero pre-pass waste patterns, and a justified single-reference carve (optimization-catalog.md).
- Customization surface is deliberately empty per the recorded 2026-07-08 decline — project config flows through the central resolve-psm-config.py resolver, the exact family pattern.
- Graceful profiler degradation: the no-profiler static-evidence path (added in the 2026-07-08 fix round) keeps the skill usable without Blackfire/Xdebug.

## Recommendations

1. Add the <skills-dir> resolution rule and reroute the three stale sibling references (SKILL.md Profil/Identifikasi/Verifikasi + catalog line 7) — a four-line edit that stops every run from reading superseded validator, inventory, and patterns content. (resolves: architecture-1, enhancement-3)
2. Port psm-develop's failure guards: target gate before the 'sudah ramping' exit, fail-closed reading of unrunnable psm-validate verdicts, verify_attempts cap with handoff, clean-tree check before Terapkan, and headless statuses gagal / butuh intervensi. (resolves: enhancement-1, enhancement-2, enhancement-4)
3. Harden the baseline evidence chain: name the plan artifact path at first write in Profil, add ps-profile-summary.py for method-identical metric extraction (unit-testable with a checked-in cachegrind fixture — the old 'needs fixture env' blocker dissolves), and reconcile plan statuses on resume. (resolves: architecture-2, determinism-1, enhancement-5)
4. Run the leanness trim pass over SKILL.md and the catalog (restatements, dead tokens, generic bullets) — roughly 150-200 tokens back and a crisper read. (resolves: leanness-1, leanness-2, leanness-3, leanness-4, leanness-5, architecture-3)

## Experience

- **Optimize with profiler** — Activate (resolve psm config, read module inventory) → Profil: flashlight + Blackfire/Xdebug baseline written to .psm-optimize-plan.md → Identifikasi: plan opportunities against the catalog → Budi approves → Terapkan → Verifikasi: psm-validate across 1.7/8/9 + re-measured metrics vs baseline.
- **Optimize without profiler** — Same spine, but the baseline is static evidence: ps-hotspot-scan.py candidates + hotspot deltas (or mechanism-confirmed-in-diff for unmeasurable fixes) stand in for profiler metrics.
- **Already-lean exit** — Profil finds no hotspots and no profiler signal → skill declares the module 'sudah ramping' and stops — currently reachable by a wrong-but-existing target path (enhancement-1).
- Headless: Headless mode exists with status returns and memlog assumption-tracking, but defines only success-shaped statuses (selesai / sudah-ramping) — no gagal or butuh intervensi, so automation cannot distinguish failure from success (enhancement-2).

## Findings

### High (4)

#### architecture-1 — Sibling routes target the stale skills/ mirror instead of the live tree

- Lens: architecture
- Location: `SKILL.md:27,33,43; references/optimization-catalog.md:7`
- Evidence: Four references route to {project-root}/skills/… and all three content targets diverge from the live .claude/skills/ copies: skills/psm-validate/SKILL.md is the old 3-layer validator (no Lapis 4 browser E2E, and its activation parses config.yaml directly — the exact procedure psm-optimize's own On Activation forbids via the resolver); skills/psm-develop/scripts/ps-module-inventory.py lacks the live version's plan-validation capability (146 diff lines); skills/psm-cross-version/references/version-safe-patterns.md lacks the cross-version output checklist. The family has already codified the fix: psm-develop SKILL.md:16 defines a <skills-dir> resolution token with 'Rujuk sibling lewat <skills-dir>/psm-validate/…, bukan {project-root}/skills/… — jangan bergantung pada mirror skills/'. This violates the skill's stated promise that verification proves the module 'tetap lolos psm-validate di ketiga versi' — the gate executes against an outdated contract. (The {project-root}/skills/psm-setup/scripts/resolve-psm-config.py route is exempt: that path is the deliberately maintained runtime resolver, identical in both trees and used family-wide.)
- Recommendation: Add the <skills-dir> line to Resolution rules (mirroring psm-develop SKILL.md:16) and rewrite the three sibling content routes in SKILL.md (lines 27, 33, 43) and references/optimization-catalog.md line 7 to <skills-dir>/psm-{validate,develop,cross-version}/…. Leave the resolve-psm-config.py invocation as-is.

#### enhancement-1 — Add: target gate before the 'sudah ramping' clean exit (psm-develop 'Gerbang target' pattern)

- Lens: enhancement
- Location: `SKILL.md:Profil (line 27) and Mode headless (line 47)`
- Evidence: ps-hotspot-scan.py returns empty candidates for any existing folder with no PHP (verified in scripts/ps-hotspot-scan.py — only a nonexistent path errors, exit 2), and SKILL.md explicitly labels an empty scan a success ('itu hasil sukses'). A wrong-but-existing path — a typo, an empty folder, the shop root instead of the module — slides straight into the 'module sudah ramping' exit, and headless returns the success-shaped status: sudah-ramping. psm-develop guards exactly this with its Gerbang target (stop when inventory finds no version/hooks/files; show script errors as-is; headless gagal); psm-optimize runs the same inventory script but never checks that it proved a module, and defines no behavior for either script exiting non-zero.
- Recommendation: Before the 'sudah ramping' exit is reachable, require the inventory to have proven a real module (version/hooks/files present); if the target is not a filled module or either script exits non-zero, stop and ask/redirect instead of concluding lean (headless: a distinct gagal status, mirroring psm-develop's two stop statuses).

#### enhancement-2 — Add: bounded verify loop and fail-closed verdict (psm-develop verify_attempts + unreadable-verdict patterns)

- Lens: enhancement
- Location: `SKILL.md:Verifikasi (line 43) and Mode headless (line 47)`
- Evidence: The redesign loop ('tulis temuan itu kembali ke .psm-optimize-plan.md dan rancang ulang... jangan menyatakan selesai') has no attempt cap and no defined behavior when psm-validate itself fails to run or returns non-JSON. psm-develop persists verify_attempts: N in the plan with a 2-3 cap escalating to Budi (headless butuh intervensi), and explicitly rules 'validate unreadable = NOT lolos' (headless gagal). A headless automator invoking psm-optimize on a stubborn module loops redesign→apply→validate indefinitely, and a validate crash risks being read as absence of failures. psm-optimize's headless section defines only success and sudah-ramping returns — no failure statuses at all.
- Recommendation: Adopt both sibling guards: store verify_attempts in .psm-optimize-plan.md, cap at 2-3 with diagnosis written to the plan and handoff to Budi (headless butuh intervensi); state that an unrunnable or unreadable psm-validate verdict counts as not-pass (headless gagal), and add the two stop statuses to Mode headless.

#### enhancement-3 — Add: <skills-dir> sibling-resolution pattern — three cross-skill references currently resolve to the stale skills/ mirror

- Lens: enhancement
- Location: `SKILL.md:Resolution rules (lines 12-17), Profil (line 27), Identifikasi & rencana (line 33), Verifikasi (line 43)`
- Evidence: psm-develop's Resolution rules define <skills-dir> precisely to avoid the stale root mirror ('jangan bergantung pada mirror skills/ di root project'), keeping only the psm-setup resolver under {project-root}/skills/. psm-optimize routes ps-module-inventory.py, version-safe-patterns.md, and psm-validate's SKILL.md through {project-root}/skills/..., and diff confirms the mirror copies of the first two differ from the live .claude/skills tree today — every run profiles with a stale inventory script and plans against a stale version-safe-patterns doc, silently.
- Recommendation: Add the <skills-dir> rule to Resolution rules (copy psm-develop's wording) and reroute the three sibling references through it; leave only the resolve-psm-config.py call on {project-root}/skills/ (the runtime resolver legitimately lives there).

### Medium (4)

#### architecture-2 — Baseline artifact unnamed at the point it must be written

- Lens: architecture
- Location: `SKILL.md:29`
- Evidence: Profil commands 'Tulis baseline ke artefak segera setelah diukur' without naming a path; the artifact is only bound to <module-path>/.psm-optimize-plan.md later, in Identifikasi (line 35, 'memuat blok baseline yang sudah ditulis di tahap Profil'). Resume (On Activation step 3) and the Verifikasi gate ('bandingkan dengan blok baseline di .psm-optimize-plan.md — bukan dari ingatan') both key on that exact file. If the session compacts or a headless run ends between Profil and Identifikasi — or the model writes the baseline to a scratch location — the baseline is lost, which is precisely the failure the bolded rule states it exists to prevent ('Baseline yang hanya hidup di percakapan akan hilang saat resume/headless').
- Recommendation: Name the path at first use: 'Tulis blok baseline ke <module-path>/.psm-optimize-plan.md segera setelah diukur', so Profil produces exactly what resume and Verifikasi consume.

#### determinism-1 — Profiler metric extraction and baseline round-trip are unscripted measurement plumbing

- Lens: determinism
- Location: `SKILL.md: Profil (lines 27-29, baseline metrics) + Verifikasi (line 43, re-measure & compare)`
- Evidence: Profil instructs 'gunakan flashlight dengan Blackfire (BLACKFIRE_ENABLED=true) atau Xdebug (XDEBUG_ENABLED=true)' and 'Tulis baseline ke artefak ... wall-time, jumlah query, memori'; Verifikasi instructs 'ukur ulang dengan profiler yang sama lalu bandingkan dengan blok baseline di .psm-optimize-plan.md (bukan dari ingatan) — syaratnya metrik membaik'. No script in psm-optimize (scripts/ holds only ps-hotspot-scan.py) or psm-validate produces these numbers, so the model must parse raw profiler output (Xdebug cachegrind is a large machine-format file) ad-hoc, write the numbers into a free-form markdown block, and later re-extract and re-parse both — with no guarantee the before/after measurements use the same extraction method, which can silently corrupt the 'metrik membaik' gate. This is the deferred profiler-compare finding re-judged: the deterministic core is the fetch/parse/extract, not the compare.
- Recommendation: Determinism leak (prompt doing script work) — fix via the pre-pass JSON pattern: add scripts/ps-profile-summary.py that converts raw profiler output (cachegrind parse for Xdebug; Blackfire CLI/JSON for Blackfire) into compact JSON {flow, profiler, wall_time_ms, memory_kb, sql_count}, and have both the Profil baseline block and the Verifikasi re-measure embed that exact JSON so extraction is method-identical before and after. Keep the comparison verdict ('metrik membaik', trade-offs between wall-time and memory) in the prompt — determinism-test Q3, that is judgment. The 2026-07-08 'needs fixture env' blocker dissolves for the Xdebug path: cachegrind is a stable text format unit-testable with a small checked-in fixture, no live profiler required.

#### enhancement-4 — Add: undo-net gate before Terapkan (psm-develop clean-working-tree/backup pattern)

- Lens: enhancement
- Location: `SKILL.md:Terapkan (line 39)`
- Evidence: Terapkan modifies used source in place on the strength of an assumption — 'asumsikan Budi memakai git untuk pembatalan' — with no check. psm-develop, for the identical operation class, verifies git status shows a clean tree, offers a folder backup otherwise, and in headless either auto-backs-up (logging the path to memlog) or returns butuh intervensi rather than applying without an undo net. A module outside git, or with a dirty tree mixing Budi's uncommitted work into the optimization diff, has no recovery path here.
- Recommendation: Mirror psm-develop's one-gate sentence in Terapkan: confirm clean git working tree before touching files, warn/offer backup otherwise, and forbid silent headless application without an undo net.

#### enhancement-5 — Add: reconcile-on-resume — resume trusts plan statuses blindly (psm-develop --reconcile pattern)

- Lens: enhancement
- Location: `SKILL.md:On Activation #3 (line 23)`
- Evidence: Resume is 'baca untuk melanjutkan dari keadaan terakhir' with no drift check. psm-develop reconciles plan status against the code on resume (ps-module-inventory --reconcile) because Budi may have git-reverted items still marked 'diterapkan'. psm-optimize's Verifikasi gate depends on delta comparisons against the plan's baseline block, so stale 'diterapkan' statuses after a revert corrupt exactly the before/after evidence the mandatory gate reads.
- Recommendation: On resume with an existing plan, re-run ps-hotspot-scan.py and compare candidate counts against the plan's baseline block, and spot-check items marked 'diterapkan' against the code before continuing; treat mismatches as status corrections to write back to the plan (headless: log the correction to memlog).

### Low (7)

#### architecture-3 — Tautological resolution rule for an unused token

- Lens: architecture
- Location: `SKILL.md:16`
- Evidence: The canonical block defines '{skill-name} → the skill directory's basename'; here the literal name is substituted, yielding 'psm-optimize → basename direktori skill' — a self-referential rule — and no {skill-name}/psm-optimize path token is used anywhere in the skill.
- Recommendation: Delete the line (the token is unused), or restore the '{skill-name}' form if the token is intended for future use.

#### architecture-4 — SKILL.md in the warn band; Verifikasi is the lift candidate

- Lens: architecture
- Location: `SKILL.md:43`
- Evidence: SKILL.md is 2361 tokens against the [1500 desired, 2500 budget] tier — the principles' warn band (name the section most worth lifting, do not block). Verifikasi is a single unbroken ~700-token paragraph mixing the gate rule with the per-class performance-evidence mechanics (profiler path vs two static paths).
- Recommendation: No action required now. If the file grows past 2500, lift the per-class evidence mechanics of Verifikasi to a reference with a one-line routing pointer, keeping the gate rule itself inline.

#### leanness-1 — Measure-first / gate rules restated up to four times in SKILL.md

- Lens: leanness
- Location: `SKILL.md:10 (Overview, 'Tiga pantangan...') and SKILL.md:27 (Profil, '(jangan optimasi spekulatif)')`
- Evidence: The three prohibitions in the Overview closer ('jangan optimasi tanpa bukti profil, jangan terapkan tanpa rencana disetujui, jangan nyatakan selesai sebelum kedua bukti verifikasi hijau') each restate a gate already stated where it acts: Profil opens with 'Ukur sebelum mengubah apa pun — optimasi tanpa bukti adalah tebakan', Identifikasi has 'minta persetujuan sebelum menyentuh file — gerbang yang tak boleh dilewati', Verifikasi has 'jangan menyatakan selesai'. Profil additionally repeats the same rule a second time inside itself ('itu hasil sukses... (jangan optimasi spekulatif)'). Canon re-teach shape: facts restated across sections; SKILL.md is always fully loaded, so in-file repetition buys no durability. (The catalog's own copy of the principle is exempt — carved files must stand alone per canon test 6.)
- Recommendation: Cut the 'Tiga pantangan menjiwai alur ini...' sentence from the Overview and the '(jangan optimasi spekulatif)' parenthetical in Profil; each gate keeps its single statement, with its why, in the section that enforces it.

#### leanness-2 — Resolution rules define two tokens the skill never uses

- Lens: leanness
- Location: `SKILL.md:14-16 (Resolution rules)`
- Evidence: '{skill-root}' is defined at line 14 but appears nowhere in SKILL.md or the reference (the bare-path rule in the same bullet already covers 'references/...' and 'scripts/...'), and line 16 defines 'psm-optimize → basename direktori skill' though the name is never used as a resolvable token — only as literal text in '.psm-optimize-plan.md'. Canon core test: a rule for a token that never appears changes none of the reader's moves; dead wiring is friction paid on every invocation.
- Recommendation: Delete '{skill-root}' from the bare-path bullet and drop the 'psm-optimize → basename' bullet; keep bare paths, {project-root}, and <module-path>, which are all live.

#### leanness-3 — Verifikasi re-lists its own evidence taxonomy as a summary definition

- Lens: leanness
- Location: `SKILL.md:43 (Verifikasi, 'Module teroptimasi bila...' sentence)`
- Evidence: The sentence 'Module teroptimasi bila kompatibilitas tak mundur di ketiga versi dan bukti performa yang sesuai kelasnya (metrik profiler membaik, atau delta hotspot statis turun, atau mekanisme terpasang & terkonfirmasi di diff untuk fix tak-terpantau) terpenuhi...' recaps, in a parenthetical, the three evidence classes enumerated in full immediately above in the same paragraph. Canon re-teach shape: restated facts; the recap adds no decision the detailed clauses did not already fix.
- Recommendation: Truncate to 'Module teroptimasi bila kompatibilitas tak mundur di ketiga versi dan bukti performa sesuai kelasnya terpenuhi tanpa regresi perilaku' — drop the parenthetical re-list.

#### leanness-4 — Batch-your-tool-calls clause re-teaches harness behavior

- Lens: leanness
- Location: `SKILL.md:27 (Profil)`
- Evidence: 'Keduanya cuma butuh <module-path> dan tak saling bergantung, jadi jalankan sekaligus dalam satu batch' — the independence note is useful wiring, but 'jalankan sekaligus dalam satu batch' instructs parallel invocation of independent calls, which the harness already mandates and a capable model does untold. Canon re-teach shape: mechanics for a tool the model already drives fluently.
- Recommendation: Keep 'keduanya cuma butuh <module-path> dan tak saling bergantung'; cut 'jadi jalankan sekaligus dalam satu batch'.

#### leanness-5 — Catalog carries generic performance-101 bullets alongside its PrestaShop-specific value

- Lens: leanness
- Location: `references/optimization-catalog.md:25, 30, 35-36`
- Evidence: 'Plus higiene SQL umum (ambil kolom yang dipakai, bukan SELECT *)', 'Lazy service — service mahal sebaiknya tak dibangun bila tak dipakai', and 'Defer/async JS non-kritis. Hindari memuat aset di halaman yang tak butuh' fail the core test — any capable model applies SELECT-column hygiene, lazy construction, and defer/async without prompting. The bullets that earn the file are the PrestaShop-specific ones (Configuration::get internal cache, Cache::clean('*') cost, ObjectModel clearCache granularity, decorate-with-.inner, registerJavascript priorities, index check in the module's install SQL).
- Recommendation: Cut the generic web/SQL hygiene lines; keep every bullet that carries a PrestaShop mechanism, detection point, or version-safety consequence.
