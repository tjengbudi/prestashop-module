# Analysis Report: skills/psm-agent-expert

Generated: 2026-07-08 · Schema: 2

**Grade: Good**

> A cohesive, richly-voiced stateless consulting hub whose persona drives every capability; the one theme worth acting on is that activation front-loads deterministic first-run setup and a full knowledge-base read in prose, before the user has even been greeted.

psm-agent-expert is an authentic, well-built stateless hub: a senior PrestaShop cross-version consultant whose Indonesian persona and cross-version-safety principle carry through all four capabilities without overlap, and whose capability prompts are lean and outcome-shaped. The primary opportunity is the activation/first-run path, which reads the whole shared KB eagerly, performs a fixed directory-scaffold and a Docker/flashlight environment check in prose, and can fire all of it before the greeting — deterministic plumbing and heavy work that should be scripted, load-on-demand, and gated behind an offer. The persona was treated as investment and is not flagged as waste.

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 0 |
| Medium | 5 |
| Low | 4 |

## Themes

### 1. Activation front-loads deterministic first-run setup as ungated prose

- Root cause: On Activation and maintain-knowledge's first-run path pack heavy, one-correct-answer work into the prompt and run it before the user has been greeted or stated intent: a full eager read of tech/* and ecommerce/* (which the capabilities already load on demand), a fixed KB directory/file scaffold, and a Docker/flashlight presence check. Directory-scaffolding and environment checks are deterministic plumbing a script should own; the eager KB read duplicates on-demand capability loads; and doing all of it unprompted ahead of 'Sapa Budi' hijacks a first-timer's opening moment.
- Fix: Greet first, then soft-gate the heavy work behind an offer ('KB bersama belum ada — mau kubangun & seed sekarang? Docker/flashlight belum siap, cek sekalian?'). Move the deterministic pieces into a scripts/ helper: init_kb.py to mkdir the fixed tree and write stub files, and a small presence check returning Docker/flashlight state as JSON — leaving the prompt to judge only the seed *content* and what to do about the environment. Trim steady-state activation to reading lightweight project state (projects/<module>.md); let tech/* and ecommerce/* load through the capabilities that already own those reads.
- Findings:
  - `architecture-1` Whole knowledge base read eagerly at activation, duplicating on-demand capability loads — `SKILL.md:On Activation (lines 44-45)`
  - `determinism-1` First-run knowledge-base structure creation done by prose — `SKILL.md On Activation (line 44) + references/maintain-knowledge.md First run (lines 15-16)`
  - `determinism-2` Docker + flashlight image presence check done by prose — `SKILL.md On Activation (line 44)`
  - `enhancement-1` Soft-gate the first-run KB build + Docker setup before it fires ahead of the greeting — `SKILL.md On Activation (first-run bullet) + references/maintain-knowledge.md First run`

### 2. Knowledge-base write-side has loose ends

- Root cause: The curator capability is strong on reading and seeding but underspecifies the write side: a named 'personal-preferences' store has no read or write path, there is no rule for reconciling curated facts against fresher contradicting research, and maintain-knowledge — the capability most naturally fired on a schedule (new PS release → update breaking-changes) — has no non-interactive return path like the other capabilities do.
- Fix: Close the KB lifecycle loop in maintain-knowledge: either wire the personal-preferences store (name the file, read it at activation, own its writes) or drop the sentence; add a reconciliation rule (on conflict, flag to Budi, prefer the newer sourced fact, record old→new with source/date so the KB can't ossify a wrong answer); and add a headless return path (given a target topic non-interactively, research, write, and return a terse summary of files touched + source + date).
- Findings:
  - `agent-cohesion-1` Personal-preferences store is a loose thread with no read/write path — `references/maintain-knowledge.md:27 (with SKILL.md On Activation)`
  - `enhancement-3` No reconcile of curated KB against fresh research when they conflict — `references/answer-technical.md + references/maintain-knowledge.md (Perbarui)`
  - `enhancement-2` No non-interactive return path for maintain-knowledge to match the other capabilities — `references/maintain-knowledge.md`

## Strengths

- Load-bearing persona: a senior PrestaShop 1.6→1.7→8→9 consultant whose Indonesian voice, concrete version-risk phrasing, and 'offer, don't impose' stance are investment that shapes every capability — preserve it verbatim.
- Cross-version-safety principle is a genuine through-line, traceable from the Principles section into answer-technical's behavior — the agent's defining value is wired, not just stated.
- Clean stateless topology: single SKILL.md carrying identity, four descriptively-named references, nothing stray at root, self-contained capability prompts with legitimate handoffs.
- Lean, outcome-shaped capability prompts with no scoring formulas, format templates, or rigid sequences.
- Agent source files are fully path-standards clean — every lint hit is against generated .analysis/ reports and the builder's .memlog.md, not agent content.

## Recommendations

1. Rework the activation/first-run path: greet first, gate the KB build + Docker check behind an offer, script the deterministic scaffold and environment check, and move steady-state domain reads to on-demand. (resolves: architecture-1, determinism-1, determinism-2, enhancement-1)
2. Firm up the KB write side in maintain-knowledge: wire or drop the preferences store, add conflict reconciliation, add a headless update return path. (resolves: agent-cohesion-1, enhancement-3, enhancement-2)
3. Decide the config posture: either opt into a persistent_facts default for project-context.md, or leave a one-line note that the config.yaml + shared KB path is intentionally sufficient. (resolves: customization-1)
4. Keep the WebReader-not-WebFetch rule in maintain-knowledge only and have answer-technical reference it, removing the duplicate mechanic. (resolves: leanness-1)

## Agent Profile

- Name: PrestaShop Module Expert
- Title: Konsultan PrestaShop Cross-Version & E-commerce
- Type: stateless
- Mission: Conversational entry point for PrestaShop module development: answers cross-version technical questions, brainstorms e-commerce functions, routes to the right psm workflow, and curates the shared psm knowledge base.

## Capabilities

- **answer-technical** (prompt) — Cross-version-aware technical Q&A, sourced from the curated KB with devdocs research on gaps.
- **brainstorm-ecommerce** (prompt) — Advanced-elicitation brainstorming of e-commerce functions; offer, don't impose.
- **route-workflow** (prompt) — Hands off multi-step work to validate/cross-version/scaffold/develop with context prepared.
- **maintain-knowledge** (prompt) — Builds, seeds, and updates the shared psm knowledge base; agent is its curator.

## Per-Lens Verdicts

- **leanness**: Passes — capability prompts are lean and outcome-shaped; one minor cross-file mechanic repetition.
- **architecture**: Sound stateless topology and activation; one eager-load-at-activation redundancy that should be on-demand.
- **determinism**: Largely judgment-shaped; two first-run setup operations (KB tree creation, Docker/flashlight check) are deterministic plumbing left in prose with no scripts/ to hold them.
- **customization**: customize.toml is the sole build-time mechanism, metadata-only with the override surface soundly declined; one opportunity to opt into a persistent_facts default.
- **enhancement**: Strong interactive hub with good headless coverage and missing-file robustness; gaps in first-run gating and uneven headless/conflict handling.
- **agent-cohesion**: Authentic and purposeful — persona drives all four capabilities and the journey chains cleanly; one named-but-unwired personal-preferences store.

## Experience

- **Ask a cross-version question** — Greet → answer-technical loads curated tech/* → answers with explicit version-risk callouts → researches devdocs and updates KB on a gap.
- **Shape a new module** — brainstorm-ecommerce elicits needs and offers e-commerce functions → route-workflow hands off to scaffold/develop with context prepared.
- **First run (new project)** — Activation builds+seeds the shared KB, checks Docker/flashlight, then greets — the path this report recommends gating and scripting.
- Headless: answer-technical and route-workflow both define non-interactive return paths; maintain-knowledge (the most naturally automated capability) lacks one.

## Findings

### Medium (5)

#### architecture-1 — Whole knowledge base read eagerly at activation, duplicating on-demand capability loads

- Lens: architecture
- Location: `SKILL.md:On Activation (lines 44-45)`
- Evidence: On every non-first waking, activation instructs 'baca tech/*, ecommerce/*, dan projects/<module>.md yang relevan'. But answer-technical.md already loads tech/* as its source-of-truth when it runs, and brainstorm-ecommerce.md loads the ecommerce catalog on demand. The activation sweep front-loads raw knowledge into parent context before any capability is chosen and re-reads what a capability would load itself — a read-avoidance anti-pattern for a stateless agent with no sanctum reason to prime identity.
- Recommendation: Trim activation to reading only lightweight project state (projects/<module>.md for the module in play) to restore 'where were we', and let tech/* and ecommerce/* load through the capabilities that already own those reads. Keep first-run structure build/seed at activation; move steady-state domain reads to on-demand.

#### determinism-1 — First-run knowledge-base structure creation done by prose

- Lens: determinism
- Location: `SKILL.md On Activation (line 44) + references/maintain-knowledge.md First run (lines 15-16)`
- Evidence: 'First run (folder belum ada): bangun strukturnya dan seed isinya' and 'Bila folder belum ada, buat strukturnya' ask the model to create a fixed, known tree (tech/, ecommerce/, projects/) with a fixed named file set. The directory layout and filenames have one correct answer.
- Recommendation: Add a scripts/init_kb.py that deterministically mkdirs the tree and writes stub files, so the model spends tokens only on the seed content (summarizing research into curated files), which is genuine judgment and correctly stays in the prompt. The seeding is not a leak; only the mkdir + fixed-file creation is.

#### determinism-2 — Docker + flashlight image presence check done by prose

- Lens: determinism
- Location: `SKILL.md On Activation (line 44)`
- Evidence: 'Lalu cek Docker + image flashlight; bila belum ada, bantu Budi menyiapkan' — the model is told to check whether Docker is installed and whether the flashlight image exists. The signal-verb 'cek' over environment presence has one correct answer settled by docker images / exit code, not model judgment.
- Recommendation: Push the presence check into a small script returning present/absent as JSON, and let the prompt decide only what to do about the result (offer setup, defer to psm-validate).

#### customization-1 — No persistent_facts default to auto-carry project context

- Lens: customization
- Location: `customize.toml [agent] (override half absent)`
- Evidence: The agent declines the override surface entirely and loads context at activation from config.yaml section psm plus its shared KB. For a stateless agent this leaves the BMad default persistent_facts glob (file:{project-root}/**/project-context.md) unused, so a generic project brief never preloads without a query. The KB is deliberate and richer, but project-context.md is a distinct org-level concern the runtime KB does not cover.
- Recommendation: Opt into persistent_facts = [ { code = "project-context", file = "file:{project-root}/**/project-context.md" } ] so general project context preloads alongside the psm KB load. If the maintainer judges config.yaml + KB sufficient and project-context.md out of scope, keep metadata-only and leave a one-line note saying so — this is an opportunity, not a defect.

