#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Unit test untuk ps-plan-layers.py — keputusan reuse/rerun deterministik.

Kontrak: file lapis dipakai ulang HANYA bila ada + terbaca + lebih baru dari source
module + cakupan versinya memuat yang diminta. Basi/kurang/rusak -> rerun (jangan
pernah memvonis atas bukti basi). Jalankan: uv run scripts/tests/test-ps-plan-layers.py
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

MOD_PATH = Path(__file__).resolve().parent.parent / "ps-plan-layers.py"
spec = importlib.util.spec_from_file_location("ps_plan_layers", MOD_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

TV = ["1.7.8", "8.1", "9.1"]
# Token sesi tetap utk test: plan WAJIB --session (kecuali --new-session).
SESSION = "abcdefghij012345"


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}: {name}")
    return cond


def _touch(path, mtime):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("x", encoding="utf-8")
    os.utime(path, (mtime, mtime))


def _layer(path, versions, mtime):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"versions": {v: {"pass": True} for v in versions}}), encoding="utf-8")
    os.utime(path, (mtime, mtime))


BROWSERS = ["chromium", "firefox"]
TAGS = {"1.7.8": "1.7.8.11", "8.1": "8.1.6-nginx", "9.1": "9.1.4-nginx"}  # default tag-map


def _rec(ver, browser, fp, tag=None, **kw):
    """Record bukti E2E lengkap (pass gate-grade passing) — field per cell-contract > Fields."""
    r = {"version": ver, "browser": browser,
         "started_at": "2026-11-26T10:00:00.000000+00:00",
         "finished_at": "2026-11-26T10:05:00.000000+00:00",
         "boot": "cold", "boot_id": "b0", "session": SESSION, "browser_mode": "sequential",
         "scenario_set": "full", "scenarios_run": ["psm-universal-smoke", "s1"],
         "source_fingerprint": fp, "image_tag": tag or TAGS[ver], "run_id": "r0", "job_id": "j0",
         "tier": None, "state": "pass", "conclusive": True, "reason": None, "errors": [],
         "install": {"ok": True}, "launch_error": None, "bo_authed": True, "findings": [],
         "inconclusive": [], "authored_assertions": 2, "scenario_notes": [],
         "browser_notes": [], "parallel_only": None, "console_errors": [], "screenshots": [],
         "scenario_spans": None,
         "phase_durations": {f"browser:{browser}": {"seconds": 1.0, "outcome": "ok"}},
         "boot_phases": {}, "keeper_boot": None, "wall_clock": 300.0}
    r.update(kw)
    return r


def _module(root, name="mymod"):
    m = root / name
    _touch(m / f"{name}.php", 1000)
    _touch(m / "index.php", 900)
    _touch(m / "vendor" / "x.php", 800)
    _touch(m / ".psm-develop-plan.json", 700)
    return m


def _seed(reports, m, fp, cells, **kw):
    for ver, b in cells:
        mod.append_record(mod.history_path(reports, m.name, ver, b), _rec(ver, b, fp, **kw))


def _cfg(root, versions="1.7.8,8.1,9.1", browsers="chromium,firefox", name="psm-config.json"):
    p = root / name
    p.write_text(json.dumps({"psm_target_versions": versions, "psm_e2e_browsers": browsers}),
                 encoding="utf-8")
    return p


def _plan(m, reports, *extra):
    r = subprocess.run(["uv", "run", str(MOD_PATH), str(m), "--reports-dir", str(reports),
                        "--session", SESSION, *extra], capture_output=True, text=True)
    try:
        out = json.loads(r.stdout) if r.returncode == 0 else None
    except json.JSONDecodeError:
        out = None
    return r, out


def _e2e_matrix(plan):
    return [(e["version"], e["browser"], e["reason"]) for e in plan["rerun_matrix"]
            if e["layer"] == "e2e"]


ALL6 = [(v, b) for v in TV for b in BROWSERS]


