# Analysis Report: psm-validate

Generated: 2026-07-08 · Schema: 2

**Grade: Good**

> The rank-1 determinism fix landed — verdict assembly is now a deterministic script and the determinism lens is clean — but the reworded prompt re-narrates the script's internal logic (leanness) and the new adversarial-JSON contract has an unpinned version-key format that can silently drop a real error (architecture). Deferred rank-2/3 items still stand. Persona treated as investment, not waste.

psm-validate correctly moved verdict computation out of the prompt into ps-aggregate.py; determinism is now clean and the honest-degrade rule is enforced in code. The primary opportunity is a two-part regression from that edit — the Vonis section narrates logic the script now owns, and Lapis 3's adversarial version-key format is unspecified against the aggregator's exact-match filter, so a major-form version string could silently drop a blocking finding — plus the two still-open enhancement items (headless image-pull policy, failing-verdict dead-end).

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 1 |
| Medium | 4 |
| Low | 2 |

## Themes

### 1. Rank-1 edit left prose narrating logic that moved into the script

- Root cause: Moving verdict assembly into ps-aggregate.py was correct, but the reworded Vonis section re-describes what the script computes internally (the pass/conclusive rule) and the flashlight-honesty rule now appears three times; Lapis 3 also carries a negative-space clause narrating what the layer no longer does. The only load-bearing line is 'do not override the script's pass/conclusive'.
- Fix: Trim the Vonis section to the script invocation, the do-not-override rule, and the human-summary bar (keep the flashlight_conclusive callout for Budi); drop the internal-logic narration and the Lapis 3 'satu-satunya tugasmu' clause. Keep the honesty rule at exactly two genuinely distinct consumers (Lapis 2 operator-facing, summary human-facing).
- Findings:
  - `leanness-1` Vonis section restates the script's internal pass/conclusive rule after it moved into ps-aggregate.py — `SKILL.md:Vonis dan output`
  - `leanness-2` Flashlight-inconclusive honesty rule repeated across three sections — `SKILL.md:Lapis 2 / Vonis / human-summary`
  - `leanness-3` Negative-space clause narrating Lapis 3's boundary — `SKILL.md:Lapis 3`

### 2. Adversarial-JSON contract has an unpinned version-key format

- Root cause: ps-aggregate.py filters adversarial findings with exact full-version membership (1.7.8/8.1/9.0), but SKILL.md Lapis 3 does not pin the format of the versions key. A model writing major-form '8' or '9' produces a version that matches no target key, so a real severity:error adversarial finding silently drops out of blocking and the version can falsely pass — directly against the 'never pass on the untested' promise.
- Fix: Either state in Lapis 3 that versions entries must be the exact full-version tokens passed to --versions, or have adversarial_layer normalize both sides (reuse the norm_versions major-mapping) before membership testing so major- and full-form both resolve. Add a regression test for a major-form adversarial finding.
- Findings:
  - `architecture-1` Adversarial versions key format unspecified against aggregate's full-version filter — `SKILL.md:Lapis 3 vs scripts/ps-aggregate.py:adversarial_layer`

### 3. Deferred rank-2/3 items still open

- Root cause: Not yet addressed by design (rank-2 and rank-3 were deferred): headless has no policy for the flashlight image-download gate (silent multi-GB pull or hang), the agent dead-ends after a failing verdict instead of offering the next move, and the description still headlines 'di flashlight' — the one layer that may not run.
- Fix: Rank 2: give headless a non-interactive image policy (skip Layer 2 when the image is not local; require an explicit --allow-pull opt-in). Rank 3: close a failing interactive verdict with a one-line next-move offer (hand blocking errors to psm-develop / re-run after patch), and regrain the description to lead with the always-on static + adversarial identity, flashlight when Docker is available.
- Findings:
  - `enhancement-1` Headless mode has no policy for the flashlight image-download gate — `SKILL.md:Mode headless + Lapis 2`
  - `enhancement-3` Agent dead-ends after a failing verdict instead of offering the next move — `SKILL.md:Vonis dan output (Budi summary)`
  - `agent-cohesion-1` Description headlines flashlight (conditional layer) as the whole capability — `SKILL.md:3 (description)`

