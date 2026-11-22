#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Unit tests for review-round.py. Run: uv run scripts/tests/test-review-round.py"""
import hashlib
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "review-round.py"
_failures = []
_checks = []


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}: {name}")
    _checks.append(name)
    if not cond:
        _failures.append(name)


def run(*args):
    r = subprocess.run([sys.executable, str(SCRIPT), *map(str, args)], capture_output=True, text=True)
    out = json.loads(r.stdout) if r.stdout.strip() else {}
    return r.returncode, out, r.stderr


def finding(loc, issue="x"):
    return {"location": loc, "issue": issue, "implementation_impact": "i", "suggestion": "s"}


def write(path, data):
    path.write_text(json.dumps(data) if not isinstance(data, str) else data, encoding="utf-8")


def triage(rd, ch, fixed, questions=(), ml=(), escalated=None):
    write(rd / "triage.json", {"round": int(rd.name.split("-")[1]), "critical_high": ch, "fixed": fixed,
                               "escalated": len(questions) if escalated is None else escalated,
                               "dropped": 1, "code_defects": 0, "oscillations": [],
                               "questions_for_budi": list(questions), "medium_low": list(ml)})


def test_next(td):
    print("next")
    code, a, _ = run("next", "--doc", td / "mod" / ".psm-develop-plan.md", "--out-root", td / "out",
                     "--max-rounds", 2)
    run_dir = Path(a["run_dir"])
    check("first call creates run dir named after doc", code == 0 and run_dir.name.startswith("psm-develop-plan-"))
    check("round 1 allocated", a["round"] == 1 and Path(a["round_dir"]).is_dir() and not a["cap_reached"])
    check("run_id is a timestamp", len(a["run_id"]) == 15 and a["run_id"][8] == "-")
    check("doc_tag names the doc file", a["doc_tag"] == "[doc:.psm-develop-plan.md]")
    _, b, _ = run("next", "--doc", "x.md", "--out-root", td / "out", "--max-rounds", 2, "--run-dir", run_dir)
    check("round 2 is final", b["round"] == 2 and b["final_round"])
    _, c, _ = run("next", "--doc", "x.md", "--out-root", td / "out", "--max-rounds", 2, "--run-dir", run_dir)
    check("cap reached creates no dir", c["cap_reached"] and c["round"] is None and not (run_dir / "round-3").exists())
    _, d, _ = run("next", "--doc", td / "mod" / ".psm-develop-plan.md", "--out-root", td / "out", "--max-rounds", 2)
    check("second run never reuses a run dir", d["run_dir"] != a["run_dir"])
    code, _, err = run("next", "--doc", "x.md", "--out-root", td, "--max-rounds", 2, "--run-dir", td / "nope")
    check("missing run dir is an error (exit 2)", code == 2 and "not found" in err)


def round_dir(td, name="doc-20261122-120000", n=1):
    rd = td / name / f"round-{n}"
    rd.mkdir(parents=True)
    return rd


