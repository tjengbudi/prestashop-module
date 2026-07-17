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

# "Folder mana yang bukan source module" hanya boleh punya SATU definisi — dua
# implementasi berbeda (substring vs komponen path) pernah sama-sama salah &
# gagal ke arah tak aman. Pakai-ulang dari ps-static-scan (impor by-path karena
# nama file ber-tanda-hubung), pola yang sama dgn ps-e2e-run -> ps-flashlight-run.
_SS_PATH = Path(__file__).resolve().parent / "ps-static-scan.py"
_spec = importlib.util.spec_from_file_location("ps_static_scan", _SS_PATH)
assert _spec and _spec.loader, f"tak bisa memuat sibling {_SS_PATH}"
ss = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ss)


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


def plan_layer(path, requested, src_mtime, src_path):
    """Putuskan reuse/rerun satu file lapis + alasannya."""
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
    covered = layer_versions(payload)
    if covered is None:
        return {"reuse": False, "reason": "cakupan versi file lapis tak bisa dipastikan", "path": str(p)}
    missing = sorted(set(requested) - covered)
    if missing:
        return {"reuse": False, "reason": f"cakupan kurang: {', '.join(missing)}", "path": str(p)}
    return {"reuse": True, "reason": "lebih baru dari module & cakupan versi cocok", "path": str(p)}


def main():
    ap = argparse.ArgumentParser(
        description="Pra-pass: tentukan file lapis mana yang masih sah dipakai ulang.",
        epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("module_path", help="Path folder module PrestaShop")
    ap.add_argument("--reports-dir", required=True, help="Folder laporan (psm_reports_dir)")
    ap.add_argument("--versions", default="1.7.8,8.1,9.1", help="Versi target dipisah koma")
    ap.add_argument("-o", "--output", help="File output JSON (default: stdout)")
    args = ap.parse_args()

    module_dir = Path(args.module_path).resolve()
    if not module_dir.is_dir():
        print(f"error: bukan folder: {module_dir}", file=sys.stderr)
        return 2
    requested = [v.strip() for v in args.versions.split(",") if v.strip()]
    src_mtime, src_path = newest_source_mtime(module_dir)
    rel = str(src_path.relative_to(module_dir)) if src_path else None

    plans = {}
    for layer in LAYERS:
        path = Path(args.reports_dir) / f"{module_dir.name}-{layer}.json"
        plans[layer] = plan_layer(path, requested, src_mtime, rel)

    result = {"module": module_dir.name, "versions": requested,
              "newest_source": rel, "layers": plans,
              "rerun": [l for l, p in plans.items() if not p["reuse"]]}
    out = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"ditulis: {args.output}", file=sys.stderr)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
