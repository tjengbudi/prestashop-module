# Analysis Report: psm-validate

Generated: 2026-07-08 · Schema: 2

**Grade: Good**

> The two regressions from the rank-1 edit are both verified closed — leanness is clean and the adversarial version-key hole is fixed with major/full-form matching that does not leak across majors, covered by a regression test. Only the deliberately-deferred rank-2/3 items remain: a headless flashlight image-pull policy (high) and two interactive-polish items. Persona treated as investment, not waste.

psm-validate now has a clean determinism boundary, a lean SKILL.md, and a data-flow contract that can no longer silently drop a blocking adversarial finding. The single remaining item of substance is the deferred rank-2 headless image-download policy: a CI run with no local flashlight image can silently trigger a multi-GB pull or hang on a confirmation no one answers. The two rank-3 polish items (dead-end after a failing verdict, description headlining the conditional flashlight layer) are low-risk framing/experience gaps.

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 1 |
| Medium | 2 |
| Low | 0 |

## Themes

### 1. Deferred rank-2/3 items — all that remains

- Root cause: Everything else is clean; the only open findings are the items deliberately deferred when rank-1 was chosen first. Headless has no policy for the flashlight image-download gate (silent multi-GB pull or hang), the agent dead-ends after a failing interactive verdict instead of offering a next move, and the description still headlines 'di flashlight' — the one layer that may not run — while the always-on static and adversarial layers go unnamed.
- Fix: Rank 2: give Mode headless a non-interactive image policy — default to skip Layer 2 and degrade honestly when the flashlight image is not already local, with an explicit opt-in flag (e.g. --allow-image-pull) for callers that want the pull. Rank 3: close a failing interactive verdict with a one-line next-move offer (hand blocking errors to psm-develop / re-run once patched), and regrain the description to lead with the always-on static + adversarial identity, flashlight when Docker is available.
- Findings:
  - `enhancement-1` Headless mode has no policy for the flashlight image-download gate — `SKILL.md:Mode headless vs Lapis 2`
  - `enhancement-3` Agent dead-ends after a failing interactive verdict instead of offering the next move — `SKILL.md:Vonis dan output (Budi summary)`
  - `agent-cohesion-1` Description headlines flashlight (conditional layer), hides always-on layers — `SKILL.md:3 (description)`

## Strengths

- Determinism boundary is correct end-to-end: three deterministic scripts (static, flashlight, aggregate) own rule-matching, exact count parsing, the merge+pass computation, and version normalization; the prompt owns only adversarial judgment and human-facing prose.
- Honest-degrade is enforced in code: flashlight not-conclusive (Docker absent, pull-fail, timeout, no_console) never blocks nor claims pass, with per-version flashlight_conclusive surfaced. The load-bearing 'never pass on the untested' persona is structural, not just declared.
- The adversarial-findings contract is now safe against a real failure mode: major- and full-form version strings both resolve without leaking across majors, so a blocking finding can no longer silently drop and falsely pass a version — regression-tested.
- ps-aggregate.py ships with an 18-assert unit test covering native pass computation, every not-conclusive degrade path, and the version-matching regression; scripts lint clean, all three scripts tested. SKILL.md is lean at 1721 tokens.
- Config remains right for a stateless agent — no needless customize.toml, tunables externalized to project config via a shared resolver.

## Recommendations

1. Give Mode headless a non-interactive flashlight image policy: default to skip Layer 2 and degrade honestly when the image is not already local; require an explicit opt-in flag (e.g. --allow-image-pull) for headless callers that want the pull. Closes the silent multi-GB pull / hang in CI. (resolves: enhancement-1)
2. Close a failing interactive verdict with a one-line next-move offer (hand blocking errors to psm-develop, or re-run once patched), interactive-only, and regrain the description to lead with the always-on static + adversarial identity (flashlight when Docker available). (resolves: enhancement-3, agent-cohesion-1)

## Agent Profile

- Name: psm-validate
- Title: PrestaShop Cross-Version Module Validator
- Type: stateless
- Mission: Produce an evidence-based verdict on whether a module is healthy across PrestaShop 1.7/8/9 at once, via deterministic rules, real flashlight behavior, and adversarial e-commerce review.

## Capabilities

- **Layer 1 — static cross-version scan** (script) — ps-static-scan.py matches assets/ps-rules.json ruleset per version; always runs, always conclusive.
- **Layer 2 — flashlight behavior test** (script) — ps-flashlight-run.py spins prestashop-flashlight per version, installs, runs coding-standard against real core; Docker-gated, degrades to skipped.
- **Layer 3 — adversarial e-commerce review** (prompt) — Model's skeptical judgment; emits findings as JSON (versions keyed to the same tokens as --versions) for the aggregator.
- **Verdict aggregation** (script) — ps-aggregate.py merges the three layers and computes per-version/overall pass natively; flashlight not-conclusive never blocks nor claims pass; adversarial versions match major- and full-form without leaking across majors.