def test_merge(td):
    print("merge")
    rd = round_dir(td / "m1")
    write(rd / "adversarial.json", [finding("§2 Step 3", "Ambiguous hook"), finding("§4", "Missing table")])
    write(rd / "edge-case.json", [finding("§2  step 3", "ambiguous `hook`"), finding("§2 Step 3", "other")])
    write(rd / "implementer.json", [])
    write(rd / "stale.json", [])
    code, s, _ = run("merge", rd, "--lens", "adversarial=2", "--lens", "edge-case=2", "--lens", "implementer=0")
    merged = json.loads((rd / "merged.json").read_text())
    ids = [f["id"] for f in merged["findings"]]
    check("complete round exits 0", code == 0 and s["complete"])
    check("stable ids <lens>-<k>", ids == ["adversarial-1", "adversarial-2", "edge-case-2"])
    check("exact duplicate removed after normalization",
          merged["duplicates_removed"] == [{"id": "edge-case-1", "duplicate_of": "adversarial-1"}])
    check("cluster by normalized location", merged["clusters"] == [["adversarial-1", "edge-case-2"]])
    check("stale file reported as unexpected", s["unexpected"] == ["stale.json"])
    check("run id and round read from path", merged["run_id"] == "20261122-120000" and merged["round"] == 1)

    rd = round_dir(td / "m2")
    write(rd / "adversarial.json", "Here are my findings: [...]")
    write(rd / "edge-case.json", [{"location": "a", "trigger_condition": "t"}])
    write(rd / "implementer.json", [finding("a")])
    write(rd / "extra-1.json", {"findings": []})
    code, s, _ = run("merge", rd, "--lens", "adversarial=1", "--lens", "edge-case=1", "--lens", "implementer=3",
                     "--lens", "extra-1=0", "--lens", "extra-2=0")
    reasons = {i["lens"]: i["reason"] for i in s["invalid"]}
    check("incomplete round exits 1", code == 1 and not s["complete"])
    check("prose-wrapped file is invalid JSON", "not valid JSON" in reasons.get("adversarial", ""))
    check("unmapped schema names missing keys", "issue" in reasons.get("edge-case", ""))
    check("count mismatch detected", "reported 3" in reasons.get("implementer", ""))
    check("non-array detected", "not a JSON array" in reasons.get("extra-1", ""))
    check("missing file listed", s["missing"] == ["extra-2"])

    rd = round_dir(td / "m3")
    write(rd / "implementer.json", [])
    code, s, _ = run("merge", rd, "--lens", "implementer")
    check("lens with no reported count is invalid", code == 1 and "no count" in s["invalid"][0]["reason"])
    code, _, _ = run("merge", rd, "--lens", "Bad Name=1")
    check("invalid lens name is an error", code == 2)


MEMLOG = """---
skill: x
---

- (decision) keep hook displayHeader
- (rejected) [20261122-120000.r1-q1] Budi: ignore multistore note
- (escalated) round 1: [20261122-120000.r1-q1] multistore?
- (escalated) round 1: [20261122-120000.r1-q2] change table schema?
- (escalated by triage) round 2: [20261122-120000.r2-q1] reverse fix?
- (fix) round 2: [20261122-120000.r2-q1] applied option B
- (fix) round 1: §3 named the hook
- (gap) old medium
"""


def test_carry(td):
    print("carry")
    mem = td / "carry.memlog.md"
    write(mem, MEMLOG)
    code, c, _ = run("carry", "--memlog", mem)
    check("rejected and decisions carried", code == 0 and len(c["rejected"]) == 1 and c["decisions"] == ["keep hook displayHeader"])
    check("only unanswered escalations pending", [p["id"] for p in c["escalated_pending"]] == ["20261122-120000.r1-q2"])
    _, c, _ = run("carry", "--memlog", td / "absent.md")
    check("missing memlog gives empty lists", c == {"rejected": [], "decisions": [], "escalated_pending": []})


SHARED = """- (decision) module-wide: keep hook displayHeader
- (decision) [doc:.psm-cross-plan.md] [20261122-110000.r1-q1] Budi: drop 1.6 path
- (rejected) [doc:.psm-develop-plan.md] [20261122-120000.r1-q1] Budi: ignore multistore
- (escalated) [doc:.psm-develop-plan.md] round 1: [20261122-120000.r1-q2] change schema?
- (escalated) [doc:.psm-cross-plan.md] round 1: [20261122-110000.r1-q2] keep override?
- (fix) [doc:.psm-develop-plan.md] round 1: §3 named the hook
- (fix) [doc:.psm-cross-plan.md] round 1: §2 added md5
- (escalated) round 1: [20261122-100000.r1-q1] legacy untagged question
- (fix) [doc:.psm-develop-plan.md] round 2: [20261122-110000.r1-q2] answered across docs
"""


def test_carry_scoped(td):
    print("carry --doc")
    mem = td / "shared.memlog.md"
    write(mem, SHARED)
    _, c, _ = run("carry", "--memlog", mem, "--doc", td / ".psm-develop-plan.md")
    check("untagged decision carried, other doc's decision skipped",
          c["decisions"] == ["module-wide: keep hook displayHeader"])
    check("own rejection carried with tag stripped", c["rejected"] == ["[20261122-120000.r1-q1] Budi: ignore multistore"])
    check("own and untagged legacy escalations pending, other doc's skipped",
          [p["id"] for p in c["escalated_pending"]] == ["20261122-120000.r1-q2", "20261122-100000.r1-q1"])
    check("fixes absent without --fixes", "fixes" not in c)
    _, c, _ = run("carry", "--memlog", mem, "--doc", ".psm-cross-plan.md", "--fixes")
    check("answers matched across the whole memlog", [p["id"] for p in c["escalated_pending"]] == ["20261122-100000.r1-q1"])
    check("--fixes lists only this doc's fixes", c["fixes"] == ["round 1: §2 added md5"])
    _, c, _ = run("carry", "--memlog", mem)
    check("no --doc keeps every entry", len(c["decisions"]) == 2 and len(c["escalated_pending"]) == 2)


