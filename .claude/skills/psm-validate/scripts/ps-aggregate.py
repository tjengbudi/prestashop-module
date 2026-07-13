#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Satukan empat lapis validasi jadi satu vonis terstruktur — deterministik.

Menerima output JSON ps-static-scan.py (Lapis 1) dan ps-flashlight-run.py
(Lapis 2), file temuan adversarial buatan model (Lapis 3), plus output
ps-e2e-run.py (Lapis 4, uji perilaku browser), lalu menghitung `pass` per versi
dan keseluruhan secara NATIVE — bukan lewat model.

Aturan lolos: sebuah versi lolos hanya bila TAK ADA temuan severity `error` dari
lapis manapun yang KONKLUSIF di versi itu. Lapis yang tak konklusif (Docker absen,
gagal pull, timeout, tak ada console) TAK PERNAH memblok — vonis versi itu jatuh
ke lapis yang benar-benar teruji (jujur: tak klaim lolos maupun gagal atas yang
tak diuji). Skrip menandai `conclusive` per versi supaya pemanggil tahu seberapa
kuat vonisnya.

Pembagian kerja: skrip menghitung/menggabung/membandingkan (satu jawaban benar);
model tinggal menghasilkan temuan adversarial (Lapis 3) & prosa untuk manusia.
"""
import argparse
import json
import sys
from pathlib import Path

ERROR = "error"


def load_json(path, label):
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: gagal baca {label} ({path}): {e}", file=sys.stderr)
        sys.exit(2)


def static_layer(static, full_ver):
    """Lapis 1 selalu jalan & selalu konklusif — sumber kebenaran aturan pasti."""
    v = static.get("versions", {}).get(full_ver)
    if v is None:
        return {"ran": False, "conclusive": False, "errors": 0, "warnings": 0,
                "reason": "versi tak ada di hasil static-scan", "findings": []}
    findings = [
        {"source": "static", "id": f["id"], "severity": f["severity"],
         "message": f["message"], "fix": f.get("fix", ""),
         "location": _first_loc(f.get("occurrences")), "count": f.get("count", 1)}
        for f in v.get("findings", [])
    ]
    return {"ran": True, "conclusive": True, "errors": v.get("errors", 0),
            "warnings": v.get("warnings", 0), "findings": findings}


def _first_loc(occ):
    if occ:
        o = occ[0]
        return f"{o.get('file', '?')}:{o.get('line', 0)}"
    return ""


def flashlight_layer(flash, full_ver):
    """Lapis 2 — konklusif hanya bila container benar-benar menjalankan uji.

    Tak konklusif (degrade jujur, tak memblok): Docker absen, gagal pull, timeout,
    atau tak ada PS console. Konklusif: install teruji (lolos/ditolak) & CS terbaca.
    """
    if not flash or flash.get("status") == "skipped" or not flash.get("docker_available", False):
        reason = (flash or {}).get("reason", "Docker tidak tersedia — uji flashlight dilewati.")
        return {"state": "skipped", "conclusive": False, "errors": 0, "reason": reason, "findings": []}

    v = flash.get("versions", {}).get(full_ver)
    if v is None:
        return {"state": "skipped", "conclusive": False, "errors": 0,
                "reason": "versi tak ada di hasil flashlight", "findings": []}

    # Kegagalan infrastruktur → tak konklusif, jangan memblok.
    infra = list(v.get("errors", []))  # gagal pull / timeout container
    install = v.get("install") or {}
    if install.get("no_console"):
        infra.append("PrestaShop console tak ada di image — install tak bisa diuji")
    if infra:
        return {"state": "not_conclusive", "conclusive": False, "errors": 0,
                "reason": "; ".join(infra), "findings": []}

    # Konklusif: kumpulkan temuan error nyata (install ditolak / phpcs error).
    findings = []
    if not install.get("ok"):
        findings.append({"source": "flashlight", "id": "flashlight-install",
                         "severity": ERROR, "message": "modul gagal install di core asli",
                         "fix": "periksa log install flashlight", "location": v.get("image", "")})
    cs = v.get("coding_standard") or {}
    # Hanya errors konklusif yang memblok. Neon auto-generate (advisory) memetakan
    # temuannya ke warnings (errors=0) di ps-flashlight-run, jadi tak sampai sini.
    if cs.get("available") and cs.get("parse_ok") and cs.get("errors", 0) > 0:
        for m in cs.get("error_messages", []):
            findings.append({"source": "flashlight", "id": "flashlight-phpstan",
                             "severity": ERROR, "message": m.get("message", "phpstan error"),
                             "fix": m.get("source", ""), "location": f"line {m.get('line', '?')}"})
        if not cs.get("error_messages"):
            findings.append({"source": "flashlight", "id": "flashlight-phpstan",
                             "severity": ERROR, "message": f"{cs['errors']} phpstan error",
                             "fix": "", "location": v.get("image", "")})
    # CS tak terparse: install tetap konklusif, tapi catat CS tak teruji.
    cs_note = None
    if cs.get("available") and cs.get("parse_ok") is False:
        cs_note = cs.get("note", "laporan phpstan tak terparse — coding standard tak diuji")
    errs = sum(1 for f in findings if f["severity"] == ERROR)
    layer = {"state": "fail" if errs else "pass", "conclusive": True,
             "errors": errs, "findings": findings}
    if cs_note:
        layer["cs_note"] = cs_note
    return layer


def e2e_layer(e2e, full_ver):
    """Lapis 4 — konklusif hanya bila browser+container naik bersih & module ter-install.

    Tak konklusif (degrade jujur, tak memblok): Playwright/Docker absen, image belum
    ada, binary browser belum di-`install`, container tak healthy, PS tak terjangkau,
    module gagal install (itu wilayah vonis Lapis 2), atau timeout. Konklusif: assertion
    browser (smoke/skenario) benar-benar dievaluasi — kegagalannya memblok.
    """
    if not e2e or e2e.get("status") == "skipped" or not e2e.get("e2e_available", False):
        reason = (e2e or {}).get("reason", "Playwright/Docker tak tersedia — uji E2E dilewati.")
        return {"state": "skipped", "conclusive": False, "errors": 0, "reason": reason, "findings": []}

    v = e2e.get("versions", {}).get(full_ver)
    if v is None:
        return {"state": "skipped", "conclusive": False, "errors": 0,
                "reason": "versi tak ada di hasil e2e", "findings": []}

    # Kegagalan infrastruktur → tak konklusif, jangan memblok.
    infra = list(v.get("errors", []))
    if v.get("skipped_browser"):
        infra.append("tak ada browser yang bisa diluncurkan (jalankan 'playwright install')")
    if not (v.get("install") or {}).get("ok"):
        infra.append("module tak ter-install — perilaku browser tak bisa dinilai (Lapis 2 memvonis install)")
    if not v.get("browsers"):
        infra.append("tak ada browser dijalankan")
    if infra:
        return {"state": "not_conclusive", "conclusive": False, "errors": 0,
                "reason": "; ".join(dict.fromkeys(infra)), "findings": []}

    # Konklusif (≥1 browser jalan & module ter-install): temuan browser memblok versi ini.
    # Masalah per-browser (browser_notes) & spec authored rusak (scenario_notes) TAK
    # membatalkan temuan konklusif — hanya coverage yang disurface sbg catatan (tak memblok).
    findings = [
        {"source": "e2e", "id": f.get("id", "e2e"), "severity": f.get("severity", ERROR),
         "message": f.get("message", ""), "fix": f.get("fix", ""), "location": f.get("location", "")}
        for f in v.get("findings", [])
    ]
    errs = sum(1 for f in findings if f["severity"] == ERROR)
    layer = {"state": "fail" if errs else "pass", "conclusive": True, "errors": errs, "findings": findings}
    notes = []
    inc = v.get("inconclusive") or []
    if inc:
        notes.append(f"{len(inc)} assertion tak konklusif (mis. login BO gagal)")
    for bn in (v.get("browser_notes") or []):
        notes.append(f"coverage browser: {bn}")
    sn = e2e.get("scenario_notes") or []
    if sn:
        notes.append(f"{len(sn)} spec E2E authored dilewati: {'; '.join(sn)}")
    if notes:
        layer["inconclusive_note"] = "; ".join(notes) + " — tak memblok"
    return layer


def _major(ver):
    """Petakan versi ke major key: 1.7.8.11 -> 1.7, 8.1 -> 8, 9.1 -> 9."""
    ver = str(ver).strip()
    return "1.7" if ver.startswith("1.7") else ver.split(".")[0]


def _version_matches(entry, full_ver):
    """Temuan berlaku utk full_ver bila entri sama persis ATAU semajor.

    Model bisa menulis 'versions' dalam bentuk penuh (8.1) atau major (8);
    keduanya harus resolve supaya temuan error tak diam-diam terlewat.
    """
    return entry.strip() == full_ver or _major(entry) == _major(full_ver)


def adversarial_layer(adversarial, full_ver, target_versions):
    """Lapis 3 — temuan judgment model. Selalu 'jalan' (model selalu menilai)."""
    if adversarial is None:
        return {"ran": False, "conclusive": False, "errors": 0,
                "reason": "tak ada file temuan adversarial", "findings": []}
    findings = []
    for f in adversarial.get("findings", []):
        vers = f.get("versions")  # kosong/None = semua versi target
        if vers and not any(_version_matches(e, full_ver) for e in vers):
            continue
        findings.append({"source": "adversarial", "id": f.get("id", "adv"),
                         "severity": f.get("severity", "warning"),
                         "message": f.get("message", ""), "fix": f.get("fix", ""),
                         "location": f.get("location", "")})
    errs = sum(1 for f in findings if f["severity"] == ERROR)
    return {"ran": True, "conclusive": True, "errors": errs, "findings": findings}


def merge_version(full_ver, static, flash, adversarial, e2e, target_versions):
    s = static_layer(static, full_ver)
    fl = flashlight_layer(flash, full_ver)
    adv = adversarial_layer(adversarial, full_ver, target_versions)
    e = e2e_layer(e2e, full_ver)

    blocking = [f for layer in (s, fl, adv, e) for f in layer["findings"] if f["severity"] == ERROR]
    # Lolos bila tak ada error dari lapis KONKLUSIF manapun.
    passed = len(blocking) == 0
    # Vonis konklusif hanya bila setidaknya static teruji; catat flashlight/e2e tak konklusif.
    conclusive = s["conclusive"]  # static selalu konklusif; jadi versi selalu punya vonis dasar
    return {
        "pass": passed,
        "conclusive": conclusive,
        "flashlight_conclusive": fl["conclusive"],
        "e2e_conclusive": e["conclusive"],
        "layers": {"static": s, "flashlight": fl, "adversarial": adv, "e2e": e},
        "blocking": blocking,
    }


def main():
    ap = argparse.ArgumentParser(description="Satukan empat lapis validasi jadi vonis terstruktur.")
    ap.add_argument("--static", required=True, help="JSON output ps-static-scan.py")
    ap.add_argument("--flashlight", help="JSON output ps-flashlight-run.py (opsional bila dilewati)")
    ap.add_argument("--adversarial", help="JSON temuan adversarial buatan model (opsional)")
    ap.add_argument("--e2e", help="JSON output ps-e2e-run.py (Lapis 4, opsional bila dilewati)")
    ap.add_argument("--versions", help="Versi target dipisah koma (default: dari hasil static)")
    ap.add_argument("-o", "--output", help="File output JSON (default: stdout)")
    args = ap.parse_args()

    static = load_json(args.static, "static-scan")
    flash = load_json(args.flashlight, "flashlight") if args.flashlight else None
    adversarial = load_json(args.adversarial, "adversarial") if args.adversarial else None
    e2e = load_json(args.e2e, "e2e") if args.e2e else None

    if args.versions:
        target_versions = [v.strip() for v in args.versions.split(",")]
    else:
        target_versions = list(static.get("versions", {}).keys())

    versions = {}
    overall_pass = True
    all_conclusive = True
    all_e2e_conclusive = True
    for full_ver in target_versions:
        m = merge_version(full_ver, static, flash, adversarial, e2e, target_versions)
        versions[full_ver] = m
        overall_pass = overall_pass and m["pass"]
        all_conclusive = all_conclusive and m["flashlight_conclusive"]
        all_e2e_conclusive = all_e2e_conclusive and m["e2e_conclusive"]

    flashlight_ran = bool(flash and flash.get("docker_available"))
    e2e_ran = bool(e2e and e2e.get("e2e_available") and e2e.get("status") == "ran")
    result = {
        "module": static.get("module", ""),
        "target_versions": target_versions,
        "versions": versions,
        "pass": overall_pass,
        "flashlight_conclusive": all_conclusive,
        "e2e_conclusive": all_e2e_conclusive,
        "layers_run": {
            "static": True,
            "flashlight": flashlight_ran,
            "adversarial": adversarial is not None,
            "e2e": e2e_ran,
        },
    }
    # Spec E2E authored yang dilewati (JSON rusak / tanpa steps) di-echo di top-level supaya
    # TAK hilang walau semua versi tak konklusif — jangan biarkan uji authored diam-diam absen.
    e2e_scenario_notes = (e2e or {}).get("scenario_notes") or []
    if e2e_scenario_notes:
        result["e2e_scenario_notes"] = e2e_scenario_notes
    out = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"ditulis: {args.output}", file=sys.stderr)
    else:
        print(out)
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
