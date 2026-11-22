# Analysis Report: /home/budi/dev/prestashop-module/.claude/skills/psm-review-loop

Generated: 2026-11-22 · Schema: 2

**Grade: Fair**

> Sound, lean core (leanness passes, all paths and sibling scripts verified), but the triage handoff is not self-contained and the loop has no way to stop early on items awaiting a human — the two fixes that matter most.

The skill states its destination well: fresh-reviewer isolation, a strict severity bar, the already-implemented-document rule learned from the bankwire test, and caller gotchas all earn their place. The main opportunity is orchestration robustness: the fresh triage subagent cannot load its own instructions, approved fixes have no apply step, escalations make the loop spin to the cap, and round-file bookkeeping (merge, numbering, run isolation) is left to the model.

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 4 |
| Medium | 10 |
| Low | 6 |

## Themes

### 1. Triage handoff is not self-contained

- Root cause: Triage & fix and the fix-side gotchas live in SKILL.md, but the work is done by a fresh subagent that only sees its prompt; the parent also has no step to apply fixes Budi approves after the triage subagent returns.
- Fix: Carve Triage & fix plus fix-side gotchas into a standalone references/triage-and-fix.md (defines its own paths, full memlog commands), hand that path to the triage subagent, and add an explicit apply-approved-answers step (fresh subagent) before the next round's reviewers start.
- Findings:
  - `architecture-1` The triage subagent is told to follow SKILL.md sections it has no way to load — `SKILL.md:Review round (line 38); Triage & fix; Gotchas`
  - `architecture-2` No step applies the fixes Budi approves — `SKILL.md:Review round (line 38); Triage & fix (line 50)`
  - `architecture-6` The memlog append commands omit the target argument the script requires — `SKILL.md:Triage & fix (line 54)`

### 2. Stop logic ignores pending human decisions and stalled progress

- Root cause: Only rejected findings are passed forward, so unanswered/headless escalations are re-raised every round and the loop can only end at the cap; the return also cannot tell a caller why it is blocked.
- Fix: Pass escalations forward as 'already escalated — do not raise again'; stop immediately when all remaining critical/high await a human; add a no-progress stop (critical/high not decreasing two rounds running); extend the JSON with reason, remaining_critical_high, escalations, and return it whenever a skill is the invoker.
- Findings:
  - `enhancement-1` Add: pass open escalations forward and stop early when only human decisions remain — `SKILL.md:30, 38, 56-60, 72-78`
  - `architecture-3` Headless escalations keep coming back and force the loop to the round cap — `SKILL.md:Headless mode; Stop; Review round (line 30)`
  - `enhancement-3` Add: stop when rounds stop making progress, before hitting the cap — `SKILL.md:56-60`
  - `enhancement-5` Add: report the blocking reason and remaining highs in the return, including when called interactively by a skill — `SKILL.md:62, 72-78`

### 3. Round-file bookkeeping is unchecked and not run-scoped

- Root cause: Reviewer files are merged, validated, numbered and located by model judgment, under a path keyed only by document basename, with no check that every lens finished or that skill output formats map to the loop schema.
- Fix: Add a run-scoped output dir (<doc-name>-<timestamp>), a small script that allocates the next round dir/cap flag and merges+validates lens files into one merged.json (stable IDs, exact-dup removal, invalid-file list), deterministic names for extra lenses, a rule that a round with a failed lens can never be clean, and an explicit 'map to loop schema; on HALT write []' instruction for the core reviewer skills.
- Findings:
  - `determinism-1` Triage subagent reads raw reviewer files and merges them every round, and nothing checks their shape — `SKILL.md:Review round (lines 32, 38) and Triage & fix (line 44)`
  - `determinism-2` Model does round numbering, round directory naming and round-cap counting — `SKILL.md:Review round (line 32) and Stop (line 59); Headless mode (line 75, "rounds")`
  - `architecture-5` Round files are keyed by document basename, so different runs collide — `SKILL.md:Review round (line 32)`
  - `enhancement-2` Add: a round counts as clean only if every lens finished, and keep round files per run — `SKILL.md:32-38, 58`
  - `customization-1` Extra review_lenses entries have no defined output filename, so one lens can silently overwrite another's findings — `SKILL.md:Review round (line 32)`
  - `architecture-4` The reviewer skills' own return-only formats conflict with the required file schema — `SKILL.md:Review round (lines 32-35)`

### 4. Memlog schema conflates entries and floods the caller's log

