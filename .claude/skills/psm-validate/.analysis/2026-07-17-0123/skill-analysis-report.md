# Analysis Report: /home/budi/dev/prestashop-module/.claude/skills/psm-validate

Generated: 2026-07-17 · Schema: 2

**Grade: Good**

> Four-layer gate with all prior false-pass invariants verified intact — but the freshly ported E2E harness edits opened two high findings on the blocking channel (substring-based BO login check can false-auth, and the documented per-browser uniqueness workaround is inexpressible in specs), while SKILL.md sits 7 tokens under the hard budget.

The skill's core discipline holds: verdict assembly stays fully delegated to ps-aggregate.py, all four adversarially-confirmed false-pass and honest-degrade invariants were re-verified intact, config flows through the single resolver, and lint is clean across scripts and paths. The primary opportunity is the freshly ported E2E harness edge: page-meaning is classified by substring heuristics that gate the conclusive-blocking channel, and three verified gotchas are documented as operator rituals instead of being handled by the script. A restatement trim pass (~180-250 tokens) is needed to restore SKILL.md headroom before any further edit.

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 2 |
| Medium | 11 |
| Low | 7 |

## Themes

### 1. Page meaning classified by substring, gating the blocking channel

- Root cause: The fresh _bo_login success check infers 'authenticated' from the absence of a passwd substring, and FATAL_SIGNS matches generic phrases anywhere in serialized HTML. Both decide semantic state from content position-blind, and both feed conclusiveness — a 500 page or the legacy token interstitial reads as authed, a healthy page embedding 'There was an error' in a JS translation dictionary reads as fatal. Either way a harness artifact becomes a conclusive finding that blames the module.
- Fix: Key both classifiers on structure instead of substring absence/presence: login success requires a positive structural signal (dashboard locator or URL no longer on AdminLogin) AND passwd-field count 0; generic FATAL_SIGNS phrases must co-occur with an error-page selector or status>=500. Add FakePage tests for the interstitial and 500 shapes.
- Findings:
  - `determinism-1` Fresh _bo_login success check infers 'authenticated' from absence of a substring, and it gates conclusiveness — `scripts/ps-e2e-run.py:436-461 (_bo_login)`
  - `determinism-2` FATAL_SIGNS classifies page-brokenness by generic substrings over full serialized HTML — `scripts/ps-e2e-run.py:95-99 (FATAL_SIGNS), 290-293 (expect_no_fatal)`

### 2. Verified gotchas documented as operator rituals instead of harness plumbing

- Root cause: Three user-verified E2E failure modes are prescribed as manual workarounds in e2e-quickstart.md when the script could handle them deterministically: per-browser data uniqueness is the documented fix for shared-DB duplicates but no {browser} placeholder exists to express it (so a healthy module gets a conclusive blocking finding in the second browser), cold-container BO warm-up is a manual curl ritual, and expect_text timing is an authoring workaround.
- Fix: Move the three workarounds into the script: add a {browser} token to substitute()/ctx and point the shared-DB gotcha at it; warm BO via wait_http on AdminLogin before driving browsers (plus one retry in _bo_login); bounded wait_for_load_state('load') before expect_text reads content. Script + reference changes only, no SKILL.md cost.
- Findings:
  - `enhancement-1` Add: {browser} placeholder — the documented per-browser uniqueness workaround is inexpressible, so shared-DB duplicates become false blocking verdicts — `scripts/ps-e2e-run.py:154-160 + references/e2e-quickstart.md:155-157`
  - `enhancement-2` Add: automate the documented BO warm-up so cold-container login stops degrading coverage (opportunity) — `scripts/ps-e2e-run.py:436-460 (_bo_login) + :618 (wait_http FO only); references/e2e-quickstart.md:152-154`
  - `enhancement-4` Add: auto-settle expect_text after navigation instead of prescribing an authoring workaround (opportunity) — `scripts/ps-e2e-run.py:298-301 + references/e2e-quickstart.md:94`

### 3. Cross-section restatement pressing SKILL.md against the hard budget

