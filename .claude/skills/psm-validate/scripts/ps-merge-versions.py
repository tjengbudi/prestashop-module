#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Satukan file lapis PER-VERSI (dari subagent per-versi) jadi satu file kanonik per-lapis.

Orkestrasi paralel psm-validate menjalankan lapis mahal (2 flashlight, 4 e2e) di SATU
subagent per versi target — isolasi konteks + paralelisme, memperluas pola Lapis 3.
Tiap subagent menulis file lapisnya sendiri (`<module>-<lapis>-<versi>.json`, masing-masing
memuat SATU versi di `versions`). Skrip ini menyatukannya jadi `<module>-<lapis>.json` yang
bentuknya SAMA PERSIS dengan output satu run multi-versi — sehingga ps-plan-layers.py dan
ps-aggregate.py tak perlu tahu apakah lapis dijalankan serial atau paralel.

Kenapa skrip, bukan tangan: SKILL.md melarang merakit/menilai ulang bukti dengan tangan.
Penggabungan punya SATU jawaban benar (union versi + rekonsiliasi top-level deterministik),
jadi ia milik skrip. Konflik = input rusak: dua file mengklaim versi yang SAMA dengan isi
BERBEDA berarti bukti tak konsisten (mis. dua run atas core beda) — tolak KERAS (exit 2),
jangan diam-diam memilih salah satu lalu memvonis atasnya.