def test_e2e_cells():
    """CAP-2: bukti E2E per sel dari histori — storage, fresh, gate-grade, alasan, bentuk plan."""
    ok = True
    tm = mod.fl.parse_tag_map(None, None)

    # --- Storage: baris rusak (contract test: valid, rusak, valid -> dua record) -------
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        h = mod.history_path(root, "mymod", "9.1", "chromium")
        ok &= check("history_path = <reports>/<module>-e2e-<ver>-<browser>.jsonl",
                    h == root / "mymod-e2e-9.1-chromium.jsonl")
        ok &= check("histori absen -> ([], False)", mod.read_history(h, "9.1", "chromium") == ([], False))
        a, b = _rec("9.1", "chromium", "fp", run_id="A"), _rec("9.1", "chromium", "fp", run_id="B")
        h.write_text(json.dumps(a) + "\n{bukan json\n" + json.dumps(b) + "\n", encoding="utf-8")
        recs, tail = mod.read_history(h, "9.1", "chromium")
        ok &= check("corrupt line: valid, rusak, valid -> dua record valid, bukan ekor rusak",
                    [r["run_id"] for r in recs] == ["A", "B"] and tail is False)
        with open(h, "a", encoding="utf-8") as f:
            f.write("[1,2]\n")
        recs, tail = mod.read_history(h, "9.1", "chromium")
        ok &= check("corrupt-last: rusak terakhir -> corrupt_tail, record sebelumnya tetap terbaca",
                    len(recs) == 2 and tail is True)
        ok &= check("corrupt-last -> reason corrupt-history walau record lulus",
                    mod.cell_reason(recs, tail, "fp", TAGS["9.1"], []) == "corrupt-history"
                    and not mod.has_passing_evidence(recs, tail, "fp", TAGS["9.1"]))
        bad_lines = [_rec("9.1", "chromium", "fp", started_at="2026-11-26T10:00:00+07:00"),
                     _rec("9.1", "chromium", "fp", started_at="2026-11-26"),
                     _rec("9.1", "chromium", "fp", started_at=None),
                     _rec("9.1", "chromium", "fp", state="stopped"),
                     _rec("9.1", "firefox", "fp"),
                     _rec("8.1", "chromium", "fp")]
        h.write_text("".join(json.dumps(x) + "\n" for x in bad_lines), encoding="utf-8")
        recs, tail = mod.read_history(h, "9.1", "chromium")
        ok &= check("rusak: started_at bukan UTC / bukan ISO, state di luar enum, sel lain",
                    recs == [] and tail is True)
        good = [_rec("9.1", "chromium", "fp", started_at="2026-11-26T10:00:00Z"),
                _rec("9.1", "chromium", "fp", started_at="2026-11-26T10:00:00+00:00")]
        h.write_text("".join(json.dumps(x) + "\n" for x in good) + "\n\n", encoding="utf-8")
        recs, tail = mod.read_history(h, "9.1", "chromium")
        ok &= check("pembaca terima 'Z' & tanpa pecahan detik; baris kosong bukan baris rusak",
                    len(recs) == 2 and tail is False)
        # append: penjaga newline (penulis terbunuh di tengah baris) & tak menulis ulang baris lama
        h2 = mod.history_path(root, "mymod", "9.1", "firefox")
        h2.write_bytes(b'{"version": "9.1", "brow')
        mod.append_record(h2, _rec("9.1", "firefox", "fp", run_id="C"))
        raw = h2.read_bytes()
        recs, tail = mod.read_history(h2, "9.1", "firefox")
        ok &= check("append: baris setengah jadi tak menelan record baru (diawali \\n)",
                    raw.startswith(b'{"version": "9.1", "brow\n') and raw.endswith(b"\n")
                    and [r["run_id"] for r in recs] == ["C"] and tail is False)
        mod.append_record(h2, _rec("9.1", "firefox", "fp", run_id="D"))
        ok &= check("append: baris lama tak ditulis ulang; satu baris per record",
                    h2.read_bytes().startswith(raw) and h2.read_bytes().count(b"\n") == raw.count(b"\n") + 1)
        ok &= check("append: OS error (path folder) -> PlanInputError",
                    _raises(lambda: mod.append_record(root, {"x": 1})))
        ok &= check("read_history: OS error (path folder) -> PlanInputError menyebut path",
                    _raises(lambda: mod.read_history(root, "9.1", "chromium"), str(root)))

    # --- State rules (merge-time) & incomplete-record (reader) ------------------------
    pd = {"browser:chromium": {"seconds": 1.0, "outcome": "ok"}}
    ds = mod.derive_state
    ok &= check("derive_state: driven, install ok, tanpa findings -> pass",
                ds({"browser": "chromium", "phase_durations": pd, "install": {"ok": True},
                    "errors": [], "findings": []}) == {"state": "pass", "conclusive": True, "reason": None})
    ok &= check("derive_state: findings -> fail (conclusive)",
                ds({"browser": "chromium", "phase_durations": pd, "install": {"ok": True},
                    "errors": [], "findings": [{"x": 1}]})["state"] == "fail")
    ok &= check("derive_state: install gagal -> inconclusive reason install",
                ds({"browser": "chromium", "phase_durations": {}, "install": {"ok": False},
                    "errors": ["install"]})["reason"] == "install")
    ok &= check("derive_state: boot gagal (install null) -> reason errors, bukan crash",
                ds({"browser": "chromium", "phase_durations": {}, "install": None,
                    "errors": ["wait-healthy timeout"]})["reason"] == "errors")
    ok &= check("derive_state: launch_error -> reason launch-error",
                ds({"browser": "chromium", "phase_durations": pd, "install": {"ok": True},
                    "launch_error": "boom", "errors": []})["reason"] == "launch-error")
    ok &= check("derive_state: tak di-drive (tanpa browser:<engine>) -> not-driven",
                ds({"browser": "chromium", "phase_durations": {"browser:firefox": {}},
                    "install": {"ok": True}, "errors": []})["reason"] == "not-driven")
    ok &= check("derive_state: browser:<engine>#2 juga dihitung di-drive",
                ds({"browser": "chromium", "phase_durations": {"browser:chromium#2": {}},
                    "install": {"ok": True}, "errors": [], "findings": []})["state"] == "pass")
    inc = _rec("9.1", "chromium", "fp", authored_assertions=None)
    ok &= check("incomplete-record: pass dgn authored_assertions null -> inconclusive",
                mod.record_state(inc) == {"state": "inconclusive", "conclusive": False,
                                          "reason": "incomplete-record"})
    ok &= check("incomplete-record: key absen (browser_notes) juga",
                mod.record_state({k: v for k, v in _rec("9.1", "chromium", "fp").items()
                                  if k != "browser_notes"})["reason"] == "incomplete-record")
    ok &= check("incomplete-record tak pernah gate-grade; plan reason inconclusive",
                not mod.is_gate_grade(inc, "fp", TAGS["9.1"])
                and mod.cell_reason([inc], False, "fp", TAGS["9.1"], []) == "inconclusive")

    # --- Gate-grade: newer fail mengalahkan pass lama (contract test) ------------------
    T = TAGS["9.1"]
    p_ = _rec("9.1", "chromium", "fp")
    f_ = _rec("9.1", "chromium", "fp", state="fail", findings=[{"scenario": "s1", "step": 3}])
    ok &= check("gate-grade: pass segar cold full -> bukti lulus, reason None",
                mod.has_passing_evidence([p_], False, "fp", T)
                and mod.cell_reason([p_], False, "fp", T, []) is None)
    ok &= check("gate-grade newer-fail: pass lalu fail (fp sama) -> tanpa bukti lulus, reason fail",
                not mod.has_passing_evidence([p_, f_], False, "fp", T)
                and mod.cell_reason([p_, f_], False, "fp", T, []) == "fail")
    ok &= check("failing: cold full conclusive terbaru = fail (segar atau basi)",
                mod.is_failing([p_, f_]) and not mod.is_failing([f_, p_])
                and mod.is_failing([_rec("9.1", "chromium", "old", state="fail", findings=[{}])]))

    # --- warm / partial / not-run: alasan, tak pernah gate-grade, tak menyembunyikan ---
    warm = _rec("9.1", "chromium", "fp", boot="warm")
    part = _rec("9.1", "chromium", "fp", scenario_set="partial")
    nrun = _rec("9.1", "chromium", "fp", state="not-run", conclusive=False,
                reason="fail-fast after 8.1:chromium")
    for name, r, why in (("warm", warm, "warm-only"), ("partial", part, "partial"),
                         ("not-run", nrun, "not-run")):
        ok &= check(f"{name}: reason {why}, tak gate-grade",
                    mod.cell_reason([r], False, "fp", T, []) == why
                    and not mod.is_gate_grade(r, "fp", T))
        ok &= check(f"{name}: tak menyembunyikan gate-grade lulus yang lebih tua",
                    mod.cell_reason([p_, r], False, "fp", T, []) is None)
        ok &= check(f"{name}: tak menyembunyikan gate-grade fail yang lebih tua",
                    not mod.has_passing_evidence([f_, r], False, "fp", T)
                    and mod.is_failing([f_, r]))
    ok &= check("reason inconclusive-steps: pass gate-grade dgn inconclusive tak kosong",
                mod.cell_reason([_rec("9.1", "chromium", "fp", inconclusive=[{"s": 1}])],
                                False, "fp", T, []) == "inconclusive-steps")
    smoke = _rec("9.1", "chromium", "fp", authored_assertions=0)
    ok &= check("reason not-gradeable: authored_assertions 0 (smoke-only)",
                mod.cell_reason([smoke], False, "fp", T, []) == "not-gradeable"
                and mod.is_not_gradeable([smoke], "fp", T, []))
    noted = _rec("9.1", "chromium", "fp", scenario_notes=["a.json: rusak"])
    ok &= check("reason not-gradeable: scenario_notes == notes sekarang",
                mod.cell_reason([noted], False, "fp", T, ["a.json: rusak"]) == "not-gradeable")
    ok &= check("reason scenario-notes: scenario_notes beda dari notes sekarang",
                mod.cell_reason([noted], False, "fp", T, []) == "scenario-notes"
                and not mod.is_not_gradeable([noted], "fp", T, []))
    ok &= check("reason browser-notes: pass gate-grade lain yang tak passing",
                mod.cell_reason([_rec("9.1", "chromium", "fp", browser_notes=["x"])],
                                False, "fp", T, []) == "browser-notes")
    ok &= check("reason inconclusive: record inconclusive segar",
                mod.cell_reason([_rec("9.1", "chromium", "fp", state="inconclusive",
                                      conclusive=False, reason="crash")], False, "fp", T, [])
                == "inconclusive")
    # stale-tag vs stale-source: tanpa record segar, record valid terbaru yang dinilai
    ok &= check("stale-tag: fingerprint cocok, tag beda",
                mod.cell_reason([_rec("9.1", "chromium", "fp", tag="9.1.3-nginx")],
                                False, "fp", T, []) == "stale-tag")
    ok &= check("stale-source: fingerprint beda",
                mod.cell_reason([_rec("9.1", "chromium", "old")], False, "fp", T, []) == "stale-source")
    ok &= check("stale-source menang bila record terbaru fp-nya beda (walau yg lama stale-tag)",
                mod.cell_reason([_rec("9.1", "chromium", "fp", tag="x"),
                                 _rec("9.1", "chromium", "old")], False, "fp", T, [])
                == "stale-source")
    ok &= check("missing: tanpa record", mod.cell_reason([], False, "fp", T, []) == "missing")

    # --- Fresh (contract tests, empat kasus) ------------------------------------------
    def _fresh_case(mutate, reports_inside=False):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            m = _module(root)
            reports = (m / "reports") if reports_inside else (root / "reports")
            fp0 = mod.source_fingerprint(m, reports)
            _seed(reports, m, fp0, ALL6)
            mutate(m, reports)
            fp1 = mod.source_fingerprint(m, reports)
            cells = mod.plan_e2e_cells(reports, m.name, TV, BROWSERS, fp1, tm, [])
            return [c["reason"] for row in cells.values() for c in row.values()]

    def _del(m, _r):
        (m / "index.php").unlink()  # BUKAN file termuda: gerbang mtime takkan melihatnya
    ok &= check("fresh: hapus file yang bukan termuda -> SEMUA sel stale",
                _fresh_case(_del) == ["stale-source"] * 6)
    ok &= check("fresh: sentuh vendor/x -> SEMUA sel stale (vendor ikut fingerprint)",
                _fresh_case(lambda m, _r: os.utime(m / "vendor" / "x.php", (5000, 5000)))
                == ["stale-source"] * 6)

    def _edit_bookkeeping(m, _r):
        (m / ".psm-develop-plan.json").write_text('{"ubah": 1}', encoding="utf-8")
        (m / ".memlog.md").write_text("catatan", encoding="utf-8")
    ok &= check("fresh: sunting .psm-develop-plan.json / .memlog.md -> semua sel tetap segar",
                _fresh_case(_edit_bookkeeping) == [None] * 6)

    def _append_inside(m, reports):
        mod.append_record(mod.history_path(reports, m.name, "9.1", "chromium"),
                          _rec("9.1", "chromium", "zzz", boot="warm"))
    ok &= check("fresh: append histori ke reports dir DI DALAM module -> semua sel tetap segar",
                _fresh_case(_append_inside, reports_inside=True) == [None] * 6)

    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        m = _module(root)
        fp = mod.source_fingerprint(m)
        ok &= check("fingerprint deterministik & hex sha256",
                    fp == mod.source_fingerprint(str(m))
                    and re.fullmatch(r"[0-9a-f]{64}", fp) is not None)
        (m / "index.php").rename(m / "index2.php")
        ok &= check("fingerprint: rename file -> berubah", mod.source_fingerprint(m) != fp)
        fp = mod.source_fingerprint(m)
        (m / ".git").mkdir()
        (m / ".git" / "HEAD").write_text("ref", encoding="utf-8")
        (m / "sub").mkdir()
        (m / "sub" / ".psm-x").write_text("bukan top-level", encoding="utf-8")
        fp_sub = mod.source_fingerprint(m)
        (m / "sub" / ".psm-x").unlink()
        (m / "sub").rmdir()
        ok &= check("fingerprint: .git top-level dikecualikan, .psm-* di sub-folder TIDAK",
                    fp_sub != fp and mod.source_fingerprint(m) == fp)
        os.symlink("/etc", m / "link-keluar")
        ok &= check("fingerprint: symlink dicatat tapi tak diikuti (tak menjelajah /etc)",
                    mod.source_fingerprint(m) != fp)
        (m / "link-keluar").unlink()
        ok &= check("fingerprint: reports dir == akar module -> PlanInputError",
                    _raises(lambda: mod.source_fingerprint(m, m)))
        ok &= check("fingerprint: akar module tak ada -> PlanInputError",
                    _raises(lambda: mod.source_fingerprint(root / "tak-ada")))
        if os.geteuid() != 0:
            locked = m / "kunci"
            locked.mkdir()
            os.chmod(locked, 0)
            try:
                ok &= check("fingerprint: stat/baca error (bukan lenyap) -> PlanInputError sebut path",
                            _raises(lambda: mod.source_fingerprint(m), "kunci"))
            finally:
                os.chmod(locked, 0o755)
        # newest_source_mtime melewati catatan top-level & reports dir di dalam module
        _touch(m / ".psm-develop-plan.json", 9e8)
        _touch(m / ".memlog.md", 9e8)
        _touch(m / "reports" / "mymod-static.json", 9e8)
        nm, where = mod.newest_source_mtime(m, m / "reports")
        ok &= check("newest_source_mtime: lewati .psm-*, .memlog.md, reports dir dalam module",
                    nm == 1000 and where.name == "mymod.php")
        ok &= check("newest_source_mtime: tanpa reports_dir, file laporan dalam module dihitung",
                    mod.newest_source_mtime(m)[0] == 9e8)

    # --- Bentuk plan per sel (CLI) ----------------------------------------------------
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        m = _module(root)
        reports = root / "reports"
        cfg = _cfg(root)
        fp = mod.source_fingerprint(m, reports)

        # Narrowed plan (I/O matrix): config 3x2, tanpa bukti, --versions 9.1 --per-version
        r, plan = _plan(m, reports, "--config", str(cfg), "--versions", "9.1", "--per-version")
        ok &= check("narrowed: exit 0 & source_fingerprint di output",
                    r.returncode == 0 and plan["source_fingerprint"] == fp)
        ok &= check("narrowed: rerun_matrix e2e memuat KEENAM sel (bukan cuma 9.1)",
                    _e2e_matrix(plan) == [(v, b, "missing") for v, b in ALL6])
        ok &= check("narrowed: per_version hanya 9.1, layers.e2e berkunci browser 9.1",
                    list(plan["per_version"]) == ["9.1"]
                    and set(plan["per_version"]["9.1"]["layers"]["e2e"]) == set(BROWSERS)
                    and "e2e" in plan["per_version"]["9.1"]["rerun"])
        ok &= check("narrowed: non-e2e rerun_matrix tetap dibatasi --versions",
                    all(e["version"] == "9.1" for e in plan["rerun_matrix"] if e["layer"] != "e2e"))
        ok &= check("narrowed: entri sel memuat path histori",
                    plan["per_version"]["9.1"]["layers"]["e2e"]["firefox"]["path"]
                    == str(mod.history_path(reports, "mymod", "9.1", "firefox")))

        # Configured-cells test (spec Tasks > tests): 9.1:chromium lulus gate-grade,
        # --versions 9.1 --per-version (tanpa plan --browsers) -> tepat lima sel lainnya.
        _seed(reports, m, fp, [("9.1", "chromium")])
        r, plan = _plan(m, reports, "--config", str(cfg), "--versions", "9.1", "--per-version")
        ok &= check("configured cells: rerun_matrix e2e = tepat lima sel lainnya",
                    [(v, b) for v, b, _ in _e2e_matrix(plan)]
                    == [c for c in ALL6 if c != ("9.1", "chromium")])
        pv91 = plan["per_version"]["9.1"]["layers"]["e2e"]
        ok &= check("configured cells: 9.1:chromium reuse, reason null",
                    pv91["chromium"] == {"reuse": True, "reason": None,
                                         "path": str(mod.history_path(reports, "mymod", "9.1", "chromium"))})
        # per_version[9.1].rerun mencerminkan HANYA sel 9.1
        _seed(reports, m, fp, [("9.1", "firefox")])
        r, plan = _plan(m, reports, "--config", str(cfg), "--versions", "9.1", "--per-version")
        ok &= check("per_version[9.1].rerun tanpa e2e saat kedua sel 9.1 lulus, matriks masih 4 sel",
                    "e2e" not in plan["per_version"]["9.1"]["rerun"]
                    and len(_e2e_matrix(plan)) == 4 and plan["all_reuse"] is False)

        # Chromium-only (I/O matrix): semua chromium lulus -> firefox `missing` di tiga versi
        _seed(reports, m, fp, [("1.7.8", "chromium"), ("8.1", "chromium")])
        r, plan = _plan(m, reports, "--config", str(cfg))
        e2e = plan["layers"]["e2e"]
        ok &= check("chromium-only: kanonik layers.e2e berkunci browser lalu versi",
                    set(e2e) == set(BROWSERS) and list(e2e["chromium"]) == TV)
        ok &= check("chromium-only + 9.1:firefox lulus: firefox `missing` di 1.7.8 & 8.1 saja",
                    [e2e["firefox"][v]["reason"] for v in TV] == ["missing", "missing", None])
        ok &= check("chromium-only: chromium reuse di ketiga versi & e2e di rerun top-level",
                    all(e2e["chromium"][v]["reuse"] for v in TV) and "e2e" in plan["rerun"])

        # Gate-grade newer-fail lewat CLI: pass lalu fail (fp sama) di 9.1:firefox
        mod.append_record(mod.history_path(reports, "mymod", "9.1", "firefox"),
                          _rec("9.1", "firefox", fp, state="fail", findings=[{"x": 1}]))
        r, plan = _plan(m, reports, "--config", str(cfg))
        ok &= check("newer-fail (CLI): 9.1:firefox reason fail",
                    plan["layers"]["e2e"]["firefox"]["9.1"] == {
                        "reuse": False, "reason": "fail",
                        "path": str(mod.history_path(reports, "mymod", "9.1", "firefox"))})

        # stale-tag lewat CLI: tag 9.1 di-bump -> sel 9.1 stale-tag, versi lain tak tersentuh
        r, plan = _plan(m, reports, "--config", str(cfg), "--extra-tag-map", "9.1=9.1.5-nginx")
        ok &= check("stale-tag (CLI): tag-map di-bump -> 9.1:chromium stale-tag, 8.1 tetap reuse",
                    plan["layers"]["e2e"]["chromium"]["9.1"]["reason"] == "stale-tag"
                    and plan["layers"]["e2e"]["chromium"]["8.1"]["reuse"] is True)

        # Chromium-only murni pada histori lain (tanpa 9.1:firefox): firefox missing x3
        rep2 = root / "reports2"
        fp2 = mod.source_fingerprint(m, rep2)
        _seed(rep2, m, fp2, [(v, "chromium") for v in TV])
        r, plan = _plan(m, rep2, "--config", str(cfg), "--versions", "9.1", "--per-version")
        ok &= check("chromium-only: plan menandai firefox `missing` untuk SEMUA tiga versi",
                    _e2e_matrix(plan) == [(v, "firefox", "missing") for v in TV])

        # --versions harus string terkonfigurasi persis; config buruk -> exit 2
        for vs in ("9.1.0", "9.2"):
            r, _ = _plan(m, reports, "--config", str(cfg), "--versions", vs)
            ok &= check(f"--versions {vs} bukan string terkonfigurasi -> exit 2 sebut himpunannya",
                        r.returncode == 2 and "1.7.8, 8.1, 9.1" in r.stderr
                        and "Traceback" not in r.stderr)
        for name, body in (("webkitx", {"psm_e2e_browsers": "webkitx"}),
                           ("9.1+9.1.0", {"psm_target_versions": "9.1,9.1.0"}),
                           ("list kosong", {"psm_target_versions": []}),
                           ("non-dotted", {"psm_target_versions": "9.x"})):
            bad = root / "bad.json"
            bad.write_text(json.dumps(body), encoding="utf-8")
            r, _ = _plan(m, reports, "--config", str(bad), "--versions", "9.1")
            ok &= check(f"bad config ({name}) -> exit 2 tanpa traceback",
                        r.returncode == 2 and "Traceback" not in r.stderr)
        narrow = _cfg(root, versions=["9.1"], browsers=None, name="narrow.json")
        r, plan = _plan(m, reports, "--config", str(narrow))
        ok &= check("config list ['9.1'] + browsers null -> sel 9.1 x default browser",
                    r.returncode == 0 and list(plan["layers"]["e2e"]["chromium"]) == ["9.1"]
                    and set(plan["layers"]["e2e"]) == set(BROWSERS) and plan["versions"] == ["9.1"])

        # History OS error -> exit 2 menyebut path
        rep3 = root / "reports3"
        (mod.history_path(rep3, "mymod", "8.1", "firefox")).mkdir(parents=True)
        r, _ = _plan(m, rep3, "--config", str(cfg))
        ok &= check("history OS error -> exit 2 menyebut path histori",
                    r.returncode == 2 and "mymod-e2e-8.1-firefox.jsonl" in r.stderr
                    and "Traceback" not in r.stderr)
        # reports dir == akar module -> exit 2
        r, _ = _plan(m, m, "--config", str(cfg))
        ok &= check("reports dir == akar module -> exit 2", r.returncode == 2
                    and "Traceback" not in r.stderr)
    return ok