- Root cause: Rejected findings and fixes share --type decision and every medium/low is logged per round, so carry-forward lists need a full model reread and the caller's memlog fills with near-duplicates.
- Fix: Use distinct types (rejected, fix with 'round N:'), keep medium/low only in round files and append one deduplicated gap entry at Stop; let the round script compose the round event and running totals.
- Findings:
  - `determinism-3` Rejected findings and fixes share one memlog type, so building the carry-forward list needs the model — `SKILL.md:On Activation (line 26), Review round (line 30), Triage & fix (lines 50, 54), Stop (line 60)`
  - `enhancement-4` Remove: logging every medium/low as a memlog gap each round — `SKILL.md:54, 62`
  - `determinism-4` Model composes the round event line and the running medium/low total — `SKILL.md:Triage & fix (line 54) and Headless mode (line 75, "remaining_medium_low")`

## Strengths

- Destination-first Overview naming stance, outcome, consumer and bar; leanness lens found only ~60 tokens of restatement.
- Fresh, unanchored reviewers each round with only Budi's decisions carried forward — proven in the test (deferred K1-K6 not re-raised).
- Strict severity bar that counts ambiguity as high while demoting scope-expansion and quota filler.
- Already-implemented-document rule (code as truth, code defects excluded from the stop criterion) learned from a real run.
- Caller-specific gotchas (psm-plan pair + pair-check/validate-plan, bmad-spec CAP IDs, quick-dev frozen block) all verified against real scripts and flags.
- customize.toml is the only config surface; max_rounds and review_lenses wired via {workflow.*}.

## Recommendations

1. Carve triage-and-fix into a standalone reference handed to the triage subagent, with full memlog commands and an apply-approved-answers step. (resolves: architecture-1, architecture-2, architecture-6)
2. Rework Stop: pass escalations forward, stop early when only human decisions remain, add a no-progress stop, extend the JSON return. (resolves: enhancement-1, architecture-3, enhancement-3, enhancement-5)
3. Add a round script (next round dir + cap flag, merge/validate lens files) with a run-scoped output path, lens-completeness rule, extra-lens naming and schema-override instruction. (resolves: determinism-1, determinism-2, architecture-5, enhancement-2, customization-1, architecture-4, determinism-4)
4. Split memlog types (rejected / fix) and log medium/low once at Stop. (resolves: determinism-3, enhancement-4)
5. Trim the three restatements and specify on_complete in headless mode. (resolves: leanness-1, leanness-2, leanness-3, customization-2)

## Experience

- **Interactive review** — Resolve customization + psm config → identify doc/sources/companions → init or read memlog → per round: 3+ fresh reviewers write files → fresh triage subagent verifies, classifies, fixes, returns questions → parent asks Budi → repeat until clean / cap / oscillation → brief report
- **Called by a skill (headless)** — Doc, sources, companions from args → same rounds without asking → escalations logged to memlog → JSON with selesai | gagal | butuh intervensi
- Headless: Supported with a three-status JSON return, but escalations currently force the loop to the round cap before returning butuh intervensi.

## Findings

### High (4)

#### architecture-1 — The triage subagent is told to follow SKILL.md sections it has no way to load

- Lens: architecture
- Location: `SKILL.md:Review round (line 38); Triage & fix; Gotchas`
- Evidence: Line 38 hands the round to 'one fresh triage subagent: it reads the round's finding files and the memlog, carries out **Triage & fix** and **Gotchas**'. A fresh subagent sees only its prompt. Nothing tells the parent to pass the SKILL.md path or the text of those sections. The subagent therefore lacks the severity bar, the scope/data/decision rules for what goes to Budi, the already-implemented rule, the memlog logging commands, and the pair-check command, which are exactly what it needs to do its job. The same content is also paid by the parent on every invocation, although only the triage subagent uses it. That content is the main reason SKILL.md is over desired (2237 vs 2000).
- Recommendation: Move 'Triage & fix' and the fix-side gotchas to a standalone references/triage-and-fix.md. The fix-side gotchas are: mirror the .md/.json pair and run pair-check plus validate-plan; never change the `Status: direncanakan` token; never renumber CAP-N IDs; always ask about findings inside `<frozen-after-approval>`. The new file must define <doc>, <doc-dir>, the memlog path and <skills-dir> itself. Line 38 then hands the subagent that file's path along with the finding files and the memlog. SKILL.md keeps a one-line routing pointer and a short companion-identification gotcha for activation step 3. This fixes the handoff and brings SKILL.md under the desired tier. If you do not carve, line 38 must at least pass `{skill-root}/SKILL.md` and name the sections to follow.

