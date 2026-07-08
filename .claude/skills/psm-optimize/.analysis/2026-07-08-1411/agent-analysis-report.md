# Analysis Report: psm-optimize

Generated: 2026-07-08T14:16:21Z · Schema: 2

**Grade: Excellent**

> Excellent stateless workflow with an authentic evidence-based persona treated as investment; the one thing worth fixing is the no-profiler path, which dead-ends at the performance gate because three sibling lenses all found the same unsatisfiable 'metrik membaik' proof.

psm-optimize is a cohesive, well-staged performance-engineering workflow: the profil→rencana→konfirmasi→terapkan→verifikasi spine has real step-to-step dependencies, the script boundary is well-drawn (hotspot-scan over-collects then defers N+1 judgment to the model; psm-validate's JSON verdict is read as-is), and the persona is genuine domain framing, not waste. The primary opportunity is unhappy-path completeness: when no runtime profiler is available the performance half of the dual gate has no numbers to satisfy, so a legitimate static run cannot declare done — define a static-mode verdict and the agent is airtight.

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 1 |
| Medium | 5 |
| Low | 4 |

## Themes

### 1. No-profiler path dead-ends at the performance gate

- Root cause: Profil explicitly allows a static-only run ('statis, tanpa angka') when Blackfire/Xdebug is unavailable, but Verifikasi declares done only when 'metrik membaik' against re-measured profiler numbers. With no runtime baseline there is nothing to re-measure, so the performance half of the dual gate is unsatisfiable and a legitimate static run can never conclude — a silent dead-end after real work is applied. Raised independently by enhancement, agent-cohesion, and touched by determinism.
- Fix: Define a static-mode verdict in Verifikasi: when no profiler is available, performance proof = re-run ps-hotspot-scan.py and confirm query-in-loop / N+1 candidate count dropped vs the baseline block, with psm-validate green in all three versions as the hard gate. Report explicitly as 'kompatibilitas terverifikasi, performa runtime tak terukur — delta hotspot statis membaik' so the static path has a real green exit.
- Findings:
  - `enhancement-1` No-profiler path dead-ends at the performance gate — `SKILL.md: Profil + Verifikasi`
  - `agent-cohesion-1` Verify gate has no defined performance proof on the no-profiler path — `SKILL.md (Verifikasi) vs (Profil)`

### 2. Verify gate's performance half is unscripted while its compat half is not

- Root cause: The compatibility half of the mandatory gate reads a psm-validate JSON verdict as-is, but the performance half has the model read raw Blackfire/Xdebug output by hand to extract wall-time/query/memory and compare against prose baseline numbers — a parse-of-known-format plus numeric comparison that fails the determinism test and is paid on every optimize run.
- Fix: Add a metrics script (e.g. scripts/ps-profile-metrics.py) that spins flashlight with the profiler and emits {wall_time, query_count, memory} JSON, with a compare mode diffing baseline-vs-after to a membaik/regresi verdict — making the performance gate a read-the-verdict step symmetric with the psm-validate half. This same script is what the static-mode fallback (hotspot delta) can reuse.
- Findings:
  - `determinism-1` Profiler metric capture + before/after compare has no script; done as prose in the gate — `SKILL.md (Profil + Verifikasi)`

### 3. optimization-catalog restates discipline SKILL.md already owns

- Root cause: The catalog's Profil and Pagar wajib sections re-teach measurement discipline, profiler ENV wiring, and version-safe/no-behavior-change guardrails that the SKILL.md capability prompts already establish — restated facts living in the wrong file. The catalog's job is enumerating opportunities, not re-carrying the flow's own rules.
- Fix: Delete the catalog's Profil section and cut or one-line the Pagar wajib section (a pointer back to SKILL.md's gates), keeping the catalog focused on the Caching/Query/Service/Aset opportunities it exists to enumerate.
- Findings:
  - `leanness-1` Catalog re-teaches profiling discipline already owned by SKILL.md — `references/optimization-catalog.md (Profil section)`
  - `leanness-2` Catalog 'Pagar wajib' restates guardrails SKILL.md already establishes — `references/optimization-catalog.md (Pagar wajib section)`

### 4. Unhappy-path completeness beyond the profiler gap