def test_require_config_cli():
    """<reports>/psm-config.json ada tapi --config absen -> exit 2 (tak menyempit diam-diam)."""
    ok = True
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        m = _module(root)
        reports = root / "reports"
        reports.mkdir()
        cfg = _cfg(reports, versions="1.7.6,1.7.8,8.1,9.1")
        r, _out = _plan(m, reports, "--versions", "9.1", "--per-version")
        ok &= check("plan: psm-config.json di reports tanpa --config -> exit 2 menyebut --config",
                    r.returncode == 2 and "--config" in r.stderr)
        r2, out2 = _plan(m, reports, "--versions", "9.1", "--per-version", "--config", str(cfg))
        ok &= check("plan: dgn --config -> 1.7.6 ikut diwajibkan",
                    r2.returncode == 0 and any(e["layer"] == "e2e" and e["version"] == "1.7.6"
                                               for e in out2["rerun_matrix"]))
    return ok


def test_session_cli():
    """--new-session (token, eksklusif) & --session wajib berbentuk [a-z0-9]{16}."""
    ok = True

    def run(*a):
        return subprocess.run(["uv", "run", str(MOD_PATH), *a], capture_output=True, text=True)
    r1, r2 = run("--new-session"), run("--new-session")
    ok &= check("--new-session: exit 0, stdout HANYA token [a-z0-9]{16}",
                r1.returncode == 0 and re.fullmatch(r"[a-z0-9]{16}\n", r1.stdout) is not None)
    ok &= check("--new-session: token acak (dua panggilan beda)", r1.stdout != r2.stdout)
    with tempfile.TemporaryDirectory() as td:
        m = _module(Path(td))
        for extra in ([str(m)], ["--per-version"], ["--session", SESSION],
                      ["--reports-dir", "_bmad-output/psm-validate"]):
            r = run("--new-session", *extra)
            ok &= check(f"--new-session + {extra[0]} -> exit 2", r.returncode == 2 and r.stdout == "")
        rep = Path(td) / "reports"
        for label, sess in (("absen", None), ("huruf besar", "ABCDEFGHIJ012345"),
                            ("15 karakter", "abcdefghij01234"), ("ada '-'", "abcdefgh-j012345")):
            args = [str(m), "--reports-dir", str(rep), "--versions", "9.1"]
            if sess is not None:
                args += ["--session", sess]
            r = run(*args)
            ok &= check(f"plan --session {label} -> exit 2", r.returncode == 2
                        and "--session" in r.stderr and "Traceback" not in r.stderr)
        r = run(str(m), "--reports-dir", str(rep), "--versions", "9.1", "--session", r1.stdout.strip())
        ok &= check("plan dgn token dari --new-session -> exit 0", r.returncode == 0)
    return ok


# --- CAP-1: tier E2E (derive_e2e_step + CLI) --------------------------------------------
CELLS6 = [f"{v}:{b}" for v in TV for b in BROWSERS]
CANARY = "9.1:chromium"
TM = mod.fl.parse_tag_map(None, None)
_CLOCK = [0]
_T0 = datetime(2026, 11, 26, 10, 0, 0, tzinfo=timezone.utc)


def _tr(cell, fp="fp1", job=None, **kw):
    """Record bertimestamp naik (urutan pembuatan) — pass gate-grade passing kecuali di-override."""
    _CLOCK[0] += 1
    ver, b = cell.split(":")
    ts = (_T0 + timedelta(seconds=_CLOCK[0])).isoformat(timespec="microseconds")
    return _rec(ver, b, fp, started_at=ts, job_id=job if job is not None else f"j{_CLOCK[0]}", **kw)


def PASS(cell, fp="fp1", **kw):
    return _tr(cell, fp, **kw)


def FAIL(cell, fp="fp1", scen="s1", **kw):
    kw.setdefault("findings", [{"scenario": scen, "step": 3, "action": "expect_text"}])
    return _tr(cell, fp, state="fail", **kw)


def WPASS(cell, fp="fp1", **kw):
    return _tr(cell, fp, boot="warm", **kw)


def WFAIL(cell, fp="fp1", **kw):
    return FAIL(cell, fp, boot="warm", **kw)


def INC(cell, reason, fp="fp1", **kw):
    """Record inconclusive tanpa engine (crash/no-slots/stopped) seperti ditulis runner."""
    return _tr(cell, fp, state="inconclusive", conclusive=False, reason=reason, boot=None,
               scenario_set=None, install=None, authored_assertions=None, **kw)


def _derive(H, fp="fp1", canary=CANARY, cells=None, sv=None, sb=None, session=SESSION, notes=None):
    cells = cells or CELLS6
    vs = sv if sv is not None else sorted({c.split(":")[0] for c in cells}, key=mod.fl.version_key)
    bs = sb if sb is not None else list(dict.fromkeys(c.split(":")[1] for c in cells))
    return mod.derive_e2e_step(H, cells, canary, vs, bs, fp, TM, session, current_notes=notes)


def _add(H, *recs):
    for r in recs:
        H.setdefault(f"{r['version']}:{r['browser']}", []).append(r)
    return H


def _is(d, step, nxt, **kw):
    """Langkah + e2e_next_cells persis (+ field lain bila disebut)."""
    if d["e2e_step"] != step or d["e2e_next_cells"] != nxt:
        return False
    return all(d[k if k.startswith("e2e_") else "e2e_" + k] == v for k, v in kw.items())


def _ac1_invariant(d):
    """AC 1: sel non-canary di next HANYA bila gate, atau focus/cold-version dan sel itu = /
    se-versi dgn e2e_focus_cell."""
    fver = d["e2e_focus_cell"].split(":")[0]
    for c in d["e2e_next_cells"]:
        if c == CANARY:
            continue
        if d["e2e_step"] == "gate":
            continue
        if d["e2e_step"] in ("focus", "cold-version") and (
                c == d["e2e_focus_cell"] or c.split(":")[0] == fver):
            continue
        return False
    return True


