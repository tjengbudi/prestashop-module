#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Deterministic round bookkeeping for psm-review-loop.

Subcommands (all print one JSON object to stdout):
  next   allocate the run dir (<out-root>/<doc-name>-<run-id>/) on the first call, then the
         next round-N dir; cap_reached=true (no dir created) once max_rounds rounds exist.
         Also returns doc_tag "[doc:<doc filename>]", the prefix of every memlog entry the loop
         writes.
  merge  validate one round's lens files (parse, array, four required keys, length equals the
         count the reviewer reported) and write <round-dir>/merged.json: stable IDs <lens>-<k>,
         exact duplicates removed, candidate clusters by normalized location, invalid/missing
         lens lists. Exit 1 when the round is incomplete.
  carry  filter a memlog to what reviewers receive: rejected, decision and still-pending
         escalated entries (an escalation is answered once a later rejected/decision/fix entry
         carries its [id]). --fixes adds the doc's fix entries (triage only).
  close  read merged.json + triage.json of a round, the earlier rounds and the memlog; return
         the memlog event line, running totals, the stop verdict and, on stop, the gap line and
         the result line "review-loop result: <status> (<reason>|clean) for <doc> sha256=<hex>".
  reviewed  {"clean", "sha256", "last_result"}: clean iff the latest result line for this doc
         (matched by file name) is selesai and its sha256 equals the doc's current hash.

