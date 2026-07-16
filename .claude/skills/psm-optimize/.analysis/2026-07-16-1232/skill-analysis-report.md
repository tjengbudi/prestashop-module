# Analysis Report: /home/budi/dev/prestashop-module/.claude/skills/psm-optimize

Generated: 2026-07-16 · Schema: 2

**Grade: Excellent**

> Converged after two fix rounds: determinism and customization pass clean, no high findings remain, and the six residual medium/low items from this final pass were applied in-session — the only open action is syncing the shared headless-return contract into psm-develop.

This is the convergence scan after the 2026-07-16-1155 'fair' report: the stale skills/ mirror routing, the success-shaped failure paths, and the fragile baseline evidence chain are all closed, and the self-introduced parse_blackfire key-scavenging leak caught by the first re-run is verified fixed (location-scoped extraction, loud rc=2 on ambiguity, 16/16 tests). The findings below are what this final pass surfaced — two medium contract edges and four low restatements — and all except the informational token-band note were fixed immediately after the scan; deterministic checks (integrity, script lint, both test suites, 2862 tokens against the 3000 budget) pass on the final state.

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 0 |
| Medium | 2 |
| Low | 4 |

## Themes

### 1. Headless blocked-return payloads carried half the contract (fixed in-session; psm-develop sync pending)

- Root cause: The four-status vocabulary ported from psm-develop inherited its source's asymmetry: gagal returned reason without the memlog path, butuh intervensi returned memlog without a reason, and sudah-ramping omitted the memlog path entirely — so a caller on a blocked exit could not always locate the assumption trail.
- Fix: Applied: every non-selesai return now carries status + one-line reason + memlog path (sudah-ramping includes the memlog path too). Remaining: apply the same edit to psm-develop's Mode headless so the family contract stays uniform — deliberately not done here because psm-develop is being edited in a parallel session.
- Findings:
  - `architecture-1` Blocked-status returns each carry only half of the required reason+memlog pair — `SKILL.md:59-61 (Mode headless)`
  - `enhancement-2` Add: blocked-status headless returns split the canon's reason+memlog pair — `SKILL.md:61 (Mode headless — empat status akhir)`

### 2. Verify-cap had no reset semantics (fixed in-session)

- Root cause: verify_attempts persists across sessions by design, but nothing reset it — after a butuh-intervensi handoff and a real fix, a headless re-run would read verify_attempts: 3 and re-block deterministically, bounding the module's lifetime instead of one redesign loop.
- Fix: Applied: Verifikasi now resets verify_attempts to 0 when a new/revised plan is approved after intervention.
- Findings:
  - `enhancement-1` Add: verify-cap pattern lacks reset semantics after human intervention — `SKILL.md:51 (Verifikasi — batas 3 percobaan)`

### 3. Residual restatements (fixed in-session)