def test_tier_derivation():
    """derive_e2e_step: setiap baris I/O matrix sisi plan, AC 1, langkah & himpunan sel persis."""
    ok = True
    # Fresh module: config 3x2, tanpa histori
    d = _derive({})
    ok &= check("fresh: focus tier 0 [9.1:chromium], full, warm false, recorded false",
                _is(d, "focus", [CANARY], tier=0, scenarios="full", warm=False,
                    focus_cell=CANARY, focus_recorded_failure=False, cells_arg="9.1:chromium",
                    required_cells=[CANARY], blocked_causes={}))
    ok &= check("derive_e2e_step mengembalikan SEMUA field tier",
                set(d) == {"e2e_step", "e2e_tier", "e2e_focus_cell", "e2e_focus_recorded_failure",
                           "e2e_next_cells", "e2e_required_cells", "e2e_cells_arg",
                           "e2e_blocked_causes", "e2e_scenarios", "e2e_warm"})

    # Canary blocking bug: canary cold fail, tanpa record lain
    H = _add({}, FAIL(CANARY))
    d = _derive(H)
    ok &= check("canary blocking bug: focus canary saja, warm true, failed-only",
                _is(d, "focus", [CANARY], tier=0, warm=True, scenarios="failed-only",
                    focus_recorded_failure=True))
    # failed set hanya scenario string tak kosong: null / non-string -> kosong -> full
    d = _derive(_add({}, FAIL(CANARY, findings=[{"scenario": None}, {"scenario": 3},
                                               {"scenario": ""}, "x"])))
    ok &= check("failed set tanpa scenario string -> e2e_scenarios full (warm tetap true)",
                _is(d, "focus", [CANARY], warm=True, scenarios="full"))
    d = _derive(_add({}, FAIL(CANARY, findings=[{"scenario": None}],
                              inconclusive=[{"scenario": "s2"}])))
    ok &= check("failed set memuat inconclusive[].scenario -> failed-only",
                d["e2e_scenarios"] == "failed-only")
    # warm-reset / keeper-start di --session ini -> warm false; di sesi lain tak berpengaruh
    for why in ("warm-reset", "keeper-start"):
        d = _derive(_add({}, FAIL(CANARY), INC(CANARY, why)))
        ok &= check(f"record {why} sesi ini -> e2e_warm false (focus tetap)",
                    _is(d, "focus", [CANARY], warm=False))
        d = _derive(_add({}, FAIL(CANARY), INC(CANARY, why, session="zzzzzzzzzzzzzzzz")))
        ok &= check(f"record {why} sesi lain -> e2e_warm true", d["e2e_warm"] is True)

    # Clean canary: canary lulus gate-grade -> gate tier 1, cells_arg persis
    d = _derive(_add({}, PASS(CANARY)))
    ok &= check("clean canary: gate tier 1, lima sel, cells_arg persis",
                _is(d, "gate", [c for c in CELLS6 if c != CANARY], tier=1, warm=False,
                    scenarios="full", focus_cell=CANARY,
                    cells_arg="1.7.8:chromium+firefox,8.1:chromium+firefox,9.1:firefox"))

    # Loop-back (tier 1 gagal di 8.1:firefox, patch -> fp1)
    def _tier1_base(fail_cells=("8.1:firefox",), fp="fp0"):
        H = _add({}, PASS(CANARY, fp, job="c0"))
        for c in CELLS6:
            if c == CANARY:
                continue
            _add(H, FAIL(c, fp, job="g1") if c in fail_cells else PASS(c, fp, job="g1"))
        return H
    H = _tier1_base()
    d = _derive(H)
    ok &= check("loop-back 1: focus [8.1:firefox] tier 0, warm true, failed-only",
                _is(d, "focus", ["8.1:firefox"], tier=0, focus_cell="8.1:firefox",
                    warm=True, scenarios="failed-only"))
    _add(H, WPASS("8.1:firefox"))
    d = _derive(H)
    ok &= check("loop-back 2: warm pass -> cold-version [8.1 x2], cold full",
                _is(d, "cold-version", ["8.1:chromium", "8.1:firefox"], tier=0, warm=False,
                    scenarios="full", cells_arg="8.1:chromium+firefox"))
    _add(H, PASS("8.1:chromium", job="cv"), PASS("8.1:firefox", job="cv"))
    d = _derive(H)
    ok &= check("loop-back 3: kedua sel 8.1 cold pass -> cold-canary [9.1:chromium]",
                _is(d, "cold-canary", [CANARY], tier=0, focus_cell=CANARY, cells_arg="9.1:chromium"))
    hosted = dict((k, list(v)) for k, v in H.items())
    _add(H, PASS(CANARY, job="cc"))
    d = _derive(H)
    ok &= check("loop-back 4: canary cold pass -> gate [1.7.8 x2, 9.1:firefox]",
                _is(d, "gate", ["1.7.8:chromium", "1.7.8:firefox", "9.1:firefox"], tier=1,
                    cells_arg="1.7.8:chromium+firefox,9.1:firefox"))
    _add(H, *(PASS(c, job="g2") for c in ("1.7.8:chromium", "1.7.8:firefox", "9.1:firefox")))
    d = _derive(H)
    ok &= check("done: next [], cells_arg null, tier null, required []",
                _is(d, "done", [], tier=None, cells_arg=None, required_cells=[],
                    blocked_causes={}, warm=False, scenarios="full"))

    # Hosted in 8.1: loop-back di cold-canary; cakupan default / --versions 8.1
    d = _derive(hosted, sv=["8.1"])
    ok &= check("hosted in 8.1 (--versions 8.1): blocked-by-scope tier 0, required [canary]",
                _is(d, "blocked-by-scope", [], tier=0, required_cells=[CANARY],
                    blocked_causes={CANARY: "out-of-scope"}, cells_arg=None))
    d = _derive(hosted)
    ok &= check("hosted in 8.1 (cakupan default): next [9.1:chromium], bukan blocked-by-scope",
                _is(d, "cold-canary", [CANARY]))

    # Interim loop-back: fix-loop cold full pass -> cold-canary langsung, gate memuat 8.1:chromium
    H = _tier1_base()
    _add(H, PASS("8.1:firefox"))
    d = _derive(H)
    ok &= check("interim loop-back: cold full pass -> cold-canary langsung",
                _is(d, "cold-canary", [CANARY]))
    _add(H, PASS(CANARY))
    d = _derive(H)
    ok &= check("interim loop-back: gate memuat 8.1:chromium (diurut ulang, tak dibuang)",
                _is(d, "gate", ["1.7.8:chromium", "1.7.8:firefox", "8.1:chromium", "9.1:firefox"]))

    # Two failing: satu run tier 1 gagal di 1.7.8:chromium & 8.1:firefox
    def _two():
        H = _add({}, PASS(CANARY, "fp0", job="c0"))
        _add(H, FAIL("8.1:firefox", "fp0", job="g1"))  # started_at lebih awal...
        _add(H, FAIL("1.7.8:chromium", "fp0", job="g1"))  # ...tapi urutan versi menang di run
        for c in ("1.7.8:firefox", "8.1:chromium", "9.1:firefox"):
            _add(H, _tr(c, "fp0", job="g1", state="not-run", conclusive=False,
                        reason="fail-fast after 1.7.8:chromium", boot=None, scenario_set=None))
        return H
    H = _two()
    d = _derive(H)
    ok &= check("two failing: focus 1.7.8:chromium (urutan versi di dalam run)",
                _is(d, "focus", ["1.7.8:chromium"], focus_cell="1.7.8:chromium"))
    _add(H, PASS("1.7.8:chromium"))
    d = _derive(H)
    ok &= check("two failing: lalu focus 8.1:firefox", _is(d, "focus", ["8.1:firefox"]))
    _add(H, PASS("8.1:firefox"))
    d = _derive(H)
    ok &= check("two failing: lalu cold-canary", _is(d, "cold-canary", [CANARY]))
    _add(H, PASS(CANARY))
    d = _derive(H)
    ok &= check("two failing: lalu gate",
                _is(d, "gate", ["1.7.8:firefox", "8.1:chromium", "9.1:firefox"]))
    H = _two()
    _add(H, WPASS("1.7.8:chromium"))
    d = _derive(H)
    ok &= check("two failing: warm pass di 1.7.8:chromium -> cold-version [1.7.8 x2]",
                _is(d, "cold-version", ["1.7.8:chromium", "1.7.8:firefox"]))

    # Focus cell: run terbaru menang atas urutan versi; job_id null = run sendiri; seri lintas run
    H = _add({}, FAIL("1.7.8:chromium", job="A"), FAIL("9.1:firefox", job="B"))
    ok &= check("focus: run terbaru (9.1:firefox) menang atas versi lebih tua di run lama",
                _derive(H)["e2e_focus_cell"] == "9.1:firefox")
    H = _add({}, FAIL("1.7.8:chromium", job=None), FAIL("9.1:firefox", job=None))
    H["1.7.8:chromium"][0]["job_id"] = None
    H["9.1:firefox"][0]["job_id"] = None
    ok &= check("focus: job_id null = run sendiri -> record terbaru saja",
                _derive(H)["e2e_focus_cell"] == "9.1:firefox")
    a, b = FAIL("8.1:firefox", job="A"), FAIL("1.7.8:firefox", job="B")
    b["started_at"] = a["started_at"]
    c = FAIL("9.1:chromium", job="A")
    c["started_at"] = a["started_at"]
    H = _add({}, a, b, c)
    ok &= check("focus: seri started_at lintas run diputus urutan versi -> run B (1.7.8:firefox)",
                _derive(H)["e2e_focus_cell"] == "1.7.8:firefox")

    # Promote order (satu fp): cold fail lalu warm pass / warm pass lalu cold fail
    d = _derive(_add({}, FAIL("8.1:firefox"), WPASS("8.1:firefox")))
    ok &= check("promote: non-canary cold fail -> warm pass = cold-version",
                _is(d, "cold-version", ["8.1:chromium", "8.1:firefox"]))
    d = _derive(_add({}, FAIL(CANARY), WPASS(CANARY)))
    ok &= check("promote: canary cold fail -> warm pass = cold-canary", _is(d, "cold-canary", [CANARY]))
    for cell in (CANARY, "8.1:firefox"):
        d = _derive(_add({}, WPASS(cell), FAIL(cell)))
        ok &= check(f"promote: {cell} warm pass lalu cold fail -> focus, warm false, full",
                    _is(d, "focus", [cell], warm=False, scenarios="full"))
    # partial pass setara warm untuk langkah 5
    d = _derive(_add({}, FAIL("8.1:firefox"), PASS("8.1:firefox", scenario_set="partial")))
    ok &= check("promote: partial pass juga mempromosikan (cold-version)",
                d["e2e_step"] == "cold-version")

    # Diverge (bacaan Budi)
    d = _derive(_add({}, FAIL(CANARY), WPASS(CANARY), FAIL(CANARY)))
    ok &= check("diverge: cold fail, warm pass, cold fail -> focus cold full",
                _is(d, "focus", [CANARY], warm=False, scenarios="full", focus_recorded_failure=True))
    d = _derive(_add({}, FAIL(CANARY), WPASS(CANARY), WFAIL(CANARY)))
    ok &= check("diverge: cold fail, warm pass, warm fail -> focus, warm true",
                _is(d, "focus", [CANARY], warm=True))
    d = _derive(_add({}, FAIL(CANARY), PASS(CANARY, scenario_set="partial"), FAIL(CANARY)))
    ok &= check("diverge: partial pass juga dihitung", d["e2e_warm"] is False)
    d = _derive(_add({}, FAIL(CANARY, "fp0"), WPASS(CANARY, "fp0"), FAIL(CANARY)))
    ok &= check("diverge: pass warm di fingerprint lain tak dihitung -> warm true",
                d["e2e_warm"] is True)

    # Smoke-only: authored_assertions 0 di setiap record
    H = _add({}, PASS(CANARY, authored_assertions=0))
    d = _derive(H)
    ok &= check("smoke-only: gate lima sel sesudah canary",
                _is(d, "gate", [c for c in CELLS6 if c != CANARY], tier=1))
    _add(H, *(PASS(c, authored_assertions=0) for c in CELLS6 if c != CANARY))
    d = _derive(H)
    ok &= check("smoke-only: lalu blocked-not-gradeable, tier null, next []",
                _is(d, "blocked-not-gradeable", [], tier=None, cells_arg=None,
                    required_cells=CELLS6, blocked_causes={c: "not-gradeable" for c in CELLS6}))
    # Ekor rusak + pass smoke-only terakhir: bacaan harfiah kontrak -> tetap not-gradeable
    # (menambal ekor = ubah kontrak, deferred-work CAP-1 r5)
    Hc = {c: list(v) for c, v in H.items()}
    Hc["8.1:firefox"] = (Hc["8.1:firefox"], True)
    d = _derive(Hc)
    ok &= check("corrupt-tail + smoke-only terakhir -> tetap blocked-not-gradeable (harfiah)",
                _is(d, "blocked-not-gradeable", [], tier=None))
    # Review step-04: bentuk input API murni & gerbang bentuk skenario tak crash
    r0 = PASS(CANARY)
    ok &= check("_history_entry: pasangan list [records, True] = (records, corrupt_tail)",
                mod._history_entry([[r0], True]) == ([r0], True))
    try:
        mod._history_entry([[r0], "x"])
        bad = False
    except ValueError:
        bad = True
    ok &= check("_history_entry: isi bukan record -> ValueError", bad)
    try:
        _derive({}, canary="7.0:chromium")
        bad = False
    except ValueError as e:
        bad = "7.0:chromium" in str(e)
    ok &= check("derive_e2e_step: canary di luar cells -> ValueError menyebutnya", bad)
    ok &= check("_scenario_shape_notes: versions list -> [] (tak crash; validate_layer_shape menandai)",
                mod._scenario_shape_notes({"versions": ["x"]}, "9.1") == [])
    # scenario-notes not-gradeable -> blocked-not-gradeable
    notes = ["typo.json: aksi tak dikenal"]
    H = _add({}, *(PASS(c, scenario_notes=notes) for c in CELLS6))
    d = _derive(H, notes=notes)
    ok &= check("scenario-notes == notes sekarang -> blocked-not-gradeable",
                _is(d, "blocked-not-gradeable", [], blocked_causes={c: "not-gradeable" for c in CELLS6}))
    d = _derive(H, notes=[])
    ok &= check("scenario-notes beda dari notes sekarang -> bukan not-gradeable",
                d["e2e_step"] != "blocked-not-gradeable")
    H = _add({}, *(PASS(c) for c in CELLS6 if c != "8.1:firefox"),
             PASS("8.1:firefox", authored_assertions=0))
    d = _derive(H)
    ok &= check("campuran lulus + satu not-gradeable -> blocked-not-gradeable menyebut sel itu saja",
                _is(d, "blocked-not-gradeable", [], required_cells=["8.1:firefox"],
                    blocked_causes={"8.1:firefox": "not-gradeable"}))

    # Clean module
    d = _derive(_add({}, *(PASS(c) for c in CELLS6)))
    ok &= check("clean module: done, tier null, next [], cells_arg null",
                _is(d, "done", [], tier=None, cells_arg=None, focus_cell=CANARY,
                    focus_recorded_failure=False))
    # ekor histori rusak = tanpa bukti lulus
    H = {c: [PASS(c)] for c in CELLS6}
    H[CANARY] = (H[CANARY], True)
    ok &= check("ekor histori rusak di canary -> bukan done/gate",
                _derive(H)["e2e_step"] not in ("done", "gate"))

    # Infra twice (satu sesi, satu fp)
    for name, seq, blocked, cause in (
            ("no-slots,no-slots", ["no-slots", "no-slots"], True, "no-slots"),
            ("no-slots,crash", ["no-slots", "crash"], True, "crash"),
            ("no-slots,stopped,crash", ["no-slots", "stopped", "crash"], True, "crash"),
            ("no-slots,pass,crash", ["no-slots", None, "crash"], False, None)):
        H = {CANARY: [PASS(CANARY) if r is None else INC(CANARY, r) for r in seq]}
        d = _derive(H)
        if blocked:
            ok &= check(f"infra twice {name}: blocked-infra, tier null, cause {cause}",
                        _is(d, "blocked-infra", [], tier=None, required_cells=[CANARY],
                            blocked_causes={CANARY: cause}, cells_arg=None))
        else:
            ok &= check(f"infra twice {name}: tidak blocked", d["e2e_step"] != "blocked-infra")
    d = _derive({CANARY: [INC(CANARY, "no-slots", session="zzzzzzzzzzzzzzzz"),
                          INC(CANARY, "crash")]})
    ok &= check("infra: record sesi lain tak dihitung", d["e2e_step"] != "blocked-infra")
    d = _derive({CANARY: [INC(CANARY, "crash", "fp0"), INC(CANARY, "crash")]})
    ok &= check("infra: record basi tak dihitung", d["e2e_step"] != "blocked-infra")
    d = _derive({"8.1:firefox": [PASS("8.1:firefox", inconclusive=[{"scenario": "s"}]),
                                 PASS("8.1:firefox", browser_notes=["x"])]})
    ok &= check("infra: inconclusive-steps lalu browser-notes -> blocked-infra browser-notes",
                _is(d, "blocked-infra", [], blocked_causes={"8.1:firefox": "browser-notes"}))

    # Scope: --versions 9.1 --browsers chromium di langkah gate
    d = _derive(_add({}, PASS(CANARY)), sv=["9.1"], sb=["chromium"])
    five = [c for c in CELLS6 if c != CANARY]
    ok &= check("scope: blocked-by-scope tier 1, required lima sel, causes out-of-scope",
                _is(d, "blocked-by-scope", [], tier=1, required_cells=five, cells_arg=None,
                    blocked_causes={c: "out-of-scope" for c in five}, warm=False, scenarios="full"))
    d = _derive(_add({}, PASS(CANARY)), sv=["8.1", "9.1"])
    ok &= check("scope sebagian: gate tersaring, causes {} di luar blocked-*",
                _is(d, "gate", ["8.1:chromium", "8.1:firefox", "9.1:firefox"], blocked_causes={},
                    required_cells=five))
    d = _derive(_add({}, FAIL(CANARY)), sv=["8.1"])
    ok &= check("scope menggantikan focus: warm false & full walau focus aslinya warm",
                _is(d, "blocked-by-scope", [], tier=0, warm=False, scenarios="full",
                    focus_recorded_failure=True))

    # Canary-version loop-back: 9.1:firefox gagal -> cold-version [9.1 x2] memenuhi canary
    H = _tier1_base(fail_cells=("9.1:firefox",))
    _add(H, WPASS("9.1:firefox"))
    d = _derive(H)
    ok &= check("canary-version loop-back: cold-version [9.1 x2]",
                _is(d, "cold-version", ["9.1:chromium", "9.1:firefox"]))
    _add(H, PASS("9.1:chromium", job="cv"), PASS("9.1:firefox", job="cv"))
    d = _derive(H)
    ok &= check("canary-version loop-back: lalu gate (cold-canary dilewati)",
                _is(d, "gate", ["1.7.8:chromium", "1.7.8:firefox", "8.1:chromium", "8.1:firefox"]))

    # Canary non-default 8.1:firefox
    d = _derive({}, canary="8.1:firefox")
    ok &= check("canary 8.1:firefox: fresh -> focus [8.1:firefox]",
                _is(d, "focus", ["8.1:firefox"], focus_cell="8.1:firefox"))
    d = _derive(_add({}, PASS("8.1:firefox")), canary="8.1:firefox")
    ok &= check("canary 8.1:firefox lulus -> gate lima sel lain",
                _is(d, "gate", [c for c in CELLS6 if c != "8.1:firefox"],
                    cells_arg="1.7.8:chromium+firefox,8.1:chromium,9.1:chromium+firefox"))

    # Config tanpa chromium: canary default = versi terbaru x browser pertama
    cells_fw = [f"{v}:{b}" for v in TV for b in ("firefox", "webkit")]
    canary_fw = mod.fl.normalize_canary("", TV, ["firefox", "webkit"])
    d = _derive({}, canary=canary_fw, cells=cells_fw)
    ok &= check("config tanpa chromium: canary 9.1:firefox, fresh -> focus [9.1:firefox]",
                canary_fw == "9.1:firefox" and _is(d, "focus", ["9.1:firefox"]))
    d = _derive(_add({}, PASS("9.1:firefox")), canary=canary_fw, cells=cells_fw)
    ok &= check("config tanpa chromium: gate cells_arg ber-browser terkonfigurasi",
                d["e2e_cells_arg"] == "1.7.8:firefox+webkit,8.1:firefox+webkit,9.1:webkit")

    # cells_arg = sintaks --cells ps-run-layer yang sebenarnya
    rl_path = MOD_PATH.parent / "ps-run-layer.py"
    rl_spec = importlib.util.spec_from_file_location("ps_run_layer_t", rl_path)
    rl = importlib.util.module_from_spec(rl_spec)
    rl_spec.loader.exec_module(rl)
    arg = "1.7.8:chromium+firefox,8.1:chromium+firefox,9.1:firefox"
    ok &= check("cells_arg diterima parse_cells ps-run-layer apa adanya",
                rl.parse_cells(arg, TV, BROWSERS)
                == [("1.7.8", BROWSERS), ("8.1", BROWSERS), ("9.1", ["firefox"])])

    # AC 1: invarian atas histori bangkitan (4^6 kombinasi x {dasar, F basi, +warm pass, +warm fail})
    kinds = (None, "pass", "fail", "crash")
    bad, count = [], 0
    for combo in range(4 ** 6):
        H = {}
        n = combo
        t = 0
        for c in CELLS6:
            kind = kinds[n % 4]
            n //= 4
            if kind is None:
                continue
            t += 1
            ver, b = c.split(":")
            ts = (_T0 + timedelta(seconds=t)).isoformat(timespec="microseconds")
            if kind == "crash":
                r = _rec(ver, b, "fp1", started_at=ts, job_id=f"g{t}", state="inconclusive",
                         conclusive=False, reason="crash", boot=None, scenario_set=None,
                         install=None, authored_assertions=None)
            elif kind == "fail":
                r = _rec(ver, b, "fp1", started_at=ts, job_id=f"g{t}", state="fail",
                         findings=[{"scenario": "s1", "step": 1}])
            else:
                r = _rec(ver, b, "fp1", started_at=ts, job_id=f"g{t}")
            H[c] = [r]
        base = _derive(H)
        variants = [base]
        F = base["e2e_focus_cell"]
        ver, b = F.split(":")
        ts = (_T0 + timedelta(seconds=100)).isoformat(timespec="microseconds")
        stale = {k: list(v) for k, v in H.items()}
        stale[F] = [dict(r, source_fingerprint="fp0") for r in stale.get(F, [])]
        variants.append(_derive(stale))
        for st, extra in (("pass", {}), ("fail", {"findings": [{"scenario": "s1", "step": 1}]})):
            Hv = {k: list(v) for k, v in H.items()}
            Hv.setdefault(F, []).append(_rec(ver, b, "fp1", started_at=ts, job_id="w1",
                                             boot="warm", state=st, **extra))
            variants.append(_derive(Hv))
        for d in variants:
            count += 1
            if not _ac1_invariant(d):
                bad.append((combo, d))
    ok &= check(f"AC 1: invarian e2e_next_cells atas {count} derivasi bangkitan"
                f"{'' if not bad else ' — gagal: ' + str(bad[:2])}", not bad and count == 4 ** 6 * 4)
    return ok