#### architecture-2 — No step applies the fixes Budi approves

- Lens: architecture
- Location: `SKILL.md:Review round (line 38); Triage & fix (line 50)`
- Evidence: Triage & fix says fixes that change scope, touch existing data, or reverse a decision 'go to Budi first'. The triage subagent has already returned by the time Budi answers. Line 38 then says 'You ask Budi the batched questions, log the answers, and start the next round.' No step applies an approved fix. The parent cannot apply it without breaking the stated rule that it 'only orchestrates rounds'. The next round's triage only sees new reviewer findings, so an approved fix lands only if a fresh reviewer happens to raise the same point again. An approved fix can silently never be applied, and the loop can still exit 'Clean'.
- Recommendation: Add an explicit step. After Budi answers, dispatch a fix subagent with the triage reference, the memlog and the answer list, before the next round's reviewers start, so they review the corrected document. Alternatively, have the next round open with the triage subagent applying logged 'approved' answers before reviewers fire. Log approved answers as `--type decision` so the step has a clear input.

#### determinism-1 — Triage subagent reads raw reviewer files and merges them every round, and nothing checks their shape

- Lens: determinism
- Location: `SKILL.md:Review round (lines 32, 38) and Triage & fix (line 44)`
- Evidence: Each reviewer "writes a JSON array [{"location","issue","implementation_impact","suggestion"}] to .../round-N/<lens>.json and returns ONLY {"count": N, "path": "..."}". Then the triage subagent "reads the round's finding files" and must "Merge findings, drop duplicates". In the real run that meant 46-66 raw findings across three files per round, merged and deduplicated by the model, for up to max_rounds=5 rounds. Nothing checks that each file parses, carries the four required keys, or matches the count the reviewer reported. A malformed or prose-wrapped file reaches triage unnoticed.
- Recommendation: Determinism leak. Apply the determinism test: concatenating JSON arrays, checking the four required keys, comparing the array length to the reported count, assigning stable IDs (<lens>-<k>), removing exact duplicates and grouping by normalized location all give the same output for the same input and can be unit-tested. The signal-verb scan hits 'merge', 'drop duplicates' and 'validate'. Add a script, for example scripts/merge-round.py <round-dir>, that does this work and emits one compact merged.json with per-lens counts, candidate duplicate clusters grouped by location, and a list of invalid files to re-run. This is the pre-pass JSON pattern. The triage subagent then reads merged.json instead of three raw files. Only semantic deduplication (different wording, same point) and checking each finding against the document stay in the prompt.

#### enhancement-1 — Add: pass open escalations forward and stop early when only human decisions remain

- Lens: enhancement
- Location: `SKILL.md:30, 38, 56-60, 72-78`
- Evidence: Pattern: headless readiness / graceful degradation. Only 'findings Budi rejected and binding decisions' are passed to fresh reviewers. In headless mode, fixes that need Budi are 'not applied — log them as assumptions/escalations', so they never become rejected findings. The next round's fresh reviewers raise the same points again, triage sends them back to Budi, and the round can never be clean. The same thing happens interactively when Budi leaves an escalation unanswered. The loop then runs to the max_rounds cap (default 5, ~0.8-1M subagent tokens per round) only to return 'butuh intervensi', which it already knew after round 1.
- Recommendation: In Review round, add a sentence passing items awaiting a human decision (headless escalations and unanswered questions) forward under the same 'already decided — do not raise again' label, phrased as 'already escalated'. In Stop, add a condition: when every remaining critical/high after triage is waiting for a human decision, stop right away. Headless returns 'butuh intervensi'; interactive asks Budi now instead of starting another round.

### Medium (10)

#### architecture-3 — Headless escalations keep coming back and force the loop to the round cap

- Lens: architecture
- Location: `SKILL.md:Headless mode; Stop; Review round (line 30)`
- Evidence: In headless mode, 'fixes that need Budi are not applied — log them as assumptions/escalations'. Only 'findings Budi rejected and binding decisions' are passed to reviewers as already decided. An unapplied escalated high finding is neither, so fresh reviewers raise it again every round. 'Clean' requires 0 critical/high after triage, so a headless run with even one escalation spins to `{workflow.max_rounds}` before returning `butuh intervensi`. That spends up to four extra rounds of 3+ parallel reviewers with no possible progress.
- Recommendation: State the headless behavior. Either pass escalated findings forward as 'pending human decision — do not raise again' and exclude them from the clean count, or end with `butuh intervensi` as soon as a round's only remaining critical/high findings are escalations.