- Root cause: SKILL.md is at 2993 of 3000 hard-budget tokens with ~180-250 tokens of recoverable restatement: the Validate intro re-enumerates per-layer gating that each layer heading carries, Lapis 1 narrates ps-rules.json rule categories the script self-labels, the honesty-on-degrade rule appears four-plus times, On Activation over-enumerates resolver keys, and Lapis 2 narrates script orchestration blow-by-blow. The next edit trips the hard ceiling unless this slack is recovered.
- Fix: One trim pass applying the three proposed_smallest rewrites (Validate intro, Lapis 1, degrade rule stated once at the Vonis summary-production site) plus the On Activation key-list truncation and the Lapis 2 compression; route the proposed_smallest cuts through a variant eval if confirmation is wanted.
- Findings:
  - `leanness-1` Validate intro restates per-layer gating that each layer heading already carries — `SKILL.md:25 (## Validate intro)`
  - `leanness-2` Lapis 1 parenthetical narrates ps-rules.json ruleset internals — `SKILL.md:27 (Lapis 1)`
  - `leanness-3` Honesty-on-degrade rule restated four-plus times across sections — `SKILL.md:29,33,37-39,43`
  - `leanness-4` On Activation step 1 over-enumerates resolver keys and pre-states Lapis 4 facts — `SKILL.md:19 (On Activation step 1)`
  - `leanness-5` Lapis 2 narrates the script's internal orchestration blow-by-blow — `SKILL.md:29 (Lapis 2)`
  - `architecture-1` SKILL.md in warn tier with near-zero headroom to hard budget — `SKILL.md (whole file; heaviest section ## Validate)`

### 4. Model-to-script seams without validation or explicit handoff

- Root cause: Three seams where model output or operator config feeds the deterministic verdict lack a pinned contract: ps-aggregate counts only the literal severity 'error' and silently drops unresolvable version tokens from adversarial JSON; supplemental validator rules can only be hand-applied because ps-static-scan.py --rules replaces rather than merges; and the Lapis 3 reviewer is never explicitly handed the target-version tokens its return schema depends on.
- Fix: Validate the adversarial payload in ps-aggregate (severity in {error,warning}, versions resolve against targets, violations surfaced loudly as adversarial_schema_notes or exit 2); add --extra-rules merge to ps-static-scan.py; pin the Lapis 3 handoff to include the run's --versions tokens.
- Findings:
  - `determinism-3` Knowledge-base rule augmentation makes the prompt hand-apply deterministic rules the scan script cannot ingest — `SKILL.md On Activation step 3 + scripts/ps-static-scan.py:150 (--rules)`
  - `determinism-4` Model-authored adversarial JSON is aggregated without structural validation; off-enum severities and bad version tokens silently un-block — `scripts/ps-aggregate.py:183-198 (adversarial_layer) + SKILL.md Lapis 3`
  - `architecture-3` Lapis 3 subagent handoff omits the target-version list its return contract depends on — `SKILL.md: ## Validate, Lapis 3`

### 5. Browser option set hardcoded beside its config key

- Root cause: The new interactive scope menu sources versions from psm_target_versions but enumerates browser choices as literal 'chromium/firefox/keduanya' prose, and Overview/Lapis 4/prerequisite bake in the canonical engine pair — an org override of psm_e2e_browsers (plausible here, firefox install is deferred) is contradicted by the offered choices and install instruction.
- Fix: Source the browser option set from the resolved psm_e2e_browsers value (same pattern as versions) and neutralize the prose/prerequisite to the resolved set, keeping the canonical pair only as an example.
- Findings:
  - `customization-1` Interactive browser scope options hardcoded beside psm_e2e_browsers — `SKILL.md:On Activation step 2`
  - `customization-2` Engine pair chromium+firefox baked into SKILL.md prose and install prerequisite — `SKILL.md:Overview, Validate Lapis 4 heading and prerequisite`

## Strengths

- Verdict assembly is fully delegated to ps-aggregate.py and all four adversarially-confirmed invariants were re-verified intact this run: findings!=[] implies errors==[] per version, per-browser launch-fail/probe-miss land in browser_notes not errors, infra failure neither blocks nor claims pass, and honest-degrade statuses (skipped/skipped_image/skipped_browser) survive end to end.
- Headless story is complete: every interaction point has a flag or config default, scope selection asks nothing in headless, and the enhancement lens found no over-applied patterns to cut.
- Single-resolver config mechanism (customize.toml declined by recorded decision) remains compliant; the four fresh harness values are correctly constants or per-run flags (--nav-timeout, --headed, --screenshot-dir), not missing config surface.
- Clean deterministic floor: workflow integrity pass, scripts lint 0 findings with all four Python scripts tested (110+ asserts), path lint 0 live findings.
- Interactive scope selection sources versions from config and the verdict carries a narrowed-scope guard.

