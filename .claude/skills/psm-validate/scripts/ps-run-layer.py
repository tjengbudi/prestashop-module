#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Jalankan SATU lapis mahal (2 flashlight / 4 e2e) untuk BANYAK versi serentak, lalu tulis
satu file lapis KANONIK — bentuknya sama persis dengan run multi-versi serial.

Kenapa skrip, bukan fan-out subagent: penggabungan bukti punya satu jawaban benar, dan
"file mana yang jadi input" ditentukan sepenuhnya oleh (module, lapis, versi target) yang
sudah dipegang pemanggil. Begitu daftar input diketik model, gerbang-gerbang yang menjaga
file lapis kehilangan pijakan: skrip penggabung tak lagi tahu module/lapis/versi apa yang
seharusnya ada, jadi ia tak bisa memeriksa kesegaran, identitas, maupun kelengkapan. Skrip
ini memegang keempatnya by construction:

  - KESEGARAN — bukti diproduksi lalu ditulis oleh proses yang sama, jadi mtime file kanonik
    jujur dan gerbang mtime ps-plan-layers tetap berlaku (file hasil penggabungan terpisah
    selalu tampak lebih muda dari module, apa pun umur buktinya).
  - IDENTITAS — satu module, satu lapis, satu peta flag untuk semua anak, dan nama file
    lapis DITURUNKAN dari (folder laporan, module, lapis) alih-alih diketik: bukti tak bisa
    mendarat di file module lain atau lapis lain.
  - KELENGKAPAN — versi yang tak menghasilkan bukti DIHILANGKAN dari `versions`, tak pernah
    dikarang jadi vonis. ps-aggregate menandainya tak konklusif dan `ready` jatuh; itu
    degrade jujur, bukan kegagalan yang memblok.
  - ISOLASI — file per-versi hidup di direktori temp dan ikut terhapus, jadi tak ada artefak
    setengah jadi yang menetap di folder laporan dengan nama yang mirip bukti sah.

Skrip lapisnya sendiri TIDAK disentuh: tiap anak adalah `ps-<lapis>-run.py <module>
--versions <satu>` persis di mode single-versi yang sudah teruji. Flag lapis diteruskan apa
adanya sesudah `--`, jadi flag baru di skrip lapis tak perlu didaftarkan ulang di sini.

exit 2 = error input (lapis tak paralel, flag milik skrip ini ada di passthrough, token path
belum diresolve, anak menolak inputnya, bukti tak konsisten) — bukti per-versi dipertahankan
di direktori temp yang disebut pesannya supaya kegagalan bisa didiagnosis, bukan dibuang
bersama puluhan menit boot Docker. exit 1 = ada versi yang gagal atau tak menghasilkan bukti.
exit 0 = semua versi menghasilkan bukti dan lolos, ATAU lapisnya memang tak tersedia
(Docker/browser absen) — sama seperti run serial, degrade jujur bukan vonis gagal.

Contoh:
  uv run scripts/ps-run-layer.py --layer e2e --module modules/mymod \\
      --versions 1.7.8,8.1,9.1 --jobs 3 --reports-dir reports \\
      -- --tag-map 1.7.8=1.7.8.11,8.1=8.1.6-nginx,9.1=9.1.4-nginx --browsers chromium,firefox