#### architecture-4 — The reviewer skills' own return-only formats conflict with the required file schema

- Lens: architecture
- Location: `SKILL.md:Review round (lines 32-35)`
- Evidence: Every lens must write `[{location, issue, implementation_impact, suggestion}]` to a file and return ONLY `{count, path}`. bmad-review-edge-case-hunter's SKILL.md says 'Return ONLY a valid JSON array' with different fields (trigger_condition, guard_snippet, potential_consequence). bmad-review-adversarial-general outputs 'a Markdown list' and has HALT conditions that 'ask for guidance', which no one can answer inside a subagent. The prompts never tell the subagent that the loop's file schema and return format override the invoked skill's output section. The subagent gets two competing ONLY instructions, and triage may receive files in mixed schemas.
- Recommendation: In the core-lens instructions, say explicitly: run the skill's analysis, then map its findings into the loop schema, which overrides the skill's output format. Also say how to handle a HALT (no user is present, so write `[]` and return count 0). Give the mapping for edge-case-hunter's fields.

#### architecture-5 — Round files are keyed by document basename, so different runs collide

- Lens: architecture
- Location: `SKILL.md:Review round (line 32)`
- Evidence: Findings go to `{project-root}/_bmad-output/psm-review-loop/<doc-name>/round-N/<lens>.json`. The main caller, psm-plan, always produces `.psm-develop-plan.md`, so every module's plan shares the same folder. A later run, or a lens that fails to write, leaves stale files from an earlier run. The triage subagent 'reads the round's finding files' without telling which run they came from. Concurrent runs overwrite each other.
- Recommendation: Make each run's output unique, for example `<doc-name>-<timestamp>/round-N/` or a hash of the doc path. Have the parent give the triage subagent the exact list of paths that the reviewers returned this round, instead of a folder to scan.

#### determinism-2 — Model does round numbering, round directory naming and round-cap counting

- Lens: determinism
- Location: `SKILL.md:Review round (line 32) and Stop (line 59); Headless mode (line 75, "rounds")`
- Evidence: Output paths use ".../_bmad-output/psm-review-loop/<doc-name>/round-N/<lens>.json". The Cap rule is "{workflow.max_rounds} rounds done and high findings remain", and the headless return reports "rounds": 0. N, the cap comparison and the final count all come from the model's own tracking (confirmed in the test run). Nothing covers a second run on the same document, where round-1..k directories from a previous run already exist. A model that restarts at 1 overwrites or mixes stale reviewer files, and a model that miscounts stops early or late.
- Recommendation: Determinism leak. By the determinism test, listing round-* directories, choosing the next N, creating the directory and comparing N to max_rounds each have one correct answer. Add a small script, for example scripts/round-state.py next --doc-name <name> --max-rounds <n>, that returns {"round": N, "dir": "...", "cap_reached": bool}. Give it a run-scoped prefix or archive step so a fresh run does not collide with old round directories. The prompt then consumes the returned N and the cap flag instead of counting.

#### determinism-3 — Rejected findings and fixes share one memlog type, so building the carry-forward list needs the model

- Lens: determinism
- Location: `SKILL.md:On Activation (line 26), Review round (line 30), Triage & fix (lines 50, 54), Stop (line 60)`
- Evidence: Rejected findings are logged as "--type decision" (line 50), and "each substantive fix" is also "--type decision" (line 54). Every round, reviewers must receive only "findings Budi rejected and binding decisions ... labeled 'already decided — do not raise again'". Oscillation detection also needs the history of earlier rounds' fixes. Because both kinds share one tag and fixes carry no round number, the model has to reread the whole memlog and classify each entry to build these lists. memlog.py offers a free-form --type, so the conflation comes from this skill.
- Recommendation: Determinism leak caused by the logging schema. Log with distinct tags, for example --type rejected for ignored findings and --type fix with "round N:" in the text for applied fixes. Building the carry-forward list and the per-round fix history then becomes a filter that passes the determinism test (it can be unit-tested), and a short script or grep can emit it as compact JSON for the reviewers and the triage subagent. This is the pre-pass JSON pattern. Judging whether a new finding reverses or repeats an earlier fix stays in the triage prompt, because that is semantic.

#### customization-1 — Extra review_lenses entries have no defined output filename, so one lens can silently overwrite another's findings

