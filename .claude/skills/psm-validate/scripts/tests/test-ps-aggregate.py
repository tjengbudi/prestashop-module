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
import sys
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
    r = mod.merge_version("8.1", static, None, None, None, TV)
    ok &= check("static bersih -> versi lolos", r["pass"])
    ok &= check("tanpa flashlight -> flashlight_conclusive False", not r["flashlight_conclusive"])
    ok &= check("static selalu memberi vonis dasar konklusif", r["conclusive"])

    # 2. Static punya error -> versi gagal (dihitung native, bukan model)
    static_bad = static_result({"8.1": [("cls-attribute", "error")], "9.1": [], "1.7.8": []})
    r = mod.merge_version("8.1", static_bad, None, None, None, TV)
    ok &= check("static error -> versi gagal", not r["pass"] and len(r["blocking"]) == 1)
    r91 = mod.merge_version("9.1", static_bad, None, None, None, TV)
    ok &= check("versi lain tanpa error tetap lolos", r91["pass"])

    # 3. Flashlight skipped (Docker absen) -> TAK memblok versi yang static-nya bersih
    flash_skipped = {"module": "m", "docker_available": False, "status": "skipped",
                     "reason": "Docker absen", "versions": {}}
    r = mod.merge_version("8.1", static, flash_skipped, None, None, TV)
    ok &= check("flashlight skipped tak memblok versi bersih", r["pass"])
    ok &= check("flashlight skipped -> state skipped, tak konklusif",
                r["layers"]["flashlight"]["state"] == "skipped" and not r["flashlight_conclusive"])

    # 4. Flashlight gagal infra (timeout) -> TAK memblok (degrade jujur), tak diklaim gagal
    flash_infra = {"module": "m", "docker_available": True, "status": "ran",
                   "versions": {"8.1": {"version": "8.1", "image": "img", "install": None,
                                        "coding_standard": None,
                                        "errors": ["timeout menjalankan container img"], "pass": False}}}
    r = mod.merge_version("8.1", static, flash_infra, None, None, TV)
    ok &= check("flashlight timeout tak memblok (enhancement-2)", r["pass"])
    ok &= check("flashlight timeout -> not_conclusive",
                r["layers"]["flashlight"]["state"] == "not_conclusive")

    # 4b. Flashlight skipped_image (image absen, pull tak diizinkan) -> tak memblok (enhancement-1)
    flash_noimg = {"module": "m", "docker_available": True, "status": "ran",
                   "versions": {"8.1": {"version": "8.1", "image": "img", "install": None,
                                        "coding_standard": None, "skipped_image": True,
                                        "errors": ["image img belum ada lokal & pull tak diizinkan"],
                                        "pass": False}}}
    r = mod.merge_version("8.1", static, flash_noimg, None, None, TV)
    ok &= check("flashlight skipped_image tak memblok (enhancement-1)", r["pass"])
    ok &= check("flashlight skipped_image -> not_conclusive",
                r["layers"]["flashlight"]["state"] == "not_conclusive" and not r["flashlight_conclusive"])

    # 5. Flashlight no_console -> tak konklusif, tak memblok
    flash_nocon = {"module": "m", "docker_available": True, "status": "ran",
                   "versions": {"8.1": {"version": "8.1", "image": "img",
                                        "install": {"ok": False, "no_console": True, "log": ""},
                                        "coding_standard": {"available": False},
                                        "errors": [], "pass": False}}}
    r = mod.merge_version("8.1", static, flash_nocon, None, None, TV)
    ok &= check("flashlight no_console tak memblok", r["pass"] and not r["flashlight_conclusive"])

    # 6. Flashlight KONKLUSIF + install ditolak -> MEMBLOK (uji nyata gagal)
    flash_fail = {"module": "m", "docker_available": True, "status": "ran",
                  "versions": {"8.1": {"version": "8.1", "image": "img",
                                       "install": {"ok": False, "no_console": False, "log": "boom"},
                                       "coding_standard": {"available": False},
                                       "errors": [], "pass": False}}}
    r = mod.merge_version("8.1", static, flash_fail, None, None, TV)
    ok &= check("install ditolak (konklusif) -> memblok", not r["pass"] and r["flashlight_conclusive"])

    # 7. Flashlight konklusif + phpstan error (neon module) -> memblok dengan lokasi
    flash_cs = {"module": "m", "docker_available": True, "status": "ran",
                "versions": {"8.1": {"version": "8.1", "image": "img",
                                     "install": {"ok": True, "no_console": False, "log": ""},
                                     "coding_standard": {"available": True, "parse_ok": True, "errors": 2,
                                                         "error_messages": [{"line": 3, "source": "X", "message": "bad"},
                                                                            {"line": 9, "source": "Y", "message": "worse"}]},
                                     "errors": [], "pass": False}}}
    r = mod.merge_version("8.1", static, flash_cs, None, None, TV)
    ok &= check("phpstan 2 error (neon module) -> 2 temuan memblok", not r["pass"] and len(r["blocking"]) == 2)

    # 7b. phpstan auto-neon (advisory: errors=0, warnings) -> TAK memblok meski ada temuan
    flash_adv = {"module": "m", "docker_available": True, "status": "ran",
                 "versions": {"8.1": {"version": "8.1", "image": "img",
                                      "install": {"ok": True, "no_console": False, "log": ""},
                                      "coding_standard": {"available": True, "parse_ok": True,
                                                          "generated_config": True, "errors": 0, "warnings": 2,
                                                          "error_messages": [{"line": 3, "source": "phpstan", "message": "mungkin"}]},
                                      "errors": [], "pass": True}}}
    r = mod.merge_version("8.1", static, flash_adv, None, None, TV)
    ok &= check("phpstan auto-neon advisory (errors=0) tak memblok", r["pass"] and len(r["blocking"]) == 0)

    # 8. Adversarial error -> memblok; adversarial warning -> tak memblok
    adv = {"findings": [{"id": "adv-sqli", "severity": "error", "message": "SQL injection",
                         "versions": ["8.1"], "location": "x.php:5"},
                        {"id": "adv-perf", "severity": "warning", "message": "query in loop",
                         "versions": ["8.1"]}]}
    r = mod.merge_version("8.1", static, None, adv, None, TV)
    ok &= check("adversarial error memblok", not r["pass"])
    ok &= check("adversarial error terkumpul 1 blocking (warning tak)", len(r["blocking"]) == 1)
    # adversarial tanpa versi -> berlaku semua versi target
    adv_all = {"findings": [{"id": "adv-x", "severity": "error", "message": "global"}]}
    r91_all = mod.merge_version("9.1", static, None, adv_all, None, TV)
    ok &= check("adversarial tanpa versi -> berlaku semua target", not r91_all["pass"])
    # regression architecture-1: versions major-form ('8') harus match full-form target ('8.1')
    adv_major = {"findings": [{"id": "adv-m", "severity": "error", "message": "major-form",
                               "versions": ["8"]}]}
    r_m = mod.merge_version("8.1", static, None, adv_major, None, TV)
    ok &= check("adversarial major-form '8' match target '8.1' (tak diam-diam drop)", not r_m["pass"])
    r_m91 = mod.merge_version("9.1", static, None, adv_major, None, TV)
    ok &= check("major-form '8' TAK bocor ke versi lain (9.1 tetap lolos)", r_m91["pass"])
    # full-form tetap match apa adanya
    adv_full = {"findings": [{"id": "adv-f", "severity": "error", "message": "full-form",
                              "versions": ["1.7.8"]}]}
    r_f = mod.merge_version("1.7.8", static, None, adv_full, None, TV)
    ok &= check("adversarial full-form '1.7.8' tetap match", not r_f["pass"])

    # --- Lapis 4 (E2E) — semantik konklusif-memblok, flaky-tak-memblok ---

    # 9. E2E skipped (Playwright/Docker absen) -> tak memblok, tak konklusif
    e2e_skip = {"module": "m", "e2e_available": False, "status": "skipped",
                "reason": "Playwright tak terpasang", "versions": {}}
    r = mod.merge_version("8.1", static, None, None, e2e_skip, TV)
    ok &= check("e2e skipped tak memblok versi bersih", r["pass"])
    ok &= check("e2e skipped -> state skipped, e2e_conclusive False",
                r["layers"]["e2e"]["state"] == "skipped" and not r["e2e_conclusive"])

    # 9b. E2E skipped_browser (binary belum di-install) -> tak konklusif, tak memblok
    e2e_nobrowser = {"module": "m", "e2e_available": True, "status": "ran",
                     "versions": {"8.1": {"version": "8.1", "install": {"ok": True}, "browsers": [],
                                          "findings": [], "errors": [], "skipped_browser": True,
                                          "pass": False}}}
    r = mod.merge_version("8.1", static, None, None, e2e_nobrowser, TV)
    ok &= check("e2e skipped_browser tak memblok", r["pass"])
    ok &= check("e2e skipped_browser -> not_conclusive",
                r["layers"]["e2e"]["state"] == "not_conclusive" and not r["e2e_conclusive"])

    # 9c. E2E infra (container tak healthy) -> tak konklusif, tak memblok
    e2e_infra = {"module": "m", "e2e_available": True, "status": "ran",
                 "versions": {"8.1": {"version": "8.1", "install": None, "browsers": [],
                                      "findings": [], "errors": ["flashlight tak jadi 'healthy' (timeout)"],
                                      "pass": False}}}
    r = mod.merge_version("8.1", static, None, None, e2e_infra, TV)
    ok &= check("e2e infra-fail tak memblok (degrade jujur)", r["pass"] and not r["e2e_conclusive"])

    # 9d. E2E install gagal -> tak konklusif di E2E (Lapis 2 yang memvonis install)
    e2e_noinstall = {"module": "m", "e2e_available": True, "status": "ran",
                     "versions": {"8.1": {"version": "8.1", "install": {"ok": False}, "browsers": [],
                                          "findings": [], "errors": ["module gagal install"], "pass": False}}}
    r = mod.merge_version("8.1", static, None, None, e2e_noinstall, TV)
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
    r = mod.merge_version("8.1", static, None, None, e2e_fail, TV)
    ok &= check("e2e konklusif + fatal -> memblok", not r["pass"] and r["e2e_conclusive"])
    ok &= check("e2e temuan masuk blocking sebagai source e2e",
                any(f.get("source") == "e2e" for f in r["blocking"]))
    r91 = mod.merge_version("9.1", static, None, None, e2e_fail, TV)
    ok &= check("e2e temuan versi 8.1 TAK bocor ke 9.1 (versi tak ada -> skipped)", r91["pass"])

    # 10b. E2E konklusif bersih -> lolos & konklusif; inconclusive_note bila login BO gagal
    e2e_clean = {"module": "m", "e2e_available": True, "status": "ran",
                 "versions": {"8.1": {"version": "8.1", "install": {"ok": True},
                                      "browsers": ["chromium"], "findings": [],
                                      "inconclusive": [{"browser": "chromium", "scenario": "psm-universal-smoke",
                                                        "action": "expect_no_fatal", "message": "BO"}],
                                      "errors": [], "pass": True}}}
    r = mod.merge_version("8.1", static, None, None, e2e_clean, TV)
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
    r = mod.merge_version("8.1", static, None, None, e2e_mixed, TV)
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
    r = mod.merge_version("8.1", static, None, None, e2e_specnote, TV)
    ok &= check("scenario_notes (spec authored dilewati) disurface di note walau lolos",
                r["pass"] and "checkout.json" in r["layers"]["e2e"].get("inconclusive_note", ""))

    # 11. e2e_layer langsung: skipped -> findings kosong
    ok &= check("e2e_layer skipped -> findings kosong", mod.e2e_layer(e2e_skip, "8.1")["findings"] == [])

    print("\n" + ("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
