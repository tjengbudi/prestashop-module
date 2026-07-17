#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Unit test untuk ps-aggregate.py — verifikasi vonis dihitung native & degrade jujur.

Fokus kontrak: pass per-versi & keseluruhan dihitung dari temuan error lapis
konklusif; lapis flashlight tak konklusif (skipped/pull-fail/timeout/no-console)
TAK PERNAH memblok. Jalankan: uv run scripts/tests/test-ps-aggregate.py
"""
import importlib.util
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


def static_result(versions):
    """versions: {full_ver: [(id, severity)]} -> bentuk output ps-static-scan."""
    out = {"module": "m", "versions": {}}
    for ver, finds in versions.items():
        errs = sum(1 for _, sev in finds if sev == "error")
        out["versions"][ver] = {
            "major": ver.split(".")[0], "errors": errs,
            "warnings": len(finds) - errs, "pass": errs == 0,
            "findings": [{"id": i, "severity": s, "kind": "x", "message": i,
                          "fix": "", "occurrences": [{"file": "a.php", "line": 1}], "count": 1}
                         for i, s in finds],
        }
    out["pass"] = all(v["pass"] for v in out["versions"].values())
    return out


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
                                       "install": {"ok": False, "no_console": False, "log": "boom"},
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

    # --- Lapis 4 (E2E) — semantik konklusif-memblok, flaky-tak-memblok ---

    # 9. E2E skipped (Playwright/Docker absen) -> tak memblok, tak konklusif
    e2e_skip = {"module": "m", "e2e_available": False, "status": "skipped",
                "reason": "Playwright tak terpasang", "versions": {}}
    r = mod.merge_version("8.1", static, None, None, e2e_skip)
    ok &= check("e2e skipped tak memblok versi bersih", r["pass"])
    ok &= check("e2e skipped -> state skipped, e2e_conclusive False",
                r["layers"]["e2e"]["state"] == "skipped" and not r["e2e_conclusive"])

    # 9b. E2E skipped_browser (binary belum di-install) -> tak konklusif, tak memblok
    e2e_nobrowser = {"module": "m", "e2e_available": True, "status": "ran",
                     "versions": {"8.1": {"version": "8.1", "install": {"ok": True}, "browsers": [],
                                          "findings": [], "errors": [], "skipped_browser": True,
                                          "pass": False}}}
    r = mod.merge_version("8.1", static, None, None, e2e_nobrowser)
    ok &= check("e2e skipped_browser tak memblok", r["pass"])
    ok &= check("e2e skipped_browser -> not_conclusive",
                r["layers"]["e2e"]["state"] == "not_conclusive" and not r["e2e_conclusive"])

    # 9c. E2E infra (container tak healthy) -> tak konklusif, tak memblok
    e2e_infra = {"module": "m", "e2e_available": True, "status": "ran",
                 "versions": {"8.1": {"version": "8.1", "install": None, "browsers": [],
                                      "findings": [], "errors": ["flashlight tak jadi 'healthy' (timeout)"],
                                      "pass": False}}}
    r = mod.merge_version("8.1", static, None, None, e2e_infra)
    ok &= check("e2e infra-fail tak memblok (degrade jujur)", r["pass"] and not r["e2e_conclusive"])

    # 9d. E2E install gagal -> tak konklusif di E2E (Lapis 2 yang memvonis install)
    e2e_noinstall = {"module": "m", "e2e_available": True, "status": "ran",
                     "versions": {"8.1": {"version": "8.1", "install": {"ok": False}, "browsers": [],
                                          "findings": [], "errors": ["module gagal install"], "pass": False}}}
    r = mod.merge_version("8.1", static, None, None, e2e_noinstall)
    ok &= check("e2e install-fail -> not_conclusive di E2E (tak memblok ganda)",
                r["pass"] and r["layers"]["e2e"]["state"] == "not_conclusive")

    # 10. E2E KONKLUSIF + assertion gagal -> MEMBLOK versi itu
    e2e_fail = {"module": "m", "e2e_available": True, "status": "ran",
                "versions": {"8.1": {"version": "8.1", "install": {"ok": True},
                                     "browsers": ["chromium", "firefox"],
                                     "findings": [{"id": "e2e-smoke-expect_no_fatal", "severity": "error",
                                                   "message": "[chromium/psm-universal-smoke] fatal FO",
                                                   "location": "fo", "versions": ["8.1"]}],
                                     "inconclusive": [], "errors": [], "pass": False}}}
    r = mod.merge_version("8.1", static, None, None, e2e_fail)
    ok &= check("e2e konklusif + fatal -> memblok", not r["pass"] and r["e2e_conclusive"])
    ok &= check("e2e temuan masuk blocking sebagai source e2e",
                any(f.get("source") == "e2e" for f in r["blocking"]))
    r91 = mod.merge_version("9.1", static, None, None, e2e_fail)
    ok &= check("e2e temuan versi 8.1 TAK bocor ke 9.1 (versi tak ada -> skipped)", r91["pass"])

    # 10b. E2E konklusif bersih -> lolos & konklusif; inconclusive_note bila login BO gagal
    e2e_clean = {"module": "m", "e2e_available": True, "status": "ran",
                 "versions": {"8.1": {"version": "8.1", "install": {"ok": True},
                                      "browsers": ["chromium"], "findings": [],
                                      "inconclusive": [{"browser": "chromium", "scenario": "psm-universal-smoke",
                                                        "action": "expect_no_fatal", "message": "BO"}],
                                      "errors": [], "pass": True}}}
    r = mod.merge_version("8.1", static, None, None, e2e_clean)
    ok &= check("e2e bersih konklusif -> lolos & e2e_conclusive True", r["pass"] and r["e2e_conclusive"])
    ok &= check("e2e inconclusive (login BO gagal) -> catatan, tak memblok",
                "inconclusive_note" in r["layers"]["e2e"])

    # 10c. REGRESI false-pass (determinism-1/enhancement-1): satu browser MEMBLOK sementara
    # co-tenant gagal luncur -> temuan konklusif TETAP memblok (browser_notes tak membatalkan).
    e2e_mixed = {"module": "m", "e2e_available": True, "status": "ran",
                 "scenario_notes": [],
                 "versions": {"8.1": {"version": "8.1", "install": {"ok": True},
                                      "browsers": ["chromium"],  # firefox gagal luncur
                                      "findings": [{"id": "e2e-smoke-expect_no_fatal", "severity": "error",
                                                    "message": "[chromium/smoke] fatal FO", "location": "fo",
                                                    "versions": ["8.1"]}],
                                      "inconclusive": [],
                                      "browser_notes": ["browser firefox gagal diluncurkan: boom"],
                                      "errors": [], "skipped_browser": False, "pass": False}}}
    r = mod.merge_version("8.1", static, None, None, e2e_mixed)
    ok &= check("browser co-tenant gagal luncur TAK membatalkan temuan konklusif (fix false-pass)",
                not r["pass"] and r["e2e_conclusive"] and r["layers"]["e2e"]["state"] == "fail")
    ok &= check("coverage browser gagal disurface sbg inconclusive_note (tak memblok)",
                "firefox" in r["layers"]["e2e"].get("inconclusive_note", ""))

    # 10d. spec authored rusak (scenario_notes) disurface di note walau versi lolos bersih
    e2e_specnote = {"module": "m", "e2e_available": True, "status": "ran",
                    "scenario_notes": ["checkout.json: tak ada 'steps' list — dilewati"],
                    "versions": {"8.1": {"version": "8.1", "install": {"ok": True}, "browsers": ["chromium"],
                                         "findings": [], "inconclusive": [], "browser_notes": [],
                                         "errors": [], "pass": True}}}
    r = mod.merge_version("8.1", static, None, None, e2e_specnote)
    ok &= check("scenario_notes (spec authored dilewati) disurface di note walau lolos",
                r["pass"] and "checkout.json" in r["layers"]["e2e"].get("inconclusive_note", ""))

    def _flash_cs(cs):
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
            r = subprocess.run(["uv", "run", str(MOD_PATH), "--static", str(sp),
                                "--versions", "8.1", "-o", str(op), *args_extra],
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

    # 11. e2e_layer langsung: skipped -> findings kosong
    ok &= check("e2e_layer skipped -> findings kosong", mod.e2e_layer(e2e_skip, "8.1")["findings"] == [])

    # 12. Cakupan E2E disurface di vonis (enhancement-1) — lewat CLI, logikanya di main().
    # Tanpa penanda ini, module TANPA spec authored (cuma smoke) bervonis identik dgn
    # yang punya skenario use-case lengkap: "E2E konklusif lolos" terbaca lebih dari faktanya.
    def _aggregate(e2e_payload, static_payload=static):
        with tempfile.TemporaryDirectory() as td:
            sp, ep, op = Path(td) / "s.json", Path(td) / "e.json", Path(td) / "o.json"
            sp.write_text(json.dumps(static_payload), encoding="utf-8")
            ep.write_text(json.dumps(e2e_payload), encoding="utf-8")
            subprocess.run(["uv", "run", str(MOD_PATH), "--static", str(sp), "--e2e", str(ep),
                            "--versions", "8.1", "-o", str(op)], capture_output=True, text=True)
            return json.loads(op.read_text(encoding="utf-8"))

    def _e2e_ran(sources):
        return {"module": "m", "e2e_available": True, "status": "ran",
                "scenario_sources": sources,
                "versions": {"8.1": {"version": "8.1", "install": {"ok": True},
                                     "browsers": ["chromium"], "findings": [], "inconclusive": [],
                                     "browser_notes": [], "errors": [], "pass": True}}}

    smoke = _aggregate(_e2e_ran(["builtin:psm-universal-smoke"]))
    ok &= check("E2E hanya smoke -> e2e_smoke_only True (cakupan jujur, walau lolos)",
                smoke["pass"] is True and smoke.get("e2e_smoke_only") is True)
    authored = _aggregate(_e2e_ran(["builtin:psm-universal-smoke", "configure.json"]))
    ok &= check("E2E dgn spec authored -> e2e_smoke_only False",
                authored.get("e2e_smoke_only") is False
                and "configure.json" in authored.get("e2e_scenario_sources", []))
    noe2e = _aggregate(e2e_skip)
    ok &= check("E2E tak jalan -> tak ada klaim cakupan sama sekali",
                "e2e_smoke_only" not in noe2e)

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

    # 13c. determinism-4: e2e_smoke_only dihitung lalu tak dibaca gerbang mana pun ->
    # module yang perilakunya tak pernah diuji dapat hijau empat-lapis penuh.
    e2e_smoke = _e2e_ran(["builtin:psm-universal-smoke"])
    e2e_auth = _e2e_ran(["builtin:psm-universal-smoke", "configure.json"])
    l_smoke = mod.e2e_layer(e2e_smoke, "8.1")
    ok &= check("e2e smoke-only -> inconclusive_note (perilaku module tak teruji)",
                "smoke universal" in l_smoke.get("inconclusive_note", ""))
    ok &= check("e2e dgn spec authored -> tanpa catatan smoke-only",
                "smoke universal" not in mod.e2e_layer(e2e_auth, "8.1").get("inconclusive_note", ""))
    ready_smoke = mod.compute_ready(
        {"8.1": mod.merge_version("8.1", static, None, None, e2e_smoke)}, ["static", "e2e"])
    ok &= check("ready: E2E smoke-only -> False walau lapis konklusif & lolos",
                l_smoke["conclusive"] is True and ready_smoke is False)
    ok &= check("ready: E2E dgn skenario authored -> True",
                mod.compute_ready({"8.1": mod.merge_version("8.1", static, None, None, e2e_auth)},
                                  ["static", "e2e"]) is True)
    ok &= check("e2e smoke-only tetap TAK memblok (`pass` buta konklusivitas)",
                mod.merge_version("8.1", static, None, None, e2e_smoke)["pass"] is True)
    # Insentif terbalik yang direproduksi lensa: MENGHAPUS spec yang rusak dulu membalik
    # ready False -> True, jadi gerbangnya menghadiahi module yang tak punya uji sama sekali.
    e2e_broken = _e2e_ran(["builtin:psm-universal-smoke"])
    e2e_broken["scenario_notes"] = ["configure.json: JSON rusak — dilewati"]
    ok &= check("hapus spec rusak TAK memperbaiki ready (insentif terbalik tutup)",
                mod.compute_ready({"8.1": mod.merge_version("8.1", static, None, None, e2e_broken)},
                                  ["static", "e2e"]) is False and ready_smoke is False)
    ok &= check("is_smoke_only: satu definisi dipakai gerbang & field top-level",
                mod.is_smoke_only(e2e_smoke) is True and mod.is_smoke_only(e2e_auth) is False)

    # 13d. determinism-6: versi target yang static-scan tak pernah pindai dulu pass=true &
    # exit 0 — ketiadaan bukti terbaca sebagai lolos. Lewat CLI: gerbangnya ada di main().
    def _cli_versions(static_payload, versions):
        with tempfile.TemporaryDirectory() as td:
            sp, op = Path(td) / "s.json", Path(td) / "o.json"
            sp.write_text(json.dumps(static_payload), encoding="utf-8")
            r = subprocess.run(["uv", "run", str(MOD_PATH), "--static", str(sp),
                                "--versions", versions, "-o", str(op)],
                               capture_output=True, text=True)
            return r.returncode, r.stderr

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
    rc, err = _cli_versions(static81, "1.7.8,8.1,9.1")
    ok &= check("versi target tak dipindai static -> exit 2 (dulu pass=true exit 0)",
                rc == 2 and "1.7.8" in err and "9.1" in err and "Traceback" not in err)
    rc, _ = _cli_versions(static81, "8.1")
    ok &= check("versi target sepenuhnya terpindai -> jalan normal", rc == 0)

    print("\n" + ("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