- Lens: customization
- Location: `SKILL.md:Review round (line 32)`
- Evidence: Each lens writes to `{project-root}/_bmad-output/psm-review-loop/<doc-name>/round-N/<lens>.json`. The three core lenses have obvious names. A `{workflow.review_lenses}` entry can be a `skill:`, a `file:`, or a plain-text reviewer prompt, and nothing says what `<lens>` is for it. Two plain-text entries, or an entry whose derived name matches a core lens (e.g. a team adds an extra 'adversarial' prompt), would write to the same file. The triage subagent only reads the round's finding files. A clobbered file drops findings without any warning, and that can make the stop rule ('0 critical/high after triage') report clean too early.
- Recommendation: Define a deterministic name for extra lenses in SKILL.md, for example `extra-<index>.json` (1-based position in `{workflow.review_lenses}`), or `<skill-name>.json` for `skill:` entries and `extra-<index>.json` otherwise. Core lens files keep their fixed names. This keeps the override additive and its output visible to triage.

#### enhancement-2 — Add: a round counts as clean only if every lens finished, and keep round files per run

- Lens: enhancement
- Location: `SKILL.md:32-38, 58`
- Evidence: Pattern: graceful degradation in a hostile environment. Nothing covers a reviewer subagent that crashes, hits its context limit, or writes no or malformed JSON. A round with a missing lens file can look like 0 findings, triage finds 0 high, and the loop stops as 'Clean' and returns 'selesai', which a headless caller trusts. Round files go to `_bmad-output/psm-review-loop/<doc-name>/round-N/`, and that path is not unique per run. A later run on the same document, or a different document with the same file name, can leave stale lens files that triage then reads as this round's findings.
- Recommendation: Before handing off to triage, require each lens to have returned `{count, path}` with a file that exists and parses. Re-run a failed lens once; if it fails again, mark the round incomplete. An incomplete round can never satisfy Clean, and in headless mode it ends as 'butuh intervensi' with the reason. Add a run identifier to the output path, for example a timestamp under `<doc-name>/`.

#### enhancement-3 — Add: stop when rounds stop making progress, before hitting the cap

- Lens: enhancement
- Location: `SKILL.md:56-60`
- Evidence: Pattern: testable progression/stop conditions. 'Ambiguity counts as high on purpose', and the adversarial reviewer must report at least ten issues. With fresh reviewers each round, there is usually another sentence with two readings, so new highs keep appearing. Oscillation only catches a fix being repeated or reversed, not a steady stream of new highs. In the two-round test, unique findings fell only from 39 to 32. As written, the expected path is often the 5-round cap at roughly 4-5M tokens, while the last rounds add little.
- Recommendation: Add one Stop bullet: if the verified critical/high count does not go down for two rounds in a row, stop and report the remaining items, the same way the cap does (headless: 'butuh intervensi'). This costs no assurance on documents that are converging, and the report still lists what is left.

#### enhancement-4 — Remove: logging every medium/low as a memlog gap each round

- Lens: enhancement
- Location: `SKILL.md:54, 62`
- Evidence: Pattern: memlog over-applied. Each round logs 'each medium/low as `--type gap`'. Most medium/low findings are quota filler from the adversarial lens, and fresh reviewers raise them again every round, so a 5-round run can append well over a hundred near-duplicate gap entries. The memlog often belongs to the caller: for bmad-spec it 'is the authority on decisions', and finalize has to account for every entry. Those runs end up flooding the caller's memlog with noise. The final report still has to deduplicate the medium/low list across rounds.
- Recommendation: Keep medium/low findings only in the round JSON files. At Stop, append a single `--type gap` entry with the deduplicated medium/low list, or a pointer to it. Nothing is lost: the per-round detail stays on disk under `_bmad-output`, and the decision trail keeps only what downstream readers need.

#### enhancement-5 — Add: report the blocking reason and remaining highs in the return, including when called interactively by a skill

- Lens: enhancement
- Location: `SKILL.md:62, 72-78`
- Evidence: Pattern: headless JSON return (principles: on 'blocked', include a one-line `reason`). 'butuh intervensi' covers three different situations: a decision is pending, the cap was hit, or oscillation occurred. The return carries only `remaining_medium_low`, with no count of remaining critical/high and no pending-escalation count. A calling skill (psm-plan, bmad-spec, bmad-prd, bmad-quick-dev) therefore cannot tell whether to proceed, ask the user, or re-run without parsing the memlog. When a skill invokes this one interactively, the run ends with a prose report to Budi instead of a result the caller can act on.
- Recommendation: Add `reason` (`awaiting_decision | cap | oscillation | lens_failure`), `remaining_critical_high`, and `escalations` to the JSON. Return the same JSON whenever the invoker is a skill, interactive or headless, after any prose shown to Budi.