#### enhancement-1 — Soft-gate the first-run KB build + Docker setup before it fires ahead of the greeting

- Lens: enhancement
- Location: `SKILL.md On Activation (first-run bullet) + references/maintain-knowledge.md First run`
- Evidence: On Activation orders build/seed KB and 'cek Docker + image flashlight; bila belum ada, bantu Budi menyiapkan' BEFORE the final 'Sapa Budi'. When seed sources are missing, maintain-knowledge escalates to devdocs research. So a brand-new user can trigger KB scaffolding, live web research, and an interactive Docker/flashlight setup detour before the agent has said hello or learned their intent.
- Recommendation: Greet first, then soft-gate the heavy work: detect the missing KB/Docker and offer it ('KB bersama belum ada — mau kubangun & seed sekarang? Docker/flashlight juga belum siap, cek sekalian?') rather than performing build + research + environment setup unprompted.

### Low (4)

#### enhancement-2 — No non-interactive return path for maintain-knowledge to match the other capabilities

- Lens: enhancement
- Location: `references/maintain-knowledge.md`
- Evidence: answer-technical and route-workflow both close with an explicit 'dipanggil non-interaktif → jawab/arahkan langsung' path. maintain-knowledge has none, yet it is the capability most naturally automated — 'Tiap rilis PrestaShop baru adalah pemicu untuk memperbarui tech/breaking-changes-*.md' is exactly a scheduled/headless trigger.
- Recommendation: Add a closing line: when a target file/topic is supplied non-interactively, research, write the update, and return a terse summary of what changed (files touched, source, date) without conversational framing.

