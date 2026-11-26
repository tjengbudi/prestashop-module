#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Unit test untuk ps-aggregate.py — verifikasi vonis dihitung native & degrade jujur.

Fokus kontrak: pass per-versi & keseluruhan dihitung dari temuan error lapis
konklusif; lapis flashlight tak konklusif (skipped/pull-fail/timeout/no-console)
TAK PERNAH memblok. Jalankan: uv run scripts/tests/test-ps-aggregate.py
"""
import contextlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

MOD_PATH = Path(__file__).resolve().parent.parent / "ps-aggregate.py"
spec = importlib.util.spec_from_file_location("ps_aggregate", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}: {name}")
    return cond


def static_result(versions, rules_evaluated=12, main_file_found=True):
    """versions: {full_ver: [(id, severity)]} -> bentuk output ps-static-scan.

    `rules_evaluated`/`main_file_found` ditiru dari produsen aslinya karena agregat kini
    MEMBACA keduanya: nol aturan dinilai (atau main file tak resolve) = cakupan tak tuntas,
    bukan lolos. Default di sini meniru run sehat; test yang menguji cabang itu menyetelnya.
    """
    out = {"module": "m", "main_file_found": main_file_found, "versions": {}}
    for ver, finds in versions.items():
        errs = sum(1 for _, sev in finds if sev == "error")
        out["versions"][ver] = {
            "major": ver.split(".")[0], "errors": errs,
            "warnings": len(finds) - errs, "pass": errs == 0,
            "rules_evaluated": rules_evaluated,
            "findings": [{"id": i, "severity": s, "kind": "x", "message": i,
                          "fix": "", "occurrences": [{"file": "a.php", "line": 1}], "count": 1}
                         for i, s in finds],
        }
    out["pass"] = all(v["pass"] for v in out["versions"].values())
    return out


# --- Bukti E2E: histori per sel (cell-contract.md > Evidence record / Aggregate) -------
pl = mod.pl
SESSION = "abcdefghij012345"
BR = ["chromium", "firefox"]
FP = "f" * 64  # fingerprint tiruan untuk test in-memory (CLI memakai fingerprint module asli)


def _tag(ver):
    """Tag ter-resolve dgn peta default — cara yang sama dgn plan, runner, agregat."""
    return pl.fl.resolve_tag(pl.fl.parse_tag_map(None), ver)


def _rec(ver, browser, fp=FP, **kw):
    """Record histori lengkap = pass gate-grade PASSING (Fields kontrak + boot_wall_clock/boot_log)."""
    r = {"version": ver, "browser": browser,
         "started_at": "2026-11-26T10:00:00.000000+00:00",
         "finished_at": "2026-11-26T10:05:00.000000+00:00",
         "boot": "cold", "boot_id": f"boot-{ver}", "session": SESSION,
         "browser_mode": "sequential", "scenario_set": "full",
         "scenarios_run": ["psm-universal-smoke", "s1"], "source_fingerprint": fp,
         "image_tag": _tag(ver), "run_id": "r0", "job_id": "j0", "tier": None,
         "state": "pass", "conclusive": True, "reason": None, "errors": [],
         "install": {"ok": True}, "launch_error": None, "bo_authed": True, "findings": [],
         "inconclusive": [], "authored_assertions": 2, "scenario_notes": [],
         "browser_notes": [], "parallel_only": None, "console_errors": 0, "screenshots": [],
         "scenario_spans": None,
         "phase_durations": {f"browser:{browser}": {"seconds": 12.5, "outcome": "ok"}},
         "boot_phases": {"pull": {"seconds": 1.0, "outcome": "ok"},
                         "wait-healthy": {"seconds": 30.0, "outcome": "ok"}},
         "keeper_boot": None, "wall_clock": 300.0, "boot_wall_clock": 420.0, "boot_log": None}
    r.update(kw)
    return r


def _finding(ver, browser, scenario="s1", action="expect_text"):
    return {"id": f"e2e-{scenario}-{action}", "severity": "error",
            "message": f"[{browser}/{scenario}] {action}: teks tak ada", "location": "fo",
            "fix": "periksa", "browser": browser, "scenario": scenario, "source": "s1.json",
            "action": action, "step": 3, "versions": [ver]}


def _fail(ver, browser, **kw):
    return _rec(ver, browser, state="fail", findings=[_finding(ver, browser)], **kw)


def _row(ver, cells, notes=(), corrupt=()):
    """{browser: [record...]} -> row info evaluate_cell (in-memory, fingerprint FP)."""
    return {b: mod.evaluate_cell(list(recs), b in corrupt, FP, _tag(ver), list(notes))
            for b, recs in cells.items()}


def _both(ver, **kw):
    return {b: [_rec(ver, b, **kw)] for b in BR}


def _merge(ver, static_payload, cells=None, browsers=BR, notes=()):
    row = _row(ver, cells, notes) if cells is not None else None
    return mod.merge_version(ver, static_payload, None, None, row, None, browsers=browsers)


def _write_cfg(path, versions="1.7.8,8.1,9.1", browsers="chromium,firefox", **extra):
    cfg = {"psm_target_versions": versions, "psm_e2e_browsers": browsers, **extra}
    Path(path).write_text(json.dumps(cfg), encoding="utf-8")
    return str(path)


def _run_main(args):
    """ps-aggregate main() in-process (cepat). Return (rc, stderr)."""
    err = io.StringIO()
    saved = sys.argv
    sys.argv = ["ps-aggregate.py", *args]
    try:
        with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
            rc = mod.main()
    except SystemExit as e:
        rc = e.code
    finally:
        sys.argv = saved
    return rc, err.getvalue()


class Env:
    """Module asli + folder laporan + config + static bersih; histori ditulis lewat
    ps-plan-layers.append_record dgn fingerprint module yang SEBENARNYA."""

    def __init__(self, td, versions="1.7.8,8.1,9.1", browsers="chromium,firefox",
                 static_versions=None, **cfg_extra):
        root = Path(td)
        self.root = root
        self.m = root / "mymod"
        self.m.mkdir()
        (self.m / "mymod.php").write_text("<?php // mymod", encoding="utf-8")
        self.rep = root / "reports"
        self.rep.mkdir()
        self.cfg = _write_cfg(root / "psm-config.json", versions, browsers, **cfg_extra)
        self.fp = pl.source_fingerprint(self.m, self.rep)
        sv = static_versions or [v.strip() for v in versions.split(",")]
        st = static_result({v: [] for v in sv})
        st["module"] = "mymod"
        self.static = root / "static.json"
        self.static.write_text(json.dumps(st), encoding="utf-8")
        self.out = root / "out.json"

    def path(self, ver, browser):
        return pl.history_path(self.rep, "mymod", ver, browser)

    def add(self, ver, browser, rec=None, **kw):
        rec = rec if rec is not None else _rec(ver, browser, self.fp, **kw)
        pl.append_record(self.path(ver, browser), rec)

    def fail(self, ver, browser, **kw):
        self.add(ver, browser, _fail(ver, browser, fp=self.fp, **kw))

    def seed_all(self, versions=None, browsers=BR, **kw):
        for v in versions or json.loads(self.static.read_text())["versions"]:
            for b in browsers:
                self.add(v, b, **kw)

    def run(self, *extra, require="static,e2e", config=True):
        if self.out.exists():
            self.out.unlink()
        args = ["--static", str(self.static), "--reports-dir", str(self.rep),
                "--module", str(self.m), "-o", str(self.out), *extra]
        if config:
            args += ["--config", self.cfg]
        if require:
            args += ["--require", require]
        rc, err = _run_main(args)
        out = json.loads(self.out.read_text(encoding="utf-8")) if self.out.exists() else None
        return rc, err, out


def main():
    ok = True
    TV = ["1.7.8", "8.1", "9.1"]

    # 1. Static bersih, tanpa flashlight/adversarial -> lolos, tapi flashlight tak konklusif
    static = static_result({v: [] for v in TV})
    r = mod.merge_version("8.1", static, None, None, None)
    ok &= check("static bersih -> versi lolos", r["pass"])
    ok &= check("tanpa flashlight -> flashlight_conclusive False", not r["flashlight_conclusive"])
    ok &= check("static selalu memberi vonis dasar konklusif", r["conclusive"])

    # 2. Static punya error -> versi gagal (dihitung native, bukan model)
    static_bad = static_result({"8.1": [("cls-attribute", "error")], "9.1": [], "1.7.8": []})
    r = mod.merge_version("8.1", static_bad, None, None, None)
    ok &= check("static error -> versi gagal", not r["pass"] and len(r["blocking"]) == 1)
    r91 = mod.merge_version("9.1", static_bad, None, None, None)
    ok &= check("versi lain tanpa error tetap lolos", r91["pass"])

    # 3. Flashlight skipped (Docker absen) -> TAK memblok versi yang static-nya bersih
    flash_skipped = {"module": "m", "docker_available": False, "status": "skipped",
                     "reason": "Docker absen", "versions": {}}
    r = mod.merge_version("8.1", static, flash_skipped, None, None)
    ok &= check("flashlight skipped tak memblok versi bersih", r["pass"])
    ok &= check("flashlight skipped -> state skipped, tak konklusif",
                r["layers"]["flashlight"]["state"] == "skipped" and not r["flashlight_conclusive"])

    # 4. Flashlight gagal infra (timeout) -> TAK memblok (degrade jujur), tak diklaim gagal
    flash_infra = {"module": "m", "docker_available": True, "status": "ran",
                   "versions": {"8.1": {"version": "8.1", "image": "img", "install": None,
                                        "coding_standard": None,
                                        "errors": ["timeout menjalankan container img"], "pass": False}}}
    r = mod.merge_version("8.1", static, flash_infra, None, None)
    ok &= check("flashlight timeout tak memblok (enhancement-2)", r["pass"])
    ok &= check("flashlight timeout -> not_conclusive",
                r["layers"]["flashlight"]["state"] == "not_conclusive")

    # 4b. Flashlight skipped_image (image absen, pull tak diizinkan) -> tak memblok (enhancement-1)
    flash_noimg = {"module": "m", "docker_available": True, "status": "ran",
                   "versions": {"8.1": {"version": "8.1", "image": "img", "install": None,
                                        "coding_standard": None, "skipped_image": True,
                                        "errors": ["image img belum ada lokal & pull tak diizinkan"],
                                        "pass": False}}}
    r = mod.merge_version("8.1", static, flash_noimg, None, None)
    ok &= check("flashlight skipped_image tak memblok (enhancement-1)", r["pass"])
    ok &= check("flashlight skipped_image -> not_conclusive",
                r["layers"]["flashlight"]["state"] == "not_conclusive" and not r["flashlight_conclusive"])

    # 5. Flashlight no_console -> tak konklusif, tak memblok
    flash_nocon = {"module": "m", "docker_available": True, "status": "ran",
                   "versions": {"8.1": {"version": "8.1", "image": "img",
                                        "install": {"ok": False, "no_console": True, "log": ""},
                                        "coding_standard": {"available": False},
                                        "errors": [], "pass": False}}}
    r = mod.merge_version("8.1", static, flash_nocon, None, None)
    ok &= check("flashlight no_console tak memblok", r["pass"] and not r["flashlight_conclusive"])

    # 5b. no_psroot (PS root absen) -> infra juga: tak konklusif, tak memblok (determinism-6)
    flash_nopsroot = {"module": "m", "docker_available": True, "status": "ran",
                      "versions": {"8.1": {"version": "8.1", "image": "img",
                                           "install": {"ok": False, "no_psroot": True, "log": ""},
                                           "coding_standard": {"available": False},
                                           "errors": [], "pass": False}}}
    r = mod.merge_version("8.1", static, flash_nopsroot, None, None)
    ok &= check("flashlight no_psroot -> infra, tak memblok",
                r["pass"] and not r["flashlight_conclusive"]
                and r["layers"]["flashlight"]["state"] == "not_conclusive")

    # 6. Flashlight KONKLUSIF + install ditolak -> MEMBLOK (uji nyata gagal)
    flash_fail = {"module": "m", "docker_available": True, "status": "ran",
                  "versions": {"8.1": {"version": "8.1", "image": "img",
                                       "install": {"ok": False, "no_console": False,
                                                   "no_verdict": False, "log": "boom"},
                                       "coding_standard": {"available": False},
                                       "errors": [], "pass": False}}}
    r = mod.merge_version("8.1", static, flash_fail, None, None)
    ok &= check("install ditolak (konklusif) -> memblok", not r["pass"] and r["flashlight_conclusive"])

    # 7. Flashlight konklusif + phpstan error (neon module) -> memblok dengan lokasi
    flash_cs = {"module": "m", "docker_available": True, "status": "ran",
                "versions": {"8.1": {"version": "8.1", "image": "img",
                                     "install": {"ok": True, "no_console": False, "log": ""},
                                     "coding_standard": {"available": True, "parse_ok": True, "errors": 2,
                                                         "error_messages": [{"line": 3, "source": "X", "message": "bad"},
                                                                            {"line": 9, "source": "Y", "message": "worse"}]},
                                     "errors": [], "pass": False}}}
    r = mod.merge_version("8.1", static, flash_cs, None, None)
    ok &= check("phpstan 2 error (neon module) -> 2 temuan memblok", not r["pass"] and len(r["blocking"]) == 2)

    # 7b. phpstan auto-neon (advisory: errors=0, warnings) -> TAK memblok meski ada temuan
    flash_adv = {"module": "m", "docker_available": True, "status": "ran",
                 "versions": {"8.1": {"version": "8.1", "image": "img",
                                      "install": {"ok": True, "no_console": False, "log": ""},
                                      "coding_standard": {"available": True, "parse_ok": True,
                                                          "generated_config": True, "errors": 0, "warnings": 2,
                                                          "error_messages": [{"line": 3, "source": "phpstan", "message": "mungkin"}]},
                                      "errors": [], "pass": True}}}
    r = mod.merge_version("8.1", static, flash_adv, None, None)
    ok &= check("phpstan auto-neon advisory (errors=0) tak memblok", r["pass"] and len(r["blocking"]) == 0)

    # 8. Adversarial error -> memblok; adversarial warning -> tak memblok
    adv = {"versions": TV, "findings": [
        {"id": "adv-sqli", "severity": "error", "message": "SQL injection",
         "versions": ["8.1"], "location": "x.php:5"},
        {"id": "adv-perf", "severity": "warning", "message": "query in loop",
         "versions": ["8.1"]}]}
    r = mod.merge_version("8.1", static, None, adv, None)
    ok &= check("adversarial error memblok", not r["pass"])
    ok &= check("adversarial error terkumpul 1 blocking (warning tak)", len(r["blocking"]) == 1)
    # adversarial tanpa versi -> berlaku semua versi target
    adv_all = {"versions": TV, "findings": [{"id": "adv-x", "severity": "error", "message": "global"}]}
    r91_all = mod.merge_version("9.1", static, None, adv_all, None)
    ok &= check("adversarial tanpa versi -> berlaku semua target", not r91_all["pass"])
    # regression architecture-1: versions major-form ('8') harus match full-form target ('8.1')
    adv_major = {"versions": TV, "findings": [{"id": "adv-m", "severity": "error",
                                              "message": "major-form", "versions": ["8"]}]}
    r_m = mod.merge_version("8.1", static, None, adv_major, None)
    ok &= check("adversarial major-form '8' match target '8.1' (tak diam-diam drop)", not r_m["pass"])
    r_m91 = mod.merge_version("9.1", static, None, adv_major, None)
    ok &= check("major-form '8' TAK bocor ke versi lain (9.1 tetap lolos)", r_m91["pass"])
    # full-form tetap match apa adanya
    adv_full = {"versions": TV, "findings": [{"id": "adv-f", "severity": "error",
                                             "message": "full-form", "versions": ["1.7.8"]}]}
    r_f = mod.merge_version("1.7.8", static, None, adv_full, None)
    ok &= check("adversarial full-form '1.7.8' tetap match", not r_f["pass"])

    # 8b. Validasi skema payload adversarial (determinism-4): pelanggaran tercatat KERAS,
    # bukan diam-diam tak-memblok (severity off-enum) / ter-drop (token versi tak resolve).
    ok &= check("validate_adversarial: payload sehat -> tanpa pelanggaran",
                mod.validate_adversarial(adv, TV) == [])
    ok &= check("validate_adversarial: None (tanpa file) -> tanpa pelanggaran",
                mod.validate_adversarial(None, TV) == [])
    adv_badsev = {"versions": TV, "findings": [{"id": "adv-c", "severity": "critical", "message": "x"}]}
    notes_sev = mod.validate_adversarial(adv_badsev, TV)
    ok &= check("severity di luar enum ('critical') -> pelanggaran tercatat",
                len(notes_sev) == 1 and "critical" in notes_sev[0] and "adv-c" in notes_sev[0])
    adv_badver = {"versions": TV, "findings": [{"id": "adv-v", "severity": "error", "message": "x",
                                               "versions": ["PS8"]}]}
    notes_ver = mod.validate_adversarial(adv_badver, TV)
    ok &= check("token versi tak resolve ('PS8') -> pelanggaran tercatat",
                len(notes_ver) == 1 and "PS8" in notes_ver[0])
    # token non-string: pelanggaran skema KERAS (exit 2), bukan AttributeError ->
    # exit 1 yang bertabrakan dgn kode 'vonis gagal'
    adv_nonstr = {"versions": TV, "findings": [{"id": "adv-n", "severity": "error", "message": "x",
                                               "versions": [8]}]}
    notes_nonstr = mod.validate_adversarial(adv_nonstr, TV)
    ok &= check("token versi non-string (8) -> pelanggaran tercatat, tak crash",
                len(notes_nonstr) == 1 and "bukan string" in notes_nonstr[0])
    ok &= check("_version_matches: token non-string di-coerce (tak meledak)",
                mod._version_matches(8, "8.1") is True)
    # REGRESI minor-key: dulu kecocokan diputus lewat MAJOR saja, jadi temuan yang
    # reviewer batasi eksplisit ke 9.0 ikut memblok 9.1 (dan sebaliknya). Benar untuk
    # bentuk major, salah begitu minor disebut — dan minor kini bisa disebut.
    ok &= check("_version_matches: '9.0' TIDAK cocok utk 9.1 (dulu cocok lewat major)",
                mod._version_matches("9.0", "9.1") is False)
    ok &= check("_version_matches: '9.1' TIDAK cocok utk 9.0",
                mod._version_matches("9.1", "9.0") is False)
    ok &= check("_version_matches: major telanjang '9' tetap cocok utk 9.1 & 9.0",
                mod._version_matches("9", "9.1") and mod._version_matches("9", "9.0"))
    ok &= check("_version_matches: '9.1' cocok utk target lebih spesifik 9.1.4",
                mod._version_matches("9.1", "9.1.4") is True)
    ok &= check("_version_matches: major beda tetap tak cocok",
                mod._version_matches("8.1", "9.1") is False)
    ok &= check("_version_matches: dua-komponen 1.7 tak tertukar dgn 1.6",
                mod._version_matches("1.7.8", "1.7.8.11")
                and not mod._version_matches("1.7", "1.6.1"))
    # Aturan khas-minor yang tak dinilai = cakupan HILANG, bentuk yang sama dgn
    # rules_evaluated 0 — cuma sebagian. Kalau agregat diam, "bersih di 9" terbaca
    # tuntas padahal aturan Hummingbird tak pernah dijalankan.
    st_skip = static_result({"9": []})
    st_skip["versions"]["9"]["minor_rules_skipped"] = ["9.1"]
    lay_skip = mod.static_layer(st_skip, "9")
    ok &= check("minor_rules_skipped terisi -> tak konklusif + note sebut minornya",
                lay_skip["conclusive"] is False
                and "9.1" in lay_skip.get("inconclusive_note", ""))
    st_full = static_result({"9.1": []})
    st_full["versions"]["9.1"]["minor_rules_skipped"] = []
    ok &= check("minor_rules_skipped kosong -> tetap konklusif (gerbang tak kelebihan sapu)",
                mod.static_layer(st_full, "9.1")["conclusive"] is True)
    # REGRESI determinism-4: BENTUK container digerbang sebelum nilai field. Dulu
    # payload salah-bentuk -> AttributeError -> exit 1 = kode vonis-gagal (file rusak
    # terbaca "module gagal"). Sekarang pelanggaran skema bersih (exit 2).
    ok &= check("payload list telanjang -> pelanggaran, bukan crash",
                len(mod.validate_adversarial([{"id": "x"}], TV)) == 1)
    ok &= check("'findings' bukan list (dict) -> pelanggaran, bukan crash",
                len(mod.validate_adversarial({"versions": TV, "findings": {"a": {}}}, TV)) == 1)
    notes_str = mod.validate_adversarial({"versions": TV, "findings": ["cuma string"]}, TV)
    ok &= check("entri findings bertipe string -> pelanggaran, bukan crash",
                len(notes_str) == 1 and "harus object" in notes_str[0])
    # 'versions' skalar truthy: dulu lolos gerbang lalu TypeError saat di-iterasi
    # -> exit 1 = kode vonis-gagal (file rusak terbaca "module gagal").
    for bad in (8.1, True, {"a": 1}):
        n = mod.validate_adversarial({"versions": TV, "findings": [
            {"id": "v", "severity": "error", "message": "x", "versions": bad}]}, TV)
        ok &= check(f"'versions' bertipe {type(bad).__name__} -> pelanggaran, bukan crash",
                    len(n) == 1 and "harus list" in n[0])
    n_str = mod.validate_adversarial({"versions": TV, "findings": [
        {"id": "v", "severity": "error", "message": "x", "versions": "8.1"}]}, TV)
    ok &= check("'versions' string (bukan list) -> pelanggaran (iterasi per-karakter dicegah)",
                len(n_str) == 1 and "harus list" in n_str[0])

    # --- Lapis 4 (E2E) — histori per sel; record terpilih = gate-grade terbaru, else terbaru ---

    # 9. Tanpa histori sama sekali -> tiap sel `missing`: tak memblok, tak konklusif
    r = _merge("8.1", static)
    ok &= check("e2e tanpa histori -> inconclusive 'missing', tak memblok, tak konklusif",
                r["pass"] and r["e2e_state"] == "inconclusive" and r["reason"] == "missing"
                and not r["e2e_conclusive"])
    ok &= check("e2e tanpa histori -> inconclusive_note menyebut kedua sel + alasannya",
                "8.1:chromium (missing)" in r["layers"]["e2e"].get("inconclusive_note", "")
                and "8.1:firefox (missing)" in r["layers"]["e2e"]["inconclusive_note"])

    # 9b. Infra (container tak healthy, install null) -> record inconclusive: tak memblok
    infra = {b: [_rec("8.1", b, state="inconclusive", conclusive=False, reason="errors",
                      errors=["flashlight tak jadi 'healthy' (timeout)"], install=None,
                      phase_durations={}, findings=None, authored_assertions=None)]
             for b in BR}
    r = _merge("8.1", static, infra)
    ok &= check("e2e infra-fail tak memblok (degrade jujur), tak konklusif",
                r["pass"] and not r["e2e_conclusive"] and r["e2e_state"] == "inconclusive"
                and r["reason"] == "inconclusive")

    # 10b. Gate-grade fail TANPA temuan ERROR terbaca -> tetap memblok (state rekaman memvonis)
    r = _merge("8.1", static, {"chromium": [_rec("8.1", "chromium", state="fail",
                                                  findings=[{"severity": "warning"}, "rusak"])],
                               "firefox": [_rec("8.1", "firefox")]})
    ok &= check("e2e gate-grade fail tanpa temuan ERROR -> tetap memblok (bukan pass)",
                not r["pass"] and r["e2e_state"] == "fail"
                and any(f["id"] == "e2e-fail" for f in r["blocking"]))

    # 10. Gate-grade fail -> MEMBLOK versi itu, reason literal `fail`
    r = _merge("8.1", static, {"chromium": [_fail("8.1", "chromium")],
                               "firefox": [_rec("8.1", "firefox")]})
    ok &= check("e2e gate-grade fail -> memblok & konklusif",
                not r["pass"] and r["e2e_conclusive"] and r["e2e_state"] == "fail"
                and r["reason"] == "fail")
    ok &= check("e2e temuan masuk blocking sebagai source e2e (ber-browser)",
                any(f.get("source") == "e2e" and f.get("browser") == "chromium"
                    for f in r["blocking"]))
    ok &= check("e2e temuan versi 8.1 TAK bocor ke 9.1 (sel 9.1 tanpa histori)",
                _merge("9.1", static)["pass"])

    # 10a. Temuan record NON-gate-grade (partial / warm / basi) TAK memblok — hanya tampil
    # di e2e_cells. Kalau tidak, run parsial yang dipersempit memvonis seluruh versi.
    part = {"chromium": [_fail("8.1", "chromium", scenario_set="partial")],
            "firefox": [_rec("8.1", "firefox")]}
    r = _merge("8.1", static, part)
    ent = mod.e2e_cell_entry(_row("8.1", part)["chromium"])
    ok &= check("temuan record partial tak memblok (pass True, e2e_state bukan fail)",
                r["pass"] and r["layers"]["e2e"]["findings"] == [] and r["e2e_state"] == "inconclusive")
    ok &= check("temuan record partial tetap tampil di e2e_cells (gate_grade False)",
                ent["gate_grade"] is False and len(ent["findings"]) == 1 and ent["state"] == "fail")
    stale = {"chromium": [_fail("8.1", "chromium", fp="lama" * 16)],
             "firefox": [_rec("8.1", "firefox")]}
    r = _merge("8.1", static, stale)
    ok &= check("fail BASI tak memblok, alasan sel = stale-fail (bukan stale-source)",
                r["pass"] and r["e2e_state"] == "inconclusive" and r["reason"] == "stale-fail")

    # 10b. Pass gate-grade dgn assertion tak konklusif (login BO gagal) -> note, tak memblok
    inc = _both("8.1")
    inc["chromium"] = [_rec("8.1", "chromium", inconclusive=[
        {"browser": "chromium", "scenario": "psm-universal-smoke", "action": "expect_text",
         "step": 2, "message": "BO", "location": "bo"}])]
    r = _merge("8.1", static, inc)
    ok &= check("e2e inconclusive-steps -> konklusif & lolos, tapi note + reason inconclusive-steps",
                r["pass"] and r["e2e_conclusive"]
                and "inconclusive-steps" in r["layers"]["e2e"].get("inconclusive_note", "")
                and r["reason"] == "inconclusive-steps")

    # 10c. REGRESI false-pass: satu browser MEMBLOK sementara co-tenant gagal luncur -> temuan
    # konklusif TETAP memblok (browser lain yang inconclusive tak membatalkannya).
    mixed = {"chromium": [_fail("8.1", "chromium")],
             "firefox": [_rec("8.1", "firefox", state="inconclusive", conclusive=False,
                              reason="launch-error", launch_error="firefox: boom",
                              phase_durations={})]}
    r = _merge("8.1", static, mixed)
    ok &= check("browser co-tenant gagal luncur TAK membatalkan temuan konklusif (fix false-pass)",
                not r["pass"] and r["e2e_state"] == "fail"
                and r["layers"]["e2e"]["state"] == "fail")
    ok &= check("sel co-tenant yang gagal luncur disurface di inconclusive_note",
                "8.1:firefox (inconclusive)" in r["layers"]["e2e"].get("inconclusive_note", ""))

    # 10d. Spec authored rusak (scenario_notes) di record -> note, ready jatuh, tak memblok
    sn = _both("8.1")
    sn["chromium"] = [_rec("8.1", "chromium", scenario_notes=["checkout.json: tak ada 'steps'"])]
    r = _merge("8.1", static, sn)
    ok &= check("scenario_notes di record -> reason scenario-notes di note walau lolos",
                r["pass"] and "8.1:chromium (scenario-notes)"
                in r["layers"]["e2e"].get("inconclusive_note", ""))
    r_ng = _merge("8.1", static, sn, notes=["checkout.json: tak ada 'steps'"])
    ok &= check("scenario_notes SAMA dgn notes module sekarang -> not-gradeable (tak pernah ready)",
                "8.1:chromium (not-gradeable)" in r_ng["layers"]["e2e"].get("inconclusive_note", "")
                and mod.compute_ready({"8.1": r_ng}, ["static", "e2e"]) is False)

    # 10e. Record pass/fail yang field wajibnya null -> incomplete-record (state inconclusive)
    inc_rec = _both("8.1")
    inc_rec["firefox"] = [_rec("8.1", "firefox", session=None)]
    ent = mod.e2e_cell_entry(_row("8.1", inc_rec)["firefox"])
    ok &= check("pass tanpa `session` -> e2e_cells state inconclusive, tak gate-grade",
                ent["state"] == "inconclusive" and ent["gate_grade"] is False
                and ent["reason"] == "inconclusive")

    # 10f. Newer fail (I/O matrix): pass lalu fail di fingerprint sama -> fail menang
    nf = {"chromium": [_rec("8.1", "chromium"), _fail("8.1", "chromium")],
          "firefox": [_rec("8.1", "firefox")]}
    r = _merge("8.1", static, nf)
    ok &= check("Newer fail: pass lalu fail -> reason fail, tak siap",
                r["reason"] == "fail" and mod.e2e_cell_entry(_row("8.1", nf)["chromium"])["reason"]
                == "fail" and mod.compute_ready({"8.1": r}, ["static", "e2e"]) is False)
    fp_ = {"chromium": [_fail("8.1", "chromium"), _rec("8.1", "chromium")],
           "firefox": [_rec("8.1", "firefox")]}
    ok &= check("kontrol: fail lalu pass -> sel punya bukti lulus, siap",
                mod.compute_ready({"8.1": _merge("8.1", static, fp_)}, ["static", "e2e"]) is True)

    # 10g. warm/partial/not-run: tak pernah gate-grade, tak menyembunyikan record lebih tua
    wpn = {"chromium": [_rec("8.1", "chromium"), _rec("8.1", "chromium", boot="warm")],
           "firefox": [_rec("8.1", "firefox"),
                       _rec("8.1", "firefox", state="not-run", conclusive=False,
                            reason="fail-fast after 8.1:chromium", install=None,
                            phase_durations={}, findings=None, authored_assertions=None)]}
    r = _merge("8.1", static, wpn)
    ok &= check("warm & not-run yang lebih baru tak menyembunyikan pass gate-grade lama -> siap",
                r["e2e_state"] == "pass" and r["reason"] is None
                and mod.compute_ready({"8.1": r}, ["static", "e2e"]) is True)
    only = {"chromium": [_rec("8.1", "chromium", boot="warm")],
            "firefox": [_rec("8.1", "firefox", scenario_set="partial")]}
    row_only = _row("8.1", only)
    ok &= check("hanya warm -> warm-only; hanya partial -> partial (tak pernah gate-grade)",
                row_only["chromium"]["reason"] == "warm-only"
                and row_only["firefox"]["reason"] == "partial"
                and not row_only["chromium"]["gate_grade"] and not row_only["firefox"]["gate_grade"])

    def _flash_cs(cs):
        # `coverage_ok` ditambahkan seperti produsen sehat (canary terdeteksi) kecuali test
        # menyetelnya sendiri — agregat kini membacanya: phpstan yang tak menganalisis satu
        # file pun dari module bukan "bersih", melainkan "tak diukur".
        if cs.get("available") and cs.get("parse_ok") and "coverage_ok" not in cs:
            cs = {**cs, "coverage_ok": True}
        return {"module": "m", "docker_available": True, "status": "ran",
                "versions": {"8.1": {"version": "8.1", "image": "img",
                                     "install": {"ok": True, "no_console": False, "log": ""},
                                     "coding_standard": cs, "errors": [], "pass": True}}}

    # 10e. CS tak dievaluasi -> install tetap konklusif TAPI disurface di
    # inconclusive_note (kanal yang dibaca aturan jujur SKILL.md). Dulu dicatat di
    # cs_note yang tak dibaca siapa pun -> separuh vonis Lapis 2 hilang senyap.
    r = mod.merge_version("8.1", static, _flash_cs(
        {"available": True, "parse_ok": False, "note": "JSON phpstan kosong/tak valid"}), None, None)
    fl_layer = r["layers"]["flashlight"]
    ok &= check("phpstan tak terparse -> inconclusive_note (bukan cs_note yang tak dibaca)",
                "phpstan" in fl_layer.get("inconclusive_note", "") and "cs_note" not in fl_layer)
    r = mod.merge_version("8.1", static, _flash_cs({"available": False}), None, None)
    ok &= check("phpstan absen dari image -> inconclusive_note (dulu senyap total)",
                "tak diuji" in r["layers"]["flashlight"].get("inconclusive_note", ""))


    # 11b. compute_ready: pass buta konklusivitas, ready menjawab siap-rilis
    v_clean = {"8.1": mod.merge_version("8.1", static, None, None, None)}
    ok &= check("ready: hanya static diwajibkan & bersih -> True",
                mod.compute_ready(v_clean, ["static"]) is True)
    ok &= check("ready: flashlight diwajibkan tapi tak jalan -> False (pass=True tapi tak siap)",
                v_clean["8.1"]["pass"] is True and mod.compute_ready(v_clean, ["static", "flashlight"]) is False)
    v_bad = {"8.1": mod.merge_version("8.1", static_bad, None, None, None)}
    ok &= check("ready: ada error memblok -> False walau lapis konklusif",
                mod.compute_ready(v_bad, ["static"]) is False)
    ok &= check("compute_ready: lapis diwajibkan tak ada di hasil -> False (bukan KeyError)",
                mod.compute_ready(v_clean, ["ngawur"]) is False)
    # Lapis boleh konklusif TAPI separuhnya tak dievaluasi (phpstan absen) / cakupan
    # menyusut -> inconclusive_note. ready HARUS ikut jatuh; kalau tidak ia mengklaim
    # persis coverage yang tak diuji.
    v_note = {"8.1": mod.merge_version("8.1", static, _flash_cs({"available": False}), None, None)}
    ok &= check("ready: lapis konklusif tapi ber-inconclusive_note -> False (CS tak dievaluasi)",
                v_note["8.1"]["layers"]["flashlight"]["conclusive"] is True
                and mod.compute_ready(v_note, ["static", "flashlight"]) is False)

    # 11c. Gerbang CLI --require (dulu NOL coverage: mutasi apa pun lolos senyap)
    def _cli(args_extra):
        with tempfile.TemporaryDirectory() as td:
            sp, op = Path(td) / "s.json", Path(td) / "o.json"
            sp.write_text(json.dumps(static), encoding="utf-8")
            cfg = _write_cfg(Path(td) / "c.json", ",".join(TV))
            r = subprocess.run(["uv", "run", str(MOD_PATH), "--static", str(sp),
                                "--config", cfg, "-o", str(op), *args_extra],
                               capture_output=True, text=True)
            out = json.loads(op.read_text(encoding="utf-8")) if op.exists() else None
            return r.returncode, r.stderr, out

    rc, _, out = _cli([])
    ok &= check("CLI default: KEEMPAT lapis diwajibkan (bukan 'yang kebetulan dijalankan')",
                out["required_layers"] == ["static", "flashlight", "adversarial", "e2e"])
    ok &= check("CLI default: static-only run -> ready False walau pass True (anti false-confidence)",
                out["pass"] is True and out["ready"] is False)
    rc, _, out = _cli(["--require", "static"])
    ok &= check("CLI --require static: penyempitan sadar -> ready True & terekam",
                out["ready"] is True and out["required_layers"] == ["static"])
    rc, err, _ = _cli(["--require", "static,ngawur"])
    ok &= check("CLI --require lapis tak dikenal -> exit 2 bersih (bukan KeyError Traceback exit 1)",
                rc == 2 and "ngawur" in err and "Traceback" not in err)
    # Container KOSONG (verifier adversarial): ',' itu truthy -> tak jatuh ke default ketat,
    # tapi memfilter jadi [] -> compute_ready mengiterasi nol lapis -> ready=true atas NOL
    # bukti, di runner tanpa Docker sekalipun. Gerbang dibatalkan dengan dua ketukan.
    for degen in (",", "   ", ",,,"):
        rc, err, out = _cli(["--require", degen])
        ok &= check(f"CLI --require {degen!r} (kosong sesudah filter) -> exit 2, bukan ready atas nol lapis",
                    rc == 2 and out is None and "tak menyebut satu lapis pun" in err)

    # 11. e2e_layer langsung: tanpa bukti -> findings kosong, tak konklusif
    lay_none = mod.e2e_layer(None, "8.1", BR)
    ok &= check("e2e_layer tanpa histori -> findings kosong & tak konklusif",
                lay_none["findings"] == [] and lay_none["conclusive"] is False
                and lay_none["state"] == "inconclusive")
    ok &= check("e2e_layer tanpa browser terkonfigurasi -> tak pernah lolos vakum",
                mod.e2e_layer({}, "8.1", [])["conclusive"] is False
                and mod.e2e_verdict({}, []) == ("inconclusive", "missing"))

    # 12. Field top-level E2E dari record TERPILIH (e2e_summary) — cakupan jujur.
    def _summary(cells_by_ver, browsers=BR, notes=()):
        cells = {v: _row(v, c, notes) for v, c in cells_by_ver.items()}
        return mod.e2e_summary(cells, list(cells_by_ver), browsers)

    smoke = _summary({"8.1": _both("8.1", authored_assertions=0)})
    ok &= check("E2E hanya smoke (authored 0 di semua record pass/fail) -> e2e_smoke_only True",
                smoke["e2e_smoke_only"] is True)
    authored = _summary({"8.1": _both("8.1")})
    ok &= check("E2E dgn assertion authored -> e2e_smoke_only False",
                authored["e2e_smoke_only"] is False)
    ok &= check("tanpa record pass/fail -> e2e_smoke_only False (tak ada klaim cakupan)",
                _summary({"8.1": {b: [] for b in BR}})["e2e_smoke_only"] is False)
    ok &= check("e2e_browsers = terkonfigurasi; e2e_browsers_run = engine yang men-drive",
                authored["e2e_browsers"] == BR and authored["e2e_browsers_run"] == BR)
    chrom_only = _summary({"8.1": {"chromium": [_rec("8.1", "chromium")], "firefox": []}})
    ok &= check("Chromium-only: e2e_browsers tetap kedua, e2e_browsers_run hanya chromium",
                chrom_only["e2e_browsers"] == BR and chrom_only["e2e_browsers_run"] == ["chromium"])
    notes_sum = _summary({"8.1": {"chromium": [_rec("8.1", "chromium", scenario_notes=["x.json: rusak"])],
                                  "firefox": [_rec("8.1", "firefox", scenario_notes=["x.json: rusak"])]}})
    ok &= check("e2e_scenario_notes dari record terpilih, tanpa duplikat",
                notes_sum["e2e_scenario_notes"] == ["x.json: rusak"])
    shots = _summary({"8.1": {
        "chromium": [_rec("8.1", "chromium", screenshots=[
            "/rep/e2e-shots/run-20261126-100000/8.1/chromium-s1-goto.png",
            "/rep/e2e-shots/run-20261126-100000/8.1/chromium-s1-fail.png"])],
        "firefox": [_rec("8.1", "firefox", screenshots=[
            "/rep/e2e-shots/run-20261126-110000/8.1/firefox-s1-goto.png"])]}})
    ok &= check("e2e_screenshot_dir = folder run berbeda dari record terpilih (list)",
                shots["e2e_screenshot_dir"] == ["/rep/e2e-shots/run-20261126-100000",
                                                "/rep/e2e-shots/run-20261126-110000"])
    nr = _summary({"8.1": {"chromium": [_rec("8.1", "chromium"),
                                        _rec("8.1", "chromium", state="not-run", conclusive=False,
                                             reason="fail-fast after 9.1:chromium")],
                           "firefox": [_rec("8.1", "firefox", state="not-run", conclusive=False,
                                            reason="fail-fast after 9.1:chromium"),
                                       _rec("8.1", "firefox")]}})
    ok &= check("not_run_cells = sel yang record TERBARU-nya not-run (bukan yang lebih tua)",
                nr["not_run_cells"] == [{"cell": "8.1:chromium",
                                         "reason": "fail-fast after 9.1:chromium"}])

    # e2e_phase_durations: tiap boot_id (keeper_boot termasuk) sekali; boot_id null tak menambah.
    pd = _summary({
        "8.1": {"chromium": [_rec("8.1", "chromium", boot_id="B1", boot_wall_clock=400.0)],
                "firefox": [_rec("8.1", "firefox", boot_id="B1", boot_wall_clock=400.0,
                                 wall_clock=111.0,
                                 keeper_boot={"boot_id": "K1", "boot_phases": {
                                     "baseline": {"seconds": 5.0, "outcome": "ok"}},
                                     "wall_clock": 900.0})]},
        "9.1": {"chromium": [_rec("9.1", "chromium", boot_id=None)],
                "firefox": [_rec("9.1", "firefox", boot_id="B2", boot_wall_clock=50.0)]}},
        )["e2e_phase_durations"]
    ok &= check("phase durations: boot_id sama dihitung sekali + keeper_boot ikut",
                sorted(pd["8.1"]["boots"]) == ["B1", "K1"]
                and pd["8.1"]["boots"]["B1"]["wall_clock"] == 400.0
                and pd["8.1"]["boots"]["K1"]["wall_clock"] == 900.0
                and "baseline" in pd["8.1"]["boots"]["K1"]["phases"])
    ok &= check("phase durations: browsers[...] = phase_durations + wall_clock sel",
                pd["8.1"]["browsers"]["firefox"]["wall_clock"] == 111.0
                and "browser:firefox" in pd["8.1"]["browsers"]["firefox"]["phases"]
                and "pull" in pd["8.1"]["boots"]["B1"]["phases"])
    ok &= check("phase durations: record ber-boot_id null tak menambah boots",
                list(pd["9.1"]["boots"]) == ["B2"] and len(pd["9.1"]["browsers"]) == 2)

    # 13. GERBANG CAKUPAN (analyze 2026-07-17-1024). Tiga sinyal "apakah ini benar-benar
    # diuji?" dihitung dengan benar lalu DIBUANG sebelum `ready` diputuskan. Satu kelas,
    # tiga seam — masing-masing diuji di titik yang dilewati produksi.

    # 13a. determinism-1 (CRITICAL): cakupan yang DINYATAKAN reviewer ditegakkan
    # ps-plan-layers (menolak reuse) tapi diabaikan skrip ini -> reviewer jujur yang bilang
    # "aku cuma meninjau 8.1" terbaca "ketiga versi bersih".
    adv_scope81 = {"versions": ["8.1"], "findings": []}
    r_in = mod.merge_version("8.1", static, None, adv_scope81, None)
    r_out = mod.merge_version("9.1", static, None, adv_scope81, None)
    ok &= check("adversarial: versi DALAM cakupan reviewer -> konklusif",
                r_in["layers"]["adversarial"]["conclusive"] is True)
    ok &= check("adversarial: versi DI LUAR cakupan -> tak konklusif (bukan diam-diam bersih)",
                r_out["layers"]["adversarial"]["conclusive"] is False
                and "tak ditinjau" in r_out["layers"]["adversarial"]["reason"])
    ok &= check("ready: versi tak ditinjau reviewer -> False (dulu True = klaim review yang tak terjadi)",
                mod.compute_ready({"9.1": r_out}, ["static", "adversarial"]) is False
                and mod.compute_ready({"8.1": r_in}, ["static", "adversarial"]) is True)
    adv_scope81_find = {"versions": ["8.1"], "findings": [
        {"id": "adv-g", "severity": "error", "message": "global"}]}
    ok &= check("temuan reviewer tak bocor ke versi yang tak ia tinjau",
                mod.merge_version("9.1", static, None, adv_scope81_find, None)["layers"]["adversarial"]["findings"] == [])
    ok &= check("cakupan superset (review penuh dipakai-ulang di run 9.1) -> konklusif",
                mod.merge_version("9.1", static, None, {"versions": TV, "findings": []},
                                  None)["layers"]["adversarial"]["conclusive"] is True)
    ok &= check("cakupan major-form '8' mencakup target '8.1'",
                mod.merge_version("8.1", static, None, {"versions": ["8"], "findings": []},
                                  None)["layers"]["adversarial"]["conclusive"] is True)

    # 13b. Gerbang skema cakupan di seam model->skrip.
    ok &= check("skema: 'versions' top-level absen -> pelanggaran (cakupan tak dinyatakan)",
                len(mod.validate_adversarial({"findings": []}, TV)) == 1)
    ok &= check("skema: 'versions' top-level kosong -> pelanggaran",
                len(mod.validate_adversarial({"versions": [], "findings": []}, TV)) == 1)
    ok &= check("skema: 'versions' top-level bukan list -> pelanggaran",
                len(mod.validate_adversarial({"versions": "8.1", "findings": []}, TV)) == 1)
    ok &= check("skema: token cakupan non-string -> pelanggaran",
                len(mod.validate_adversarial({"versions": [8], "findings": []}, TV)) == 1)
    # REGRESI (ketangkap saat mereproduksi fix ini): cakupan superset BUKAN pelanggaran —
    # menolaknya membuat file review penuh tak bisa dipakai-ulang di run yang dipersempit,
    # justru pemakaian-ulang itulah yang dibolehkan ps-plan-layers.
    ok &= check("skema: cakupan lebih luas dari target run ini -> BUKAN pelanggaran",
                mod.validate_adversarial({"versions": TV, "findings": []}, ["9.1"]) == [])
    # Token per-temuan diukur ke CAKUPAN, bukan target run (verifier adversarial): review
    # penuh yang dipakai-ulang di run 9.1 sah membawa temuan bertanda 8.1 — menolaknya
    # membuat gerbang ini bertengkar dgn cek cakupan di atas soal pertanyaan yang sama.
    ok &= check("skema: temuan bertanda 8.1 di review penuh yang dipakai-ulang di run 9.1 -> sah",
                mod.validate_adversarial({"versions": TV, "findings": [
                    {"id": "a1", "severity": "error", "message": "x", "versions": ["8.1"]}]},
                    ["9.1"]) == [])
    n_typo = mod.validate_adversarial({"versions": TV, "findings": [
        {"id": "a2", "severity": "error", "message": "x", "versions": ["PS8"]}]}, ["9.1"])
    ok &= check("skema: token ngawur tetap ditangkap walau cakupan luas",
                len(n_typo) == 1 and "PS8" in n_typo[0])

    # 13c. determinism-4: smoke-only (nol assertion authored) MENJATUHKAN ready — per sel
    # sekarang: not-gradeable tak pernah dihitung sbg bukti lulus.
    c_smoke = _both("8.1", authored_assertions=0)
    c_auth = _both("8.1")
    l_smoke = mod.e2e_layer(_row("8.1", c_smoke), "8.1", BR)
    ok &= check("e2e smoke-only -> inconclusive_note menyebut not-gradeable",
                "not-gradeable" in l_smoke.get("inconclusive_note", ""))
    ok &= check("e2e dgn assertion authored -> tanpa inconclusive_note",
                "inconclusive_note" not in mod.e2e_layer(_row("8.1", c_auth), "8.1", BR))
    ok &= check("ready: E2E smoke-only -> False walau lapis konklusif & lolos",
                l_smoke["conclusive"] is True
                and mod.compute_ready({"8.1": _merge("8.1", static, c_smoke)},
                                      ["static", "e2e"]) is False)
    ok &= check("ready: E2E dgn assertion authored di semua sel -> True",
                mod.compute_ready({"8.1": _merge("8.1", static, c_auth)}, ["static", "e2e"]) is True)
    ok &= check("e2e smoke-only tetap TAK memblok (`pass` buta konklusivitas)",
                _merge("8.1", static, c_smoke)["pass"] is True)
    ok &= check("satu assertion konklusif sudah cukup -> ready True (kontrol positif)",
                mod.compute_ready({"8.1": _merge("8.1", static, _both("8.1", authored_assertions=1))},
                                  ["static", "e2e"]) is True)
    # Hitungan yang salah bentuk = cakupan tak diketahui, BUKAN nol dan BUKAN teruji.
    for bad in (None, "3", [], True, -1):
        cb = _both("8.1")
        cb["chromium"] = [_rec("8.1", "chromium", authored_assertions=bad)]
        ok &= check(f"authored_assertions={bad!r} -> sel tanpa bukti lulus, ready False",
                    mod.compute_ready({"8.1": _merge("8.1", static, cb)}, ["static", "e2e"]) is False)

    # 13e. Error console = OBSERVASI (advisory), bukan celah cakupan: `ready` tak boleh
    # bergantung pada berisik-tidaknya skrip pihak-ketiga.
    c_noisy = _both("8.1", console_errors=3)
    l_noisy = mod.e2e_layer(_row("8.1", c_noisy), "8.1", BR)
    ok &= check("error console -> advisory_note, BUKAN inconclusive_note",
                "advisory_note" in l_noisy and "inconclusive_note" not in l_noisy)
    ok &= check("toko diam vs toko berisik -> ready SAMA (0 dan 3 error console)",
                mod.compute_ready({"8.1": _merge("8.1", static, c_noisy)}, ["static", "e2e"])
                is mod.compute_ready({"8.1": _merge("8.1", static, c_auth)}, ["static", "e2e"])
                is True)
    ok &= check("advisory menjumlah sel & menyebut cara menegakkannya",
                "6" in l_noisy["advisory_note"] and "expect_no_console_error" in l_noisy["advisory_note"])
    # Celah cakupan SUNGGUHAN di browser_notes tetap menjatuhkan ready.
    c_gap = _both("8.1")
    c_gap["firefox"] = [_rec("8.1", "firefox", browser_notes=["engine tak dijalankan: firefox"])]
    ok &= check("browser_notes -> reason browser-notes & ready jatuh (kanal cakupan utuh)",
                "browser-notes" in mod.e2e_layer(_row("8.1", c_gap), "8.1", BR).get("inconclusive_note", "")
                and mod.compute_ready({"8.1": _merge("8.1", static, c_gap)}, ["static", "e2e"]) is False)

    # 13d. determinism-6 (dikonversi, cell-contract > Aggregate): versi TERKONFIGURASI yang tak
    # ada di hasil static = belum terbukti (tak konklusif, ready false), BUKAN input error.
    def _cli_versions(static_payload, versions, *extra):
        with tempfile.TemporaryDirectory() as td:
            sp, op = Path(td) / "s.json", Path(td) / "o.json"
            sp.write_text(json.dumps(static_payload), encoding="utf-8")
            cfg = _write_cfg(Path(td) / "c.json", versions)
            rc, err = _run_main(["--static", str(sp), "--config", cfg, "-o", str(op),
                                 "--require", "static", *extra])
            return rc, err, (json.loads(op.read_text(encoding="utf-8")) if op.exists() else None)

    # Sibling absen (verifier adversarial): exec_module dulu meledak jadi traceback exit 1 —
    # kode yang SAMA dengan "module gagal validasi", jadi CI tak bisa membedakan folder
    # scripts/ yang tersalin sebagian dari module yang benar-benar punya error pemblokir.
    try:
        mod.load_sibling(Path("/nonexistent/ps-plan-layers.py"), "x")
        rc_sib = None
    except SystemExit as e:
        rc_sib = e.code
    ok &= check("sibling absen -> exit 2 (error input), BUKAN exit 1 yang bertabrakan dgn vonis-gagal",
                rc_sib == 2)

    static81 = static_result({"8.1": []})
    rc, err, out = _cli_versions(static81, "1.7.8,8.1,9.1")
    ok &= check("versi terkonfigurasi tak dipindai static -> exit != 2, tak konklusif, ready False",
                rc != 2 and out is not None and out["ready"] is False
                and out["versions"]["9.1"]["layers"]["static"]["conclusive"] is False
                and out["versions"]["9.1"]["ready"] is False
                and out["versions"]["8.1"]["ready"] is True and "Traceback" not in err)
    rc, _, out = _cli_versions(static81, "8.1")
    ok &= check("versi target sepenuhnya terpindai -> jalan normal & ready",
                rc == 0 and out["ready"] is True and out["target_versions"] == ["8.1"])
    rc, err, _ = _cli_versions(static81, "8.1", "--versions", "8.1,9.1")
    ok &= check("--versions beda dari psm_target_versions -> exit 2 menyebut keduanya",
                rc == 2 and "8.1,9.1" in err and "terkonfigurasi" in err)
    rc, _, out = _cli_versions(static_result({v: [] for v in TV}), "9.1,1.7.8,8.1",
                               "--versions", "8.1, 9.1,1.7.8")
    ok &= check("--versions sama sbg himpunan (urutan/spasi beda) -> diterima, urut numerik",
                rc == 0 and out["target_versions"] == ["1.7.8", "8.1", "9.1"])
    for bad_cfg in ("", "9.1,9.1.0", "nine"):
        rc, err, _ = _cli_versions(static81, bad_cfg)
        ok &= check(f"psm_target_versions {bad_cfg!r} tak sah (kosong/setara/bukan digit) -> exit 2",
                    rc == 2 and "Traceback" not in err)

    # 13d. CANARY phpstan (keputusan user 2026-07-17, opsi 1): laporan JSON phpstan tak bisa
    # membedakan "bersih" dari "tak menganalisis apa-apa" (map `files` cuma memuat file
    # ber-error), jadi module bisa MEMBELI vonis CS bersih lewat neon yang mengecualikan
    # dirinya sendiri. Kelas det-1 yang sama, di Lapis 2.
    fl_nocov = _flash_cs({"available": True, "parse_ok": True, "generated_config": False,
                          "coverage_ok": False, "errors": 0, "warnings": 0, "error_messages": []})
    ok &= check("phpstan tak menyentuh module -> inconclusive_note (0 error bukan bersih)",
                "tak menganalisis satu file pun"
                in mod.flashlight_layer(fl_nocov, "8.1").get("inconclusive_note", ""))
    ok &= check("phpstan tak menyentuh module -> ready jatuh, tapi TAK memblok",
                mod.compute_ready({"8.1": mod.merge_version("8.1", static, fl_nocov, None, None)},
                                  ["static", "flashlight"]) is False
                and mod.merge_version("8.1", static, fl_nocov, None, None)["pass"] is True)
    fl_cov = _flash_cs({"available": True, "parse_ok": True, "generated_config": False,
                        "coverage_ok": True, "errors": 0, "warnings": 0, "error_messages": []})
    ok &= check("phpstan benar-benar menganalisis module & bersih -> tanpa note, ready utuh "
                "(kontrol positif: gerbang tak menandai module bersih)",
                "inconclusive_note" not in mod.flashlight_layer(fl_cov, "8.1")
                and mod.compute_ready({"8.1": mod.merge_version("8.1", static, fl_cov, None, None)},
                                      ["static", "flashlight"]) is True)
    fl_old = _flash_cs({"available": True, "parse_ok": True, "generated_config": False,
                        "errors": 0, "warnings": 0, "error_messages": []})
    del fl_old["versions"]["8.1"]["coding_standard"]["coverage_ok"]
    ok &= check("file lapis lama tanpa coverage_ok -> tak bisa dipastikan, bukan bersih",
                "tak bisa dipastikan"
                in mod.flashlight_layer(fl_old, "8.1").get("inconclusive_note", ""))
    # determinism-2 (ronde-6): coverage_ok salah-tipe. Dulu `is False`+`not in` MELOLOSKAN
    # non-bool non-False (`"false"`/`0`/`1.5`/`[]`) sbg cakupan TERUJI (leak: ready=true palsu).
    # Kini _bool_fact identity-strict: hanya True yang fakta bersih; sisanya tak bisa dipastikan.
    for bad in ("false", 0, 1.5, [], 1):
        fl_bad = _flash_cs({"available": True, "parse_ok": True, "generated_config": False,
                            "coverage_ok": bad, "errors": 0, "warnings": 0, "error_messages": []})
        ok &= check(f"coverage_ok salah-tipe {bad!r} -> inconclusive_note (bukan cakupan teruji)",
                    "tak bisa dipastikan"
                    in mod.flashlight_layer(fl_bad, "8.1").get("inconclusive_note", ""))
    # Urutan cabang: parse_ok False tak pernah punya coverage_ok, jadi cabang "skrip lama"
    # akan menyalip pesan parse-gagal & menyalahkan file lapis atas laporan yang rusak.
    # determinism-3 (analyze ronde-5): auto-neon = OBSERVASI (phpstan BENAR-BENAR jalan, tapi
    # penegakan ditahan karena config-nya kami yang karang). Dulu `generated_config` diemit KHUSUS
    # untuk menandai itu lalu tak dibaca siapa pun & ke-N pesannya dibuang: run advisory jadi
    # byte-identik dgn run bersih yang DITEGAKKAN. Kanalnya sama dgn error console: disurface,
    # tak menggerbang.
    fl_adv = _flash_cs({"available": True, "parse_ok": True, "generated_config": True,
                        "coverage_ok": True, "errors": 0, "warnings": 2,
                        "error_messages": [{"line": 12, "message": "Call to undefined method Foo::bar()"},
                                           {"line": 3, "message": "bad"}]})
    l_adv = mod.flashlight_layer(fl_adv, "8.1")
    ok &= check("auto-neon -> advisory_note (bukan sinyal yatim) & sebut jalan keluarnya",
                "advisory_note" in l_adv and "phpstan.neon milik module" in l_adv["advisory_note"])
    ok &= check("auto-neon -> advisory TIDAK menjatuhkan ready (bukan celah cakupan)",
                "inconclusive_note" not in l_adv
                and mod.compute_ready({"8.1": mod.merge_version("8.1", static, fl_adv, None, None)},
                                      ["static", "flashlight"]) is True)
    ok &= check("auto-neon -> pesan phpstan sampai ke laporan sbg warning (dulu dibuang di lantai)",
                len([f for f in l_adv["findings"] if f["severity"] == "warning"]) == 2
                and any("undefined method" in f["message"] for f in l_adv["findings"])
                and l_adv["errors"] == 0 and l_adv["state"] == "pass")
    ok &= check("run advisory kini TERBEDAKAN dari run bersih yang ditegakkan (dulu byte-identik)",
                mod.flashlight_layer(fl_cov, "8.1") != l_adv
                and "advisory_note" not in mod.flashlight_layer(fl_cov, "8.1"))

    fl_parsefail = _flash_cs({"available": True, "parse_ok": False, "note": "gagal parse JSON phpstan"})
    note_pf = mod.flashlight_layer(fl_parsefail, "8.1").get("inconclusive_note", "")
    ok &= check("parse gagal tetap dilaporkan sbg parse gagal (cabang canary tak menyalip)",
                "gagal parse JSON phpstan" in note_pf and "skrip lama" not in note_pf)

    # 14. determinism-1 (analyze ronde-5, CRITICAL): static_layer dulu pin conclusive=True
    # dengan alasan "Lapis 1 selalu jalan". Benar tentang skripnya, salah tentang aturannya —
    # versi yang nol aturan menyentuhnya keluar 0 error lalu terbaca konklusif LOLOS.
    # Direproduksi vs skrip nyata: module ber-eval() dapat ready=true di --versions 1.6.
    st_zero = static_result({"8.1": []}, rules_evaluated=0)
    lay_zero = mod.static_layer(st_zero, "8.1")
    ok &= check("nol aturan dinilai -> inconclusive_note (0 error BUKAN lolos)",
                "inconclusive_note" in lay_zero and "nol aturan" in lay_zero["inconclusive_note"])
    ok &= check("nol aturan dinilai -> ready jatuh",
                mod.compute_ready({"8.1": mod.merge_version("8.1", st_zero, None, None, None)},
                                  ["static"]) is False)
    ok &= check("nol aturan dinilai -> `pass` TETAP buta konklusivitas (tak memblok)",
                mod.merge_version("8.1", st_zero, None, None, None)["pass"])

    # Kontrol positif: cabang di atas tak boleh menyala di run sehat, kalau tidak ia cuma
    # ready=false permanen dan tak membedakan apa pun.
    st_ok = static_result({"8.1": []})
    ok &= check("aturan benar-benar dinilai -> tak ada note, ready utuh",
                "inconclusive_note" not in mod.static_layer(st_ok, "8.1")
                and mod.compute_ready({"8.1": mod.merge_version("8.1", st_ok, None, None, None)},
                                      ["static"]) is True)

    # File lapis dari skrip lama tak punya angkanya sama sekali. ps-plan-layers MEMANG
    # memakai ulang file lapis lama, jadi "tak tercatat" harus gagal ke sisi jujur —
    # bukan diam-diam dianggap tercakup. Lapis 1 termurah; ulanginya nyaris gratis.
    st_old = static_result({"8.1": []})
    del st_old["versions"]["8.1"]["rules_evaluated"]
    ok &= check("file lapis lama tanpa rules_evaluated -> tak dipastikan, bukan diklaim lolos",
                "inconclusive_note" in mod.static_layer(st_old, "8.1")
                and mod.compute_ready({"8.1": mod.merge_version("8.1", st_old, None, None, None)},
                                      ["static"]) is False)

    # Seam kedua det-1, bentuk yang sama: main file tak resolve -> aturan `files: __MAIN__`
    # no-op TANPA sepatah kata, jadi lapis menilai lebih sedikit dari yang diklaimnya.
    st_nomain = static_result({"8.1": []}, main_file_found=False)
    ok &= check("main file tak resolve -> aturan __MAIN__ tak dinilai, disurface",
                "__MAIN__" in mod.static_layer(st_nomain, "8.1").get("inconclusive_note", "")
                and mod.compute_ready({"8.1": mod.merge_version("8.1", st_nomain, None, None, None)},
                                      ["static"]) is False)

    # 15. determinism-2 (ronde-5): himpunan versi KOSONG. `for m in {}.values()` tak pernah
    # jalan -> "semua versi terbukti" secara vakum -> ready=true atas NOL versi di gerbang
    # TERKETAT, di runner tanpa Docker. Kembaran `--require` kosong yang sudah digerbang
    # satu tingkat di bawah; seam ini dulu tak punya coverage sama sekali.
    ok &= check("compute_ready atas nol versi -> False (dibaca skill sibling, bukan cuma CLI)",
                mod.compute_ready({}, list(mod.LAYERS)) is False)
    # Dikonversi (cell-contract > Aggregate): static tanpa satu versi pun = versi terkonfigurasi
    # belum terbukti — tak konklusif & ready false, bukan exit 2. Daftar terkonfigurasi KOSONG
    # tetap exit 2 (normalizer), lihat 13d.
    rc, err, out = _cli_versions({"module": "m", "main_file_found": True, "versions": {},
                                  "pass": True}, "1.7.8,8.1,9.1")
    ok &= check("static tanpa satu versi pun -> exit != 2, tiap versi tak konklusif, ready False",
                rc != 2 and out is not None and out["ready"] is False
                and all(m["layers"]["static"]["conclusive"] is False
                        for m in out["versions"].values())
                and sorted(out["versions"]) == sorted(TV) and "Traceback" not in err)

    # 16. Refutasi verifier atas fix ronde-5 sendiri. (a) static_layer dulu tetap pin
    # `conclusive: True` sementara docstring-nya bilang cakupan sudah DIHITUNG — objek yang
    # sama memuat conclusive:true dan catatan yang bilang cakupan tak diketahui, dan yang
    # dipercaya pemanggil field-nya. Tak satu pun test menyentuh field ini, itu sebabnya
    # literal usang itu selamat.
    ok &= check("nol aturan dinilai -> layer.conclusive False (bukan cuma note)",
                mod.static_layer(st_zero, "8.1")["conclusive"] is False)
    ok &= check("aturan dinilai -> layer.conclusive True (kontrol positif)",
                mod.static_layer(st_ok, "8.1")["conclusive"] is True)

    # (b) gerbang menjaga NILAI, bukan TIPE: "0"/[]/true/-1 lolos lalu memulihkan ready=true —
    # kelas yang validate_extra_rules ada untuk menutup, direproduksi di checker yang ditulis
    # untuk mencegahnya. Absen & salah-bentuk sama-sama "cakupan tak diketahui".
    for bad in ("0", [], {}, True, -1, "dua belas", 1.5):
        st_bad = static_result({"8.1": []})
        st_bad["versions"]["8.1"]["rules_evaluated"] = bad
        ok &= check(f"rules_evaluated={bad!r} (salah tipe) -> tak dipastikan, bukan lolos",
                    "inconclusive_note" in mod.static_layer(st_bad, "8.1")
                    and mod.compute_ready({"8.1": mod.merge_version("8.1", st_bad, None, None, None)},
                                          ["static"]) is False)
    st_strfalse = static_result({"8.1": []}, main_file_found="false")
    ok &= check("main_file_found='false' (string JSON) -> tak lolos identity check `is False`",
                "__MAIN__" in mod.static_layer(st_strfalse, "8.1").get("inconclusive_note", ""))

    # (c) file lapis buatan SKRIP tak punya gerbang bentuk sama sekali, jadi file terpotong
    # meledak Traceback + exit 1 = kode "module punya error pemblokir". Alasan yang ditulis
    # validate_adversarial tak pernah khusus file buatan model.
    def _cli_static(payload):
        with tempfile.TemporaryDirectory() as td:
            sp = Path(td) / "s.json"
            sp.write_text(json.dumps(payload), encoding="utf-8")
            cfg = _write_cfg(Path(td) / "c.json", "8.1")
            p = subprocess.run(["uv", "run", str(MOD_PATH), "--static", str(sp),
                                "--config", cfg, "--require", "static"],
                               capture_output=True, text=True)
            return p.returncode, p.stderr
    malformed = {
        "payload list telanjang": ["bukan", "object"],
        "versions list": {"module": "m", "main_file_found": True, "versions": []},
        "entri versi string": {"module": "m", "main_file_found": True, "versions": {"8.1": "rusak"}},
        "findings string": {"module": "m", "main_file_found": True,
                            "versions": {"8.1": {"rules_evaluated": 3, "findings": "rusak"}}},
        "finding tanpa id": {"module": "m", "main_file_found": True,
                             "versions": {"8.1": {"rules_evaluated": 3, "findings": [{"severity": "error"}]}}},
    }
    for name, payload in malformed.items():
        rc, err = _cli_static(payload)
        ok &= check(f"file lapis rusak ({name}) -> exit 2, BUKAN Traceback exit 1 yang "
                    "bertabrakan dgn vonis-gagal",
                    rc == 2 and "Traceback" not in err)

    # 17. Sapuan orphan (analyze ronde-5 rank-2). (a) `ready` PER-VERSI dibaca KETIGA skill
    # sibling ("siap hanya bila ready true di 1.7.x, 8.x, dan 9.x") tapi diemit NOL produsen:
    # bukan cuma tak ditulis — TAK BISA dinyatakan, karena yang ada cuma satu ready global.
    # Model lalu membaca yang global & melaporkannya tiga kali = klaim per-versi palsu.
    st3 = static_result({"1.7.8": [], "8.1": [("cls-attribute", "error")], "9.1": []})
    with tempfile.TemporaryDirectory() as td:
        sp, op = Path(td) / "s.json", Path(td) / "o.json"
        sp.write_text(json.dumps(st3), encoding="utf-8")
        cfg = _write_cfg(Path(td) / "c.json", "1.7.8,8.1,9.1")
        subprocess.run(["uv", "run", str(MOD_PATH), "--static", str(sp), "--config", cfg,
                        "--versions", "1.7.8,8.1,9.1", "--require", "static", "-o", str(op)],
                       capture_output=True, text=True)
        v3 = json.loads(op.read_text(encoding="utf-8"))
    ok &= check("`ready` per-versi diemit (kontrak 3 sibling akhirnya bisa dinyatakan)",
                all("ready" in m for m in v3["versions"].values()))
    ok &= check("`ready` per-versi MEMBEDAKAN versi (8.1 gagal, dua lainnya siap)",
                v3["versions"]["8.1"]["ready"] is False
                and v3["versions"]["1.7.8"]["ready"] is True
                and v3["versions"]["9.1"]["ready"] is True)
    ok &= check("`ready` keseluruhan = AND dari per-versi (satu pemilik, tak bisa beda pendapat)",
                v3["ready"] is False)
    # (b) Rollup error/warning per-versi: SKILL.md & psm-scaffold disuruh membacanya "apa
    # adanya", tapi satu-satunya `warnings` yang ada milik lapis static -> warning
    # adversarial/flashlight tak terhitung. Kanal warning BARU dari fix advisory auto-neon
    # bahkan tak punya penghitung sejak lahir.
    adv_warn = {"versions": ["8.1"], "findings": [
        {"id": "a1", "severity": "warning", "message": "harga tak divalidasi", "versions": ["8.1"]}]}
    m_w = mod.merge_version("8.1", static_result({"8.1": [("x", "warning")]}), fl_adv, adv_warn, None)
    ok &= check("rollup per-versi menghitung warning dari SEMUA lapis (static+adversarial+advisory)",
                m_w["warnings"] == 4 and m_w["errors"] == 0)
    ok &= check("rollup errors per-versi = jumlah temuan yang memblok",
                mod.merge_version("8.1", static_bad, None, None, None)["errors"] == 1)
    # (c) `--require` yang menyempit dulu MELEWATI konklusivitas static sepenuhnya -> ready=true
    # atas versi yang nol aturan pernah menyentuhnya, dan satu-satunya yang mencatatnya
    # (`conclusive` per-versi) tak dibaca gerbang mana pun.
    st_nobase = static_result({"8.1": []}, rules_evaluated=0)
    m_nb = _merge("8.1", st_nobase, _both("8.1"))
    ok &= check("versi tanpa vonis DASAR -> tak siap walau lapis yang diwajibkan konklusif",
                m_nb["conclusive"] is False
                and mod.version_ready(m_nb, ["e2e"]) is False
                and mod.compute_ready({"8.1": m_nb}, ["e2e"]) is False)
    ok &= check("versi ber-vonis dasar & lapis wajib konklusif -> siap (gerbang tak kelebihan sapu)",
                mod.version_ready(_merge("8.1", static, _both("8.1")), ["e2e"]) is True)

    # 18. Sinyal yatim sisa dari inventaris: bukti ditangkap lalu menganggur di file lapis
    # sementara vonisnya menyuruh operator mencarinya sendiri.
    fl_boot = {"module": "m", "docker_available": True, "status": "ran",
               "versions": {"8.1": {"version": "8.1", "image": "img",
                                    "errors": ["flashlight tak jadi healthy (timeout)"],
                                    "boot_log": "nginx: [emerg] bind() to 0.0.0.0:80 failed",
                                    "install": None, "pass": False}}}
    l_boot = mod.flashlight_layer(fl_boot, "8.1")
    ok &= check("boot_log ikut ke alasan tak-konklusif (kegagalan boot paling sulit didiagnosis)",
                l_boot["conclusive"] is False and "bind() to 0.0.0.0:80" in l_boot["reason"])
    e2e_boot = {b: [_rec("8.1", b, state="inconclusive", conclusive=False, reason="errors",
                         errors=["container tak healthy"], boot_log="php-fpm: gagal start",
                         install=None, phase_durations={}, findings=None,
                         authored_assertions=None)] for b in BR}
    m_boot = _merge("8.1", static, e2e_boot)
    ok &= check("boot_log Lapis 4 juga terikat (ekor log ikut ke reason layers.e2e)",
                "php-fpm: gagal start" in m_boot["layers"]["e2e"]["reason"])
    ok &= check("reason per-versi tetap nilai kontrak murni (tanpa ekor log)",
                m_boot["reason"] == "inconclusive" and m_boot["e2e_state"] == "inconclusive")
    fl_ifail = _flash_cs({"available": False})
    fl_ifail["versions"]["8.1"]["install"] = {"ok": False, "no_console": False, "no_psroot": False,
                                              "no_verdict": False,
                                              "log": "CRITICAL Error thrown while running command"}
    f_inst = [f for f in mod.flashlight_layer(fl_ifail, "8.1")["findings"]
              if f["id"] == "flashlight-install"]
    ok &= check("install.log ikut ke temuan install-fail (vonis membawa buktinya, bukan menyuruh cari)",
                len(f_inst) == 1 and "Error thrown while running command" in f_inst[0]["fix"])
    # enh-3 (ronde-6): no_verdict memisahkan "installer MENOLAK module" (memblok) dari
    # "installer tak pernah mencapai vonisnya: exec mati / output terpotong" (infra). Dulu
    # keduanya jatuh ke ok=False -> temuan memblok "modul gagal install" = infra dijual sbg vonis.
    fl_nv = _flash_cs({"available": False})
    fl_nv["versions"]["8.1"]["install"] = {"ok": False, "no_console": False, "no_psroot": False,
                                           "no_verdict": True, "log": "Container is not running"}
    l_nv = mod.flashlight_layer(fl_nv, "8.1")
    ok &= check("install no_verdict (exec mati) -> infra tak-konklusif TANPA temuan memblok",
                l_nv["conclusive"] is False and l_nv["findings"] == []
                and "tak mencapai vonis" in l_nv["reason"])
    fl_rej = _flash_cs({"available": False})
    fl_rej["versions"]["8.1"]["install"] = {"ok": False, "no_console": False, "no_psroot": False,
                                            "no_verdict": False, "log": "module rejected by core"}
    l_rej = mod.flashlight_layer(fl_rej, "8.1")
    ok &= check("install ditolak (no_verdict False = PSM_INSTALL_FAIL diemit) -> temuan konklusif memblok",
                any(f["id"] == "flashlight-install" for f in l_rej["findings"]))
    # verifier ronde-6 (seam KELIMA install.ok): sibling `no_verdict` dijaga _bool_fact, tapi
    # `ok` (sinyal install PRIMER) dulu truthiness telanjang -> ok="false"/0/1 (truthy/falsy
    # non-bool) bikin install GAGAL terbaca SUKSES (ready UP palsu) atau sukses -> gagal. Kelas
    # yang sama dgn coverage_ok. Kini _bool_fact: hanya bool asli fakta; sisanya tak dipastikan.
    for bad in ("false", 0, 1, 1.5, [], None):
        fl_ok = _flash_cs({"available": False})
        fl_ok["versions"]["8.1"]["install"] = {"ok": bad, "no_console": False, "no_psroot": False,
                                               "no_verdict": False, "log": "x"}
        l_ok = mod.flashlight_layer(fl_ok, "8.1")
        ok &= check(f"install.ok salah-tipe {bad!r} -> infra tak-konklusif, BUKAN pass/memblok",
                    l_ok["conclusive"] is False and l_ok["findings"] == [])
        # Seam kembar E2E: state record dihitung ps-run-layer (derive_state); install.ok yang
        # bukan True TAK PERNAH jadi pass/fail di sana.
        ok &= check(f"derive_state E2E: install.ok salah-tipe {bad!r} -> inconclusive (seam kembar)",
                    pl.derive_state({"install": {"ok": bad}, "errors": [], "findings": [],
                                     "phase_durations": {"browser:chromium": {}}},
                                    "chromium")["conclusive"] is False)
    # REFUTASI verifier (backward-compat): file lapis LAMA (ps-plan-layers reuse) mencatat
    # exec-mati sbg install {ok:False} TANPA no_verdict. Truthiness telanjang dulu -> None
    # falsy -> vonis MEMBLOK "modul gagal install" tanpa note = persis bug enh-3 yang tak
    # termitigasi utk seam reuse. Kini identity-strict (is not False) + cabang skrip-lama.
    fl_old = _flash_cs({"available": False})
    fl_old["versions"]["8.1"]["install"] = {"ok": False, "no_console": False, "no_psroot": False,
                                            "log": "boom"}  # sengaja TANPA no_verdict
    l_old = mod.flashlight_layer(fl_old, "8.1")
    ok &= check("file lapis lama (no_verdict absen) + ok False -> infra tak-konklusif, BUKAN memblok",
                l_old["conclusive"] is False and l_old["findings"] == []
                and "skrip lama" in l_old["reason"])
    # REFUTASI verifier (gerbang NILAI vs TIPE, kelas yang membunuh penulis di ronde-5):
    # no_verdict salah-tipe harus "tak bisa dipastikan", konsisten dgn coverage_ok/
    # rules_evaluated/authored_assertions — bukan truthiness ("false" ditelan, []/{} memblok).
    for bad in ("false", [], {}, 1, -1):
        fl_bad = _flash_cs({"available": False})
        fl_bad["versions"]["8.1"]["install"] = {"ok": False, "no_console": False,
                                                "no_psroot": False, "no_verdict": bad, "log": "x"}
        l_bad = mod.flashlight_layer(fl_bad, "8.1")
        ok &= check(f"no_verdict salah-tipe {bad!r} -> infra tak-konklusif, BUKAN memblok (identity-strict)",
                    l_bad["conclusive"] is False and l_bad["findings"] == [])
    fl_loc = _flash_cs({"available": True, "parse_ok": True, "generated_config": False,
                        "coverage_ok": True, "errors": 1,
                        "error_messages": [{"line": 42, "message": "boom",
                                            "file": "/var/www/html/modules/m/m.php"}]})
    ok &= check("lokasi phpstan = file:line, bukan 'line 42' telanjang (file dulu tak dibaca)",
                mod.flashlight_layer(fl_loc, "8.1")["findings"][0]["location"]
                == "/var/www/html/modules/m/m.php:42")
    ok &= check("tanpa `file` -> tetap degrade ke 'line N' (bukan crash / 'None:42')",
                mod._phpstan_loc({"line": 7}) == "line 7")

    # Identitas bukti DITURUNKAN, bukan diketik. Dulu empat path diketik model di akhir run
    # panjang dan `module` cuma dibaca dari payload static — satu salah ketik di folder yang
    # memuat beberapa module diam-diam mengkreditkan bukti module lain ke `ready`.
    with tempfile.TemporaryDirectory() as td:
        rep = Path(td)
        cfg91 = _write_cfg(rep / "cfg-91.json", "9.1")
        sres = static_result({"9.1": []})
        sres["module"] = "mymod"
        (rep / "mymod-static.json").write_text(json.dumps(sres), encoding="utf-8")
        (rep / "mymod-flashlight.json").write_text(json.dumps(
            {"module": "mymod", "status": "ran", "pass": True,
             "versions": {"9.1": {"pass": True, "install": {"ok": True}}}}), encoding="utf-8")
        modir = rep / "mymod"; modir.mkdir()

        r = subprocess.run(["uv", "run", str(MOD_PATH), "--reports-dir", str(rep),
                            "--module", str(modir), "--config", cfg91],
                           capture_output=True, text=True)
        ok &= check("--reports-dir + --module: path lapis diturunkan (tak diketik)",
                    r.returncode in (0, 1) and "Traceback" not in r.stderr)
        written = sorted(x.name for x in rep.glob("mymod-2*.json"))
        ok &= check("nama output berstempel diturunkan di dalam skrip (model tak mengarang jam)",
                    len(written) == 1)
        if written:
            got = json.loads((rep / written[0]).read_text())
            # layers_run = {lapis: bool}. Yang diuji: file yang ADA terbaca, yang ABSEN
            # tak dikarang jadi lapis yang jalan.
            ok &= check("lapis yang PUNYA file terbaca, yang absen tak dikarang",
                        got["layers_run"]["static"] is True
                        and got["layers_run"]["e2e"] is False
                        and got["layers_run"]["adversarial"] is False)
            (rep / written[0]).unlink()

        # Gerbang identitas: bukti module lain ditolak, bukan dikreditkan.
        (rep / "mymod-flashlight.json").write_text(json.dumps(
            {"module": "modul-lain", "status": "ran", "pass": True,
             "versions": {"9.1": {"pass": True, "install": {"ok": True}}}}), encoding="utf-8")
        rc2, err2 = _run_main(["--reports-dir", str(rep), "--module", str(modir),
                               "--config", cfg91, "-o", str(rep / "o2.json")])
        ok &= check("file lapis milik module lain -> exit 2, bukan vonis",
                    rc2 == 2 and "modul-lain" in err2)
        (rep / "mymod-flashlight.json").write_text(json.dumps(
            {"module": "mymod", "status": "ran", "pass": True,
             "versions": {"9.1": {"pass": True, "install": {"ok": True}}}}), encoding="utf-8")

        # psm-config.json ada di reports tapi --config absen -> exit 2 (tak menyempit diam-diam
        # ke default skrip); kontrol: dgn --config jalan.
        pc = rep / "psm-config.json"
        had = pc.exists()
        if not had:
            pc.write_text('{"psm_target_versions": "1.7.6,9.1"}', encoding="utf-8")
        rc_nc, err_nc = _run_main(["--reports-dir", str(rep), "--module", str(modir),
                                   "-o", str(rep / "onc.json")])
        ok &= check("aggregate: psm-config.json di reports tanpa --config -> exit 2 menyebut --config",
                    rc_nc == 2 and "--config" in err_nc)
        if not had:
            pc.unlink()

        # File E2E LAMA (<module>-e2e.json / -e2e-<ver>.json) DIABAIKAN — bukan bukti, dan
        # tak bisa memicu gerbang apa pun: setelah upgrade tiap sel `missing` sampai dibuktikan ulang.
        claim = {"module": "modul-lain", "status": "ran", "e2e_available": True, "pass": True,
                 "versions": {"9.1": {"pass": True, "conclusive": True, "install": {"ok": True},
                                      "browsers": BR, "findings": [], "authored_assertions": 5}}}
        (rep / "mymod-e2e.json").write_text(json.dumps(claim), encoding="utf-8")
        (rep / "mymod-e2e-9.1.json").write_text(json.dumps(claim), encoding="utf-8")
        rc3, err3 = _run_main(["--reports-dir", str(rep), "--module", str(modir),
                               "--config", cfg91, "--require", "static,e2e",
                               "-o", str(rep / "o3.json")])
        got3 = json.loads((rep / "o3.json").read_text()) if (rep / "o3.json").exists() else {}
        ok &= check("file e2e lama diabaikan: tak exit 2, layers_run.e2e False, sel missing, ready False",
                    rc3 in (0, 1) and "modul-lain" not in err3
                    and got3.get("layers_run", {}).get("e2e") is False
                    and got3.get("ready") is False
                    and all(c["reason"] == "missing" for c in got3["e2e_cells"]["9.1"].values()))

        # Flag eksplisit tetap menang atas derivasi. Isinya harus BEDA dari file turunan:
        # turunan hanya punya 9.1, alt hanya 8.1 — versi target dari config (8.1).
        alt = rep / "alt-static.json"
        alt_res = static_result({"8.1": []})
        alt_res["module"] = "mymod"
        alt.write_text(json.dumps(alt_res), encoding="utf-8")
        cfg81 = _write_cfg(rep / "cfg-81.json", "8.1")
        r4 = subprocess.run(["uv", "run", str(MOD_PATH), "--reports-dir", str(rep),
                             "--module", str(modir), "--static", str(alt), "--config", cfg81,
                             "-o", str(rep / "out.json")], capture_output=True, text=True)
        got4 = json.loads((rep / "out.json").read_text()) if (rep / "out.json").exists() else {}
        ok &= check("--static eksplisit menang atas nama turunan (8.1 konklusif dari alt)",
                    r4.returncode in (0, 1) and list(got4.get("versions", {})) == ["8.1"]
                    and got4["versions"]["8.1"]["layers"]["static"]["conclusive"] is True)

        r5 = subprocess.run(["uv", "run", str(MOD_PATH), "--reports-dir", str(rep)],
                            capture_output=True, text=True)
        ok &= check("--reports-dir tanpa --module -> exit 2 (pasangan tak boleh separuh)",
                    r5.returncode == 2)
        r6 = subprocess.run(["uv", "run", str(MOD_PATH)], capture_output=True, text=True)
        ok &= check("tanpa --static & tanpa pasangan -> exit 2 berpesan, bukan Traceback",
                    r6.returncode == 2 and "Traceback" not in r6.stderr)

    # Lapis 5 (skenario kondisi-rusak) menggerbang HANYA bila module mengapalkan skenario.
    # Memaksanya ke tiap module akan menjatuhkan `ready` semua module lama demi lapis yang
    # belum mereka pakai; sebaliknya, yang MENYATAKAN skenario wajib melewatinya.
    with tempfile.TemporaryDirectory() as td:
        rep = Path(td)
        sres = static_result({"9.1": []})
        sres["module"] = "m"
        sp = rep / "m-static.json"
        sp.write_text(json.dumps(sres), encoding="utf-8")
        cfg_sc = _write_cfg(rep / "c.json", "9.1")

        def _agg(*extra):
            outp = rep / "out.json"
            _run_main(["--static", str(sp), "--config", cfg_sc, "-o", str(outp), *extra])
            return json.loads(outp.read_text())

        def _scen(sources, scen_ok, conclusive=True):
            sc = {"module": "m", "layer": "scenario", "status": "ran", "pass": scen_ok,
                  "scenario_sources": sources, "scenario_notes": [],
                  "versions": {"9.1": {"conclusive": conclusive, "pass": scen_ok, "scenarios": [
                      {"name": "dup", "source": "dup.json", "ok": scen_ok,
                       "conclusive": conclusive,
                       "steps": [] if scen_ok else [{"phase": "then", "ok": False,
                                                     "detail": "dapat='2' harap='1'"}]}]}}}
            q = rep / "m-scenario.json"
            q.write_text(json.dumps(sc), encoding="utf-8")
            return str(q)

        d = _agg()
        ok &= check("tanpa lapis skenario -> tak masuk required (module lama tak terdampak)",
                    "scenario" not in d["required_layers"]
                    and d["layers_run"]["scenario"] is False)

        d = _agg("--scenario", _scen(["dup.json"], True))
        ok &= check("module mengapalkan skenario & lolos -> scenario MASUK required",
                    "scenario" in d["required_layers"]
                    and d["scenario_conclusive"] is True
                    and d["versions"]["9.1"]["layers"]["scenario"]["conclusive"] is True)

        d = _agg("--scenario", _scen(["dup.json"], False))
        v = d["versions"]["9.1"]
        ok &= check("skenario gagal -> pass False & temuan memblok ber-id scenario-*",
                    d["pass"] is False and v["errors"] >= 1
                    and any(f["id"].startswith("scenario-") for f in v["blocking"]))
        ok &= check("temuan skenario membawa langkah yang gagal sbg fix (bukan pesan hampa)",
                    any("harap" in (f.get("fix") or "") for f in v["blocking"]))

        d = _agg("--scenario", _scen([], True, conclusive=False))
        ok &= check("file ada tapi nol skenario -> TAK menggerbang (nol bukti bukan lolos)",
                    "scenario" not in d["required_layers"]
                    and d["versions"]["9.1"]["layers"]["scenario"]["conclusive"] is False)

        d = _agg("--scenario", _scen(["dup.json"], True, conclusive=False))
        ok &= check("skenario tak konklusif -> menggerbang tapi ready jatuh (bukan pass senyap)",
                    "scenario" in d["required_layers"] and d["ready"] is False)

    # === Lapis 4 lewat CLI atas histori NYATA (append_record + fingerprint module asli) ===

    # AC1: config 3x2, static konklusif, enam sel pass gate-grade passing -> ready.
    with tempfile.TemporaryDirectory() as td:
        env = Env(td)
        for v in TV:
            env.add(v, "chromium", boot_id=f"B-{v}")
            env.add(v, "firefox", boot_id=f"B-{v}" if v != "8.1" else "B-8.1-ff")
        rc, err, out = env.run()
        ok &= check("AC1: enam sel lulus gate-grade + --require static,e2e -> ready True",
                    rc == 0 and out is not None and out["ready"] is True)
        ok &= check("AC1: tiap entri e2e_cells gate_grade True, reason null",
                    out is not None and all(c["gate_grade"] is True and c["reason"] is None
                                            and c["state"] == "pass"
                                            for row in out["e2e_cells"].values()
                                            for c in row.values()))
        ok &= check("AC1: e2e_phase_durations[ver].boots = satu key per boot_id berbeda",
                    out is not None
                    and sorted(out["e2e_phase_durations"]["9.1"]["boots"]) == ["B-9.1"]
                    and sorted(out["e2e_phase_durations"]["8.1"]["boots"]) == ["B-8.1", "B-8.1-ff"]
                    and sorted(out["e2e_phase_durations"]["1.7.8"]["browsers"]) == BR)
        ok &= check("AC1: per versi e2e_state pass, reason null, e2e_conclusive True",
                    out is not None and out["e2e_conclusive"] is True
                    and all(m["e2e_state"] == "pass" and m["reason"] is None
                            for m in out["versions"].values()))
        ok &= check("AC1: layers_run.e2e True, not_run_cells kosong, e2e_browsers terkonfigurasi",
                    out is not None and out["layers_run"]["e2e"] is True
                    and out["not_run_cells"] == [] and out["e2e_browsers"] == BR
                    and out["e2e_browsers_run"] == BR and out["e2e_smoke_only"] is False)

        # AC2 (fail): sel keenam punya gate-grade fail TERBARU.
        env.fail("9.1", "firefox")
        rc, err, out = env.run()
        ok &= check("AC2 fail: ready False, e2e_cells 9.1:firefox reason fail",
                    out is not None and out["ready"] is False
                    and out["e2e_cells"]["9.1"]["firefox"]["reason"] == "fail"
                    and out["e2e_cells"]["9.1"]["firefox"]["state"] == "fail")
        ok &= check("AC2 fail: versi 9.1 e2e_state fail & reason literal fail, memblok (exit 1)",
                    rc == 1 and out["versions"]["9.1"]["e2e_state"] == "fail"
                    and out["versions"]["9.1"]["reason"] == "fail"
                    and out["versions"]["9.1"]["pass"] is False
                    and out["versions"]["8.1"]["ready"] is True)

    # AC2 (missing): lima sel lulus, sel keenam tanpa record sama sekali.
    with tempfile.TemporaryDirectory() as td:
        env = Env(td)
        for v in TV:
            for b in BR:
                if (v, b) != ("1.7.8", "firefox"):
                    env.add(v, b)
        rc, err, out = env.run()
        ok &= check("AC2 missing: ready False, e2e_cells 1.7.8:firefox reason missing, state null",
                    out is not None and out["ready"] is False
                    and out["e2e_cells"]["1.7.8"]["firefox"] == {
                        "state": None, "gate_grade": False, "reason": "missing", "findings": [],
                        "parallel_only": None})
        ok &= check("AC2 missing: versi 1.7.8 inconclusive/missing, tak memblok (exit 0)",
                    rc == 0 and out["versions"]["1.7.8"]["e2e_state"] == "inconclusive"
                    and out["versions"]["1.7.8"]["reason"] == "missing"
                    and "1.7.8:firefox (missing)"
                    in out["versions"]["1.7.8"]["layers"]["e2e"]["inconclusive_note"])
        rc, _, out_s = env.run(require="static")
        ok &= check("gating tanpa e2e (--require static) tetap mungkin -> ready True",
                    out_s is not None and out_s["ready"] is True)

    # Chromium-only (I/O matrix): config 3x2, hanya chromium lulus -> firefox missing di tiga versi.
    with tempfile.TemporaryDirectory() as td:
        env = Env(td)
        env.seed_all(browsers=["chromium"])
        rc, err, out = env.run()
        ok &= check("Chromium-only: ready False, firefox missing di ketiga versi",
                    out is not None and out["ready"] is False
                    and all(out["e2e_cells"][v]["firefox"]["reason"] == "missing" for v in TV)
                    and all(out["versions"][v]["reason"] == "missing" for v in TV))
        ok &= check("Chromium-only: e2e_browsers_run hanya chromium (penyempitan terekam)",
                    out["e2e_browsers"] == BR and out["e2e_browsers_run"] == ["chromium"])

    # Headless narrowed (I/O matrix): config hanya 9.1 -> ready & versions hanya sel 9.1.
    with tempfile.TemporaryDirectory() as td:
        env = Env(td, versions="9.1", static_versions=TV)
        env.add("9.1", "chromium")
        env.add("9.1", "firefox")
        env.fail("8.1", "chromium")  # histori versi di luar config tak pernah dibaca
        rc, err, out = env.run()
        ok &= check("Headless narrowed: config 9.1 -> versions & e2e_cells hanya 9.1, ready True",
                    rc == 0 and out is not None and list(out["versions"]) == ["9.1"]
                    and list(out["e2e_cells"]) == ["9.1"] and out["ready"] is True
                    and out["target_versions"] == ["9.1"])
        rc, err, _ = env.run("--versions", "9.1,8.1")
        ok &= check("Headless narrowed: --versions lebih luas dari config -> exit 2", rc == 2)

    # Warm / partial / not-run lewat histori: tak pernah gate-grade, tak menyembunyikan apa pun.
    with tempfile.TemporaryDirectory() as td:
        env = Env(td, versions="8.1,9.1")
        env.add("9.1", "chromium")
        env.add("9.1", "chromium", boot="warm", boot_id="W1#r1")
        env.add("9.1", "firefox")
        env.add("9.1", "firefox", state="not-run", conclusive=False,
                reason="fail-fast after 8.1:chromium", install=None, phase_durations={},
                findings=None, authored_assertions=None, boot_id=None)
        env.add("8.1", "chromium", _fail("8.1", "chromium", fp=env.fp, scenario_set="partial"))
        env.add("8.1", "firefox", boot="warm")
        rc, err, out = env.run()
        c = out["e2e_cells"] if out else {}
        ok &= check("warm/not-run lebih baru: 9.1 tetap punya bukti lulus (record lama terpilih)",
                    out is not None and c["9.1"]["chromium"]["reason"] is None
                    and c["9.1"]["chromium"]["gate_grade"] is True
                    and c["9.1"]["firefox"]["reason"] is None
                    and out["versions"]["9.1"]["e2e_state"] == "pass")
        ok &= check("not_run_cells memuat sel yang record terbarunya not-run",
                    out is not None and out["not_run_cells"] == [
                        {"cell": "9.1:firefox", "reason": "fail-fast after 8.1:chromium"}])
        ok &= check("partial fail: temuan di e2e_cells tapi TAK memblok 8.1; warm-only alasannya",
                    out is not None and len(c["8.1"]["chromium"]["findings"]) == 1
                    and c["8.1"]["chromium"]["gate_grade"] is False
                    and out["versions"]["8.1"]["pass"] is True
                    and out["versions"]["8.1"]["e2e_state"] == "inconclusive"
                    and c["8.1"]["firefox"]["reason"] == "warm-only" and out["ready"] is False)
        ok &= check("phase durations memakai record TERPILIH (bukan warm/not-run terbaru)",
                    out is not None and list(out["e2e_phase_durations"]["9.1"]["boots"]) == ["boot-9.1"])

    # Corrupt history: baris rusak terakhir -> corrupt-history, tanpa bukti lulus.
    with tempfile.TemporaryDirectory() as td:
        env = Env(td, versions="9.1")
        env.add("9.1", "chromium")
        env.add("9.1", "firefox")
        with open(env.path("9.1", "chromium"), "ab") as f:
            f.write(b'{"version": "9.1", "browser": "chrom')  # penulis terbunuh di tengah baris
        rc, err, out = env.run()
        ok &= check("corrupt-history: baris terakhir rusak -> reason corrupt-history, ready False",
                    out is not None and out["e2e_cells"]["9.1"]["chromium"]["reason"] == "corrupt-history"
                    and out["e2e_cells"]["9.1"]["chromium"]["state"] == "pass"
                    and out["ready"] is False and out["versions"]["9.1"]["reason"] == "corrupt-history")
        env.add("9.1", "chromium")  # append sesudah baris rusak -> valid lagi
        rc, err, out = env.run()
        ok &= check("corrupt di tengah (valid, rusak, valid) -> terbaca, bukti lulus pulih",
                    out is not None and out["e2e_cells"]["9.1"]["chromium"]["reason"] is None
                    and out["ready"] is True)
        env.path("9.1", "firefox").write_bytes(b"bukan json\n")
        rc, err, out = env.run()
        ok &= check("histori HANYA baris rusak -> state null, reason corrupt-history",
                    out is not None and out["e2e_cells"]["9.1"]["firefox"]["state"] is None
                    and out["e2e_cells"]["9.1"]["firefox"]["reason"] == "corrupt-history")
        env.path("9.1", "firefox").unlink()
        env.path("9.1", "firefox").mkdir()  # error OS saat membaca histori
        rc, err, out = env.run()
        ok &= check("error OS membaca histori -> exit 2 menyebut path-nya",
                    rc == 2 and "mymod-e2e-9.1-firefox.jsonl" in err and "Traceback" not in err)

    # Stale: fail di fingerprint lama -> stale-fail; pass lama -> stale-source; tag beda -> stale-tag.
    with tempfile.TemporaryDirectory() as td:
        env = Env(td, versions="8.1,9.1")
        env.add("9.1", "chromium", _fail("9.1", "chromium", fp="0" * 64))
        env.add("9.1", "firefox", _rec("9.1", "firefox", "0" * 64))
        env.add("8.1", "chromium", image_tag="8.1.0-lama")
        env.add("8.1", "firefox")
        rc, err, out = env.run()
        c = out["e2e_cells"] if out else {}
        ok &= check("stale-fail: fail di fingerprint lama -> reason stale-fail (bukan stale-source)",
                    out is not None and c["9.1"]["chromium"]["reason"] == "stale-fail"
                    and out["versions"]["9.1"]["reason"] == "stale-fail")
        ok &= check("stale: pass lama -> stale-source; tag beda -> stale-tag; basi tak memblok",
                    out is not None and c["9.1"]["firefox"]["reason"] == "stale-source"
                    and c["8.1"]["chromium"]["reason"] == "stale-tag"
                    and out["pass"] is True and out["ready"] is False)
        # Tag dari config (psm_flashlight_tag_map) & --tag-map: dinilai seperti plan/runner.
        cfg_tag = _write_cfg(env.root / "cfg-tag.json", "8.1,9.1",
                             psm_flashlight_tag_map="1.7.8=1.7.8.11,8.1=8.1.0-lama,9.1=9.1.4-nginx")
        rc, err, out = env.run("--config", cfg_tag, config=False)
        ok &= check("psm_flashlight_tag_map dari --config -> record bertag itu segar, tag default basi",
                    out is not None and out["e2e_cells"]["8.1"]["chromium"]["reason"] is None
                    and out["e2e_cells"]["8.1"]["firefox"]["reason"] == "stale-tag")
        rc, err, out = env.run("--config", cfg_tag, "--tag-map",
                               "1.7.8=1.7.8.11,8.1=8.1.6-nginx,9.1=9.1.4-nginx", config=False)
        ok &= check("--tag-map menang atas psm_flashlight_tag_map",
                    out is not None and out["e2e_cells"]["8.1"]["firefox"]["reason"] is None)
        rc, err, out = env.run("--extra-tag-map", "8.1=8.1.0-lama")
        ok &= check("--extra-tag-map menambah di atas peta",
                    out is not None and out["e2e_cells"]["8.1"]["chromium"]["reason"] is None)

    # boot_log: ekor log container ikut ke reason Lapis 4.
    with tempfile.TemporaryDirectory() as td:
        env = Env(td, versions="9.1")
        for b in BR:
            env.add("9.1", b, state="inconclusive", conclusive=False, reason="errors",
                    errors=["flashlight tak jadi 'healthy' (timeout)"], install=None,
                    phase_durations={}, findings=None, authored_assertions=None,
                    boot_log="nginx: [emerg] bind() to 0.0.0.0:80 failed")
        rc, err, out = env.run()
        ok &= check("boot_log record -> ekor log di versions[ver].layers.e2e.reason",
                    out is not None and "bind() to 0.0.0.0:80"
                    in out["versions"]["9.1"]["layers"]["e2e"]["reason"]
                    and out["versions"]["9.1"]["reason"] == "inconclusive")

    # Input: --e2e = exit 2 menyebut --reports-dir; --session divalidasi; tanpa folder laporan
    # tiap sel `missing`; daftar browser terkonfigurasi tak sah = exit 2.
    with tempfile.TemporaryDirectory() as td:
        env = Env(td, versions="9.1")
        env.seed_all()
        legacy = env.root / "e.json"
        legacy.write_text("{}", encoding="utf-8")
        rc, err, out = env.run("--e2e", str(legacy))
        ok &= check("--e2e -> exit 2 menyebut --reports-dir", rc == 2 and "--reports-dir" in err
                    and out is None)
        rc, err, out = env.run("--session", "BUKAN-TOKEN")
        ok &= check("--session salah bentuk -> exit 2", rc == 2 and out is None)
        rc, err, out = env.run("--session", SESSION)
        ok &= check("--session sah -> diterima (belum dipakai), ready True",
                    rc == 0 and out is not None and out["ready"] is True)
        rc, err = _run_main(["--static", str(env.static), "--config", env.cfg,
                             "-o", str(env.out), "--require", "static,e2e"])
        out = json.loads(env.out.read_text()) if env.out.exists() else None
        ok &= check("tanpa --reports-dir/--module -> tiap sel missing, ready False",
                    rc == 0 and out is not None and out["ready"] is False
                    and out["layers_run"]["e2e"] is False
                    and all(c["reason"] == "missing" for c in out["e2e_cells"]["9.1"].values()))
        bad_br = _write_cfg(env.root / "bad-br.json", "9.1", "chromium,webkitx")
        rc, err, out = env.run("--config", bad_br, config=False)
        ok &= check("psm_e2e_browsers tak sah (webkitx) -> exit 2", rc == 2 and "webkitx" in err)
        # Default skrip (tanpa --config): 1.7.8,8.1,9.1 x chromium,firefox — sel 1.7.8/8.1 missing.
        rc, err, out = env.run(config=False)
        ok &= check("tanpa --config -> himpunan default skrip (tiga versi), ready False",
                    out is not None and out["target_versions"] == TV and out["ready"] is False
                    and out["e2e_cells"]["8.1"]["chromium"]["reason"] == "missing")

    print("\n" + ("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