def close_case(td, name, rounds, memlog="", applied=0, max_rounds=5, complete=True, doc=None):
    """rounds: list of (critical_high, fixed, questions, medium_low)."""
    base = td / name / "doc-20261122-120000"
    for n, (ch, fixed, qs, ml) in enumerate(rounds, 1):
        rd = base / f"round-{n}"
        rd.mkdir(parents=True)
        triage(rd, ch, fixed, qs, ml)
        write(rd / "merged.json", {"complete": complete if n == len(rounds) else True,
                                   "missing": [] if complete else ["edge-case"], "invalid": []})
    mem = td / name / ".memlog.md"
    write(mem, memlog)
    extra = ["--doc", doc, "--project-root", td] if doc else []
    return run("close", base / f"round-{len(rounds)}", "--memlog", mem, "--max-rounds", max_rounds,
               "--applied", applied, *extra)


def q(i, osc=False):
    return {"id": f"20261122-120000.r1-q{i}", "finding": "f", "options": ["a"], "recommended": "a", "oscillation": osc}


def test_close(td):
    print("close")
    code, c, _ = close_case(td, "c1", [(3, 3, [], [finding("§1", "style")]), (0, 0, [], [finding("§1 ", "Style")])])
    check("fresh round with 0 critical/high is clean", code == 0 and c["stop"] and c["clean"] and c["reason"] is None)
    check("event line composed", c["event"].startswith("review-loop round 2: 0 critical/high (0 fixed, 0 escalated)"))
    check("medium/low deduplicated across rounds", c["medium_low_open"] == 1 and c["gap"] and "1 medium/low" in c["gap"])
    _, c, _ = close_case(td, "c2", [(2, 2, [], [])])
    check("round that fixed things never stops clean", not c["stop"] and c["remaining_critical_high"] == 2)
    _, c, _ = close_case(td, "c3", [(2, 0, [q(1), q(2)], [])])
    check("all critical/high awaiting decision stops at once",
          c["stop"] and c["reason"] == "awaiting_decision" and c["escalations"] == 2)
    _, c, _ = close_case(td, "c4", [(1, 0, [q(1, osc=True)], [])])
    check("pending oscillation reported as oscillation", c["reason"] == "oscillation")
    _, c, _ = close_case(td, "c5", [(2, 0, [q(1), q(2)], [])], applied=2,
                         memlog="- (decision) [20261122-120000.r1-q1] Budi: A\n- (decision) [20261122-120000.r1-q2] Budi: B\n")
    check("applied approved answers keep the loop going", not c["stop"] and c["escalations"] == 0)
    _, c, _ = close_case(td, "c6", [(1, 0, [q(1)], [])], memlog="- (rejected) [20261122-120000.r1-q1] Budi: ignore\n")
    check("all escalations rejected and nothing changed is clean", c["clean"])
    _, c, _ = close_case(td, "c7", [(4, 4, [], []), (5, 5, [], []), (5, 5, [], [])])
    check("no decrease two rounds running is no_progress", c["reason"] == "no_progress")
    _, c, _ = close_case(td, "c8", [(5, 5, [], []), (4, 4, [], [])], max_rounds=2)
    check("cap reached", c["reason"] == "cap" and c["critical_high_by_round"] == [5, 4])
    _, c, _ = close_case(td, "c9", [(0, 0, [], [])], complete=False)
    check("incomplete round can never be clean", not c["clean"] and c["reason"] == "lens_failure")
    check("event names the failed lens", "incomplete (edge-case)" in c["event"])
    rd = td / "c10" / "doc-20261122-120000" / "round-1"
    rd.mkdir(parents=True)
    write(rd / "merged.json", {"complete": True, "missing": [], "invalid": []})
    write(rd / "triage.json", {"fixed": 0})
    code, _, err = run("close", rd, "--memlog", td / "none.md", "--max-rounds", 5)
    check("malformed triage.json is an error", code == 2 and "lacks" in err)
    check("no --doc gives no result line", c["result"] is None)