- Root cause: Two leftovers of the guard-porting rounds: the version-branch rule restated at apply time (already in Identifikasi and in each plan item's 'versi terpengaruh'), and the headless verification guard restating itself twice in one sentence.
- Fix: Applied: cut the Terapkan restatement and truncated the guard to 'Tetap berlaku: gerbang Verifikasi penuh seperti di atas.'
- Findings:
  - `leanness-1` Version-branch rule restated at apply time — `SKILL.md:Terapkan`
  - `leanness-2` Headless verification guard restates itself twice — `SKILL.md:Mode headless`

## Strengths

- Determinism lens passes clean: parse_blackfire now extracts only from known locations (top-level/envelope; metrics for sql), errors loudly with candidate paths on ambiguity, ignores callgraph subtrees — verified by adversarial probes and 16/16 asserts; judgment ('metrik membaik', trade-offs) stays in the prompt.
- Customization lens passes clean: the recorded no-customize.toml decision holds, config flows through the relocated resolve-psm-config.py (now only in .claude/skills — the stale skills/ mirror resolver is deleted), no stray {workflow.*} references.
- All guard patterns from psm-develop are present and adapted, not copied: target gate, undo-net with headless auto-backup, firm cap of 3, fail-closed validate reading, reconcile-on-resume rebuilt around ps-hotspot-scan, commit-offer tail, four-status BMad-mapped headless vocabulary.
- The per-class verification-evidence carve into the catalog is sound — early sudah-ramping exits never pay for it, and the catalog (kelas optimasi + jalur buktinya) stands alone.
- Workflow integrity, path standards (on real skill content), script lint, and both test suites (8 + 16 asserts) all pass on the final state.

## Recommendations

1. Sync the completed headless-return contract (status + one-line reason + memlog path on every blocked exit) into psm-develop's Mode headless, once the parallel edits to that file settle — it is the family source and still carries the asymmetry. (resolves: architecture-1, enhancement-2)
2. Nothing else is open. If a future edit pushes SKILL.md (2862 tokens) past the 3000 budget, lift the runtime-profiler mechanics from Profil into the catalog beside 'Bukti performa per kelas', keeping the gerbang-target and baseline-write rules inline. (resolves: architecture-2)

## Experience

- **Optimize with profiler** — Activate (resolver config, reconcile-on-resume) → Profil: inventory + hotspot scan → gerbang target → flashlight profiling summarized by ps-profile-summary.py → baseline written to .psm-optimize-plan.md → Identifikasi against the catalog → Budi approves → undo-net check → Terapkan → Verifikasi: psm-validate delta across 1.7/8/9 + same-method metric comparison, capped at 3 attempts → commit offer.
- **Optimize without profiler** — Same spine; baseline is static evidence (hotspot candidates), verification follows the per-class static paths in the catalog's 'Bukti performa per kelas'.
- **Already-lean exit** — Gerbang target proves a real module first; only then can an empty judged scan end as 'sudah ramping' — a genuine no-op success, distinct from a wrong-target failure.
- Headless: Four-status contract with BMad mapping (selesai/sudah-ramping=complete, gagal/butuh intervensi=blocked); every non-selesai return carries a one-line reason plus the memlog path, assumptions and corrections are memlogged, and the full verification gate still applies.

## Findings

### Medium (2)

#### architecture-1 — Blocked-status returns each carry only half of the required reason+memlog pair

- Lens: architecture
- Location: `SKILL.md:59-61 (Mode headless)`
- Evidence: Principles' headless rule: on blocked, include a one-line reason AND still return the memlog path so the caller can read the detail. psm-optimize maps gagal/butuh intervensi to blocked, but gagal returns "status + alasan" with no memlog path, and butuh intervensi returns "status + memlog" with no one-line reason. The sudah-ramping return also omits the memlog path even though headless assumptions were logged there. A caller receiving gagal cannot locate the assumption trail — the exact audit-break the principles name. psm-develop:73 (family source) shares the same asymmetry, so this is inherited, not a divergence.
- Recommendation: Make every non-selesai return carry both a one-line reason and the memlog path (and add the memlog path to the sudah-ramping return). Apply the same edit to psm-develop's Mode headless so the family contract stays uniform.

#### enhancement-1 — Add: verify-cap pattern lacks reset semantics after human intervention

- Lens: enhancement
- Location: `SKILL.md:51 (Verifikasi — batas 3 percobaan)`
- Evidence: verify_attempts persists in .psm-optimize-plan.md so the cap survives sessions, and On Activation #3 re-reads it on resume — but nothing ever resets it. Scenario: cap reached → butuh intervensi → Budi fixes the root cause and re-invokes → resume reads verify_attempts: 3 → the gate fires again immediately. A headless re-run after intervention is deterministically re-blocked. Same trait exists in the source pattern (psm-develop:63), so this is an inherited edge, not a port error.
- Recommendation: One clause in Verifikasi: reset verify_attempts to 0 when a new/revised plan is approved after an intervention, so the cap bounds one redesign loop rather than the module's lifetime.

### Low (4)

#### leanness-1 — Version-branch rule restated at apply time

- Lens: leanness
- Location: `SKILL.md:Terapkan`
- Evidence: "Pakai cabang versi eksplisit untuk area legacy/modern." duplicates the design rule already stated in Identifikasi & rencana ("decorate > override, cabang versi bila menyentuh area legacy/modern") and already encoded per-item in the approved plan ("versi terpengaruh"). Per the canon's core test, a model applying an approved plan that specifies affected versions does not need the rule re-taught; psm-develop's Terapkan carries no such restatement.
- Recommendation: Cut the sentence from Terapkan; the design-stage rule plus the plan's per-optimization 'versi terpengaruh' field carry it.

#### leanness-2 — Headless verification guard restates itself twice

- Lens: leanness
- Location: `SKILL.md:Mode headless`
- Evidence: "Tetap berlaku: gerbang Verifikasi penuh seperti di atas — hanya gerbang konfirmasi interaktif yang dilewati di headless, bukan verifikasi." The disambiguation earns its keep (both gates are called 'gerbang'), but the trailing clause restates the section's opening sentence and then restates the first clause again — defensive padding per the canon's truncate-before-delete test.
- Recommendation: Truncate to "Tetap berlaku: gerbang Verifikasi penuh seperti di atas." — keeps the gerbang disambiguation, drops the double restatement.

#### enhancement-2 — Add: blocked-status headless returns split the canon's reason+memlog pair

- Lens: enhancement
- Location: `SKILL.md:61 (Mode headless — empat status akhir)`
- Evidence: The headless canon says a blocked return carries a one-line reason AND the memlog path. psm-optimize gives each blocked status only half: gagal returns reason with no memlog path (whose path is only ever named in the return), while butuh intervensi returns memlog with no one-line reason. Mirrors the source pattern (psm-develop:73), an inherited edge of the port, not a regression.
- Recommendation: Collapse the two return shapes to the canon pair: both gagal and butuh intervensi return status + one-line reason + memlog path.

#### architecture-2 — SKILL.md in the warn band: 2850 tokens against org desired 2000 / budget 3000

- Lens: architecture
- Location: `SKILL.md`
- Evidence: Under the org's customized hard budget (3000) but over desired (2000) — the principles' tier behavior for this band is a non-blocking warning naming the section most worth lifting. The gates, gotchas, and status vocabulary must stay inline; the largest liftable slice is the runtime-profiler mechanics in Profil, which only the profiler-available branch needs.
- Recommendation: No action required now; if the next edit pushes past 3000, lift the runtime-profiler mechanics from Profil into references/ alongside 'Bukti performa per kelas' with a one-line pointer.