Doc scoping (--doc on carry/close): the memlog is shared by the documents of one folder and
by the calling skill. Entries tagged [doc:<name>] count only for that document; untagged
entries (the caller's own decisions, loop entries written before tags) count for every
document. Answers to an [id] are matched across the whole memlog. Companion files are not
part of the hash: producers keep pairs consistent with their own checks.
"""
import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

REQUIRED = ("location", "issue", "implementation_impact", "suggestion")
TRIAGE_KEYS = ("critical_high", "fixed", "escalated", "dropped", "questions_for_budi", "medium_low")
LENS_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
ENTRY_RE = re.compile(r"^- \(([a-z_-]+)(?: by [^)]*)?\) (.*)$")
ID_RE = re.compile(r"\[(\d{8}-\d{6}(?:-\d+)?\.r\d+-q\d+)\]")
ROUND_RE = re.compile(r"^round-(\d+)$")
TAG_RE = re.compile(r"^\[doc:([^\]]+)\] ?(.*)$")
RESULT_RE = re.compile(r"^review-loop result: (.+?) \((.+?)\) for (.+) sha256=([0-9a-f]{64})$")


def norm(text):
    return re.sub(r"\s+", " ", re.sub(r"[`'\"*_]", "", str(text))).strip().lower()


def doc_tag(doc):
    return f"[doc:{Path(doc).name}]"


def sha256_of(doc):
    p = Path(doc)
    return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None


def display_path(doc, root):
    try:
        return str(Path(doc).resolve().relative_to(Path(root).resolve()))
    except ValueError:
        return str(doc)


def rounds_in(run_dir):
    found = []
    for p in run_dir.iterdir() if run_dir.is_dir() else []:
        m = ROUND_RE.match(p.name)
        if m and p.is_dir():
            found.append((int(m.group(1)), p))
    return sorted(found)


def cmd_next(a):
    if a.run_dir:
        run_dir = Path(a.run_dir)
        if not run_dir.is_dir():
            raise ValueError(f"run dir not found: {run_dir}")
    else:
        name = re.sub(r"[^A-Za-z0-9._-]", "-", Path(a.doc).stem.lstrip(".")) or "doc"
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        run_dir, k = Path(a.out_root) / f"{name}-{stamp}", 2
        while run_dir.exists():
            run_dir, k = Path(a.out_root) / f"{name}-{stamp}-{k}", k + 1
        run_dir.mkdir(parents=True)
    run_id = re.search(r"\d{8}-\d{6}(?:-\d+)?$", run_dir.name)
    existing = rounds_in(run_dir)
    n = (existing[-1][0] if existing else 0) + 1
    out = {"run_id": run_id.group(0) if run_id else run_dir.name, "run_dir": str(run_dir),
           "doc_tag": doc_tag(a.doc), "round": None, "round_dir": None, "cap_reached": n > a.max_rounds, "final_round": False}
    if n <= a.max_rounds:
        rd = run_dir / f"round-{n}"
        rd.mkdir()
        out.update(round=n, round_dir=str(rd), final_round=n == a.max_rounds)
    return out, 0


def parse_lens_arg(spec):
    name, _, count = spec.partition("=")
    if not LENS_RE.match(name):
        raise ValueError(f"invalid lens name: {name!r}")
    if count == "":
        return name, None
    if not count.isdigit():
        raise ValueError(f"invalid count for lens {name}: {count!r}")
    return name, int(count)


def cmd_merge(a):
    rd = Path(a.round_dir)
    if not rd.is_dir():
        raise ValueError(f"round dir not found: {rd}")
    lenses = dict(parse_lens_arg(s) for s in a.lens)
    invalid, missing, findings, seen, dups, per_lens = [], [], [], {}, [], {}
    for lens, reported in lenses.items():
        path = rd / f"{lens}.json"
        per_lens[lens] = {"reported": reported, "valid": False, "count": 0}
        if not path.is_file():
            missing.append(lens)
            continue
        reason = None
        data: list = []
        try:
            parsed = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as e:
            reason = f"not valid JSON: {e}"
        else:
            if isinstance(parsed, list):
                data = parsed
            else:
                reason = "top level is not a JSON array"
        if reason is None:
            for i, item in enumerate(data, 1):
                if not isinstance(item, dict):
                    reason = f"item {i} is not an object"
                    break
                absent = [k for k in REQUIRED if not isinstance(item.get(k), str) or not item[k].strip()]
                if absent:
                    reason = f"item {i} lacks {', '.join(absent)}"
                    break
        if reason is None and reported is None:
            reason = "reviewer returned no count"
        if reason is None and len(data) != reported:
            reason = f"file holds {len(data)} findings, reviewer reported {reported}"
        if reason:
            invalid.append({"lens": lens, "path": str(path), "reason": reason})
            continue
        per_lens[lens].update(valid=True, count=len(data))
        for k, item in enumerate(data, 1):
            fid = f"{lens}-{k}"
            key = (norm(item["location"]), norm(item["issue"]))
            if key in seen:
                dups.append({"id": fid, "duplicate_of": seen[key]})
                continue
            seen[key] = fid
            findings.append({"id": fid, "lens": lens, **{f: item[f] for f in REQUIRED}})
    groups = {}
    for f in findings:
        groups.setdefault(norm(f["location"]), []).append(f["id"])
    clusters = [ids for ids in groups.values() if len(ids) > 1]
    known = set(lenses) | {"merged", "triage"}
    unexpected = sorted(p.name for p in rd.glob("*.json") if p.stem not in known)
    m = ROUND_RE.match(rd.name)
    run_id = re.search(r"\d{8}-\d{6}(?:-\d+)?$", rd.parent.name)
    complete = not invalid and not missing
    merged = {"run_id": run_id.group(0) if run_id else rd.parent.name,
              "round": int(m.group(1)) if m else None, "complete": complete, "lenses": per_lens,
              "invalid": invalid, "missing": missing, "unexpected": unexpected,
              "findings": findings, "duplicates_removed": dups, "clusters": clusters}
    out_path = rd / "merged.json"
    out_path.write_text(json.dumps(merged, indent=1, ensure_ascii=False), encoding="utf-8")
    summary = {k: merged[k] for k in ("run_id", "round", "complete", "invalid", "missing", "unexpected")}
    summary.update(merged=str(out_path), findings=len(findings), duplicates_removed=len(dups),
                   clusters=len(clusters))
    return summary, 0 if complete else 1


def read_memlog(path):
    """[(type, text without doc tag, tagged doc name or None)]"""
    entries = []
    p = Path(path)
    if p.is_file():
        for line in p.read_text(encoding="utf-8").splitlines():
            m = ENTRY_RE.match(line)
            if m:
                t = TAG_RE.match(m.group(2))
                entries.append((m.group(1), t.group(2), t.group(1)) if t else (m.group(1), m.group(2), None))
    return entries


def scoped(entries, doc):
    if not doc:
        return entries
    name = Path(doc).name
    return [e for e in entries if e[2] is None or e[2] == name]


def answered_ids(entries):
    return {i for t, x, _ in entries if t in ("rejected", "decision", "fix") for i in ID_RE.findall(x)}


def carry(entries, doc=None, fixes=False):
    answered = answered_ids(entries)
    mine = scoped(entries, doc)
    pending, seen = [], set()
    for t, x, _ in mine:
        if t == "escalated":
            for i in ID_RE.findall(x):
                if i not in answered and i not in seen:
                    seen.add(i)
                    pending.append({"id": i, "text": x})
    out = {"rejected": [x for t, x, _ in mine if t == "rejected"],
           "decisions": [x for t, x, _ in mine if t == "decision"],
           "escalated_pending": pending}
    if fixes:
        out["fixes"] = [x for t, x, _ in mine if t == "fix"]
    return out


def cmd_carry(a):
    return carry(read_memlog(a.memlog), a.doc, a.fixes), 0


def cmd_reviewed(a):
    current, last = sha256_of(a.doc), None
    for _, x, _ in read_memlog(a.memlog):
        m = RESULT_RE.match(x)
        if m and Path(m.group(3)).name == Path(a.doc).name:
            last = m
    clean = bool(last and current and last.group(1) == "selesai" and last.group(4) == current)
    return {"clean": clean, "sha256": current, "last_result": last.group(0) if last else None}, 0


def load_triage(rd):
    path = rd / "triage.json"
    if not path.is_file():
        raise ValueError(f"triage.json missing in {rd}")
    t = json.loads(path.read_text(encoding="utf-8"))
    absent = [k for k in TRIAGE_KEYS if k not in t]
    if absent:
        raise ValueError(f"{path} lacks {', '.join(absent)}")
    return t


def cmd_close(a):
    rd = Path(a.round_dir)
    m = ROUND_RE.match(rd.name)
    if not m or not rd.is_dir():
        raise ValueError(f"not a round dir: {rd}")
    n = int(m.group(1))
    merged_path = rd / "merged.json"
    if not merged_path.is_file():
        raise ValueError(f"merged.json missing in {rd}; run merge first")
    merged = json.loads(merged_path.read_text(encoding="utf-8"))
    history, oscillation_ids, asked, ml, ml_seen = [], set(), [], [], set()
    for k, d in rounds_in(rd.parent):
        if k > n:
            continue
        t = load_triage(d)
        history.append(int(t["critical_high"]))
        oscillation_ids |= {q.get("id") for q in t["questions_for_budi"] if q.get("oscillation")}
        asked += [q.get("id") for q in t["questions_for_budi"]]
        for item in t["medium_low"]:
            key = (norm(item.get("location", "")), norm(item.get("issue", "")))
            if key not in ml_seen:
                ml_seen.add(key)
                ml.append({"round": k, **item})
    t = load_triage(rd)
    entries = read_memlog(a.memlog)
    pending = [p["id"] for p in carry(entries, a.doc)["escalated_pending"]]
    answered = answered_ids(entries)
    # a question triage raised but never logged still awaits Budi
    pending += [i for i in asked if i and i not in answered and i not in pending]
    ch, fixed, applied = int(t["critical_high"]), int(t["fixed"]), a.applied
    changed = fixed + applied > 0
    reason, clean = None, False
    if not changed and not pending:
        clean = merged["complete"]
        reason = None if clean else "lens_failure"
    elif not changed:
        reason = "oscillation" if oscillation_ids & set(pending) else "awaiting_decision"
    elif len(history) >= 3 and history[-1] >= history[-2] >= history[-3]:
        reason = "no_progress"
    elif n >= a.max_rounds:
        reason = "cap"
    stop = clean or reason is not None
    lens_note = "complete" if merged["complete"] else "incomplete (" + ", ".join(
        merged["missing"] + [i["lens"] for i in merged["invalid"]]) + ")"
    tag = doc_tag(a.doc) + " " if a.doc else ""
    event = (f"{tag}review-loop round {n}: {ch} critical/high ({fixed} fixed, {t['escalated']} escalated), "
             f"{applied} approved answers applied, {t['dropped']} dropped (unproven), "
             f"{len(t['medium_low'])} medium/low; lenses {lens_note}")
    ml_path = rd.parent / "medium-low.json"
    ml_path.write_text(json.dumps(ml, indent=1, ensure_ascii=False), encoding="utf-8")
    out = {"round": n, "event": event, "stop": stop, "clean": clean, "reason": reason,
           "critical_high_by_round": history, "escalations": len(pending), "pending_escalations": pending,
           "remaining_critical_high": 0 if clean else len(pending) + fixed + applied,
           "medium_low_open": len(ml), "medium_low_path": str(ml_path), "gap": None, "result": None}
    if stop and a.doc:
        status = "selesai (clean)" if clean else f"butuh intervensi ({reason})"
        out["result"] = (f"review-loop result: {status} for {display_path(a.doc, a.project_root)} "
                         f"sha256={sha256_of(a.doc)}")
    if stop and ml:
        out["gap"] = f"{tag}review-loop: {len(ml)} medium/low findings left open after {n} rounds, list at {ml_path}"
    return out, 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--verbose", action="store_true", help="print tracebacks on error")
    ap.add_argument("-o", "--output", help="write the JSON here instead of stdout")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("next", help="allocate the run dir and the next round dir")
    p.add_argument("--doc", required=True, help="target document path (names the run dir)")
    p.add_argument("--out-root", required=True, help="{project-root}/_bmad-output/psm-review-loop")
    p.add_argument("--max-rounds", type=int, required=True)
    p.add_argument("--run-dir", help="existing run dir; omit on the first round")
    p = sub.add_parser("merge", help="validate and merge one round's lens files")
    p.add_argument("round_dir")
    p.add_argument("--lens", action="append", required=True,
                   help="NAME=COUNT as the reviewer returned it; bare NAME if it returned nothing")
    p = sub.add_parser("carry", help="list what reviewers must not raise again")
    p.add_argument("--memlog", required=True)
    p.add_argument("--doc", help="scope to this document (tagged entries of other docs are skipped)")
    p.add_argument("--fixes", action="store_true", help="also list this doc's fix entries (triage only)")
    p = sub.add_parser("close", help="close a round: event line, totals, stop verdict")
    p.add_argument("round_dir")
    p.add_argument("--memlog", required=True)
    p.add_argument("--max-rounds", type=int, required=True)
    p.add_argument("--applied", type=int, default=0, help="approved answers applied after triage")
    p.add_argument("--doc", help="target document: scopes pending escalations, tags lines, enables result")
    p.add_argument("--project-root", default=".", help="result path is shown relative to this when under it")
    p = sub.add_parser("reviewed", help="is the doc already reviewed clean and unchanged?")
    p.add_argument("--doc", required=True)
    p.add_argument("--memlog", required=True)
    a = ap.parse_args(argv)
    cmds = {"next": cmd_next, "merge": cmd_merge, "carry": cmd_carry, "close": cmd_close,
            "reviewed": cmd_reviewed}
    try:
        out, code = cmds[a.cmd](a)
    except (ValueError, OSError, json.JSONDecodeError) as e:
        if a.verbose:
            raise
        print(json.dumps({"error": str(e)}), file=sys.stderr)
        return 2
    text = json.dumps(out, ensure_ascii=False)
    if a.output:
        Path(a.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return code


if __name__ == "__main__":
    sys.exit(main())
