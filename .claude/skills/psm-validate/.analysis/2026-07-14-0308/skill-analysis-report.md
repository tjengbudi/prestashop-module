# Analysis Report: /home/budi/dev/prestashop-module/.claude/skills/psm-validate

Generated: 2026-07-14 · Schema: 2

**Grade: Excellent**

> Clean pass — all nine findings from the prior run are verified closed, including the HIGH false-pass bug; leanness raised two new low redundancies from the fixes, which were trimmed in-session. No open findings.

The four-layer validator is coherent and correct after the fix pass: the per-browser honest-degrade leak that produced a false pass is closed (verified adversarially by the determinism and enhancement lenses), skipped engines and broken authored specs now surface honestly, the config gate is functional via the resolver, and the family-wide resolver path divergence is healed. SKILL.md is lean at 2639 tokens (under the 3000 budget) and every script carries passing tests.

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 0 |

## Strengths

- HIGH false-pass bug closed with a provable invariant: every res['errors'] write early-returns, so a version's findings and infra-errors are mutually exclusive — a co-tenant browser's launch failure can no longer void another browser's blocking finding (verified by determinism + enhancement lenses).
- Honest-degrade is now per-browser: probe-miss and launch-fail surface as non-blocking coverage notes; skipped authored specs survive both in inconclusive_note and a top-level e2e_scenario_notes echo, so partial coverage never reads as full.
- Four validation layers compose symmetrically in ps-aggregate; e2e_layer mirrors flashlight_layer; verdict is fully script-computed and single-answer with no model re-judgment.
- Config is a single coherent resolver-based mechanism: psm_e2e_enabled/psm_e2e_browsers registered as resolver defaults (overridable via config.yaml, not module.yaml — matching the flashlight-docker-keys precedent), and the resolver now exists at the documented path all six psm-* skills reference.
- Self-contained E2E orchestration reuses ps-flashlight-run.py by sibling import with a backward-compatible optional publish port; proven on a real PS 9.1 run (install ok, chromium drove smoke + authored scenario, clean teardown).
- SKILL.md is lean (2639 tokens) and defers the E2E scenario-spec format to the script's --help rather than narrating it inline.

## Experience

- **Interactive validate** — resolve config -> pick module -> run 4 layers (static always; flashlight/E2E if enabled + Docker + browser; adversarial always) -> aggregate -> human summary that names not-conclusive layers and coverage/skip notes
- **Headless CI gate** — module-path+versions from args -> run available layers without --allow-image-pull -> JSON only -> exit on overall pass
- Headless: Solid: skips clarification, never auto-pulls images or downloads browsers, degrades to available layers, and now surfaces partial-coverage (missing browser / skipped authored spec) so a partial run is never mistaken for full coverage.

## Findings

No findings: the scanners returned a clean pass.