## Per-Lens Verdicts

- **leanness**: psm-validate passes leanness; all three prior findings genuinely closed, no residual ceremony or repetition.
- **architecture**: Structure sound; prior architecture-1 (versions-key format hole) closed with major/full-form matching that does not leak across majors, contract documented in Lapis 3 and covered by regression test. No new defects.
- **determinism**: Intelligence-placement boundary is clean; verdict assembly and version-normalization are deterministic in ps-aggregate.py, prompt carries only judgment and human-facing prose. Passes.
- **customization**: Stateless agent, about right — no customize.toml by design, config read via shared resolver at activation; no other config mechanism present. Clean.
- **enhancement**: Two prior findings still stand (deferred by design); no edits touched the headless section or failing-verdict summary, and no new enhancement finding survives scrutiny.
- **agent-cohesion**: Persona and three-layer validator capability cohere strongly after trims; one standing misalignment — the description headlines flashlight (the sole conditional layer) while the always-on layers go unnamed.

## Experience

- **Budi validates before release** — invoke on module path → L1 static → L2 flashlight if Docker → L3 adversarial (emits JSON) → ps-aggregate merges → conversational per-version pass/fail with fixes; still dead-ends after a FAIL (deferred)
- **Workflow calls as quality gate (headless)** — workflow passes module-path + versions → three layers run → aggregate computes pass → JSON + one-line summary; CI exits on overall pass. Open gap: no defined policy for the flashlight image pull (deferred rank-2).
- Headless: Real CI-gate story with native pass computation and honest not-conclusive degrade. Open gap (deferred rank-2): the flashlight image-download confirmation has no headless carve-out, risking a silent multi-GB pull or a hang.

## Findings

### High (1)

#### enhancement-1 — Headless mode has no policy for the flashlight image-download gate

- Lens: enhancement
- Location: `SKILL.md:Mode headless vs Lapis 2`
- Evidence: Lapis 2 requires an interactive confirmation before pulling the large flashlight image ('beri tahu user uji ini mengunduh image dan konfirmasi sebelum lanjut'); Mode headless drops clarifying questions and runs all three layers but never resolves what happens to that gate with no human present. A CI run with Docker up but no local image either hangs on an un-answerable confirmation or silently triggers a multi-GB pull. The aggregator handles a pull that fails, but not the cost/latency of one that succeeds unbidden.
- Recommendation: In Mode headless, state the gate's headless behavior explicitly: default to skip Lapis 2 and degrade honestly (report flashlight skipped, verdict on Lapis 1) unless an opt-in flag (e.g. --allow-image-pull) is passed, so a headless caller never blocks or silently downloads.

### Medium (2)

#### enhancement-3 — Agent dead-ends after a failing interactive verdict instead of offering the next move

- Lens: enhancement
- Location: `SKILL.md:Vonis dan output (Budi summary)`
- Evidence: On a fail, the interactive summary reports per-version fail, blocking errors + fixes, and warnings, then stops. The agent goes silent instead of offering a next move, dead-ending the user who just learned their module fails. Headless correctly stays terse — this applies only to the interactive path.
- Recommendation: After an interactive failing verdict, offer a concrete next step (hand blocking errors to psm-develop to fix, or re-run a single layer/version once addressed) — one line, interactive path only.

#### agent-cohesion-1 — Description headlines flashlight (conditional layer), hides always-on layers

- Lens: agent-cohesion
- Location: `SKILL.md:3 (description)`
- Evidence: Description reads 'Validasi module PrestaShop terhadap 1.7/8/9 di flashlight.' — flashlight is Lapis 2, which returns status:skipped when Docker is absent. The two always-on layers that actually always produce the verdict — Lapis 1 static ('selalu jalan') and Lapis 3 adversarial ('selalu') — are unnamed. A user invoking on the strength of 'di flashlight' expects behavioral testing against PS core, but the capability may silently degrade to static-only. The Overview frames all three layers correctly and the body degrades honestly, so this is a one-liner framing gap, not body-level incoherence. Confirmed unchanged.
- Recommendation: Regrain the description to lead with what always runs, e.g. 'Validasi kompatibilitas module PrestaShop 1.7/8/9 lewat pindai statis, uji flashlight, dan review adversarial.' Name the always-on layers first; keep flashlight as one of three, not the headline.