exit 2 = input error (file tak terbaca/salah-bentuk/konflik versi); exit 0 = berhasil.
Tak ada exit 1: skrip ini tak memvonis lolos/gagal — ia cuma menyatukan.
"""
import argparse
import importlib.util
import json
import sys
from pathlib import Path

# Pakai-ulang gerbang bentuk & pemuat sibling dari ps-aggregate (impor by-path karena nama
# file ber-tanda-hubung) — "bentuk file lapis yang sah" hanya boleh punya satu pemilik.
_AGG_PATH = Path(__file__).resolve().parent / "ps-aggregate.py"


def _load_aggregate():
    """Muat ps-aggregate.py by-path. Gagal = exit 2 berpesan (folder scripts/ disalin sebagian)."""
    try:
        spec = importlib.util.spec_from_file_location("ps_aggregate", _AGG_PATH)
        if not (spec and spec.loader):
            raise ImportError(f"spec tak terbentuk untuk {_AGG_PATH}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        return module
    except (OSError, ImportError, SyntaxError) as e:
        print(f"error: skrip sibling tak bisa dimuat: {_AGG_PATH.name} ({e})", file=sys.stderr)
        print("skrip psm-validate saling bergantung — salin folder scripts/ utuh", file=sys.stderr)
        sys.exit(2)


agg = _load_aggregate()

# Kunci top-level dengan aturan rekonsiliasi KHUSUS. Sisanya jatuh ke aturan generik di bawah.
_AND_KEYS = ("pass",)                                    # AND: lolos hanya bila semua lolos
_OR_KEYS = ("e2e_available", "docker_available")         # OR: lapis tersedia bila ADA yang bisa
_PREFER_RAN_KEYS = ("status",)                           # "ran" bila ada satu pun yang jalan
_FIRST_PRESENT_KEYS = ("screenshot_dir",)                # ambil yang pertama tak-None


def _canon(v):
    """Representasi kanonik untuk perbandingan kesetaraan (urut kunci stabil)."""
    return json.dumps(v, sort_keys=True, ensure_ascii=False)


def merge_versions_field(payloads):
    """Union `versions` lintas payload. Versi bertumpuk dengan isi BEDA = konflik (raise).

    Return (merged_dict, urutan_kunci). Urutan mengikuti kemunculan pertama supaya output
    deterministik terhadap urutan --inputs.
    """
    merged, order = {}, []
    for idx, p in enumerate(payloads):
        versions = p.get("versions")
        if versions is None:
            continue  # file skipped (Docker absen) tak menyumbang versi — sah, bukan error
        if not isinstance(versions, dict):
            raise ValueError(f"input[{idx}]: 'versions' bertipe {type(versions).__name__}, "
                             "harus object {versi: {...}}")
        for ver, entry in versions.items():
            if ver in merged:
                if _canon(merged[ver]) != _canon(entry):
                    raise ValueError(
                        f"versi '{ver}' muncul di >1 input dengan isi BERBEDA — bukti tak "
                        "konsisten (dua run atas core/kode beda?); jalankan ulang versi itu "
                        "sekali lalu merge, jangan gabungkan dua vonis yang bertentangan")
                continue  # duplikat identik: sah (mis. reuse), pertahankan
            merged[ver] = entry
            order.append(ver)
    return {k: merged[k] for k in order}


def merge_toplevel(payloads, merged_versions):
    """Rekonsiliasi kunci top-level (selain `versions`) jadi satu dict deterministik."""
    out = {}
    keys = []
    for p in payloads:
        for k in p:
            if k != "versions" and k not in keys:
                keys.append(k)
    for k in keys:
        present = [p[k] for p in payloads if k in p]
        if not present:
            continue
        if k in _AND_KEYS:
            out[k] = all(bool(v) for v in present)
        elif k in _OR_KEYS:
            out[k] = any(bool(v) for v in present)
        elif k in _PREFER_RAN_KEYS:
            out[k] = "ran" if any(v == "ran" for v in present) else present[0]
        elif k in _FIRST_PRESENT_KEYS:
            nn = [v for v in present if v is not None]
            out[k] = nn[0] if nn else None
        elif any(isinstance(v, list) for v in present):
            # Union urut-stabil, dedup by isi kanonik (mis. scenario_notes, browsers).
            seen, acc = set(), []
            for v in present:
                for item in (v if isinstance(v, list) else [v]):
                    c = _canon(item)
                    if c not in seen:
                        seen.add(c)
                        acc.append(item)
            out[k] = acc
        else:
            # Skalar: identik di semua -> nilai itu; beda -> ambil pertama (deterministik
            # terhadap urutan --inputs). Beda pada skalar top-level (mis. module, orchestrator)
            # tak menggerbang vonis; versions-lah yang membawa bukti, dan itu sudah dijaga.
            out[k] = present[0]
    out["versions"] = merged_versions
    return out


def main():
    ap = argparse.ArgumentParser(
        description="Satukan file lapis per-versi jadi satu file kanonik per-lapis.",
        epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--inputs", nargs="+", required=True,
                    help="File lapis per-versi (satu lapis yang SAMA, tiap file satu/sedikit versi)")
    ap.add_argument("--layer", choices=agg.LAYERS,
                    help="Nama lapis (utk validasi bentuk finding; opsional — hanya static "
                         "yang mewajibkan kunci finding)")
    ap.add_argument("-o", "--output", help="File kanonik keluaran (default: stdout)")
    args = ap.parse_args()

    if len(args.inputs) < 1:
        print("error: --inputs butuh minimal satu file", file=sys.stderr)
        return 2

    payloads = [agg.load_json(pth, f"input {pth}") for pth in args.inputs]

    # Gerbang bentuk SEBELUM merge — file terpotong (subagent di-kill saat tulis) tak boleh
    # menyelinap jadi output kanonik yang lalu meledak di ps-aggregate. Kunci finding hanya
    # diwajibkan utk static (lapis lain pakai .get()); pakai gerbang yang sama dgn ps-aggregate.
    finding_keys = ("id", "severity", "message") if args.layer == "static" else ()
    for pth, payload in zip(args.inputs, payloads):
        notes = agg.validate_layer_shape(payload, finding_keys)
        if notes:
            print(f"error: input {pth} tak lolos gerbang bentuk:", file=sys.stderr)
            for n in notes:
                print(f"  - {n}", file=sys.stderr)
            print("file lapis rusak = input rusak (exit 2) — jalankan ulang versi itu lalu ulangi",
                  file=sys.stderr)
            return 2

    try:
        merged_versions = merge_versions_field(payloads)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    result = merge_toplevel(payloads, merged_versions)
    out = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"ditulis: {args.output}", file=sys.stderr)
    else:
        print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