## Strengths

- Determinism boundary is now correct end-to-end: three deterministic scripts (static, flashlight, aggregate) own rule-matching, exact count parsing, and the merge+pass computation; the prompt owns only adversarial judgment and human-facing prose.
- Honest-degrade is now enforced in code, not just instruction: flashlight not-conclusive (Docker absent, pull-fail, timeout, no_console) never blocks nor claims pass, with per-version flashlight_conclusive surfaced to callers. The load-bearing 'never pass on the untested' persona is now structural.
- The new aggregate step reinforces rather than dilutes the meticulous-honest-validator persona; the 4-step flow still maps cleanly onto the agent's identity.
- New ps-aggregate.py ships with a 15-assert unit test covering native pass computation and every not-conclusive degrade path; scripts lint clean, all three scripts tested.
- Config remains right for a stateless agent — no needless customize.toml, tunables externalized to project config.

## Recommendations

1. Pin the adversarial versions-key format in Lapis 3 (or normalize both sides in adversarial_layer) and add a major-form regression test, so a real blocking finding can never silently drop and falsely pass a version. (resolves: architecture-1)
2. Trim the Vonis section and Lapis 3 to remove prose that re-narrates the script's internal logic; keep only the invocation, the do-not-override rule, the human-summary bar, and one honesty callout per distinct consumer. (resolves: leanness-1, leanness-2, leanness-3)
3. Give headless a non-interactive flashlight image policy (skip Layer 2 when image absent; explicit --allow-pull to opt in). Closes the silent multi-GB pull / hang in CI. (resolves: enhancement-1)
4. Close a failing interactive verdict with a one-line next-move offer, and regrain the description to lead with the always-on static + adversarial identity (flashlight when Docker available). (resolves: enhancement-3, agent-cohesion-1)

## Agent Profile

- Name: psm-validate
- Title: PrestaShop Cross-Version Module Validator
- Type: stateless
- Mission: Produce an evidence-based verdict on whether a module is healthy across PrestaShop 1.7/8/9 at once, via deterministic rules, real flashlight behavior, and adversarial e-commerce review.

## Capabilities

- **Layer 1 — static cross-version scan** (script) — ps-static-scan.py matches assets/ps-rules.json ruleset per version; always runs, always conclusive.
- **Layer 2 — flashlight behavior test** (script) — ps-flashlight-run.py spins prestashop-flashlight per version, installs, runs coding-standard against real core; Docker-gated, degrades to skipped.
- **Layer 3 — adversarial e-commerce review** (prompt) — Model's skeptical judgment; now emits findings as JSON for the aggregator to merge.
- **Verdict aggregation** (script) — ps-aggregate.py (new) merges the three layers and computes per-version/overall pass natively; flashlight not-conclusive never blocks nor claims pass.

## Per-Lens Verdicts

- **leanness**: Mostly lean; the reworded 'Vonis dan output' narrates ps-aggregate.py's internal pass/conclusive logic as prose after that logic moved into the script, and the flashlight-honesty rule now appears three times.
- **architecture**: Topology, ordering, and three-layer data-flow into ps-aggregate.py are sound; one medium data-flow precision gap on the adversarial version-key format.
- **determinism**: Prior determinism-1 and determinism-2 are genuinely closed; ps-aggregate.py owns merge/pass/conclusive natively and SKILL.md forbids the prompt overwriting them. No residual or new leak.
- **customization**: Stateless, config surface clean; no customize.toml by deliberate family design, new ps-aggregate.py introduces zero config surface and no stranded template.
- **enhancement**: Prior enhancement-2 (infra failure blocking FAIL) confirmed fixed by honest-degrade aggregation; two prior items still stand — headless image-download gate, and dead-end after a failing verdict.
- **agent-cohesion**: Coherent; the meticulous-honest-validator persona maps cleanly onto the now 4-step flow and the aggregate step reinforces the 'jujur' trait. One prior description-vs-capability mismatch persists (deferred rank-3).