def test_close_scoped(td):
    print("close --doc")
    doc = td / "mod" / ".psm-develop-plan.md"
    doc.parent.mkdir()
    write(doc, "# plan\n")
    h = hashlib.sha256(doc.read_bytes()).hexdigest()
    other = "- (escalated) [doc:.psm-cross-plan.md] round 1: [20261122-090000.r1-q1] other doc?\n"
    _, c, _ = close_case(td, "s1", [(1, 1, [], []), (0, 0, [], [finding("§1")])], memlog=other, doc=doc)
    check("other doc's pending escalation does not block clean", c["clean"] and c["escalations"] == 0)
    check("result line for a clean stop",
          c["result"] == f"review-loop result: selesai (clean) for mod/.psm-develop-plan.md sha256={h}")
    check("event and gap carry the doc tag",
          c["event"].startswith("[doc:.psm-develop-plan.md] review-loop round 2") and c["gap"].startswith("[doc:"))
    _, c, _ = close_case(td, "s2", [(1, 0, [q(1)], [])], doc=doc,
                         memlog="- (escalated) [doc:.psm-develop-plan.md] round 1: [20261122-120000.r1-q1] x\n")
    check("result line for a blocked stop", c["result"].startswith("review-loop result: butuh intervensi (awaiting_decision) for "))
    _, c, _ = close_case(td, "s3", [(2, 2, [], [])], doc=doc)
    check("no result line while the loop continues", not c["stop"] and c["result"] is None)


def test_reviewed(td):
    print("reviewed")
    d = td / "rv"
    d.mkdir()
    doc, mem = d / "1-2-story.md", d / ".memlog.md"
    write(doc, "story v1\n")
    h = hashlib.sha256(doc.read_bytes()).hexdigest()
    res = f"review-loop result: selesai (clean) for docs/stories/1-2-story.md sha256={h}"
    write(mem, f"- (decision) caller note\n- (event) review-loop result: butuh intervensi (cap) for 1-2-story.md sha256={'0' * 64}\n"
               f"- (event) {res}\n- (event) review-loop result: butuh intervensi (cap) for docs/stories/1-3-story.md sha256={h}\n")
    code, r, _ = run("reviewed", "--doc", doc, "--memlog", mem)
    check("clean and unchanged (other doc's later result ignored)",
          code == 0 and r == {"clean": True, "sha256": h, "last_result": res})
    write(doc, "story v2\n")
    _, r, _ = run("reviewed", "--doc", doc, "--memlog", mem)
    check("changed doc is not clean", not r["clean"] and r["sha256"] != h and r["last_result"] == res)
    write(doc, "story v1\n")
    write(mem, f"- (event) {res}\n- (event) review-loop result: butuh intervensi (awaiting_decision) for 1-2-story.md sha256={h}\n")
    _, r, _ = run("reviewed", "--doc", doc, "--memlog", mem)
    check("latest result not selesai is not clean", not r["clean"] and "awaiting_decision" in r["last_result"])
    code, r, _ = run("reviewed", "--doc", doc, "--memlog", d / "absent.md")
    check("missing memlog: not clean, no last result", code == 0 and r == {"clean": False, "sha256": h, "last_result": None})
    code, r, _ = run("reviewed", "--doc", d / "gone.md", "--memlog", mem)
    check("missing doc: not clean, null hash", code == 0 and not r["clean"] and r["sha256"] is None)


def main():
    with tempfile.TemporaryDirectory() as t:
        td = Path(t)
        test_next(td)
        test_merge(td)
        test_carry(td)
        test_carry_scoped(td)
        test_close(td)
        test_close_scoped(td)
        test_reviewed(td)
    print(f"{len(_checks) - len(_failures)}/{len(_checks)} passed")
    if _failures:
        print(f"FAILED: {_failures}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