## Recommendations

1. Harden the two fresh substring classifiers to structural signals (login success = positive dashboard/URL signal + passwd count 0; FATAL_SIGNS generic phrases anchored to an error-page selector), with FakePage tests for interstitial and 500 shapes. (resolves: determinism-1, determinism-2)
2. Turn the three documented E2E gotchas into harness plumbing: {browser} placeholder in substitute(), BO warm-up via wait_http before driving browsers plus one _bo_login retry, bounded load-state settle before expect_text; then demote the quickstart gotchas to background notes. (resolves: enhancement-1, enhancement-2, enhancement-4)
3. Run one restatement trim pass over SKILL.md (Validate intro gating, Lapis 1 rule enumeration, degrade rule stated once at Vonis, On Activation key list, Lapis 2 orchestration narration) to recover ~180-250 tokens of headroom. (resolves: leanness-1, leanness-2, leanness-3, leanness-4, leanness-5, architecture-1)
4. Pin the model-to-script seams: adversarial payload schema validation in ps-aggregate with loud surfacing, --extra-rules merge flag on ps-static-scan.py, explicit target-version tokens in the Lapis 3 reviewer handoff. (resolves: determinism-3, determinism-4, architecture-3)
5. Source the interactive browser options and engine prose from the resolved psm_e2e_browsers value instead of hardcoding chromium/firefox/keduanya. (resolves: customization-1, customization-2)
6. Small closures: freshness guard on layer-JSON reuse (one sentence, paid for by the rank-3 trim), headless assumption trail via memlog.py, fix the ps-e2e-run.py docstring placeholder drift (add value), decapitalize the quickstart shouts. (resolves: enhancement-3, architecture-2, leanness-7, leanness-6)

## Experience