## Experience

- **Budi validates before release** — invoke on module path → L1 static → L2 flashlight if Docker → L3 adversarial (emits JSON) → ps-aggregate merges → conversational per-version pass/fail with fixes; still dead-ends after a FAIL
- **Workflow calls as quality gate (headless)** — workflow passes module-path + versions → three layers run → aggregate computes pass → JSON + one-line summary returned; CI exits on overall pass. Gap: no defined policy for the flashlight image pull.
- Headless: Real CI-gate story with native pass computation and honest not-conclusive degrade. Open gap: the flashlight image-download confirmation has no headless carve-out, risking a silent multi-GB pull or a hang on a confirmation no one answers.

## Findings

### High (1)

#### enhancement-1 — Headless mode has no policy for the flashlight image-download gate

- Lens: enhancement
- Location: `SKILL.md:Mode headless + Lapis 2`
- Evidence: The confirm-before-pull instruction ('beri tahu user... konfirmasi sebelum lanjut') is a conversational gate assuming a human is present. Headless mode says 'jalankan ketiga lapis' with no carve-out, so a CI run with no local flashlight image silently triggers a multi-GB pull, or hangs waiting on a confirmation no one gives. The honest-degrade aggregator handles a pull that fails, but not the cost/latency of one that succeeds unbidden.
- Recommendation: In Mode headless, default to skipping Layer 2 when the flashlight image is not already local (verdict falls to Layer 1/3, which the aggregator reports as flashlight_conclusive=false), and require an explicit opt-in flag (e.g. --allow-pull) for headless callers that genuinely want the pull.

### Medium (4)

#### architecture-1 — Adversarial versions key format unspecified against aggregate's full-version filter

- Lens: architecture
- Location: `SKILL.md:Lapis 3 vs scripts/ps-aggregate.py:adversarial_layer`
- Evidence: aggregate filters each adversarial finding with `full_ver not in (f.get('versions') or target_versions)`, where target_versions are FULL keys from static output (1.7.8, 8.1, 9.0). SKILL only says 'versi terpengaruh, kosongkan bila semua target' without pinning the format. A model that writes major-form '9' or '8' produces a version that matches no target key, so a real severity:error finding silently drops out of blocking and the version can falsely pass — contradicting the 'tak pernah meloloskan module' promise. The empty-list default is safe; the subset case is the hole.
- Recommendation: State in Lapis 3 that versions entries must be the exact full-version strings passed to --versions, or have adversarial_layer normalize both sides (reuse norm_versions major-mapping) before membership testing so major- and full-form both resolve. Add a regression test.

#### leanness-1 — Vonis section restates the script's internal pass/conclusive rule after it moved into ps-aggregate.py