"""
import argparse
import json
import os
import shutil
import sys
import tempfile
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

_HERE = Path(__file__).resolve().parent

# Lapis yang memang dijalankan per versi. static murah dan sekali jalan di orkestrator;
# adversarial adalah judgment satu reviewer atas seluruh cakupan — memaralelkan keduanya
# bukan optimasi, dan file-nya tak berbentuk {versi: {...}} yang bisa disatukan.
PARALLEL_LAYERS = {"flashlight": "ps-flashlight-run.py", "e2e": "ps-e2e-run.py"}
SERIAL_LAYERS = {
    "static": "lapis static murah dan dijalankan sekali di orkestrator untuk semua versi",
    "adversarial": "lapis adversarial adalah satu reviewer atas seluruh cakupan, bukan per versi",
}

# Flag yang dimiliki skrip ini. Diteruskan lagi lewat passthrough = dua sumber kebenaran
# untuk hal yang sama, dan anak akan menimpa apa yang sudah dijamin di sini.
RESERVED_PASSTHROUGH = ("--versions", "-o", "--output")

DEFAULT_JOBS = 3  # tiap job mem-boot container PS + DB (Lapis 4 plus engine browser)

# --- Penggabungan bukti per-versi ---------------------------------------------------------
# Aturannya tinggal di sini, bersama satu-satunya yang menggabungkan. Sebelumnya ia CLI
# tersendiri yang menerima daftar file yang diketik model; bentuk itu melucuti tiap gerbang
# yang menjaga file lapis (penggabung yang cuma diberi path tak tahu module/lapis/versi apa
# yang seharusnya ada) dan file kanonik hasilnya selalu ber-mtime baru, yang membatalkan
# gerbang kesegaran ps-plan-layers atas bukti selama apa pun.
_AND_KEYS = ("pass",)                                    # AND: lolos hanya bila semua lolos
_OR_KEYS = ("e2e_available", "docker_available")         # OR: lapis tersedia bila ADA yang bisa
_PREFER_RAN_KEYS = ("status",)                           # "ran" bila ada satu pun yang jalan

_agg = None
_e2e = None


def _sibling(name, modname):
    """Muat skrip sibling by-path lewat pemuat milik ps-aggregate (satu pemilik aturannya)."""
    global _agg
    if _agg is None:
        import importlib.util
        path = _HERE / "ps-aggregate.py"
        try:
            spec = importlib.util.spec_from_file_location("ps_aggregate", path)
            if not (spec and spec.loader):
                raise ImportError(f"spec tak terbentuk untuk {path}")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            _agg = mod
        except (OSError, ImportError, SyntaxError) as e:
            print(f"error: skrip sibling tak bisa dimuat: {path.name} ({e})", file=sys.stderr)
            print("skrip psm-validate saling bergantung — salin folder scripts/ utuh", file=sys.stderr)
            sys.exit(2)
    if name == "ps-aggregate.py":
        return _agg
    return _agg.load_sibling(_HERE / name, modname)


def aggregate():
    return _sibling("ps-aggregate.py", "ps_aggregate")


def _canon(v):
    """Representasi kanonik untuk perbandingan kesetaraan (urut kunci stabil)."""
    return json.dumps(v, sort_keys=True, ensure_ascii=False)


def merge_versions_field(payloads):
    """Union `versions` lintas payload. Versi bertumpuk dengan isi BEDA = konflik (raise).

    Urutan kunci mengikuti kemunculan pertama supaya output deterministik. Payload tanpa
    `versions` (lapis skipped, mis. Docker absen) tak menyumbang versi — sah, bukan error.
    """
    merged, order = {}, []
    for idx, p in enumerate(payloads):
        versions = p.get("versions")
        if versions is None:
            continue
        if not isinstance(versions, dict):
            raise ValueError(f"input[{idx}]: 'versions' bertipe {type(versions).__name__}, "
                             "harus object {versi: {...}}")
        for ver, entry in versions.items():
            if ver in merged:
                if _canon(merged[ver]) != _canon(entry):
                    raise ValueError(
                        f"versi '{ver}' muncul di >1 bukti dengan isi BERBEDA — bukti tak "
                        "konsisten (dua run atas core/kode beda?); jalankan ulang versi itu "
                        "sekali, jangan gabungkan dua vonis yang bertentangan")
                continue  # duplikat identik: sah, pertahankan
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
        elif any(isinstance(v, list) for v in present):
            seen, acc = set(), []
            for v in present:
                for item in (v if isinstance(v, list) else [v]):
                    c = _canon(item)
                    if c not in seen:
                        seen.add(c)
                        acc.append(item)
            out[k] = acc
        else:
            # Skalar. null = tak dilaporkan (dilewati). Dua nilai berbeda = dua klaim yang
            # bertentangan tentang run yang sama; memilih salah satunya diam-diam membuang
            # yang lain, dan untuk kunci seperti screenshot_dir yang dibuang itu adalah letak
            # bukti yang justru disuruh ditinjau vonis.
            vals, seen = [], set()
            for v in present:
                if v is None:
                    continue
                c = _canon(v)
                if c not in seen:
                    seen.add(c)
                    vals.append(v)
            if len(vals) > 1:
                raise ValueError(
                    f"kunci top-level '{k}' berbeda antar bukti versi: {vals!r} — bukti tak "
                    "konsisten; semuanya mestinya berasal dari satu run atas satu module "
                    "dengan setelan yang sama")
            out[k] = vals[0] if vals else None
    out["versions"] = merged_versions
    return out


def e2e_module():
    global _e2e
    if _e2e is None:
        _e2e = _sibling("ps-e2e-run.py", "ps_e2e_run")
    return _e2e


def parse_versions(raw):
    """Daftar versi target, urut kemunculan & tanpa duplikat. Himpunan kosong = error input.

    Dedup bukan kosmetik: dua entri versi yang sama berarti dua anak menulis file bukti yang
    sama DAN mem-boot container ber-nama proyek yang sama secara serentak.
    """
    out = []
    for v in (raw or "").split(","):
        v = v.strip()
        if v and v not in out:
            out.append(v)
    return out


def reserved_in_passthrough(extra):
    """Flag milik skrip ini yang muncul di passthrough — pelanggaran, bukan preferensi.

    Anak menerima --versions dan -o dari skrip ini; meneruskannya lagi berarti versi yang
    dijalankan atau tempat bukti ditulis tak lagi bisa dipastikan siapa yang menentukan.
    Bentuk yang harus tertangkap bukan cuma `--versions x` — argparse anak juga menerima
    `-o/path` yang menempel, `--output=path`, dan singkatan awalan (`--version`, `--outp`).
    Yang menempel adalah yang paling berbahaya: ia pernah lolos gerbang lalu MENIMPA file
    lapis lain di folder laporan.
    """
    hits = []
    for tok in extra:
        head = tok.split("=", 1)[0]
        if head in RESERVED_PASSTHROUGH:
            hits.append(head)
        elif tok.startswith("-o") and len(tok) > 2 and not tok.startswith("--"):
            hits.append("-o")  # bentuk menempel: -o/path/file.json
        elif head.startswith("--") and len(head) > 2:
            for full in ("--versions", "--output"):
                if len(head) >= 4 and full.startswith(head):
                    hits.append(full)  # singkatan awalan yang argparse anak terima
                    break
    return hits


def split_screenshot_dir(extra):
    """Angkat `--screenshot-dir <base>` keluar dari passthrough. Return (sisa, base|None).

    Folder screenshot harus SATU untuk seluruh run: tiap anak yang menstempel folder run-nya
    sendiri akan memecah bukti visual jadi N folder, dan hanya satu yang sampai ke vonis.
    """
    rest, base = [], None
    i = 0
    while i < len(extra):
        tok = extra[i]
        if tok == "--screenshot-dir" and i + 1 < len(extra):
            base = extra[i + 1]
            i += 2
            continue
        if tok.startswith("--screenshot-dir="):
            base = tok.split("=", 1)[1]
            i += 1
            continue
        rest.append(tok)
        i += 1
    return rest, base


def layer_file(reports_dir, module_path, layer):
    """Path file lapis kanonik — DITURUNKAN dari (folder laporan, module, lapis).

    Dulu ini argumen `-o` yang diketik pemanggil, tak terikat ke `--module` maupun `--layer`.
    Akibatnya bukti module A bisa mendarat di `<module-B>-e2e.json`, atau bukti e2e di file
    flashlight, tanpa satu pun gerbang menyadarinya: ps-plan-layers lalu melewati lapis mahal
    untuk module B dan ps-aggregate mengkredit vonis module A kepadanya. Nama yang diturunkan
    membuat kelas itu tak punya permukaan.
    """
    return str(Path(reports_dir) / f"{Path(module_path).resolve().name}-{layer}.json")


def per_version_file(reports_dir, module_path, layer, ver):
    """Path file lapis PER-VERSI — `<reports>/<module>-<lapis>-<versi>.json`, DITURUNKAN.

    Cermin per_version_path di ps-plan-layers (pembacanya). Sama seperti layer_file, nama tak
    bisa diketik pemanggil: bukti versi V tak bisa mendarat di file versi/lapis/module lain.
    Segmen versi selalu ada, jadi tak pernah bentrok dgn nama kanonik `<module>-<lapis>.json`.
    """
    return str(Path(reports_dir) / f"{Path(module_path).resolve().name}-{layer}-{ver}.json")


def plan_children(script, module_path, versions, out_dir, extra):
    """(versi, cmd, out_path) untuk tiap versi. Murni — bisa diuji tanpa men-spawn apa pun."""
    plan = []
    for ver in versions:
        out = str(Path(out_dir) / f"{ver}.json")
        cmd = ["uv", "run", str(script), str(module_path),
               "--versions", ver, "-o", out, *extra]
        plan.append((ver, cmd, out))
    return plan


def _spawn(cmd):
    """Runner nyata: jalankan anak, kembalikan exit code-nya. Diganti test lewat injeksi."""
    import subprocess
    return subprocess.run(cmd).returncode


def execute(plan, jobs, runner=None, log=None):
    """Jalankan tiap anak (paling banyak `jobs` serentak). Return {versi: exit_code}.

    Anak adalah proses OS terpisah, jadi thread di sini hanya menunggu I/O — dan Playwright
    sync yang tak thread-safe tetap sendirian di prosesnya masing-masing.
    """
    runner = runner or _spawn  # diikat saat panggil, bukan saat def, supaya bisa diinjeksi test
    width = max(1, min(jobs, len(plan)))
    codes = {}
    with ThreadPoolExecutor(max_workers=width) as ex:
        futures = {ex.submit(runner, cmd): ver for ver, cmd, _ in plan}
        for fut, ver in futures.items():
            try:
                codes[ver] = fut.result()
            except Exception as e:  # runner meledak = versi itu tak berbukti, bukan vonis
                codes[ver] = None
                if log:
                    log(f"versi {ver}: runner gagal ({e})")
    return codes


def collect(plan, codes):
    """Baca bukti tiap anak. Return (payloads, missing, rejected).

    `missing` = versi tanpa bukti yang bisa dipercaya (anak mati, file tak ada, JSON rusak).
    `rejected` = anak menolak inputnya (exit 2) atau melaporkan versi di luar yang diminta —
    itu error input, bukan vonis, dan tak boleh dibungkus jadi "versi gagal".
    """
    pairs, missing, rejected = [], [], []
    for ver, _cmd, out in plan:
        code = codes.get(ver)
        if code == 2:
            rejected.append((ver, "anak menolak input (exit 2) — baca stderr-nya"))
            continue
        try:
            payload = json.loads(Path(out).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            missing.append(ver)
            continue
        if not isinstance(payload, dict):
            missing.append(ver)
            continue
        got = payload.get("versions")
        if isinstance(got, dict):
            stray = sorted(set(got) - {ver})
            if stray:
                rejected.append((ver, f"anak melaporkan versi di luar yang diminta: {stray}"))
                continue
        # Payload tanpa entri untuk versinya sendiri = tak ada bukti per-versi. Bentuk ini
        # NYATA di produksi: anak yang tak menemukan Docker/Playwright mengemit
        # {"status": "skipped", "versions": {}} lalu exit 0. Kalau ini dianggap sukses, versi
        # itu lenyap dari file kanonik tanpa sepatah kata pun sementara file yang sama tetap
        # berkata "ran"/pass — vonis yang isinya membantah dirinya sendiri.
        if not (got or {}):
            missing.append(ver)
            pairs.append((ver, payload))  # tetap dipakai: ia membawa alasan skip-nya
            continue
        pairs.append((ver, payload))
    return pairs, missing, rejected


def merge_only(reports_dir, module_path, layer, versions, log):
    """Sweep rilis: satukan file per-versi persisten jadi kanonik, TANPA menjalankan lapis.

    Input tiap versi = `<reports>/<module>-<lapis>-<versi>.json` (nama DITURUNKAN, sama seperti
    yang ditulis mode --per-version) — bukan daftar yang diketik, jadi gerbang identitas berlaku.
    Versi tanpa file per-versi DIHILANGKAN (degrade jujur; agregat menandainya tak konklusif,
    ready jatuh), bukan dikarang jadi vonis. mtime kanonik = mtime bukti TERTUA supaya kanonik tak
    pernah tampak lebih segar dari bukti terbasi yang menyusunnya — gerbang kesegaran ps-plan-layers
    tetap menyala bila source diedit sesudah salah satu versi dikonvergensi.
    """
    agg = aggregate()
    ss = agg.load_sibling(_HERE / "ps-static-scan.py", "ps_static_scan")
    bad = ss.unresolved_path_args([("--reports-dir", reports_dir), ("--module", module_path)])
    for name, val in bad:
        log(f"error: token '{{project-root}}' belum diresolve di {name}: {val}")
        log("ini path filesystem, bukan nilai config — resolve dulu di pemanggil")
    if bad:
        return 2
    output = layer_file(reports_dir, module_path, layer)
    pairs, missing = [], []
    for ver in versions:
        pvf = per_version_file(reports_dir, module_path, layer, ver)
        try:
            payload = json.loads(Path(pvf).read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            missing.append(ver)
            continue
        if not isinstance(payload, dict):
            missing.append(ver)
            continue
        # Gerbang bentuk sama seperti sebelum merge run nyata: file per-versi yang terpotong
        # (proses di-kill saat menulis) tak boleh menyelinap jadi kanonik lalu meledak di agregat.
        notes = agg.validate_layer_shape(payload, ())
        if notes:
            log(f"error: file per-versi {ver} tak lolos gerbang bentuk ({pvf}):")
            for n in notes:
                log(f"  - {n}")
            return 2
        got = payload.get("versions")
        # IDENTITAS pada BACA: file per-versi hanya boleh memuat versinya sendiri. Versi asing =
        # file salah-label (stale, atau ditaruh manual) — error input, bukan vonis. Nama file
        # diturunkan by construction, tapi merge-only sengaja memakan file yang tak ditulisnya
        # dalam proses ini, jadi klaim identitas HARUS ditegakkan di sini (cermin collect()).
        if isinstance(got, dict):
            stray = sorted(set(got) - {ver})
            if stray:
                log(f"error: file per-versi {ver} memuat versi di luar yang diminta: {stray} "
                    f"({pvf}) — file salah-label, bukan bukti versi {ver}")
                return 2
        try:
            mtime = Path(pvf).stat().st_mtime
        except OSError:
            missing.append(ver)
            continue
        # Bukti kosong (versions {}) = anak melewatkan lapis: versi ini TAK berbukti. Persis
        # collect(): masuk `missing` (ready jatuh, bukan diam-diam hilang dengan exit 0) TAPI
        # payload skip tetap ikut merge — ia membawa status/alasan skip untuk kasus "seluruh
        # lapis tak tersedia" di bawah.
        if not (got or {}):
            missing.append(ver)
        pairs.append((ver, payload, mtime))
    for ver in missing:
        log(f"versi {ver}: file per-versi tak ada/kosong — dihilangkan dari kanonik "
            "(agregat menandainya tak konklusif, ready jatuh)")
    if not pairs:
        log(f"error: tak ada file per-versi yang bisa digabung untuk lapis '{layer}' — "
            "jalankan lapis per versi (--per-version) dulu")
        return 1
    payloads = [p for _v, p, _m in pairs]
    try:
        result = merge_toplevel(payloads, merge_versions_field(payloads))
    except ValueError as e:
        log(f"error: {e}")
        return 2
    try:
        Path(output).write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        log(f"error: gagal menulis {output}: {e}")
        return 2
    oldest = min(m for _v, _p, m in pairs)
    try:
        os.utime(output, (oldest, oldest))
    except OSError:
        pass
    log(f"ditulis: {output} (gabung {len(pairs)} versi, mtime = bukti tertua)")
    # Exit MENGIKUTI run serial (docstring: "bentuk & exit code identik"): seluruh lapis tak
    # tersedia (semua skip/hilang, tak ada 'pass') -> 0 degrade jujur; ada versi tanpa bukti -> 1;
    # lengkap -> 0 bila lolos, 1 bila tidak. `return 1 if missing else 0` dulu MENGABAIKAN pass:
    # kanonik ber-pass:false tanpa versi hilang lolos sebagai exit 0 (gerbang CI terbaca hijau).
    if "pass" not in result and len(missing) == len(versions):
        return 0
    if missing:
        return 1
    return 0 if result.get("pass") else 1


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Jalankan satu lapis mahal untuk banyak versi serentak, tulis file lapis kanonik.",
        epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--layer", required=True,
                    help="Lapis yang dijalankan per versi: " + "|".join(PARALLEL_LAYERS))
    ap.add_argument("--module", required=True, help="Path folder module PrestaShop")
    ap.add_argument("--versions", required=True, help="Versi target, dipisah koma")
    ap.add_argument("--jobs", type=int, default=DEFAULT_JOBS,
                    help=f"Versi yang boot serentak (default {DEFAULT_JOBS}; tiap job mem-boot "
                         "container PS + DB)")
    ap.add_argument("--reports-dir", required=True,
                    help="Folder laporan (psm_reports_dir). Nama file lapis DITURUNKAN dari "
                         "module & lapis — tak bisa diketik, supaya bukti tak bisa mendarat "
                         "di file module atau lapis lain")
    ap.add_argument("--verbose", action="store_true", help="Jejak per versi ke stderr")
    ap.add_argument("--per-version", action="store_true",
                    help="Persist bukti tiap versi sebagai file lapis PER-VERSI "
                         "`<module>-<lapis>-<versi>.json` (nama diturunkan) alih-alih menulis satu "
                         "file kanonik. Untuk fase konvergensi version-first: bukti tiap versi "
                         "menetap sendiri, jadi menjalankan versi lain tak menimpanya.")
    ap.add_argument("--merge-only", action="store_true",
                    help="JANGAN jalankan lapis; baca file per-versi persisten "
                         "`<module>-<lapis>-<versi>.json` untuk --versions lalu satukan jadi file "
                         "kanonik untuk sweep rilis. mtime kanonik = mtime bukti per-versi TERTUA "
                         "(kanonik tak lebih segar dari bukti terbasinya).")
    ap.add_argument("extra", nargs=argparse.REMAINDER,
                    help="Setelah `--`: flag yang diteruskan apa adanya ke skrip lapis")
    args = ap.parse_args(argv)

    def log(msg):
        print(msg, file=sys.stderr)

    if args.per_version and args.merge_only:
        log("error: --per-version dan --merge-only saling eksklusif — satu MEMPRODUKSI file "
            "per-versi, satu MENYATUKANNYA jadi kanonik")
        return 2

    if args.layer in SERIAL_LAYERS:
        log(f"error: lapis '{args.layer}' tak dijalankan per versi — {SERIAL_LAYERS[args.layer]}")
        log("jalankan skrip lapisnya langsung dengan seluruh daftar versi")
        return 2
    if args.layer not in PARALLEL_LAYERS:
        log(f"error: lapis '{args.layer}' tak dikenal; pilih: {', '.join(PARALLEL_LAYERS)}")
        return 2

    versions = parse_versions(args.versions)
    if not versions:
        log("error: --versions kosong — tak ada yang bisa dijalankan maupun divonis")
        return 2
    if args.jobs < 1:
        log(f"error: --jobs harus >= 1 (diberi {args.jobs})")
        return 2

    if args.merge_only:
        # Tak men-spawn apa pun: flag passthrough setelah `--` tak punya tujuan, dan menerimanya
        # diam-diam menyembunyikan salah pakai.
        extra = list(args.extra)
        if extra and extra[0] == "--":
            extra = extra[1:]
        if extra:
            log("error: --merge-only tak menjalankan lapis apa pun — flag passthrough setelah "
                "`--` tak bermakna; hapus")
            return 2
        return merge_only(args.reports_dir, args.module, args.layer, versions, log)

    extra = list(args.extra)
    if extra and extra[0] == "--":
        extra = extra[1:]

    hits = reserved_in_passthrough(extra)
    if hits:
        log(f"error: flag milik skrip ini ada di passthrough: {', '.join(sorted(set(hits)))}")
        log("--versions dan -o ditentukan di sini supaya tiap anak tak bisa menimpanya")
        return 2

    extra, shot_base = split_screenshot_dir(extra)

    agg = aggregate()
    ss = agg.load_sibling(_HERE / "ps-static-scan.py", "ps_static_scan")
    bad = ss.unresolved_path_args([("--reports-dir", args.reports_dir),
                                   ("--screenshot-dir", shot_base),
                                   ("--module", args.module)])
    for name, val in bad:
        log(f"error: token '{{project-root}}' belum diresolve di {name}: {val}")
        log("ini path filesystem, bukan nilai config — resolve dulu di pemanggil")
    if bad:
        return 2

    if shot_base:
        # Distempel SEKALI di sini; anak menerima folder yang sudah berstempel dan
        # run_shot_dir-nya mempertahankannya, jadi semua versi mendarat di satu folder run.
        shot_dir = e2e_module().run_shot_dir(shot_base)
        extra = [*extra, "--screenshot-dir", shot_dir]

    script = _HERE / PARALLEL_LAYERS[args.layer]
    if not script.is_file():
        log(f"error: skrip lapis tak ada: {script}")
        return 2

    output = layer_file(args.reports_dir, args.module, args.layer)

    # Direktori bukti dibuat manual, bukan lewat context manager: pada kegagalan pasca-spawn
    # ia SENGAJA dipertahankan. Run empat lapis bisa berarti puluhan menit boot Docker, dan
    # membuang seluruhnya karena satu anak menulis payload cacat membuat kegagalan itu tak
    # bisa dipulihkan maupun didiagnosis. Pada jalur sukses ia dihapus.
    started = time.time()
    tmp = tempfile.mkdtemp(prefix="psm-layer-")
    keep = False
    try:
        plan = plan_children(script, args.module, versions, tmp, extra)
        if args.verbose:
            log(f"lapis {args.layer}: {len(plan)} versi, {min(args.jobs, len(plan))} serentak")
        codes = execute(plan, args.jobs, log=log if args.verbose else None)
        pairs, missing, rejected = collect(plan, codes)

        for ver, why in rejected:
            log(f"error: versi {ver}: {why}")
        if rejected:
            keep = True
            return 2

        # Gerbang bentuk SEBELUM merge: anak yang di-kill saat menulis meninggalkan file
        # terpotong, dan itu tak boleh menyelinap jadi file kanonik lalu meledak di agregat.
        for ver, payload in pairs:
            notes = agg.validate_layer_shape(payload, ())
            if notes:
                log(f"error: bukti versi {ver} tak lolos gerbang bentuk:")
                for n in notes:
                    log(f"  - {n}")
                keep = True
                return 2

        payloads = [p for _v, p in pairs]
        try:
            result = merge_toplevel(payloads, merge_versions_field(payloads))
        except ValueError as e:
            log(f"error: {e}")
            keep = True
            return 2

        # mtime = SAAT RUN MULAI, bukan saat tulis. Gerbang kesegaran ps-plan-layers memakai
        # mtime file lapis sebagai proksi "kapan bukti ini diproduksi"; run multi-versi bisa
        # berjalan puluhan menit, jadi stempel waktu-tulis membuat source yang diedit DI
        # TENGAH run terbaca lebih tua dari buktinya. Berlaku sama untuk file per-versi.
        if args.per_version:
            # Persist tiap bukti versi ke file per-versi (nama DITURUNKAN); TAK menulis kanonik.
            # Bukti tiap versi menetap sendiri, jadi menjalankan versi lain tak menimpanya — itulah
            # yang memungkinkan konvergensi per-versi. `result` tetap dihitung di atas, hanya untuk
            # keputusan exit/degrade di bawah, tak ditulis ke disk di mode ini.
            for ver, payload in pairs:
                # Payload skip (versions {}) TAK dipersist: versi ini tak berbukti, sudah masuk
                # `missing` & dilaporkan di bawah. Menuliskannya membuat file per-versi kosong yang
                # kelak dibaca merge-only sebagai "ada tapi hampa" — kelas yang justru dijaga di
                # sana; jangan produksi sumbernya. Versi tanpa file = tak berbukti, konsisten.
                if not (payload.get("versions") or {}):
                    continue
                pvf = per_version_file(args.reports_dir, args.module, args.layer, ver)
                try:
                    Path(pvf).write_text(json.dumps(payload, indent=2, ensure_ascii=False),
                                         encoding="utf-8")
                except OSError as e:
                    log(f"error: gagal menulis {pvf}: {e}")
                    keep = True
                    return 2
                try:
                    os.utime(pvf, (started, started))
                except OSError:
                    pass
                log(f"ditulis: {pvf}")
        else:
            try:
                Path(output).write_text(json.dumps(result, indent=2, ensure_ascii=False),
                                        encoding="utf-8")
            except OSError as e:
                log(f"error: gagal menulis {output}: {e}")
                keep = True
                return 2
            try:
                os.utime(output, (started, started))
            except OSError:
                pass
            log(f"ditulis: {output}")

        # Lapis tak tersedia sama sekali (Docker/browser absen di mesin ini): TIAP anak
        # melewatkannya dan tak satu pun mengeluarkan vonis. Bentuk dan exit code harus
        # mengikuti run serial — runner tanpa Docker bukan module yang gagal. Dibedakan dari
        # "sebagian versi tak berbukti", yang justru harus jatuh.
        if "pass" not in result and len(missing) == len(versions):
            log(f"lapis {args.layer} tak dijalankan: {result.get('reason') or 'tak tersedia'}")
            return 0
        for ver in missing:
            log(f"versi {ver}: tak menghasilkan bukti per-versi — dihilangkan dari file lapis "
                "(agregat menandainya tak konklusif, ready jatuh)")
        if missing:
            return 1
        return 0 if result.get("pass") else 1
    finally:
        if keep:
            log(f"bukti per-versi DIPERTAHANKAN untuk diagnosis: {tmp}")
        else:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
