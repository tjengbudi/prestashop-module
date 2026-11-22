---
name: psm-review-loop
description: Repeatedly review a spec or plan document until no high findings remain. Use when the user says "psm-review-loop", "review loop", "review spec sampai bersih", or "loop review rencana".
---

# psm-review-loop

## Overview

Act as a pre-implementation document QA editor. Independent reviewers hunt for gaps, a triage editor fixes what is real, and you repeat until a fresh review round finds nothing that must be fixed. The output is the same document (spec, plan, PRD, story), fixed in place, plus a trail of every round in the memlog. The consumers are the implementer who will work from this document without this conversation in the room (psm-develop, bmad-dev-story, bmad-quick-dev) and Budi, who approves it. The bar: an implementer following the document literally never has to guess and cannot build the wrong thing because of the document. You only orchestrate rounds. Full findings never enter your context.

## Resolution rules

- Bare paths (`references/triage-and-fix.md`, `scripts/review-round.py`) and `{skill-root}` resolve from this skill's installed directory.
- `{project-root}` → the project working directory.
- `<skills-dir>` → the directory containing this skill (where the sibling psm-* skills live).
- `<doc>` → path of the target document; `<doc-dir>` → its folder; `<memlog>` → `<doc-dir>/.memlog.md`.

## On Activation