- Lens: leanness
- Location: `SKILL.md:Vonis dan output`
- Evidence: The section spends ~4 clauses describing what the script computes internally ('Skrip menghitung pass per versi... sebuah versi lolos hanya bila tak ada temuan error dari lapis konklusif manapun, sementara lapis flashlight yang tak konklusif... tak pernah memblok maupun diklaim lolos'). The rank-1 fix moved exactly this into ps-aggregate.py, so the model no longer computes or can override it. The only load-bearing instruction is 'Jangan menilai ulang atau menimpa pass/conclusive/flashlight_conclusive'; the rest is meta-explanation of a component the model just invokes.
- Recommendation: Cut the internal-logic narration; keep the script invocation, the do-not-override rule, and the human-summary bar. The honesty guarantee lives in the script's output (flashlight_conclusive), which the summary already surfaces.
- Proposed smallest: Serahkan penggabungan ke skrip. Jalankan `uv run scripts/ps-aggregate.py --static <static.json> [--flashlight <flashlight.json>] [--adversarial <adv.json>] -o <psm_reports_dir>/<module>-<timestamp>.json` (lewati flag lapis yang tak dijalankan). Jangan menilai ulang atau menimpa `pass`/`conclusive`/`flashlight_conclusive` dari skrip. Untuk Budi: ringkas per versi lolos/gagal, error pemblokir + fix, dan warning; bila `flashlight_conclusive` false sebutkan eksplisit bahwa uji perilaku tak konklusif dan vonis bersandar pada lapis lain. Headless: JSON saja, jangan tambah prosa.
- Predicted delta: Nothing material. The removed sentences only describe ps-aggregate.py's internal pass/conclusive rule, which the script now enforces deterministically; the model neither computes it nor can override it (the retained 'jangan menimpa' rule guards that). Route to variant eval to confirm cut-or-keep.

#### enhancement-3 — Agent dead-ends after a failing verdict instead of offering the next move

- Lens: enhancement
- Location: `SKILL.md:Vonis dan output (Budi summary)`
- Evidence: After a failing verdict the conversational summary lists per-version fail, blocking errors with fixes, and warnings — then stops. It surfaces the fixes but never offers to act on them: no hand-off to psm-develop, no re-run offer. The user is left to figure out the next step. Headless correctly stays terse — this applies only to the interactive path.
- Recommendation: In the Budi-facing summary, after a FAIL close with a one-line next-move offer routing to the natural follow-ups (hand blocking errors to psm-develop, or re-run psm-validate once patched). Keep it one line — a door, not a wizard.

#### agent-cohesion-1 — Description headlines flashlight (conditional layer) as the whole capability

- Lens: agent-cohesion
- Location: `SKILL.md:3 (description)`
- Evidence: Description reads 'Validasi module PrestaShop terhadap 1.7/8/9 di flashlight.' — it fronts flashlight as identity. But flashlight is Layer 2, running only 'bila Docker ada' and returning status:skipped otherwise; the always-on layers are Layer 1 (static) and Layer 3 (adversarial). The headline advertises the one layer that may not run while the deterministic always-available layers are unnamed. Unchanged since prior run (rank-3 deferred).
- Recommendation: Regrain the description to name the durable capability first — cross-version static + adversarial validation always, flashlight behavioral testing when Docker is available — so the headline matches what the agent reliably delivers.

### Low (2)

#### leanness-2 — Flashlight-inconclusive honesty rule repeated across three sections

- Lens: leanness
- Location: `SKILL.md:Lapis 2 / Vonis / human-summary`
- Evidence: The 'inconclusive flashlight must not silently claim pass' rule is stated three times: Lapis 2 ('degrade dengan jujur... jangan diam-diam mengklaim lolos penuh'), Vonis ('tak pernah memblok maupun diklaim lolos'), and human-summary ('Bila flashlight_conclusive false, sebutkan eksplisit... jangan sembunyikan'). The Vonis copy is subsumed once leanness-1's internal-logic narration is removed.
- Recommendation: Let leanness-1's trim remove the Vonis copy; keep Lapis 2 (skipped-layer degradation, operator-facing) and the human-summary (Budi-facing). One rule, two distinct consumers, no third copy.

#### leanness-3 — Negative-space clause narrating Lapis 3's boundary

- Lens: leanness
- Location: `SKILL.md:Lapis 3`
- Evidence: Closing clause 'Ini satu-satunya tugasmu di lapis ini: menghasilkan temuan, bukan menghitung vonis.' narrates what this layer no longer does. The Vonis section already owns verdict computation, and the preceding sentence already tells it to write findings JSON for the aggregator.
- Recommendation: Drop the clause; the 'tulis temuanmu sebagai JSON... supaya skrip agregat memperlakukannya setara lapis lain' sentence already fixes the boundary without narrating it.