- Root cause: Two more entry states have no defined branch: an already-lean module where hotspot-scan returns nothing (pressures the agent toward the speculative optimization the catalog forbids), and a module that already fails psm-validate before optimization (a pre-existing red becomes indistinguishable from a regression the change caused).
- Fix: Add a clean 'module sudah ramping, tak ada peluang berbukti' exit before the plan gate, and extend the baseline block to record pre-optimization psm-validate status per version so Verifikasi judges the compatibility delta (no NEW failures) rather than absolute green.
- Findings:
  - `enhancement-2` No 'already fast / nothing to optimize' exit — `SKILL.md: Profil + Identifikasi & rencana`
  - `enhancement-3` Baseline the compatibility gate too, not just performance — `SKILL.md: Profil + Verifikasi`

## Strengths

- Authentic evidence-based performance-engineer persona and the three pantangan framing — genuine domain investment that must be preserved, not flattened.
- Well-drawn script boundary: ps-hotspot-scan deliberately over-collects candidates and defers N+1 judgment to the model; psm-validate's JSON verdict is read 'apa adanya' with no re-derivation.
- Baseline-written-to-artifact-immediately discipline (line 29) that survives resume and headless — the performance gate keeps its 'before'.
- Fixed profil→rencana→konfirmasi→terapkan→verifikasi ordering with real step-to-step dependencies and an unskippable approval gate on an irreversible source-change operation.
- First-class headless story and clean family integration (reuses psm-develop inventory, psm-cross-version patterns, psm-validate gate).

## Recommendations

1. Define a static-mode performance verdict in Verifikasi (hotspot-delta proof + psm-validate hard gate) so the no-profiler path has a real green exit instead of an unsatisfiable gate. (resolves: enhancement-1, agent-cohesion-1)
2. Add scripts/ps-profile-metrics.py to capture + compare profiler metrics as JSON, making the performance gate symmetric with the compat half and reusable by the static fallback. (resolves: determinism-1)
3. Add the 'already lean' clean exit and record pre-optimization psm-validate status in the baseline so compatibility is judged as a delta. (resolves: enhancement-2, enhancement-3)
4. Trim optimization-catalog's Profil and Pagar wajib sections; keep it to the opportunity enumeration only. (resolves: leanness-1, leanness-2)
5. Batch the two independent profiling script calls (inventory + hotspot-scan) into one message. (resolves: architecture-1)

## Agent Profile

- Name: psm-optimize
- Title: PrestaShop Module Performance Engineer
- Type: stateless
- Mission: Speed up an existing PrestaShop module via cache/service-container without breaking cross-version compatibility or changing behavior, gated by measure-first discipline.

## Capabilities

- **Profil** (prompt + script) — Map structure (ps-module-inventory) and surface hotspot candidates (ps-hotspot-scan); capture runtime baseline via Blackfire/Xdebug in flashlight, write baseline to artifact.
- **Identifikasi & rencana** (prompt + reference) — Pick opportunities from optimization-catalog, design version-safe fixes, write revisable plan to .psm-optimize-plan.md, gate on Budi approval.
- **Terapkan** (prompt) — Apply approved plan in place, version-branch legacy/modern, preserve functional behavior, mark per-optimization status.
- **Verifikasi** (prompt + external skill) — Dual gate: psm-validate JSON verdict (3 versions) for compatibility + profiler before/after for performance; loop back to artifact on failure.
- **ps-hotspot-scan.py** (script) — Mechanical over-collection of query/ObjectModel-in-loop candidates and heavy hook methods as JSON; N+1 judgment deferred to model.
- **Mode headless** (prompt) — Non-interactive path: args instead of questions, no confirm gate, assumptions logged to memlog, structured one-line return.

## Per-Lens Verdicts

- **leanness**: Capability prompts are tight and wiring-heavy; the only waste is optimization-catalog re-teaching profiling discipline and guardrails SKILL.md already owns.
- **architecture**: Structurally sound stateless skill — clean topology, resolving bare-path disclosure, dependency-real fixed ordering; one minor unbatched pair of independent profiling scripts.
- **determinism**: Boundary mostly well-drawn; the one leak is the profiler-metric half of the verify gate, which has no script backing while the compat half reads psm-validate JSON.
- **customization**: No customize.toml — consistent with the whole psm workflow family (only the persona agent psm-agent-expert ships one); reading shared psm config at activation is sound, not a forbidden mechanism.
- **enhancement**: Flow is well-staged with earned gates; gaps are all unhappy-path — chiefly what 'done' means when the performance gate has no numbers.
- **agent-cohesion**: Authentic and purposeful; evidence-based persona maps cleanly onto the spine, strong family integration; one verify-gate path dead-ends with no profiler.

## Experience