def _pv_file(reports, m, layer, ver, payload, mtime=5000):
    p = mod.per_version_path(reports, m.name, layer, ver)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(payload), encoding="utf-8")
    os.utime(p, (mtime, mtime))
    return p


def _phase1_files(reports, m, ver, static_findings=(), scenario_ok=True, flash=None):
    """File per-versi Lapis 1/2/5 yang SEGAR & bercakupan PERSIS ver (phase1_reuse true)."""
    rs = mod.ss.ruleset_provenance([str(mod.ss.DEFAULT_RULES)])
    tag = mod.fl.resolve_tag(TM, ver)
    _pv_file(reports, m, "static", ver, {
        "module": m.name, "main_file_found": True, "ruleset": rs,
        "versions": {ver: {"errors": sum(f["severity"] == "error" for f in static_findings),
                           "warnings": 0, "rules_evaluated": 5,
                           "findings": list(static_findings)}}})
    _pv_file(reports, m, "flashlight", ver, flash or {
        "module": m.name, "status": "skipped", "docker_available": False,
        "versions": {ver: {"tag": tag}}})
    _pv_file(reports, m, "scenario", ver, {"versions": {ver: {
        "tag": tag, "conclusive": True,
        "scenarios": [{"name": "a", "conclusive": True, "ok": scenario_ok,
                       "steps": [{"phase": "then", "ok": scenario_ok, "detail": "d"}]}]}}})


