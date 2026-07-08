# Analysis Report: skills/psm-agent-expert

Generated: 2026-07-08T09:23:00+00:00 · Schema: 2

**Grade: Excellent**

> Skill passes all lenses clean; 19 path-scanner highs are tool false positives on artifacts and process memory, not source defects.

psm-agent-expert is lean, coherent, and well-wired. The persona, principles, capability routing, and KB curation flow all earn their place. Minor observations — a duplicated caution in Communication Style, mild ceremony in Overview — are low-impact cosmetics that do not affect behavior.

| Severity | Count |
| --- | --- |
| Critical | 0 |
| High | 0 |
| Medium | 0 |
| Low | 6 |

## Themes

### 1. Minor content duplication

- Root cause: Two low-weight lines in SKILL.md repeat information already in references or other sections, adding tokens to every activation with no behavioral gain.
- Fix: Cut the 'jangan menebak' sentence from Communication Style (covered by Principles and answer-technical.md) and absorb or drop the 'Your Mission' sentence into the Overview paragraph.
- Findings:
  - `leanness-1` Duplicated caution in Communication Style — `SKILL.md:Communication Style (last sentence)`
  - `leanness-2` Ceremony: 'Your Mission' sentence in Overview — `SKILL.md:Overview ('**Your Mission:**' line)`

### 2. Path-scanner false positives on artifacts

- Root cause: scan-path-standards.py scans .analysis/ artifact files and .memlog.md process memory. Absolute paths in rendered report files and bare _bmad mentions in memlog notes are expected, not skill defects.
- Fix: No skill change needed. Consider scoping scan-path-standards.py to exclude .analysis/ and .memlog.md, or document that artifact findings are excluded from grading.
- Findings:
  - `arch-1` Path-scanner false positive: .memlog.md and .analysis/ artifacts — `.analysis/2026-06-25-2035/, .memlog.md`

## Strengths

- Lean: 1219 tokens for SKILL.md with zero waste patterns — right-sized for an always-on persona.
- Routing table design: 4 capabilities map cleanly to 4 on-demand references; core persona costs nothing for unused capability paths.
- KB architecture: shared module memory (_bmad/psm/memory/) is the right design — agent is curator, workflows are consumers, no sanctum duplication.
- First-run resilience: fallback for missing seed sources documented in maintain-knowledge.md prevents half-empty KB on fresh install.
- Cross-version principle is the first and strongest rule — enforced in Principles and in answer-technical.md capability.

## Recommendations

1. In Communication Style, remove the last sentence ('Saat tak yakin sebuah API masih ada di versi tertentu, periksa knowledge base atau riset dulu, jangan menebak.'). It duplicates 'Knowledge base adalah kebenaran' in Principles and the jangan-menebak instruction in answer-technical.md. (resolves: leanness-1)
2. In Overview, remove the 'Your Mission:' bold line — the paragraph already expresses the mission. (resolves: leanness-2)

## Experience

- **First-time activation (KB build)** — Config load → KB structure check → first-run seed from sibling skills → Docker/flashlight check → greeting
- **Technical Q&A** — Activation → KB read → answer-technical.md → cross-version answer with safe path
- **Workflow routing** — Intent detection → project state read → route-workflow.md → workflow invocation with prepared context
- Headless: Partially adaptable — answer-technical.md and route-workflow.md have inline non-interactive hints, but SKILL.md does not declare headless behavior; fundamentally interactive by design.

## Findings

### Low (6)

#### leanness-1 — Duplicated caution in Communication Style

- Lens: leanness
- Location: `SKILL.md:Communication Style (last sentence)`
- Evidence: 'Saat tak yakin sebuah API masih ada di versi tertentu, periksa knowledge base atau riset dulu, jangan menebak.' — same rule exists as 'Knowledge base adalah kebenaran' in Principles and 'jangan menebak: riset devdocs' in answer-technical.md.
- Recommendation: Remove this sentence. Principles enforce the rule at persona level; answer-technical.md carries it at capability level. No behavioral change on removal.
- Proposed smallest: Remove the sentence entirely.
- Predicted delta: None — the rule is enforced in Principles and in the reference that loads for every technical question.

#### leanness-2 — Ceremony: 'Your Mission' sentence in Overview

- Lens: leanness
- Location: `SKILL.md:Overview ('**Your Mission:**' line)`
- Evidence: '**Your Mission:** Membuat Budi tak pernah perlu menjelaskan ulang standar PrestaShop...' — this intent is already expressed by the Overview paragraph itself.
- Recommendation: Remove the bold label and sentence, or fold its content into the Overview paragraph. The framing adds no behavioral signal the paragraph doesn't already carry.
- Proposed smallest: Remove the entire 'Your Mission:' line.
- Predicted delta: None expected — Overview paragraph already communicates the mission.

#### arch-1 — Path-scanner false positive: .memlog.md and .analysis/ artifacts

- Lens: architecture
- Location: `.analysis/2026-06-25-2035/, .memlog.md`
- Evidence: scan-path-standards.py reports 19 high findings — all in generated report artifacts (.analysis/) and process-memory (.memlog.md). Source files (SKILL.md, references/*.md, customize.toml) are path-clean. Absolute paths in rendered reports and bare _bmad mentions in memlog notes are expected by design.
- Recommendation: No skill change needed. Consider scoping scan-path-standards.py to exclude .analysis/ directories and .memlog.md, or document that artifact-file findings are excluded from skill grading.

#### determinism-1 — Config parsing in prompt (accepted by design)

- Lens: determinism
- Location: `SKILL.md:On Activation`
- Evidence: Model reads YAML config and extracts user_name, communication_language, psm_target_versions — deterministic extraction work. Previously evaluated and accepted (memlog 2026-06-25: 'determinism-1 diterima, agent script-free by design').
- Recommendation: Accepted. Agent skills in BMad are script-free by convention; config parsing is lightweight and integrated into activation flow. No change required.

#### customization-1 — Override surface intentionally absent — future psm_target_versions opportunity

- Lens: customization
- Location: `customize.toml`
- Evidence: customize.toml present with [agent] metadata only. Comment explicitly documents why no [workflow] override surface exists. About right for current use. psm_target_versions default (1.7.8,8.1,9.0) is hardcoded in SKILL.md — if per-project override becomes common, this is a gap.
- Recommendation: No change now. If psm_target_versions becomes a common per-project override, expose it as a customize.toml scalar with a [workflow] section and update On Activation to read {workflow.psm_target_versions}.

#### enhancement-1 — Headless adaptability undeclared at skill level

- Lens: enhancement
- Location: `SKILL.md:On Activation, references/answer-technical.md, references/route-workflow.md`
- Evidence: answer-technical.md and route-workflow.md each have 'bila dipanggil non-interaktif' inline hints, but SKILL.md has no headless skip-to-capability entry point. Skill is fundamentally interactive by design.
- Recommendation: Low priority. If headless invocation becomes common, add one line to SKILL.md On Activation: 'Bila dipanggil non-interaktif dengan intent dan konteks lengkap, lewati salam dan langsung muat referensi yang sesuai.' Otherwise acceptable as-is.
