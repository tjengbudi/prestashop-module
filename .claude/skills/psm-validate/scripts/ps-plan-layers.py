#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Pra-pass: putuskan lapis mana yang boleh dipakai-ulang dan mana yang harus dijalankan ulang.

Deterministik: input sama -> keputusan sama. Menjawab satu pertanyaan yang punya satu
jawaban benar — apakah `<reports>/<module>-<lapis>.json` masih mewakili module dan
cakupan versi yang diminta SEKARANG?

Sebuah file lapis boleh dipakai ulang HANYA bila ketiganya benar:
  1. file itu ada dan terbaca sebagai JSON,
  2. mtime-nya LEBIH BARU dari file termuda di source module (vendor/ diabaikan),
  3. cakupan versinya memuat semua versi yang diminta.
Selain itu -> rerun, dengan alasan yang bisa dibaca manusia.

Kenapa skrip, bukan prompt: menghitung mtime rekursif, menstat empat file, dan
membandingkan himpunan versi tiap run adalah kerja mekanis yang mahal diulang dan
berbahaya bila salah — file lapis basi membuat vonis mengklaim coverage atas kode yang
sudah berubah, dan ps-aggregate tak bisa mendeteksinya (ia percaya JSON yang disodorkan).
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

LAYERS = ("static", "flashlight", "adversarial", "e2e")

# Default kanonik psm_reports_dir, bentuk TANPA token (relatif cwd project). SKILL.md
# menjanjikan "resolver absen -> lanjut dengan default kanonik skrip", tapi --reports-dir
# dulu required=True tanpa default -> janji itu tak bisa ditepati & satu-satunya bentuk
# tertulis yang dilihat model ber-token ({project-root}/...). Nilai TANPA token supaya tak
# jadi bahan token tak-terekspansi; dikunci ke PSM_DEFAULTS['psm_reports_dir'] via test drift.
DEFAULT_REPORTS_DIR = "_bmad-output/psm-validate"