def test_tier_cli():
    """CLI: field tier di kedua mode, --browsers, canary, phase1_reuse, per_version[V].clean."""
    ok = True
    tier_keys = ("e2e_step", "e2e_tier", "e2e_focus_cell", "e2e_focus_recorded_failure",
                 "e2e_next_cells", "e2e_required_cells", "e2e_cells_arg", "e2e_blocked_causes",
                 "e2e_scenarios", "e2e_warm", "phase1_reuse")
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        m = _module(root)
        reports = root / "reports"
        cfg = _cfg(root)
        fp = mod.source_fingerprint(m, reports)

        # Fresh module, kedua mode; AC 2 (rerun_matrix sama dgn/tanpa cakupan sempit)
        r1, pv = _plan(m, reports, "--config", str(cfg), "--per-version")
        r2, canon = _plan(m, reports, "--config", str(cfg))
        r3, narrow = _plan(m, reports, "--config", str(cfg), "--per-version",
                           "--versions", "9.1", "--browsers", "chromium")
        ok &= check("CLI fresh: kedua mode memancarkan semua field tier",
                    r1.returncode == 0 and r2.returncode == 0
                    and all(k in pv and k in canon for k in tier_keys))
        ok &= check("CLI fresh: focus tier 0 [9.1:chromium] sama di kedua mode",
                    all(d["e2e_step"] == "focus" and d["e2e_next_cells"] == [CANARY]
                        and d["e2e_tier"] == 0 and d["e2e_cells_arg"] == CANARY
                        for d in (pv, canon)))
        ok &= check("AC 2: rerun_matrix e2e enam sel sama dgn & tanpa --versions 9.1 --browsers chromium",
                    r3.returncode == 0 and _e2e_matrix(pv) == _e2e_matrix(narrow)
                    and len(_e2e_matrix(pv)) == 6)
        ok &= check("CLI fresh: phase1_reuse false (tanpa file lapis) di kedua mode; clean false",
                    pv["phase1_reuse"] is False and canon["phase1_reuse"] is False
                    and all(e["phase1_reuse"] is False and e["clean"] is False
                            for e in pv["per_version"].values()))
        ok &= check("CLI kanonik: tanpa per_version (phase1_reuse/clean hanya per-versi)",
                    "per_version" not in canon)

        # Clean canary via histori nyata
        _seed(reports, m, fp, [("9.1", "chromium")])
        r, plan = _plan(m, reports, "--config", str(cfg), "--per-version")
        ok &= check("CLI clean canary: gate tier 1, cells_arg persis",
                    plan["e2e_step"] == "gate" and plan["e2e_tier"] == 1
                    and plan["e2e_cells_arg"]
                    == "1.7.8:chromium+firefox,8.1:chromium+firefox,9.1:firefox")
        r, plan = _plan(m, reports, "--config", str(cfg), "--per-version",
                        "--versions", "9.1", "--browsers", "chromium")
        ok &= check("CLI scope: blocked-by-scope tier 1, required lima sel",
                    plan["e2e_step"] == "blocked-by-scope" and plan["e2e_tier"] == 1
                    and plan["e2e_required_cells"] == [c for c in CELLS6 if c != CANARY]
                    and set(plan["e2e_blocked_causes"].values()) == {"out-of-scope"})
        # --versions eksplisit = default skrip tetap cakupan (menang atas config 9.1 saja)
        cfg91 = _cfg(root, versions="9.1", name="v91.json")
        r, _o = _plan(m, reports, "--config", str(cfg91), "--versions", "1.7.8,8.1,9.1")
        ok &= check("--versions eksplisit = default skrip menang atas config (lalu exit 2 di luar himpunan)",
                    r.returncode == 2 and "1.7.8" in r.stderr)
        # --browsers eksplisit chromium,firefox menang atas config psm_e2e_browsers chromium
        cfgc = _cfg(root, browsers="chromium", name="chrome.json")
        r, _o = _plan(m, reports, "--config", str(cfgc), "--browsers", "chromium,firefox")
        ok &= check("--browsers chromium,firefox eksplisit menang atas config chromium "
                    "(dinilai apa adanya: firefox di luar himpunan -> exit 2)",
                    r.returncode == 2 and "firefox" in r.stderr and "--browsers" in r.stderr)
        r, o = _plan(m, reports, "--config", str(cfgc))
        ok &= check("tanpa --browsers: cakupan dari config (chromium) -> exit 0",
                    r.returncode == 0 and o["e2e_focus_cell"] == CANARY)
        for bad in ("safari", "", "webkit"):
            r, _o = _plan(m, reports, "--config", str(cfg), "--browsers", bad)
            ok &= check(f"--browsers {bad!r} -> exit 2 tanpa traceback",
                        r.returncode == 2 and "Traceback" not in r.stderr)
        r, o = _plan(m, reports, "--config", str(cfg), "--browsers", " Firefox ")
        ok &= check("--browsers dinormalisasi seperti psm_e2e_browsers (strip + huruf kecil)",
                    r.returncode == 0 and o["e2e_step"] == "gate"
                    and o["e2e_next_cells"] == ["1.7.8:firefox", "8.1:firefox", "9.1:firefox"])

        # Canary: tabel bentuk (exit 2 menyebut key), non-default, config tanpa chromium
        def _canary_cfg(val, **extra):
            body = {"psm_target_versions": "1.7.8,8.1,9.1", "psm_e2e_browsers": "chromium,firefox",
                    "psm_e2e_canary": val, **extra}
            p = root / "canary.json"
            p.write_text(json.dumps(body), encoding="utf-8")
            return p
        r, o = _plan(m, reports, "--config", str(_canary_cfg(" 9.1 : Chromium ")))
        ok &= check("canary ' 9.1 : Chromium ' sah -> 9.1:chromium",
                    r.returncode == 0 and o["e2e_focus_cell"] == CANARY)
        for val in ("9.1", "9.1:chromium:x", ":chromium", "9.1:", "7.0:chromium", "9.1:webkit",
                    9.1, ["9.1:chromium"]):
            r, _o = _plan(m, reports, "--config", str(_canary_cfg(val)))
            ok &= check(f"canary {val!r} -> exit 2 menyebut psm_e2e_canary",
                        r.returncode == 2 and "psm_e2e_canary" in r.stderr
                        and "Traceback" not in r.stderr)
        r, _o = _plan(m, reports, "--config",
                      str(_canary_cfg("9.1:webkit", psm_e2e_enabled="false")))
        ok &= check("canary buruk tetap exit 2 walau psm_e2e_enabled false",
                    r.returncode == 2 and "psm_e2e_canary" in r.stderr)
        for val in (None, ""):
            r, o = _plan(m, reports, "--config", str(_canary_cfg(val)))
            ok &= check(f"canary {val!r} -> default 9.1:chromium",
                        r.returncode == 0 and o["e2e_focus_cell"] == CANARY)
        r, o = _plan(m, reports, "--config", str(_canary_cfg("8.1:firefox")), "--per-version")
        ok &= check("canary non-default 8.1:firefox: focus 8.1:firefox",
                    o["e2e_step"] == "focus" and o["e2e_next_cells"] == ["8.1:firefox"])
        nochrome = _cfg(root, browsers="firefox,webkit", name="nochrome.json")
        r, o = _plan(m, reports, "--config", str(nochrome))
        ok &= check("config tanpa chromium: canary default 9.1:firefox",
                    r.returncode == 0 and o["e2e_focus_cell"] == "9.1:firefox"
                    and o["e2e_next_cells"] == ["9.1:firefox"])

    # phase1_reuse & per_version[V].clean (file Lapis 1/2/5 per-versi)
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        m = _module(root)
        reports = root / "reports"
        cfg = _cfg(root)
        err = {"id": "eval", "severity": "error", "message": "eval()", "occurrences": []}
        warn = {"id": "w", "severity": "warning", "message": "hati-hati", "occurrences": []}
        _phase1_files(reports, m, "9.1", static_findings=[warn])
        _phase1_files(reports, m, "8.1", static_findings=[err])
        r, plan = _plan(m, reports, "--config", str(cfg), "--per-version", "--versions", "8.1,9.1")
        pv = plan["per_version"] if plan else {}
        ok &= check("clean true: phase1_reuse V & tanpa temuan error (warning tak memblok)",
                    r.returncode == 0 and pv["9.1"]["phase1_reuse"] is True
                    and pv["9.1"]["clean"] is True)
        ok &= check("clean false: temuan static severity error",
                    pv["8.1"]["phase1_reuse"] is True and pv["8.1"]["clean"] is False)
        ok &= check("phase1_reuse top-level = AND atas --versions",
                    plan["phase1_reuse"] is True)
        r, plan = _plan(m, reports, "--config", str(cfg), "--per-version")
        ok &= check("phase1_reuse top-level false bila satu versi (1.7.8) belum punya file",
                    plan["phase1_reuse"] is False and plan["per_version"]["1.7.8"]["clean"] is False)
        _phase1_files(reports, m, "8.1", scenario_ok=False)
        r, plan = _plan(m, reports, "--config", str(cfg), "--per-version", "--versions", "8.1")
        ok &= check("clean false: skenario Lapis 5 gagal (temuan error)",
                    plan["per_version"]["8.1"]["clean"] is False)
        r, plan = _plan(m, reports, "--config", str(cfg), "--versions", "8.1,9.1")
        ok &= check("kanonik: phase1_reuse = tanpa lapis selain e2e/adversarial di rerun",
                    plan["phase1_reuse"] is (not [l for l in plan["rerun"]
                                                  if l not in ("e2e", "adversarial")]))
        # file rusak -> exit 2 menyebut path
        _phase1_files(reports, m, "8.1", static_findings=[{"id": "x", "severity": "error"}])
        r, _o = _plan(m, reports, "--config", str(cfg), "--per-version", "--versions", "8.1")
        ok &= check("clean: static tanpa 'message' -> exit 2 menyebut file",
                    r.returncode == 2 and "mymod-static-8.1.json" in r.stderr
                    and "Traceback" not in r.stderr)
        _phase1_files(reports, m, "8.1")
        p = mod.per_version_path(reports, m.name, "scenario", "8.1")
        body = json.loads(p.read_text())
        body["versions"]["8.1"]["scenarios"] = {"a": 1}
        _pv_file(reports, m, "scenario", "8.1", body)
        r, _o = _plan(m, reports, "--config", str(cfg), "--per-version", "--versions", "8.1")
        ok &= check("clean: scenarios bukan list objek -> exit 2 menyebut file",
                    r.returncode == 2 and "mymod-scenario-8.1.json" in r.stderr)
        body["versions"]["8.1"]["scenarios"] = [{"name": "a", "steps": "bukan-list"}]
        _pv_file(reports, m, "scenario", "8.1", body)
        r, _o = _plan(m, reports, "--config", str(cfg), "--per-version", "--versions", "8.1")
        ok &= check("clean: steps bukan list objek -> exit 2 menyebut file",
                    r.returncode == 2 and "mymod-scenario-8.1.json" in r.stderr)
        # phase1_reuse false -> clean false TANPA memuat file (skenario rusak tak menyalakan exit 2)
        mod.per_version_path(reports, m.name, "static", "8.1").unlink()
        r, plan = _plan(m, reports, "--config", str(cfg), "--per-version", "--versions", "8.1")
        ok &= check("phase1_reuse false -> clean false tanpa memuat file Lapis 1/2/5",
                    r.returncode == 0 and plan["per_version"]["8.1"]["phase1_reuse"] is False
                    and plan["per_version"]["8.1"]["clean"] is False)
    return ok


def _raises(fn, needle=None):
    try:
        fn()
    except mod.PlanInputError as e:
        return needle is None or needle in str(e)
    return False