- **Interactive full validate** — Activation resolves config via the psm resolver (fallback to canonical defaults) -> scope selection for versions and browsers -> four layers run cheap-first with per-layer JSON outputs -> ps-aggregate assembles the verdict -> model reviews key screenshots and writes the honest summary.
- **Headless CI gate** — Module path and scope from args/config, no questions -> layers run with mandatory no-image-pull gating -> aggregate JSON + exit code returned with a one-line summary.
- **E2E spec author** — references/e2e-quickstart.md -> author declarative tests/e2e/*.json specs with placeholders -> unknown actions rejected with notes, results flow into the same aggregate verdict.
- Headless: Complete and question-free (scope from args/config, honest degrade throughout), but assumptions and default fallbacks are not yet recorded to a memlog trail (architecture-2).

## Findings

### High (2)

#### determinism-1 — Fresh _bo_login success check infers 'authenticated' from absence of a substring, and it gates conclusiveness

- Lens: determinism
- Location: `scripts/ps-e2e-run.py:436-461 (_bo_login)`
- Evidence: return 'name="passwd"' not in html — the semantic state 'admin logged in' is decided by a raw-HTML substring being absent. Any post-click page lacking a passwd field reads as authed: a 500 error page (none of whose FATAL_SIGNS contain 'passwd'), or the legacy 'Invalid security token' interstitial — the very page shape this same edit batch added click_optional for on 1.7/8. False-authed sets ctx['bo_authed']=True, making every BO assertion conclusive (run_steps line 281), so authored BO scenario failures become blocking findings in ps-aggregate that blame the module for an auth/infra failure — silently violating the 'BO konklusif hanya bila login berhasil' rule. Tests cover only the two happy shapes (passwd present/absent), not the false-authed shapes.
- Recommendation: Intelligence leak: a string match deciding what content means, in a script that gates downstream blocking — the work stays in the script (determinism test: same DOM, same verdict, unit-testable with the existing FakePage) but must key on structure, not substring absence. Require a positive structural signal AND the negative one: page.locator('input[name=passwd]').count() == 0 plus (page.url no longer contains 'controller=AdminLogin', or a dashboard-only locator such as '#header_infos' present). Add FakePage tests for the interstitial/500 shapes returning False.

#### enhancement-1 — Add: {browser} placeholder — the documented per-browser uniqueness workaround is inexpressible, so shared-DB duplicates become false blocking verdicts

- Lens: enhancement
- Location: `scripts/ps-e2e-run.py:154-160 + references/e2e-quickstart.md:155-157`
- Evidence: Pattern: honest-verdict / graceful-degradation semantics violated on the conclusive channel. Chromium and Firefox share one container/DB per version, so an authored scenario that creates data passes in the first browser and fails in the second with duplicates — emitted as a conclusive severity:error finding (assemble_findings), i.e. a harness artifact blocks a healthy module. The quickstart gotcha prescribes 'pakai nama unik per-browser', but substitute() only replaces {mod}/{fo}/{bo} and all specs run on all browsers, so the prescribed fix cannot be written in a spec; the author's only real options are weakening assertions or dropping a browser, forfeiting the skill's Chromium+Firefox bar. This is memlog gap candidate (2), promoted.
- Recommendation: Add a {browser} token (engine name) to substitute() and ctx, add it to the placeholder line in the quickstart action-table section, and reword the DB-bersama gotcha to point at it ('beri nama data {browser}-suffixed'). Cheaper and truer to the layer's semantics than per-browser DB isolation, which doubles boot cost; keep isolation as a non-goal note in the memlog.

### Medium (11)

#### leanness-1 — Validate intro restates per-layer gating that each layer heading already carries

- Lens: leanness
- Location: `SKILL.md:25 (## Validate intro)`
- Evidence: "Lapis deterministik dulu (cepat, selalu jalan); lapis flashlight bila Docker tersedia; lapis adversarial selalu (judgment); lapis E2E browser bila Docker + browser Playwright tersedia" — every one of these conditions reappears in the four layer headings at lines 27/29/31/33 ("(selalu)", "(bila Docker ada)", "(judgment)", "(bila psm_e2e_enabled ≠ false dan Docker + browser Playwright ada)"). Canon core test: facts restated across sections. The intro's load-bearing content is only the cheap-first ordering rationale and the per-layer output-file convention with its resumability why.
- Recommendation: Keep the ordering-why and the output-file convention; drop the gating enumeration — each layer heading is the point of use.
- Proposed smallest: Jalankan empat lapis pengujian lalu satukan jadi vonis — lapis murah dan deterministik dulu supaya run mahal tak diulang. Tulis output tiap lapis ke `<psm_reports_dir>/<module>-<lapis>.json` (`static`/`flashlight`/`adversarial`/`e2e`) — path terprediksi membuat run yang terputus bisa dilanjutkan tanpa mengulang lapis mahal.
- Predicted delta: Nothing — availability gating lives on each layer heading where the decision is made; route to variant eval to confirm. ~35 tokens recovered.

#### leanness-2 — Lapis 1 parenthetical narrates ps-rules.json ruleset internals

- Lens: leanness
- Location: `SKILL.md:27 (Lapis 1)`
- Evidence: "(dependency terlarang PS9, kelas/method/hook/konstanta dihapus, fungsi terlarang, ps_versions_compliancy ada & range mencakup target, composer prepend-autoloader: false, index.php, Smarty unescaped)" enumerates 8 rule categories the script matches. Canon: mechanics living in the wrong file — the script performs the matching and its JSON output names every triggered rule, so the enumeration changes no move the reader makes; it also silently drifts every time assets/ps-rules.json grows. The load-bearing line is the closing rule ("sumber kebenaran... jangan menilai ulang temuannya dengan tangan"), consistent with the prior-run finding that prose must not narrate script internals.
- Recommendation: Cut the category enumeration; keep the invocation, the JSON shape, and the do-not-re-judge rule.
- Proposed smallest: **Lapis 1 — pindai statis lintas versi (selalu).** Jalankan `uv run scripts/ps-static-scan.py <module-path> --versions <target>` (lihat `--help`). Skrip mencocokkan ruleset lintas-versi di `assets/ps-rules.json` ke source module dan mengeluarkan temuan JSON per versi dengan `pass`/`errors`/`warnings`. Ini sumber kebenaran untuk aturan yang diketahui pasti — jangan menilai ulang temuannya dengan tangan.
- Predicted delta: None expected — findings arrive self-labeled from the script, and Lapis 3 already defines its own boundary as "di luar yang lolos statis". Route to variant eval to confirm. ~55 tokens recovered.

#### leanness-3 — Honesty-on-degrade rule restated four-plus times across sections

- Lens: leanness
- Location: `SKILL.md:29,33,37-39,43`
- Evidence: Lapis 2: "jangan diam-diam klaim lolos penuh"; Lapis 4: "Degrade jujur seperti Lapis 2" followed by a full restatement anyway ("versi itu tak konklusif, vonis jatuh ke lapis lain — jangan sembunyikan"); Vonis: "jangan sembunyikan" plus "jangan biarkan uji parsial terbaca seolah coverage penuh"; Mode headless re-narrates skipped_image/skipped_browser semantics ("tak konklusif, tak memblok") the scripts and aggregate already enforce. Canon: defensive padding and restated facts. The machine verdict is mechanically protected — ps-aggregate.py computes pass/conclusive flags the prose is forbidden to override — so the rule only pays where the human summary is produced (Vonis dan output).
- Recommendation: State the honesty rule once, in Vonis dan output where the summary is written; per-layer text keeps only the status vocabulary (skipped/skipped_image/skipped_browser/tak konklusif).
- Proposed smallest: Per layer: "Docker/compose absen → status: skipped; image belum ada lokal → skipped_image; DB/boot gagal → tak konklusif." Lapis 4: "Degrade jujur seperti Lapis 2 (plus skipped_browser bila browser absen)." Canonical rule sekali di Vonis dan output: "Lapis yang tak konklusif atau cakupan yang dipersempit wajib disebut eksplisit — vonis tak pernah mengklaim coverage yang tak diuji."
- Predicted delta: Essentially none for workflow callers (aggregate enforces conclusiveness mechanically); small risk the interactive summary softens degrade language, mitigated by keeping the full rule at the summary-production site. Route to variant eval to confirm. ~60-80 tokens recovered.

#### architecture-1 — SKILL.md in warn tier with near-zero headroom to hard budget

- Lens: architecture
- Location: `SKILL.md (whole file; heaviest section ## Validate)`
- Evidence: 2993 tiktoken tokens vs org desired 2000 / hard budget 3000 — warn tier per the principles' length guidance, and only 7 tokens under the hard tier after this session's scope-selection and Lapis 4 additions. ## Validate carries ~1300 tokens; its Lapis 4 paragraph restates visual-verification mechanics (--screenshot-dir placement, --headed opt-in/CI prohibition) that references/e2e-quickstart.md section 'Verifikasi visual' already covers standalone, and ## Vonis dan output repeats the screenshot-review conditional.
- Recommendation: Warn-tier action only (do not block): trim the Lapis 4 visual-verification detail to the routing pointer that already exists ('alat visual selengkapnya: references/e2e-quickstart.md') and keep one inline line for the interactive default. That restores headroom so the next edit does not trip the over-budget hard finding, which would force a larger lift.

#### architecture-2 — Headless mode omits the memlog assumption trail the principles require

- Lens: architecture
- Location: `SKILL.md: ## Mode headless`
- Evidence: The skill claims headless invocation (CI gate, called by psm-cross-version/psm-develop/psm-scaffold) and makes user-absent assumptions there: module-path inferred 'dari argumen/konteks', resolver-absent fallback to canonical defaults ('catat bahwa default dipakai' with no stated destination), scope defaulting, and parent self-review when subagents are unavailable. The return is 'ringkasan satu baris + path JSON' — no typed assumption/decision entries and no memlog path, though {project-root}/_bmad/scripts/memlog.py exists in this project. Layer JSONs record degradations (skipped/skipped_image/inconclusive_note) but not intent inferences or default fallbacks, so per the principles' Headless mode section the audit trail breaks on the next session.
- Recommendation: In ## Mode headless, append assumptions and decisions (module-path inference, defaults-used fallback, self-review substitution) as typed entries via {project-root}/_bmad/scripts/memlog.py and include the memlog path alongside the result JSON path in the return.

#### determinism-2 — FATAL_SIGNS classifies page-brokenness by generic substrings over full serialized HTML

- Lens: determinism
- Location: `scripts/ps-e2e-run.py:95-99 (FATAL_SIGNS), 290-293 (expect_no_fatal)`
- Evidence: bad = ... or any(s in html for s in FATAL_SIGNS) with signs including the generic phrases 'There was an error' and 'Uncaught Error'. page.content() includes inline script/JSON (PrestaShop FO/BO pages embed JS translation dictionaries and message templates), so a healthy page whose embedded strings legitimately contain such a phrase is conclusively classified 'fatal' — a blocking false finding against a healthy module. The specific signatures (PrestaShopException, 'Whoops, looks like something went wrong') are fine; the leak is the generic phrases deciding meaning from content position-blind.
- Recommendation: Intelligence leak: string match deciding meaning. Keep it in the script but anchor the generic phrases to structure: rely on the existing status>=500 check plus version-specific error-page markers (e.g., Symfony/PS error containers via locator), and require generic phrases to co-occur with an error-page selector rather than match anywhere in serialized HTML. Deterministic and unit-testable against fixture HTML with an embedded 'There was an error' translation string.

#### determinism-3 — Knowledge-base rule augmentation makes the prompt hand-apply deterministic rules the scan script cannot ingest

- Lens: determinism
- Location: `SKILL.md On Activation step 3 + scripts/ps-static-scan.py:150 (--rules)`
- Evidence: SKILL.md: 'baca [validator-rules.md] untuk aturan/tag tambahan di luar yang sudah di-embed di assets/ps-rules.json' — but ps-static-scan.py only accepts a single --rules file that REPLACES the default ruleset; there is no merge path for supplemental rules. Tag additions flow cleanly via --tag-map, but supplemental validator rules can only be applied by the model hand-scanning module source (signal verbs: 'scan for', 'detect pattern'), which is unreliable and re-paid every run — misses read as false passes for exactly the rules the operator added.
- Recommendation: Determinism leak: rule-vs-source regex matching has one correct answer per input (determinism test questions 1 and 2 both yes). Add an --extra-rules <file> flag to ps-static-scan.py that merges supplemental rules in the ps-rules.json schema, have the memory file carry rules in that schema, and reduce the prompt's job to passing the path — same pattern as the existing --tag-map.

#### determinism-4 — Model-authored adversarial JSON is aggregated without structural validation; off-enum severities and bad version tokens silently un-block

- Lens: determinism
- Location: `scripts/ps-aggregate.py:183-198 (adversarial_layer) + SKILL.md Lapis 3`
- Evidence: errs = sum(1 for f in findings if f['severity'] == ERROR) counts only the literal 'error'; a model that writes 'critical'/'high'/'blocker' produces a finding that silently never blocks, and a versions token that matches no target (e.g. 'PS8', '1.7-9') is silently dropped from every version by _version_matches — in both cases the Layer-3 verdict degrades with no signal. The bar file's post-processing category ('verify model output meets structural requirements') is unapplied at the one seam where model output feeds the deterministic verdict.
- Recommendation: Determinism leak by omission: schema validation of the adversarial file is script work (unit-testable pass/fail). Have ps-aggregate validate the adversarial payload — severity must be in {error,warning}, each versions entry must resolve against target_versions — and surface violations loudly (exit 2 or an 'adversarial_schema_notes' field mirroring e2e_scenario_notes) instead of silently counting the finding as non-blocking or dropping it.

#### customization-1 — Interactive browser scope options hardcoded beside psm_e2e_browsers

- Lens: customization
- Location: `SKILL.md:On Activation step 2`
- Evidence: The new scope menu sources versions from config ('versi dari psm_target_versions (satu/subset/semua)') but enumerates browser choices as literal prose 'browser Lapis 4 (chromium/firefox/keduanya; default psm_e2e_browsers)'. The default reads the resolver key, yet the option labels are a hardcoded copy of that key's canonical default. If an org overrides psm_e2e_browsers (e.g. 'chromium' only — plausible today since firefox install is deferred), the menu still offers firefox and 'keduanya' presumes exactly that pair, so the override is contradicted by the offered choices even though the default resolves correctly.
- Recommendation: Phrase the browser choice the same way as versions: source the option set from the resolved key, e.g. 'browser Lapis 4 dari psm_e2e_browsers (satu/subset/semua; default semua yang dikonfigurasi)', removing the literal chromium/firefox/keduanya enumeration.

#### enhancement-2 — Add: automate the documented BO warm-up so cold-container login stops degrading coverage (opportunity)

- Lens: enhancement
- Location: `scripts/ps-e2e-run.py:436-460 (_bo_login) + :618 (wait_http FO only); references/e2e-quickstart.md:152-154`
- Evidence: Pattern: graceful degradation applied where deterministic plumbing should prevent the degrade. The quickstart gotcha instructs the human to 'warm-up (hit BO sekali via curl) sebelum run, atau ulang run-nya' for flaky 1.7.8/8.1 cold-container login; run_one_version already polls wait_http on FO but never touches BO before _bo_login, so every cold first run silently drops BO steps to inconclusive — honest, but avoidably so. Intelligence-placement says this is script work, not operator ritual. Memlog gap candidate (1), confirmed worth doing.
- Recommendation: In run_one_version, warm BO with wait_http(bo + '/index.php?controller=AdminLogin', ...) before driving browsers, and/or one retry inside _bo_login when the login form is still present after the wait; then demote the gotcha from manual instruction to background note. No SKILL.md cost.

#### enhancement-3 — Add: guard the resume affordance — reuse of layer JSONs is invited with no freshness condition

- Lens: enhancement
- Location: `SKILL.md:25 (Validate intro) + On Activation`
- Evidence: Pattern: working state across turns, plus the 'vague progression conditions' failure mode. The Validate intro says predictable per-layer paths let an interrupted run continue 'tanpa mengulang lapis mahal', but nothing defines when reuse is safe: layer filenames carry no timestamp (<module>-<lapis>.json), On Activation never checks for existing files, and ps-aggregate accepts whatever it is handed — so a liberal reading can aggregate stale layer JSONs from before a module edit and produce a wrong verdict in a quality gate; a conservative reading re-runs minutes of Docker boots for nothing.
- Recommendation: One testable sentence at the Validate intro: reuse a layer file only when it postdates the module's last modification (mtime) and matches the chosen scope; otherwise re-run that layer. SKILL.md sits 7 tokens under hard budget, so pay for it by compressing the flag enumeration in 'Vonis dan output' (the ps-aggregate invocation detail is recoverable from --help).

### Low (7)

#### leanness-4 — On Activation step 1 over-enumerates resolver keys and pre-states Lapis 4 facts

- Lens: leanness
- Location: `SKILL.md:19 (On Activation step 1)`
- Evidence: The step lists eight-plus config keys ending in "dll"; the flashlight keys are re-listed as flags at their point of use in Lapis 2 ("--db-image, --ps-domain, --orchestrator, --startup-timeout"), and the psm_e2e_enabled gate is restated in the Lapis 4 heading. "(bukan key baru)" is negative space narrating a key that does not exist. Core test: restated facts and meta-description; the key names change no move that the point-of-use text doesn't already drive.
- Recommendation: Truncate: keep the resolver invocation, "baca apa adanya / jangan parse config.yaml sendiri", the resolver-absent fallback, and the two keys step 2's scope prompt actually consumes (psm_target_versions, psm_e2e_browsers); drop the flashlight-key enumeration, "dll", and "(bukan key baru)" — Lapis 2/4 own those facts at point of use.

#### leanness-5 — Lapis 2 narrates the script's internal orchestration blow-by-blow

- Lens: leanness
- Location: `SKILL.md:29 (Lapis 2)`
- Evidence: "skrip membangun DB+flashlight berpasangan, menunggu sehat, lalu install module dan jalankan phpstan" describes steps the script performs with no operator decision attached — mechanics belonging to the file that performs them. Truncate-before-delete: "Flashlight butuh database (image-nya web-tier saja)" is the one clause of why that makes the DB failure statuses legible, and the neon conclusive/advisory distinction shapes how findings are reported; the spin/wait/install narration between them is inferable from the script's output.
- Recommendation: Compress to: "Flashlight butuh DB terpisah (image-nya web-tier saja) — skrip mengurus pasangannya dan menjalankan phpstan terhadap core asli (neon module ada = konklusif; auto-generate = advisory, tak memblok)."

#### leanness-6 — ALL-CAPS directives in e2e-quickstart (HARUS/WAJIB/JANGAN/SELALU/DULU)

- Lens: leanness
- Location: `references/e2e-quickstart.md:16,34,56,105,110,135,139,148,157`
- Evidence: Yellow flag per spec: shouted imperatives — "docker compose HARUS aktif", "(WAJIB untuk halaman configure module)", "Skenario menuju configure HARUS men-dismiss", "JANGAN di headless/CI", "SELALU ditangkap". Most already sit next to their verified failure (the 1.7/8 "Invalid security token" interstitial evidence), so the caps add volume, not information.
- Recommendation: Decapitalize and let the stated failure carry the rule, e.g. heading "(WAJIB untuk halaman configure module)" → "(tanpa ini, skenario configure gagal di 1.7/8)". Where no failure is named next to the shout, name it instead of shouting.

#### leanness-7 — Spec-format facts duplicated across surfaces have already drifted

- Lens: leanness
- Location: `references/e2e-quickstart.md:101 vs scripts/ps-e2e-run.py:57`
- Evidence: Quickstart says placeholders substitute in `path`/`url`/`text`/`value`; the script docstring — which the quickstart itself declares "rujukan otoritatif" via `--help` — says only `path`/`url`/`text`. Code at scripts/ps-e2e-run.py:322 substitutes `value`, so the declared-authoritative surface is the stale one. This is the materialized cost of restating mechanics on multiple surfaces (the table itself earns its keep: its annotations — expect_text timing, BO conclusiveness, click_optional's interstitial use-case — exist nowhere in --help).
- Recommendation: Fix the script docstring (add `value` at ps-e2e-run.py:57) and keep exactly one bare action list authoritative (--help), leaving the quickstart table to carry only the judgment annotations that --help lacks.

#### architecture-3 — Lapis 3 subagent handoff omits the target-version list its return contract depends on

- Lens: architecture
- Location: `SKILL.md: ## Validate, Lapis 3`
- Evidence: The delegation spec hands the reviewer 'path module' and the checklist, but the required return schema demands per-finding 'versions' using 'token yang sama dengan --versions' — a value the reviewer is never explicitly given. The cross-version lens ('perilaku berbeda diam-diam antar 1.7/8/9') also needs the narrowed scope from On Activation step 2 to review the right targets. A capable model usually bridges this, but under narrowed scope the reviewer can emit mismatched or out-of-scope version tokens that the aggregate treats as target findings.
- Recommendation: Make the handoff explicit: 'beri path module, versi target (token --versions), checklist ... bila ada' so the reviewer's scope and its versions tokens are pinned to the run's selection.

#### customization-2 — Engine pair chromium+firefox baked into SKILL.md prose and install prerequisite

- Lens: customization
- Location: `SKILL.md:Overview, Validate Lapis 4 heading and prerequisite`
- Evidence: Overview says 'E2E di Chromium+Firefox', the Layer-4 heading repeats 'di Chromium+Firefox', and the prerequisite instructs 'playwright install chromium firefox' unconditionally — all echoes of the psm_e2e_browsers default rather than the resolved value. With a narrowed override the model would still instruct installing an engine the org deliberately excluded. Harm is bounded because degrade is honest (skipped_browser, browser_notes), so this misleads rather than breaks.
- Recommendation: Neutralize the prose to 'uji perilaku browser E2E' and tie the prerequisite to the resolved set ('playwright install <engine dari psm_e2e_browsers>'); keeping the canonical pair as an example is fine, presenting it as the fixed set is not.

#### enhancement-4 — Add: auto-settle expect_text after navigation instead of prescribing an authoring workaround (opportunity)

- Lens: enhancement
- Location: `scripts/ps-e2e-run.py:298-301 + references/e2e-quickstart.md:94`
- Evidence: Pattern: graceful degradation covering a flake the script can settle deterministically. expect_text reads page.content() immediately, so after submit+redirect it can false-fail on timing; the action-table row itself documents the sensitivity and tells authors to precede it with expect_visible on a marker element. A flaky red in a CI gate erodes trust in red runs, though the failure is visible (not a silent pass) and the workaround is documented — hence low. Memlog gap candidate (3).
- Recommendation: Before the content() read in expect_text, do a bounded wait_for_load_state('load') (mirroring the _bo_login networkidle-then-load fallback), keep assertion semantics unchanged, then trim the timing-workaround clause from the action-table row. Script + reference only; no SKILL.md cost.