#### enhancement-3 — No reconcile of curated KB against fresh research when they conflict

- Lens: enhancement
- Location: `references/answer-technical.md + references/maintain-knowledge.md (Perbarui)`
- Evidence: answer-technical treats tech/* as top of the source-of-truth chain and maintain-knowledge says 'Knowledge base adalah kebenaran.' Neither says what to do when fresh devdocs research contradicts an existing curated entry, so the agent could silently trust stale curated knowledge or silently overwrite without flagging.
- Recommendation: In maintain-knowledge, add: when new research contradicts an existing curated fact, flag the conflict to Budi, prefer the newer sourced fact, and update the entry with an old→new note plus source/date so the KB doesn't quietly ossify a wrong answer.

#### agent-cohesion-1 — Personal-preferences store is a loose thread with no read/write path

- Lens: agent-cohesion
- Location: `references/maintain-knowledge.md:27 (with SKILL.md On Activation)`
- Evidence: maintain-knowledge states 'Preferensi pribadi Budi (gaya kerja, keputusan berulang) disimpan terpisah dari knowledge teknis bersama' — introducing a personal-preferences store, but no capability captures or applies it and On Activation only loads tech/, ecommerce/, and projects/<module>.md. For a stateless agent the location is named but never wired.
- Recommendation: Either drop the personal-preferences sentence, or close the loop: name the file (e.g. projects/_budi-prefs.md), have On Activation read it, and have maintain-knowledge own writing it — so the mentioned store has an actual read/write path.

#### leanness-1 — WebReader-not-WebFetch rule restated in two capability files

- Lens: leanness
- Location: `references/answer-technical.md:7 and references/maintain-knowledge.md:25`
- Evidence: The same mechanic — 'riset devdocs dengan WebReader (bukan WebFetch — lebih lengkap untuk devdocs.prestashop-project.org)' — is stated in substance in both answer-technical (research-on-gap path) and maintain-knowledge (update path). maintain-knowledge is the canonical curator home; answer-technical restates it rather than routing to it.
- Recommendation: Keep the rule in maintain-knowledge.md (curator's home). In answer-technical.md drop the parenthetical and reference the maintain-knowledge capability for the research-and-update step, so the tool preference lives in one place. Trivial; skip if the duplication is intentional for standalone non-interactive invocation of answer-technical.