def main():
    ok = True
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        mdir = root / "mymod"
        reports = root / "reports"

        # source module: file termuda pada t=1000
        _touch(mdir / "mymod.php", 1000)
        _touch(mdir / "index.php", 900)
        # vendor/ diabaikan walau jauh lebih baru (bukan source yang kita vonis)
        _touch(mdir / "vendor" / "lib" / "big.php", 9000)

        # REGRESI: match path ABSOLUT dulu membuang seluruh module yang kebetulan
        # berada di bawah ancestor bernama vendor/ -> mtime 0.0 -> file lapis 1970
        # dianggap SEGAR = vonis atas bukti basi (bencana yang skrip ini cegah).
        under = root / "vendor" / "acme" / "shop" / "mymod"
        _touch(under / "mymod.php", 1000)
        nm_under, _ = mod.newest_source_mtime(under)
        ok &= check("module di bawah ancestor vendor/ -> mtime NYATA, bukan 0.0", nm_under == 1000)

        newest, where = mod.newest_source_mtime(mdir)
        ok &= check("newest_source_mtime abaikan vendor/ (1000, bukan 9000)", newest == 1000)
        ok &= check("newest_source_mtime sebut file-nya", where is not None and where.name == "mymod.php")

        # lapis LEBIH BARU + cakupan penuh -> reuse
        _layer(reports / "mymod-static.json", TV, 2000)
        p = mod.plan_layer(reports / "mymod-static.json", TV, newest, "mymod.php")
        ok &= check("lapis lebih baru + cakupan cocok -> reuse", p["reuse"] is True)

        # lapis BASI (module berubah setelahnya) -> rerun (anti vonis atas bukti basi)
        _layer(reports / "mymod-flashlight.json", TV, 500)
        p = mod.plan_layer(reports / "mymod-flashlight.json", TV, newest, "mymod.php")
        ok &= check("lapis lebih tua dari module -> rerun", p["reuse"] is False and "lebih baru" in p["reason"])
        ok &= check("alasan basi sebut file source pemicunya", "mymod.php" in p["reason"])

        # cakupan KURANG -> rerun
        _layer(reports / "mymod-e2e.json", ["9.1"], 2000)
        p = mod.plan_layer(reports / "mymod-e2e.json", TV, newest, None)
        ok &= check("cakupan versi kurang -> rerun", p["reuse"] is False and "cakupan kurang" in p["reason"])
        ok &= check("alasan cakupan sebut versi yang hilang", "1.7.8" in p["reason"] and "8.1" in p["reason"])
        # cakupan LEBIH luas tetap boleh (superset memuat yang diminta)
        _layer(reports / "mymod-wide.json", TV + ["9.2"], 2000)
        p = mod.plan_layer(reports / "mymod-wide.json", TV, newest, None)
        ok &= check("cakupan superset -> tetap reuse", p["reuse"] is True)

        # ABSEN / RUSAK -> rerun
        p = mod.plan_layer(reports / "tak-ada.json", TV, newest, None)
        ok &= check("file lapis absen -> rerun", p["reuse"] is False and "belum ada" in p["reason"])
        broken = reports / "mymod-broken.json"
        broken.write_text("{bukan json", encoding="utf-8")
        os.utime(broken, (2000, 2000))
        p = mod.plan_layer(broken, TV, newest, None)
        ok &= check("file lapis rusak -> rerun (tak crash)", p["reuse"] is False and "tak terbaca" in p["reason"])

        # cakupan tak bisa dipastikan (bentuk adversarial) -> rerun, bukan tebakan
        adv = reports / "mymod-adversarial.json"
        adv.write_text(json.dumps({"findings": []}), encoding="utf-8")
        os.utime(adv, (2000, 2000))
        p = mod.plan_layer(adv, TV, newest, None)
        ok &= check("cakupan tak bisa dipastikan -> rerun", p["reuse"] is False and "tak bisa dipastikan" in p["reason"])
        ok &= check("layer_versions bentuk tak dikenal -> None", mod.layer_versions({"x": 1}) is None)
        ok &= check("layer_versions dari dict versions -> set", mod.layer_versions(
            {"versions": {"9.1": {}}}) == {"9.1"})
        # Lapis adversarial menyatakan cakupan yang DITINJAU di top-level `versions`
        ok &= check("layer_versions dari list versions (adversarial) -> set",
                    mod.layer_versions({"versions": ["1.7.8", "8.1"], "findings": []}) == {"1.7.8", "8.1"})
        ok &= check("cakupan TAK diturunkan dari findings (versi terpengaruh != yang ditinjau)",
                    mod.layer_versions({"findings": [{"versions": ["8.1"]}]}) is None)
        adv_fresh = reports / "mymod-adversarial.json"
        adv_fresh.write_text(json.dumps({"versions": TV, "findings": []}), encoding="utf-8")
        os.utime(adv_fresh, (2000, 2000))
        pa = mod.plan_layer(adv_fresh, TV, newest, None)
        ok &= check("lapis adversarial segar + cakupan dinyatakan -> reuse (lapis termahal tak diulang)",
                    pa["reuse"] is True)

    # --- determinism-3 (analyze 2026-07-17-1024): vonis Lapis 1 punya DUA input (module
    # DAN ruleset) tapi kesegaran cuma men-stat yang pertama. Aturan KB yang baru
    # ditambahkan lalu tak pernah menyala: file lapis basi dipakai ulang & melapor pass,
    # sementara SKILL.md melarang model membackstop-nya.
    with tempfile.TemporaryDirectory() as td:
        t = Path(td)
        mod_dir = t / "mymod"
        mod_dir.mkdir()
        (mod_dir / "mymod.php").write_text("<?php class MyMod extends Module {}")
        rules = t / "ps-rules.json"
        rules.write_text('{"removed_hooks": []}')
        extra = t / "extra.json"
        extra.write_text('{"removed_hooks": []}')
        layer = t / "mymod-static.json"

        def _write_layer(ruleset_files, ruleset_mtime):
            layer.write_text(json.dumps({
                "module": "mymod", "versions": {v: {"pass": True} for v in TV},
                "ruleset": {"files": [str(p.resolve()) for p in ruleset_files],
                            "mtime": ruleset_mtime}}))
            os.utime(layer, (9e9, 9e9))  # jauh lebih baru dari source: isolasi cek ruleset

        base_state = mod.ss.ruleset_provenance([str(rules)])
        _write_layer([rules], base_state["mtime"])
        r = mod.plan_layer(layer, TV, 0.0, None, provenance={"kind": "ruleset", **base_state})
        ok &= check("ruleset sama & tak berubah -> reuse", r["reuse"] is True)

        with_extra = mod.ss.ruleset_provenance([str(rules), str(extra)])
        r = mod.plan_layer(layer, TV, 0.0, None, provenance={"kind": "ruleset", **with_extra})
        ok &= check("aturan KB BARU ditambahkan -> rerun (dulu: reuse, aturan tak pernah menyala)",
                    r["reuse"] is False and "ruleset berbeda" in r["reason"])

        os.utime(rules, (9e9 + 100, 9e9 + 100))  # ruleset inti disunting sesudah file lapis
        r = mod.plan_layer(layer, TV, 0.0, None, provenance={"kind": "ruleset", **mod.ss.ruleset_provenance([str(rules)])})
        ok &= check("ruleset inti lebih baru dari file lapis -> rerun",
                    r["reuse"] is False and "lebih baru" in r["reason"])

        _write_layer([rules], base_state["mtime"])
        stale = json.loads(layer.read_text())
        del stale["ruleset"]
        layer.write_text(json.dumps(stale))
        os.utime(layer, (9e9, 9e9))
        r = mod.plan_layer(layer, TV, 0.0, None, provenance={"kind": "ruleset", **base_state})
        ok &= check("file lapis tanpa jejak ruleset -> rerun (tak bisa dipastikan, jangan tebak)",
                    r["reuse"] is False and "tak mencatat ruleset" in r["reason"])
        r = mod.plan_layer(layer, TV, 0.0, None, provenance=None)
        ok &= check("lapis non-static tak dinilai atas ruleset (ruleset tak memproduksinya)",
                    r["reuse"] is True)

        # --- enhancement-1: spec E2E authored — satu-satunya input tulisan tangan —
        # divalidasi di pra-pass, sebelum satu container pun boot.
        e2e_dir = mod_dir / "tests" / "e2e"
        e2e_dir.mkdir(parents=True)
        (e2e_dir / "ok.json").write_text(json.dumps(
            {"name": "ok", "steps": [{"action": "goto", "area": "fo", "path": "/"},
                                     {"action": "expect_visible", "selector": "#blk"}]}))
        (e2e_dir / "typo.json").write_text(json.dumps(
            {"name": "bad", "steps": [{"action": "expect_visable", "selector": "#x"}]}))
        # Jalur CLI: unit test memanggil plan_layer LANGSUNG, jadi wiring main() ->
        # plan_layer(ruleset=...) tak tersentuh — persis mode "jalur CLI tanpa coverage"
        # yang bikin test hijau di atas kode salah. Diuji lewat proses nyata.
        reports = t / "reports"
        reports.mkdir()
        real_static = Path(mod.ss.DEFAULT_RULES)
        subprocess.run(["uv", "run", str(Path(MOD_PATH).parent / "ps-static-scan.py"),
                        str(mod_dir), "--versions", "9.1",
                        "-o", str(reports / "mymod-static.json")],
                       capture_output=True, text=True)

        def _plan_cli(*extra):
            r = subprocess.run(["uv", "run", str(MOD_PATH), str(mod_dir),
                                "--reports-dir", str(reports), "--versions", "9.1",
                                "--session", SESSION, *extra],
                               capture_output=True, text=True)
            return json.loads(r.stdout)

        ok &= check("CLI: ruleset sama -> static boleh reuse",
                    _plan_cli()["layers"]["static"]["reuse"] is True and real_static.is_file())
        ok &= check("CLI: --extra-rules diteruskan -> static rerun (wiring main() teruji)",
                    _plan_cli("--extra-rules", str(extra))["layers"]["static"]["reuse"] is False)

        notes = mod._e2e_scenario_notes(mod_dir)
        ok &= check("pra-pass menandai spec rusak SEBELUM container boot",
                    len(notes) == 1 and "typo.json" in notes[0])
        ok &= check("catatan menyebut kosakata yang SAH, bukan cuma yang salah",
                    "expect_visible" in notes[0] and "goto" in notes[0])
        # enh-5 (ronde-6): e2e_scenarios (daftar sumber) DIHAPUS — echo nama file nol pembaca,
        # cakupan authored dipikul e2e_smoke_only. Hanya e2e_scenario_notes (spec DILEWATI, ada
        # penerima: rutekan SKILL.md + gerbang) yang tersisa. Emisi main() diuji proses nyata —
        # wiring ke JSON dulu NOL coverage (seluruh output pra-pass bisa dihapus tanpa test merah).
        plan = _plan_cli()
        # CAP-1: nama `e2e_scenarios` kini field tier (`full`|`failed-only`), bukan echo daftar file.
        ok &= check("CLI: e2e_scenarios = field tier (full|failed-only), bukan echo daftar sumber",
                    plan.get("e2e_scenarios") in ("full", "failed-only"))
        ok &= check("CLI: e2e_scenario_notes sampai ke JSON pra-pass",
                    len(plan.get("e2e_scenario_notes") or []) == 1
                    and "typo.json" in plan["e2e_scenario_notes"][0])
        # Spec yang tak menegakkan apa pun ketahuan di PRA-PASS — sebelum flashlight boot
        # x N versi x M browser. Dulu penulisnya baru tahu sesudah run termahal selesai.
        (e2e_dir / "hampa.json").write_text(json.dumps(
            {"name": "hampa", "steps": [{"action": "screenshot"}]}))
        plan2 = _plan_cli()
        ok &= check("CLI pra-pass menandai spec tanpa expect_* SEBELUM container boot",
                    any("hampa.json" in n and "tak menegakkan apa pun" in n
                        for n in (plan2.get("e2e_scenario_notes") or [])))

    # --- enhancement-1 (analyze ronde-5): vonis Lapis 2/4 juga punya DUA input — module DAN
    # image core-nya. Keduanya SUDAH mencatat tag yang memproduksinya; gerbang kesegaran tak
    # pernah membacanya, jadi tag-map yang di-bump (9.0->9.1, nightly->9.1.4-nginx: pernah
    # terjadi sungguhan) membuat file lapis lama dipakai ulang & dinyatakan "cakupan cocok"
    # padahal ia memvonis core yang BERBEDA. Fix ruleset-provenance ronde lalu berhenti di
    # Lapis 1 padahal docstring-nya sendiri menalar untuk kedua lapis ini.
    with tempfile.TemporaryDirectory() as td8:
        t8 = Path(td8)
        m8 = t8 / "mymod"
        _touch(m8 / "mymod.php", 1000)
        lay = t8 / "mymod-flashlight.json"
        lay.write_text(json.dumps({"module": "mymod", "versions": {
            "9.1": {"version": "9.1", "tag": "9.1.4-nginx", "image": "x:9.1.4-nginx",
                    "pass": True}}}))
        os.utime(lay, (9e9, 9e9))
        same = {"kind": "image", "expect": {"9.1": "9.1.4-nginx"}}
        bumped = {"kind": "image", "expect": {"9.1": "9.1.5-nginx"}}
        ok &= check("image sama -> reuse (gerbang tak kelebihan sapu)",
                    mod.plan_layer(lay, ["9.1"], 1000, None, provenance=same)["reuse"] is True)
        r_bump = mod.plan_layer(lay, ["9.1"], 1000, None, provenance=bumped)
        ok &= check("tag-map di-bump -> rerun (dulu: reuse 'cakupan versi cocok' atas core LAIN)",
                    r_bump["reuse"] is False and "image berbeda" in r_bump["reason"])
        ok &= check("alasan sebut tag lama & baru supaya operator paham",
                    "9.1.4-nginx" in r_bump["reason"] and "9.1.5-nginx" in r_bump["reason"])
        lay_notag = t8 / "mymod-e2e.json"
        lay_notag.write_text(json.dumps({"versions": {"9.1": {"pass": True}}}))
        os.utime(lay_notag, (9e9, 9e9))
        # Assert ke ALASANnya, bukan cuma reuse=False: tanpa gerbang ini hasilnya tetap False
        # lewat cabang "image berbeda" (None != tag), jadi cek reuse saja lolos senyap —
        # dan pesannya jadi salah ("image berbeda (9.1: None vs ...)") padahal file lapisnya
        # cuma tak mencatat apa-apa. Kubuktikan lewat mutasi.
        r_notag = mod.plan_layer(lay_notag, ["9.1"], 1000, None, provenance=same)
        ok &= check("file lapis tak mencatat tag -> rerun beralasan BENAR (bukan 'image berbeda')",
                    r_notag["reuse"] is False and "tak mencatat tag" in r_notag["reason"])
        # Satu pemilik: tag yang diharapkan diresolve lewat ps-flashlight-run, bukan disalin.
        # Ekspresinya sempat ada di DUA main(); implementasi ketiga di sini akan mendrift.
        ok &= check("resolve_tag dipakai dari pemiliknya (bentuk penuh & dipendekkan)",
                    mod.fl.resolve_tag({"9.1": "9.1.4-nginx"}, "9.1") == "9.1.4-nginx"
                    and mod.fl.resolve_tag({"8.1": "8.1.6-nginx"}, "8.1.6") == "8.1.6-nginx")
        # CLI: wiring main() -> plan_layer(provenance=image) — jalur yang unit test lewati.
        r_cli = subprocess.run(["uv", "run", str(MOD_PATH), str(m8), "--reports-dir", str(t8),
                                "--versions", "9.1", "--extra-tag-map", "9.1=9.1.5-nginx",
                                "--session", SESSION],
                               capture_output=True, text=True)
        plan_cli = json.loads(r_cli.stdout)
        ok &= check("CLI: --extra-tag-map sampai ke gerbang reuse Lapis 2 (wiring, bukan cuma fungsi)",
                    "flashlight" in (plan_cli.get("rerun") or [])
                    and "image berbeda" in plan_cli["layers"]["flashlight"]["reason"])

    # Refutasi verifier atas fix ronde-5: gerbang himpunan kosong ditutup di ps-aggregate,
    # lalu kelasnya selamat SATU SEAM di sini — di skrip yang justru bertugas MENOLAK bukti
    # basi. `set() - covered` kosong = "cakupan cocok" secara vakum, jadi file lapis yang
    # meninjau versi yang sama sekali lain dinyatakan boleh dipakai ulang, dengan alasan
    # tertulis "cakupan versi cocok".
    with tempfile.TemporaryDirectory() as td7:
        root7 = Path(td7)
        m7 = root7 / "mymod"
        _touch(m7 / "mymod.php", 1000)
        rep7 = root7 / "reports"
        _layer(rep7 / "mymod-adversarial.json", ["9.9"], 5000)  # meninjau versi LAIN
        p = mod.plan_layer(rep7 / "mymod-adversarial.json", [], 1000, "mymod.php")
        ok &= check("nol versi diminta -> file lapis versi lain TAK boleh dipakai ulang "
                    "(dulu: reuse=True 'cakupan versi cocok')",
                    p["reuse"] is False and "nol versi" in p["reason"])
        p_ok = mod.plan_layer(rep7 / "mymod-adversarial.json", ["9.9"], 1000, "mymod.php")
        ok &= check("cakupan diminta & tercakup -> reuse tetap jalan (gerbang tak kelebihan sapu)",
                    p_ok["reuse"] is True)
        r7 = subprocess.run(["uv", "run", str(MOD_PATH), str(m7), "--reports-dir", str(rep7),
                             "--versions", " , ", "--session", SESSION],
                            capture_output=True, text=True)
        ok &= check("CLI: --versions yang menyusut jadi kosong -> exit 2, bukan pra-pass vakum",
                    r7.returncode == 2 and "nol versi" in r7.stderr
                    and "Traceback" not in r7.stderr)
        # customization-3: --reports-dir ber-token {project-root} = leak yang direproduksi
        # (dulu exit 0, path lapis harfiah, 'file belum ada' percaya diri -> rerun semua).
        r_tok = subprocess.run(["uv", "run", str(MOD_PATH), str(m7),
                                "--reports-dir", "{project-root}/_bmad-output/psm-validate",
                                "--versions", "9.1", "--session", SESSION],
                               capture_output=True, text=True)
        ok &= check("CLI: --reports-dir ber-token {project-root} -> exit 2 (bukan exit 0 path harfiah)",
                    r_tok.returncode == 2 and "belum diresolve di --reports-dir" in r_tok.stderr
                    and "Traceback" not in r_tok.stderr)
        # kontrol positif: --reports-dir bersih (belum ada) -> pra-pass jalan, rerun semua
        r_clean = subprocess.run(["uv", "run", str(MOD_PATH), str(m7), "--reports-dir", str(rep7 / "fresh"),
                                  "--versions", "9.1", "--session", SESSION],
                                 capture_output=True, text=True)
        ok &= check("CLI: --reports-dir bersih tetap jalan (gerbang token tak kelebihan sapu)",
                    r_clean.returncode == 0)

    # --- MODE PER-VERSI (siklus konvergensi version-first) ---------------------------------
    # Inti: tiap versi divonis SENDIRI. File per-versi 9.1 yang basi tak menyeret file 8.1 yang
    # segar ke rerun — yang justru mustahil dengan file kanonik satu-untuk-semua-versi (satu
    # patch source membasikan semuanya serentak). Ini BUKTI SELESAI dari spec.
    with tempfile.TemporaryDirectory() as tdpv:
        root = Path(tdpv)
        mdir = root / "mymod"
        reports = root / "reports"
        _touch(mdir / "mymod.php", 1000)  # source termuda t=1000
        newest, _ = mod.newest_source_mtime(mdir)
        tag_map = mod.fl.parse_tag_map(None, None)
        ruleset = mod.ss.ruleset_provenance([str(mod.ss.DEFAULT_RULES)])
        # Lapis e2e kini dinilai per SEL dari histori (plan_e2e_cells), bukan file per-versi.
        fp = mod.source_fingerprint(mdir, reports)
        cells = mod.plan_e2e_cells(reports, "mymod", TV, ["chromium", "firefox"], fp, tag_map, [])

        def _pv(layer, ver, mtime, versions_in_file=None):
            p = mod.per_version_path(reports, "mymod", layer, ver)
            p.parent.mkdir(parents=True, exist_ok=True)
            vs = versions_in_file if versions_in_file is not None else [ver]

            def _entry(v):
                e = {"pass": True}
                if layer in ("flashlight", "scenario"):
                    e["tag"] = mod.fl.resolve_tag(tag_map, v)
                return e
            p.write_text(json.dumps({"versions": {v: _entry(v) for v in vs}}), encoding="utf-8")
            os.utime(p, (mtime, mtime))
            return p

        # BUKTI SELESAI: 9.1 dibasikan di level FILE (mtime < source), 8.1 tetap segar.
        _pv("flashlight", "8.1", 2000)  # segar
        _pv("flashlight", "9.1", 500)   # basi (lebih tua dari source t=1000)
        pv = mod.plan_per_version(reports, "mymod", ["8.1", "9.1"], newest, "mymod.php",
                                  ruleset, tag_map, e2e_cells=cells)
        ok &= check("per-versi: file 8.1 segar -> reuse (tak diseret kebasian 9.1)",
                    pv["8.1"]["layers"]["flashlight"]["reuse"] is True
                    and "flashlight" not in pv["8.1"]["rerun"])
        ok &= check("per-versi: file 9.1 basi -> rerun HANYA 9.1 (granularitas per-versi)",
                    pv["9.1"]["layers"]["flashlight"]["reuse"] is False
                    and "flashlight" in pv["9.1"]["rerun"]
                    and "module lebih baru" in pv["9.1"]["layers"]["flashlight"]["reason"])
        # File per-versi absen -> rerun beralasan (bukan diam-diam reuse "cakupan cocok").
        ok &= check("per-versi: file lapis absen -> rerun 'belum ada'",
                    pv["9.1"]["layers"]["static"]["reuse"] is False
                    and "belum ada" in pv["9.1"]["layers"]["static"]["reason"])

        # Cakupan salah: file 9.1 yang isinya meninjau 8.1 -> rerun (tiap file harus bercakupan
        # PERSIS versinya sendiri, kalau tidak ia bukti versi lain yang menyamar).
        _pv("adversarial", "9.1", 2000, versions_in_file=["8.1"])
        pv2 = mod.plan_per_version(reports, "mymod", ["9.1"], newest, "mymod.php", ruleset, tag_map,
                                   e2e_cells=cells)
        ok &= check("per-versi: cakupan salah (file 9.1 meninjau 8.1) -> rerun",
                    pv2["9.1"]["layers"]["adversarial"]["reuse"] is False
                    and "cakupan kurang: 9.1" in pv2["9.1"]["layers"]["adversarial"]["reason"])

        # Provenance image per-versi: tag file != tag berlaku -> rerun versi ITU saja (bukti
        # core lain), sementara versi dengan tag benar tetap reuse.
        # (Dulu diuji atas file e2e per-versi; kini lewat Lapis 5 yang tetap ber-file & ber-image.)
        _pv("scenario", "8.1", 2000)
        p91 = mod.per_version_path(reports, "mymod", "scenario", "9.1")
        p91.write_text(json.dumps({"versions": {"9.1": {"pass": True, "tag": "beda-tag"}}}),
                       encoding="utf-8")
        os.utime(p91, (2000, 2000))
        pv3 = mod.plan_per_version(reports, "mymod", ["8.1", "9.1"], newest, "mymod.php",
                                   ruleset, tag_map, e2e_cells=cells)
        ok &= check("per-versi: tag image 8.1 benar -> reuse",
                    pv3["8.1"]["layers"]["scenario"]["reuse"] is True)
        ok &= check("per-versi: tag image 9.1 beda -> rerun (bukti core lain)",
                    pv3["9.1"]["layers"]["scenario"]["reuse"] is False
                    and "image berbeda" in pv3["9.1"]["layers"]["scenario"]["reason"])
        ok &= check("per-versi: layers.e2e berkunci browser (sel versi itu saja)",
                    set(pv3["9.1"]["layers"]["e2e"]) == {"chromium", "firefox"}
                    and pv3["9.1"]["layers"]["e2e"]["firefox"]["reason"] == "missing"
                    and "e2e" in pv3["9.1"]["rerun"])

        # CLI: mode per-versi berbentuk beda & DETERMINISTIK (input sama -> byte identik).
        r1 = subprocess.run(["uv", "run", str(MOD_PATH), str(mdir), "--reports-dir", str(reports),
                             "--versions", "8.1,9.1", "--per-version", "--session", SESSION],
                            capture_output=True, text=True)
        r2 = subprocess.run(["uv", "run", str(MOD_PATH), str(mdir), "--reports-dir", str(reports),
                             "--versions", "8.1,9.1", "--per-version", "--session", SESSION],
                            capture_output=True, text=True)
        ok &= check("CLI per-versi: exit 0 & bentuk mode/per_version",
                    r1.returncode == 0 and '"mode": "per-version"' in r1.stdout
                    and '"per_version"' in r1.stdout)
        ok &= check("CLI per-versi: deterministik (dua run byte identik)", r1.stdout == r2.stdout)
        r_canon = subprocess.run(["uv", "run", str(MOD_PATH), str(mdir), "--reports-dir", str(reports),
                                  "--versions", "8.1,9.1", "--session", SESSION],
                                 capture_output=True, text=True)
        ok &= check("CLI mode kanonik TAK memancarkan per_version (nol regresi bentuk)",
                    r_canon.returncode == 0 and '"per_version"' not in r_canon.stdout
                    and '"layers"' in r_canon.stdout)

        # Roll-up gerbang Fase 2: model tak boleh meng-union 4 lapis x N versi dengan tangan
        # di gerbang yang memutuskan boleh-tidaknya sweep rilis mahal dimulai.
        roll = mod.per_version_rollup(pv3, cells)
        ok &= check("roll-up: ada yang rerun -> all_reuse False",
                    roll["all_reuse"] is False)
        ok &= check("roll-up: matriks memuat pasangan (lapis, versi) yang rerun",
                    {"layer": "scenario", "version": "9.1"} in
                    [{"layer": m["layer"], "version": m["version"]} for m in roll["rerun_matrix"]])
        ok &= check("roll-up: entri e2e meliputi SEMUA sel terkonfigurasi (bukan cuma --versions) "
                    "& membawa browser + reason",
                    sorted((m["version"], m["browser"], m["reason"]) for m in roll["rerun_matrix"]
                           if m["layer"] == "e2e")
                    == sorted((v, b, "missing") for v in TV for b in ("chromium", "firefox")))
        ok &= check("roll-up: e2e TAK per-versi-capable (dijalankan via --cells; --per-version = exit 2)",
                    not any(m["per_version_capable"] for m in roll["rerun_matrix"]
                            if m["layer"] == "e2e"))
        ok &= check("roll-up: adversarial ditandai TAK per-versi-capable "
                    "(satu review lintas-versi; ps-run-layer menolak me-merge-nya)",
                    all(m["per_version_capable"] is False for m in roll["rerun_matrix"]
                        if m["layer"] == "adversarial"))
        empty = mod.per_version_rollup({"9.1": {"layers": {}, "rerun": []}}, {})
        ok &= check("roll-up: nol rerun -> all_reuse True & matriks kosong",
                    empty["all_reuse"] is True and empty["rerun_matrix"] == [])
        ok &= check("CLI per-versi memancarkan roll-up (bukan cuma tersedia di fungsi)",
                    '"all_reuse"' in r1.stdout and '"rerun_matrix"' in r1.stdout)

    ok &= test_e2e_cells()
    ok &= test_tier_derivation()
    ok &= test_tier_cli()
    ok &= test_session_cli()
    ok &= test_require_config_cli()
    print("\n" + ("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