# "Folder mana yang bukan source module" hanya boleh punya SATU definisi — dua
# implementasi berbeda (substring vs komponen path) pernah sama-sama salah &
# gagal ke arah tak aman. Pakai-ulang dari ps-static-scan (impor by-path karena
# nama file ber-tanda-hubung), pola yang sama dgn ps-e2e-run -> ps-flashlight-run.
def load_sibling(path, name):
    """Muat skrip sibling by-path. Gagal = exit 2 berpesan, bukan traceback telanjang.

    `assert spec and spec.loader` tak menjaga apa pun: spec_from_file_location tetap
    mengembalikan spec sah untuk path yang tak ada, jadi kegagalannya jatuh di exec_module
    sebagai traceback mentah. Folder scripts/ yang disalin sebagian adalah skenario nyata
    (SKILL.md sendiri mengantisipasi salinan tanpa psm-setup).
    """
    try:
        spec = importlib.util.spec_from_file_location(name, path)
        if not (spec and spec.loader):
            raise ImportError(f"spec tak terbentuk untuk {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except (OSError, ImportError, SyntaxError) as e:
        print(f"error: skrip sibling tak bisa dimuat: {Path(path).name} ({e})", file=sys.stderr)
        print("skrip psm-validate saling bergantung — salin folder scripts/ utuh", file=sys.stderr)
        sys.exit(2)


ss = load_sibling(Path(__file__).resolve().parent / "ps-static-scan.py", "ps_static_scan")
fl = load_sibling(Path(__file__).resolve().parent / "ps-flashlight-run.py", "ps_flashlight_run")


def newest_source_mtime(module_dir):
    """mtime file termuda di source module. Return (mtime, path) — (0.0, None) bila kosong."""
    newest, where = 0.0, None
    module_dir = Path(module_dir)
    for p in module_dir.rglob("*"):
        if not p.is_file() or ss.is_skipped(p, module_dir):
            continue
        try:
            m = p.stat().st_mtime
        except OSError:
            continue
        if m > newest:
            newest, where = m, p
    return newest, where


def layer_versions(payload):
    """Versi yang DITINJAU file lapis. None = tak bisa ditentukan (jangan pakai ulang).

    Dua bentuk sah: `versions` dict (static/flashlight/e2e, kunci = versi) dan
    `versions` list (lapis adversarial menyatakan cakupan yang ditinjau — lihat
    references/adversarial-lens.md). Cakupan TAK diturunkan dari `findings`:
    versi di temuan adalah versi TERPENGARUH, bukan yang ditinjau — review 3 versi
    yang menemukan satu bug di 8.1 akan terbaca "cuma meninjau 8.1".
    """
    if not isinstance(payload, dict):
        return None
    versions = payload.get("versions")
    if isinstance(versions, dict):
        return set(versions.keys())
    if isinstance(versions, list) and all(isinstance(v, str) for v in versions):
        return set(versions)
    return None


def plan_layer(path, requested, src_mtime, src_path, provenance=None):
    """Putuskan reuse/rerun satu file lapis + alasannya.

    `provenance` = INPUT KEDUA lapis ini (selain source module), bila punya. Tiap lapis punya
    satu, dan membandingkan mtime module saja membuat perubahan pada input kedua itu tak pernah
    menyala di file lapis yang dipakai ulang:
      {"kind": "ruleset", "files": [...], "mtime": float}  — Lapis 1: aturan KB baru ditambahkan
      {"kind": "image", "expect": {versi: tag}}             — Lapis 2/4: tag-map di-bump, jadi
          file lapis lama memvonis core yang BERBEDA dari yang jadi target sekarang

    Dulu param ini bernama `ruleset` dan hanya Lapis 1 yang mengisinya — padahal alasan yang
    ditulisnya berlaku sama persis untuk Lapis 2/4, yang bahkan SUDAH mencatat tag/image-nya dan
    tak dibaca siapa pun. Bentuk umum ini supaya input kedua Lapis 3 (kontrak lensa adversarial)
    punya rumah kalau nanti dipasang, bukan jadi korban berikutnya.
    """
    p = Path(path)
    if not p.is_file():
        return {"reuse": False, "reason": "file lapis belum ada", "path": str(p)}
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        return {"reuse": False, "reason": f"file lapis tak terbaca ({str(e)[:60]})", "path": str(p)}
    try:
        age = p.stat().st_mtime
    except OSError:
        return {"reuse": False, "reason": "mtime file lapis tak terbaca", "path": str(p)}
    if age <= src_mtime:
        where = f" ({src_path})" if src_path else ""
        return {"reuse": False, "reason": f"module lebih baru dari file lapis{where}", "path": str(p)}
    kind = (provenance or {}).get("kind")
    if kind == "ruleset":
        recorded = payload.get("ruleset")
        if not isinstance(recorded, dict) or not recorded.get("files"):
            return {"reuse": False, "path": str(p),
                    "reason": "file lapis tak mencatat ruleset yang memproduksinya"}
        if set(recorded.get("files") or []) != set(provenance["files"]):
            return {"reuse": False, "path": str(p),
                    "reason": "ruleset berbeda dari yang memproduksi file lapis"}
        if provenance["mtime"] > float(recorded.get("mtime") or 0.0):
            return {"reuse": False, "path": str(p), "reason": "ruleset lebih baru dari file lapis"}
    elif kind == "image":
        # Versi yang TAK ada di file lapis dilewati di sini — itu celah cakupan, dan pemeriksaan
        # `missing` di bawah yang menjawabnya dengan alasan yang benar.
        vers = payload.get("versions") or {}
        for ver in requested:
            entry = vers.get(ver)
            if not isinstance(entry, dict):
                continue
            recorded_tag = entry.get("tag")
            expect = (provenance.get("expect") or {}).get(ver)
            if not recorded_tag:
                return {"reuse": False, "path": str(p),
                        "reason": "file lapis tak mencatat tag image yang memproduksinya"}
            if expect and recorded_tag != expect:
                return {"reuse": False, "path": str(p),
                        "reason": f"image berbeda dari yang memproduksi file lapis "
                                  f"({ver}: {recorded_tag} vs {expect})"}
    covered = layer_versions(payload)
    if covered is None:
        return {"reuse": False, "reason": "cakupan versi file lapis tak bisa dipastikan", "path": str(p)}
    # Nol versi diminta = `set() - covered` kosong = "cakupan cocok" secara vakum, dan justru
    # skrip yang tugasnya MENOLAK bukti basi yang mengucapkannya. File lapis yang meninjau versi
    # yang sama sekali lain pun lolos. Kembaran gerbang himpunan kosong di ps-aggregate; dijaga
    # di sini juga karena plan_layer bisa diimpor, bukan cuma dipanggil lewat main().
    if not requested:
        return {"reuse": False, "path": str(p),
                "reason": "cakupan tak bisa dinilai atas nol versi diminta"}
    missing = sorted(set(requested) - covered)
    if missing:
        return {"reuse": False, "reason": f"cakupan kurang: {', '.join(missing)}", "path": str(p)}
    return {"reuse": True, "reason": "lebih baru dari module & cakupan versi cocok", "path": str(p)}


def _e2e_scenario_notes(module_dir):
    """Catatan spec authored yang DILEWATI (JSON rusak / tanpa expect_*) — milik ps-e2e-run.

    Diimpor malas & by-path: aturan "spec mana yang sah" hanya boleh punya satu pemilik,
    dan menyalinnya ke sini akan jadi implementasi kedua yang mendrift diam-diam. Impor
    di dalam fungsi supaya pemanggil lain (ps-aggregate -> modul ini) tak ikut menyeretnya.
    Daftar sumber (dulu juga dikembalikan) DIHAPUS: e2e_scenarios cuma echo nama file, nol
    pembaca — cakupan authored sudah dipikul e2e_smoke_only di agregat.
    """
    e2e_path = Path(__file__).resolve().parent / "ps-e2e-run.py"
    if not e2e_path.is_file():
        return []
    spec = importlib.util.spec_from_file_location("ps_e2e_run", e2e_path)
    if not (spec and spec.loader):
        return []
    e2e = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(e2e)
    _found, notes = e2e.discover_scenarios(module_dir)
    return notes


def main():
    ap = argparse.ArgumentParser(
        description="Pra-pass: tentukan file lapis mana yang masih sah dipakai ulang.",
        epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("module_path", help="Path folder module PrestaShop")
    ap.add_argument("--reports-dir", default=DEFAULT_REPORTS_DIR,
                    help=f"Folder laporan (psm_reports_dir; default kanonik: {DEFAULT_REPORTS_DIR})")
    ap.add_argument("--versions", default="1.7.8,8.1,9.1", help="Versi target dipisah koma")
    ap.add_argument("--rules", default=str(ss.DEFAULT_RULES),
                    help="Path ps-rules.json yang akan dipakai Lapis 1 (default: assets/ps-rules.json)")
    ap.add_argument("--extra-rules", help="Path aturan TAMBAHAN yang akan dipakai Lapis 1 — "
                                          "teruskan yang sama seperti ke ps-static-scan.py, "
                                          "supaya kesegaran dinilai atas ruleset yang benar-benar berlaku")
    ap.add_argument("--tag-map", help="Peta versi->tag image yang berlaku (mis. dari "
                                      "psm_flashlight_tag_map) — MENGGANTI peta default. Dipakai "
                                      "untuk tahu apakah file lapis 2/4 diproduksi image yang SAMA "
                                      "dengan target sekarang; tag di-bump = bukti dari core lain.")
    ap.add_argument("--extra-tag-map", help="Tag TAMBAHAN di atas peta yang berlaku — MENAMBAH, "
                                            "bukan mengganti. Teruskan yang sama seperti ke Lapis 2/4.")
    ap.add_argument("-o", "--output", help="File output JSON (default: stdout)")
    args = ap.parse_args()

    # customization-3: token {project-root} yang tak terekspansi sampai titik pakai = folder
    # harfiah -> "file lapis belum ada" percaya diri -> rerun semua lapis mahal. Gerbang di
    # konsumen terberat (satu pemilik di ps-static-scan). --reports-dir yang mengonstruksi
    # path lapis adalah leak yang direproduksi; --rules/--extra-rules mirror nilai config juga.
    bad = ss.unresolved_path_args([("--reports-dir", args.reports_dir), ("-o", args.output),
                                   ("--rules", args.rules), ("--extra-rules", args.extra_rules)])
    if bad:
        for name, val in bad:
            print(f"error: token '{{project-root}}' belum diresolve di {name}: {val!r} — resolve "
                  "ke root project dulu; ini path filesystem, bukan nilai config.", file=sys.stderr)
        return 2

    module_dir = Path(args.module_path).resolve()
    if not module_dir.is_dir():
        print(f"error: bukan folder: {module_dir}", file=sys.stderr)
        return 2
    requested = [v.strip() for v in args.versions.split(",") if v.strip()]
    if not requested:
        print("error: tak ada versi target — pra-pass atas nol versi memakai-ulang file lapis "
              "apa pun, termasuk yang meninjau versi lain", file=sys.stderr)
        print("sebut --versions (mis. dari psm_target_versions) lalu ulangi", file=sys.stderr)
        return 2
    src_mtime, src_path = newest_source_mtime(module_dir)
    rel = str(src_path.relative_to(module_dir)) if src_path else None

    ruleset = ss.ruleset_provenance([args.rules, args.extra_rules])
    # Tag yang berlaku SEKARANG untuk tiap versi target. Diresolve lewat pemilik aturannya
    # (ps-flashlight-run), bukan disalin ke sini — implementasi ketiga yang mendrift akan
    # membuat gerbang ini menolak reuse yang sah, atau menerima bukti dari core yang lain.
    tag_map = fl.parse_tag_map(args.tag_map, args.extra_tag_map)
    image_prov = {"kind": "image", "expect": {v: fl.resolve_tag(tag_map, v) for v in requested}}
    # Tiap lapis punya input KEDUA-nya sendiri: ruleset memproduksi vonis Lapis 1, image
    # memproduksi vonis Lapis 2 & 4. Lapis 3 (judgment model) belum punya jejak yang bisa
    # dibandingkan — biarkan None sampai kontraknya mencatat sesuatu, jangan mengarang.
    prov_of = {"static": {"kind": "ruleset", **ruleset}, "flashlight": image_prov,
               "e2e": image_prov, "adversarial": None}
    plans = {}
    for layer in LAYERS:
        path = Path(args.reports_dir) / f"{module_dir.name}-{layer}.json"
        plans[layer] = plan_layer(path, requested, src_mtime, rel,
                                  provenance=prov_of[layer])

    result = {"module": module_dir.name, "versions": requested,
              "newest_source": rel, "layers": plans,
              "rerun": [l for l, p in plans.items() if not p["reuse"]]}

    # Spec E2E authored adalah satu-satunya input yang ditulis TANGAN, dan satu-satunya
    # yang mengangkat Lapis 4 di atas smoke-only. Validasinya murah, tapi dulu hanya
    # dijalankan di dalam ps-e2e-run — setelah boot flashlight x N versi x M browser —
    # jadi satu typo baru ketahuan setelah run mahal selesai. Di sini penulisnya sempat
    # memperbaiki lebih dulu. Sengaja TAK memblok: smoke universal tetap berguna walau
    # spec authored rusak (kejujurannya sudah dipikul e2e_smoke_only).
    notes = _e2e_scenario_notes(module_dir)
    if notes:
        result["e2e_scenario_notes"] = notes
    out = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"ditulis: {args.output}", file=sys.stderr)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