- **Interactive optimize** — Budi names module → profil measures hotspots + baseline → plan written and shown → Budi approves → applied in place → dual gate verifies → before/after summary.
- **Headless (called by workflow/agent)** — Module + versions from args → no confirm gate → assumptions logged to memlog → structured return with per-version verdict + metrics.
- Headless: First-class: dedicated Mode headless section takes args instead of asking, drops the interactive gate to the caller, logs assumptions, returns a structured one-liner.

## Findings

### High (1)

#### enhancement-1 — No-profiler path dead-ends at the performance gate

- Lens: enhancement
- Location: `SKILL.md: Profil + Verifikasi`
- Evidence: Profil supports a static-only run (baseline 'statis, tanpa angka') when no Blackfire/Xdebug is available, but Verifikasi demands 'ukur ulang dengan profiler yang sama... metrik membaik' and declares done only when 'metrik membaik tanpa regresi'. With a static-only baseline there are no runtime numbers to re-measure against, so the performance half of the dual gate is unsatisfiable and the agent can never legitimately declare done — a silent dead-end after real work is applied.
- Recommendation: Define a static-mode verdict in Verifikasi: when no profiler is available, success = query-count/N+1 reduction confirmed against the hotspot-scan delta plus psm-validate green in all three versions, reported explicitly as 'kompatibilitas terverifikasi, performa runtime tak terukur — perlu cek manual/profiler.' Give the agent a green-adjacent exit instead of an impossible gate.

### Medium (5)

#### agent-cohesion-1 — Verify gate has no defined performance proof on the no-profiler path

- Lens: agent-cohesion
- Location: `SKILL.md (Verifikasi) vs (Profil)`
- Evidence: Profil explicitly supports a static-only run ('Tanpa profiler, andalkan kandidat dari hotspot-scan dan sebut bahwa angka baseline runtime tak terukur'), but Verifikasi requires the Performa proof by 'ukur ulang dengan profiler yang sama' and declares done only when 'metrik membaik'. On the static path that second mandatory proof is undefined; the obvious static metric (re-run ps-hotspot-scan and compare query_in_loop_count / candidate count) is never named as the fallback proof.
- Recommendation: In Verifikasi, add the no-profiler case: re-run ps-hotspot-scan.py and compare query_in_loop_count / candidate count against the baseline block as the static performance proof, with psm-validate (three versions green) remaining the hard gate. State plainly what 'selesai' means when runtime numbers are unmeasurable.

#### determinism-1 — Profiler metric capture + before/after compare has no script; done as prose in the gate

- Lens: determinism
- Location: `SKILL.md (Profil + Verifikasi)`
- Evidence: Profil: 'gunakan flashlight dengan Blackfire ... Tulis baseline ... wall-time, jumlah query, memori'. Verifikasi: 'ukur ulang dengan profiler yang sama, lalu bandingkan dengan blok baseline di .psm-optimize-plan.md ... untuk membuktikan perbaikan nyata'. No script captures profiler output into structured metrics; the model reads raw profiler output to extract wall-time/query-count/memory and compares baseline-vs-after by hand. The compat half of the same gate is backed by psm-validate JSON, but the performance half is unscripted prose.
- Recommendation: Add a psm-optimize metrics script (e.g. scripts/ps-profile-metrics.py) that spins flashlight with the profiler and emits {wall_time, query_count, memory} JSON, with a compare mode diffing baseline JSON against after JSON to a membaik/regresi verdict. This applies the pre-pass JSON pattern plus the Comparison category and makes the performance gate a read-the-verdict step symmetric with the psm-validate half.

#### enhancement-2 — No 'already fast / nothing to optimize' exit

- Lens: enhancement
- Location: `SKILL.md: Profil + Identifikasi & rencana`
- Evidence: Running psm-optimize on a lean module where hotspot-scan returns empty candidates and the profiler shows no meaningful hotspot has no branch for 'nothing worth optimizing' — the flow marches into Identifikasi & rencana expecting opportunities, pressuring the agent toward the speculative optimizations the catalog explicitly forbids ('Jangan optimasi spekulatif').
- Recommendation: Add one line to Profil/Identifikasi: if no measured hotspot clears a materiality bar, report 'module sudah ramping, tak ada peluang berbukti' and stop cleanly before the plan/confirm gate — a legitimate successful outcome, not a failure to push through.

#### enhancement-3 — Baseline the compatibility gate too, not just performance

- Lens: enhancement
- Location: `SKILL.md: Profil + Verifikasi`
- Evidence: Baseline capture records only wall-time/queries/memory, not the starting psm-validate status. Legacy modules that already fail validate on some version are exactly what gets optimized; at Verifikasi a pre-existing red is then indistinguishable from a regression the optimization caused, and the agent loops back to redesign for a fault it did not introduce.
- Recommendation: Extend the baseline block to also record the pre-optimization psm-validate status per version, so Verifikasi judges the compatibility delta (no new failures) rather than absolute green — the same before/after discipline already applied to performance metrics.