1. Resolve customization: `uv run {project-root}/_bmad/scripts/resolve_customization.py --skill {skill-root} --key workflow`. If that fails, merge `{skill-root}/customize.toml`, `{project-root}/_bmad/custom/psm-review-loop.toml` and `{project-root}/_bmad/custom/psm-review-loop.user.toml` in that order: scalars override, arrays append. Run each `{workflow.activation_steps_prepend}` entry now and each `{workflow.activation_steps_append}` entry once activation finishes. Keep `{workflow.persistent_facts}` as standing context (`file:` loads contents, `skill:` names a skill to consult, others are literal).
2. Load config via `uv run <skills-dir>/psm-setup/scripts/resolve-psm-config.py --project-root {project-root}`. Talk to Budi in `communication_language`. Document fixes and memlog entries use the language the document already uses (`document_output_language` for a new or empty document).
3. Note the paths of `<doc>`, any source documents (brief, parent PRD, inventory, `.psm-ideas.md`, anything `<doc>` is supposed to reflect) and companion artifacts (see Gotchas). Do not read their contents, because subagents do. If `<doc>` is missing or empty, stop.
4. If `<memlog>` exists (shared with the calling skill and the folder's other documents), continue it append-only. Otherwise run `uv run {project-root}/_bmad/scripts/memlog.py init --path <memlog>`.
5. Run `uv run scripts/review-round.py reviewed --doc <doc> --memlog <memlog>`. If `clean` and neither `--force` nor an explicit request for a fresh review was given, report "already reviewed clean, unchanged since" with its `last_result` and return `selesai` with `rounds` 0 (headless: JSON only). Callers invoke this skill unconditionally and rely on this skip.

## Review round

`scripts/review-round.py` keeps the round bookkeeping exact. If it cannot run, do its work by hand as its `--help` describes. Each round:

1. **Allocate** with `uv run scripts/review-round.py next --doc <doc> --out-root {project-root}/_bmad-output/psm-review-loop --max-rounds {workflow.max_rounds}`. From round 2 on, add `--run-dir <run_dir>` from the first call. Start every memlog entry you write with its `doc_tag`, so siblings sharing `<memlog>` stay apart.
2. **Carry forward** with `uv run scripts/review-round.py carry --memlog <memlog> --doc <doc>`. Reviewers are fresh: they never see earlier rounds' findings, fixes, files or the memlog, so their judgment is not anchored. They receive only this output: `rejected` and `decisions` labeled "already decided — do not raise again", and `escalated_pending` labeled "already escalated — do not raise again". Interactive: on the first round, also put `escalated_pending` in front of Budi with the first questions.
3. **Review.** Run these lenses as parallel subagents, giving each only paths. Each writes a JSON array `[{"location": "...", "issue": "...", "implementation_impact": "...", "suggestion": "..."}]` to `<round_dir>/<lens>.json` and returns ONLY `{"count": N, "path": "..."}`. Tell every lens that this file schema and return override the invoked skill's own output format, and that no user is present: where the skill would HALT to ask, it writes `[]` and returns count 0.
   - `adversarial`: skill `bmad-review-adversarial-general` on `<doc>`.
   - `edge-case`: skill `bmad-review-edge-case-hunter` on `<doc>`, with `also_consider`: "This is a specification document, not code. Walk every decision, state, input, target version, and error path the document describes; report where behavior is left unspecified." Map its fields as trigger_condition → issue, potential_consequence → implementation_impact, guard_snippet → suggestion.
   - `implementer`: prompt "You are the developer who must implement `<doc>` tomorrow without being able to ask its author. Read all of it and list every point where you would have to guess, two parts contradict, a reference (file, hook, table, ID, step) cannot be found or verified, or a done-criterion cannot be tested." If sources exist, add: "Also check every load-bearing claim in the sources — which ones are missing from `<doc>` or changed meaning."
   - `extra-<i>`: one per `{workflow.review_lenses}` entry, where i is its 1-based position. `skill:` runs that skill on `<doc>`, `file:` loads the reviewer prompt from the file, and plain text is the prompt itself.
4. **Merge** with `uv run scripts/review-round.py merge <round_dir> --lens adversarial=<count> --lens edge-case=<count> ...`. Pass a bare name for a lens that returned nothing. Re-run each lens listed under `invalid` or `missing` once, then merge again. If a lens still fails, the round is incomplete and can never be clean. Triage it anyway.
5. **Triage.** Hand the round to one fresh subagent with the path `{skill-root}/references/triage-and-fix.md` and its section "Triage a round". Also give it `<doc>`, `<doc_tag>`, `<doc-dir>`, `{skill-root}`, companions, sources, `<memlog>`, `<round_dir>`, `<skills-dir>`, `{project-root}`, `communication_language`, and which skill produced `<doc>`. It returns the round's counts and `questions_for_budi`.
6. **Ask Budi** all questions in one batch, each with its options and recommendation (headless: skip this step). Log each answer: approved as `--type decision --text "<doc_tag> [<id>] Budi: <answer>"`, ignored as `--type rejected --text "<doc_tag> [<id>] Budi: ignore — <finding>"`, using `uv run {project-root}/_bmad/scripts/memlog.py append --path <memlog>`. An unanswered question stays pending.
7. **Apply approved answers**, if there are any, before the next round's reviewers start: dispatch a fresh subagent with the same reference, its section "Apply approved answers", the same values, and the approved list.
8. **Close** with `uv run scripts/review-round.py close <round_dir> --memlog <memlog> --doc <doc> --project-root {project-root} --max-rounds {workflow.max_rounds} --applied <applied>`. Append its `event` to the memlog with `--type event`. If `stop` is true, go to Stop. Otherwise start the next round.

Without subagents, run everything sequentially and record in the memlog that the rounds were not independent (weaker assurance).

## Stop

`close` returns `stop` and `reason` by these rules. **Clean**: the round needed no fix and applied no answer, every lens finished, and no critical/high is open (none found, or Budi rejected each one). Never declare clean right after fixing, because fixes can introduce new problems. Otherwise it stops on:

- `awaiting_decision`: nothing was fixed or applied and a critical/high awaits a human, so another round would review the same document. It is `oscillation` instead when a pending item reverses or repeats an earlier fix.
- `lens_failure`: nothing is left to fix, but the round was incomplete.
- `no_progress`: the verified critical/high count did not decrease for two rounds in a row.
- `cap`: `{workflow.max_rounds}` rounds are done.

On stop, append `close`'s `result` line with `--type event` (the line `reviewed` checks next time), then its `gap` line (if any) with `--type gap`. Report briefly to Budi: the number of rounds, a summary of fixes, unanswered escalations, and the medium/low list from `medium_low_path`. Offer to fix the medium/low items, but start no new round unless Budi asks. Then run `{workflow.on_complete}` if non-empty.

## Gotchas

- **psm-plan, psm-develop**: `.psm-develop-plan.md` and `.psm-develop-plan.json` are a pair. Pass the other half as a companion to every subagent.
- **Producer rules** (psm-plan, psm-develop, psm-cross-version, psm-optimize, bmad-spec, bmad-quick-dev, bmad-prd, bmad-architecture, bmad-create-story) live in the triage reference. Name the producing skill in the triage prompt so they fire.

## Return

Headless (`--headless`, or invoked by a skill with no operator): take `<doc>`, sources and companions from arguments. Questions are not asked. They stay pending as `escalated` entries. Run `{workflow.on_complete}` before returning, and record its outcome in the memlog, not in the reply.

Whenever a skill is the invoker, interactive or headless, end with this JSON. Headless: return ONLY the JSON. Interactive: put it after the prose for Budi. Status values are shared psm machine tokens. The counts come from `close`.

```json
{"status": "selesai | gagal | butuh intervensi", "reason": "awaiting_decision | cap | oscillation | no_progress | lens_failure | null", "summary": "<one line>", "rounds": 0, "remaining_critical_high": 0, "escalations": 0, "remaining_medium_low": 0, "document": "<doc>", "memlog": "<doc-dir>/.memlog.md"}
```

`selesai` means a clean stop. `gagal` means the document is missing or unreadable. `butuh intervensi` comes with a `reason`. BMad mapping: `selesai`=`complete`, the other two=`blocked`.