### Low (6)

#### leanness-1 — Invocation sentence describes the system to itself

- Lens: leanness
- Location: `SKILL.md:12 (Overview, second paragraph)`
- Evidence: "Invoked directly by Budi, or by another skill (psm-plan, bmad-spec, bmad-prd, bmad-quick-dev) after its document is written." No action changes because of this line. Caller-specific behavior is in Gotchas. The no-operator case is in Headless mode ("by another skill with no operator"). The point that a memlog may belong to a caller is in On Activation step 4 ("owned by the calling skill or a previous run"). Fails the canon's core test and the 'Who reads this' cut list (meta-explanation).
- Recommendation: Delete the sentence. Every move it could inform is already covered where that move happens.

#### leanness-2 — "Stop only on this" repeats the Clean rule and contradicts Cap

- Lens: leanness
- Location: `SKILL.md:58 (Stop, Clean bullet)`
- Evidence: "Stop only on this; never stop right after fixing, because fixes can introduce new problems." Read literally, "Stop only on this" conflicts with the Cap bullet two lines later, which is also a stop. The real nudge is the second clause and its reason.
- Recommendation: Trim the line (truncate, don't delete): "Clean: a fresh review round yields 0 critical/high document findings after triage. Never declare clean right after fixing, because fixes can introduce new problems."

#### leanness-3 — Restated facts: reviewer isolation said twice, missing-doc status said twice

- Lens: leanness
- Location: `SKILL.md:30 (Review round, first paragraph); SKILL.md:25 vs SKILL.md:78`
- Evidence: Line 30 opens with "they must not see earlier rounds' findings or fixes" and ends by restating it as "Reviewers must not read the memlog or earlier rounds' files." Line 25's "(headless: `gagal`)" repeats line 78's "`gagal` = document missing/unreadable". The canon lists restated facts as cuttable.
- Recommendation: Merge line 30 into one sentence: "Every round starts from the current document with fresh reviewers who never see earlier rounds' findings, fixes, files, or the memlog, so their judgment is not anchored. Pass forward only Budi's rejected findings and binding decisions, labeled 'already decided — do not raise again'." On line 25, drop "(headless: `gagal`)" and let the Headless mode section own the status mapping.

#### architecture-6 — The memlog append commands omit the target argument the script requires

- Lens: architecture
- Location: `SKILL.md:Triage & fix (line 54)`
- Evidence: Line 54 writes `append --type event --text ...` with no script path and no `--path`. In _bmad/scripts/memlog.py, `append` requires one of `--workspace` or `--path`. Only activation step 4, which the triage subagent may not see, shows the full `memlog.py init --path <doc-dir>/.memlog.md` form.
- Recommendation: Write the full command wherever it is used: `uv run {project-root}/_bmad/scripts/memlog.py append --path <doc-dir>/.memlog.md --type ... --text ...`. Do this especially in the carved triage reference, which must stand alone.

#### determinism-4 — Model composes the round event line and the running medium/low total

- Lens: determinism
- Location: `SKILL.md:Triage & fix (line 54) and Headless mode (line 75, "remaining_medium_low")`
- Evidence: The parent builds "review-loop round N: X critical/high fixed, Y asked, Z dropped (unproven), W medium/low" by hand from the triage JSON counts, and must keep a cross-round total for remaining_medium_low.
- Recommendation: Small determinism leak. Formatting fixed fields into a template and summing counts across rounds fall to the signal verbs 'format' and 'count'. Fold this into the round-state script from determinism-2, for example a 'close --triage-json <file>' subcommand that appends the memlog event and returns running totals for the final report and the headless return.

#### customization-2 — on_complete behavior in headless mode is unspecified

- Lens: customization
- Location: `SKILL.md:Stop (line 62) vs Headless mode (lines 72-78)`
- Evidence: `{workflow.on_complete}` runs after the interactive report to Budi. Headless mode says 'Return ONLY JSON' and never mentions on_complete. When another skill calls this one with no operator, it is unclear whether a team's on_complete hook (for example a handoff or notification) should run. If it runs and produces output, it breaks the JSON-only return contract.
- Recommendation: Add one clause to Headless mode, e.g. 'Run `{workflow.on_complete}` if non-empty before emitting the JSON; its output must not precede or replace the JSON return.' Or state explicitly that on_complete is skipped in headless mode.