#### leanness-1 — Catalog re-teaches profiling discipline already owned by SKILL.md

- Lens: leanness
- Location: `references/optimization-catalog.md (Profil section)`
- Evidence: The 'Profil (ukur sebelum & sesudah)' section restates the profiling wiring the SKILL.md Profil section already establishes: Blackfire via BLACKFIRE_ENABLED=true, Xdebug via XDEBUG_ENABLED=true, query-count before/after, and 'Selalu catat baseline sebelum perubahan dan ukur ulang sesudah — optimasi tanpa pengukuran adalah tebakan' duplicates SKILL.md ('ukur sebelum mengubah apa pun — optimasi tanpa bukti adalah tebakan') plus the baseline-to-artifact directive. The catalog's job is the optimization opportunities; the profiling how-to is a restated fact in the wrong file.
- Recommendation: Delete the 'Profil' section from the catalog. SKILL.md's Profil section is the single owner of measurement discipline and profiler wiring; the catalog should stay focused on the concrete opportunities it exists to enumerate.
- Proposed smallest: Catalog opens directly at the Caching opportunity; measurement discipline lives only in SKILL.md Profil.
- Predicted delta: -120 tokens in optimization-catalog.md

### Low (4)

#### leanness-2 — Catalog 'Pagar wajib' restates guardrails SKILL.md already establishes

- Lens: leanness
- Location: `references/optimization-catalog.md (Pagar wajib section)`
- Evidence: The 'Pagar wajib' section restates three constraints the SKILL.md capability prompts already own: version-branching for legacy/modern areas, 'Optimasi tak boleh mengubah perilaku fungsional — hasil harus identik, hanya lebih cepat' (verbatim duplicate of SKILL.md Terapkan), and re-verify via psm-validate (SKILL.md Verifikasi).
- Recommendation: Cut the 'Pagar wajib' section or collapse it to a one-line pointer ('Tiap optimasi tetap tunduk pada pagar version-safe & verifikasi di SKILL.md'). The guardrails belong to the flow's capability prompts, not the opportunity catalog.
- Proposed smallest: One-line pointer in place of the section.
- Predicted delta: -70 tokens in optimization-catalog.md

#### architecture-1 — Two independent profiling scripts invoked sequentially instead of batched

- Lens: architecture
- Location: `SKILL.md — Profil section`
- Evidence: Profil runs ps-module-inventory.py (structure map) then ps-hotspot-scan.py (hotspot candidates) as separate one-after-another calls. Both take only the module path and neither consumes the other's output — independent data-gathering that could issue in one message.
- Recommendation: State that the inventory and hotspot-scan runs are issued together in a single batch (parallel tool calls), since neither depends on the other's result.

#### determinism-2 — config.yaml parsing + key extraction done inline every activation

- Lens: determinism
- Location: `SKILL.md (On Activation #1)`
- Evidence: 'Muat config dari {project-root}/_bmad/config.yaml ... Ambil versi target dari section psm ... Komunikasi dalam communication_language'. The model parses YAML and extracts two keys by hand on every activation; no script backs this read. This is a psm-family-wide pattern (every sibling inlines the same read).
- Recommendation: Family-level fix: a small yaml-aware config reader emitting {psm_target_versions, communication_language} JSON that all psm skills call. Low because the extraction is cheap (two keys) and shared across the family rather than unique to this agent.

#### customization-1 — No customize.toml — consistent with the psm workflow family convention

- Lens: customization
- Location: `psm-optimize/ (directory root; no customize.toml)`
- Evidence: psm-optimize ships no customize.toml. The customization lens flagged this as a missing [agent] roster contract, but cross-checking the family shows psm-scaffold, psm-develop, psm-cross-version, psm-validate, and psm-setup ALSO ship none — only the persona agent psm-agent-expert carries one. These are slash-invoked workflow skills registered by directory, not roster-registered persona agents, and they deliberately read shared psm config from _bmad/config.yaml at activation. Reading project config at activation is not a forbidden config mechanism. Downgraded from the lens's 'high' to informational because it is a deliberate, consistent family-wide decision, not a per-agent defect.
- Recommendation: No change required for family consistency. If roster registration is ever wanted for the whole psm workflow family, add a metadata-only [agent] block to each sibling in one pass mirroring psm-agent-expert — but do not single out psm-optimize.
