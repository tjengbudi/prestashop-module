#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Jalankan SATU lapis mahal (2 flashlight / 4 e2e / 5 scenario) untuk BANYAK versi serentak.

Lapis 2 & 5 menulis satu file lapis KANONIK (atau file per-versi dgn --per-version) — bentuknya
sama persis dengan run multi-versi serial. Lapis 4 (e2e) TIDAK menulis file lapis: ia menambah
HISTORI per sel `<reports>/<module>-e2e-<ver>-<browser>.jsonl` (lihat "LAPIS E2E" di bawah).

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

`--config <psm-config.json>` berlaku untuk SEMUA lapis dan diteruskan apa adanya ke tiap anak
(Lapis 2/5 tak memvalidasinya). `--config`, `--browsers`, `--engines`, `--run-id`, `--slot-cost`,
`--progress-append`, `--sequential-browsers`, `--engine-worker`, `--tier` (dan flag lain milik
skrip ini, termasuk
singkatan awalan >= 4 karakter, mis. `--slo`; khusus `--tier` baru mulai `--tie`, karena `--ti`
adalah singkatan `--timeout` anak yang sah) DILARANG di passthrough sesudah `--`.

Lapis 2/5 — exit 2 = error input (lapis tak paralel, flag milik skrip ini ada di passthrough,
token path belum diresolve, anak menolak inputnya, bukti tak konsisten) — bukti per-versi
dipertahankan di direktori temp yang disebut pesannya supaya kegagalan bisa didiagnosis.
exit 1 = ada versi yang gagal atau tak menghasilkan bukti. exit 0 = semua versi menghasilkan
bukti dan lolos, ATAU lapisnya memang tak tersedia (Docker absen) — degrade jujur.

LAPIS E2E (cell-contract.md > Evidence record, Runner):
  - Cakupan: TEPAT SATU dari `--cells <ver>:<browser>[+<browser>],...` atau `--versions`
    (= versi itu x SEMUA browser terkonfigurasi). Himpunan terkonfigurasi = psm_target_versions
    x psm_e2e_browsers dari `--config` (default skrip bila absen); sel di luarnya = exit 2.
    `--session <[a-z0-9]{16}>` WAJIB (dari ps-plan-layers.py --new-session). `--tier 0|1` WAJIB
    (= `e2e_tier` dari ps-plan-layers; absen atau selain `0`/`1` = exit 2) dan distempel sebagai
    bilangan bulat JSON `tier` di SETIAP rekaman yang ditulis run ini (hasil sel anak, `crash`,
    `browser-unavailable`, `no-slots`, `not-run`). `--tier` dgn `--merge-only` atau lapis lain =
    exit 2. `psm_e2e_canary` di `--config` divalidasi (normalizer ps-flashlight-run; tak sah =
    exit 2 menyebut key-nya, apa pun `psm_e2e_enabled`). `--per-version`
    atau `--jobs` (juga dgn --merge-only) = exit 2. Browser dipilih lewat `--cells`/config,
    BUKAN `--browsers` sesudah `--` (anak menerima `--engines` dari skrip ini).
  - SLOT (CAP-3/CAP-7): admisi per slot SEDAEMON — N = `--slots` (override manual), else
    `psm_e2e_slots` dari `--config` (divalidasi walau --slots diberikan; kosong = default),
    else 6; bukan bilangan bulat >= 1 = exit 2. Terpakai = jumlah label `psm.slots` semua
    container yang JALAN di daemon (satu `docker ps`; gagal/timeout = penuh) + klaim
    `slot_claims` entri registry hidup lain (dan klaim sendiri) yang container-nya belum jalan,
    dihitung di bawah `<tmp>/psm-locks/slots.lock`. Tiap versi antre = fase `wait-slots` di log
    kemajuannya (dibuka begitu run mulai; ALIVE menyebut isi cap; tak pernah SLOW); di dalamnya
    `--cleanup-orphans` jalan SEKALI sebelum hitungan pertama (hanya yang pemiliknya terbukti
    mati). Kepala antrean (urutan tertulis) diadmisi selama muat (cell-contract.md > Parallel
    browsers > Slots): versi yang men-drive n engine berbiaya n (browser paralel dalam satu
    boot, anak TANPA `--sequential-browsers`) bila n slot bebas; selain itu, bila 1 slot bebas,
    biaya 1 dengan `--sequential-browsers` bila n > 1 (n = 1: biaya 1, tanpa flag); tak satu
    slot pun bebas = tunggu. Versi yang salah satu sel terkonfigurasinya (browser terkonfigurasi
    x versi itu) punya rekaman TERBARU ber-reason `parallel-unconfirmed` SELALU diadmisi biaya 1
    sekuensial, berapa pun slot bebas — histori dibaca SEKALI sebelum admisi; histori tak
    terbaca atau ber-ekor rusak (rekaman terbaru tak diketahui) juga dipaksa sekuensial, dengan
    satu baris log. Cap penuh selama batas startup (`--startup-timeout` passthrough,
    else psm_flashlight_startup_timeout, else 180 s; dihitung hanya saat tak ada anak sendiri
    yang jalan) -> tiap sel yang masih antre = rekaman `inconclusive`, reason `no-slots`
    (`errors` = isi cap).
  - FAIL-FAST: begitu anak yang di-reap (urutan selesai) meng-append rekaman `fail`, tak ada
    versi antre yang dimulai; anak yang sedang jalan ditunggu; tiap sel yang belum dimulai =
    rekaman `not-run`, reason `fail-fast after <ver>:<browser>`. Anak exit 2 sama, reason
    `input-error after <ver>` (versi itu sendiri tanpa rekaman). Log versi yang tak satu sel pun
    mulai = satu baris `DONE rc=not-run <reason>`.
  - Tiap anak `ps-e2e-run.py --versions <ver> --engines <engine versi itu> --run-id <klaim>
    --progress-append --slot-cost <biaya admisi> [--sequential-browsers]` (+ `--config`), argv
    disusun SAAT admisi; klaim slot membawa biaya yang sama. Begitu anak di-reap,
    satu rekaman per sel yang diadmisi di-APPEND ke histori selnya: hasil sel anak + field
    level-versi + `session`, `source_fingerprint` (dihitung SEKALI sebelum admisi), `job_id`,
    `run_id` (= klaim), `state/conclusive/reason`, `phase_durations.wait-slots`. Sel tanpa hasil:
    `browser-unavailable` (engine di-drop probe binary) atau `crash`. State yang DISET anak
    dipertahankan apa adanya (tanpa derive_state): `not-run` (fail-fast antar-engine) dan
    `inconclusive` ber-reason `crash` (worker), `parallel-unconfirmed` atau `sequential-reset`;
    `errors` level-sel dua yang terakhir (sub-fase yang gagal) ditambahkan SESUDAH `errors`
    level-versi rekaman sel itu saja. Tak ada `<module>-e2e*.json`.
  - Baris terakhir stdout: satu JSON `{"e2e_status": "ran"|"skipped", "reason",
    "appended": ["<ver>:<browser>", ...], "source_fingerprint"}` — dicetak di setiap exit
    kecuali error input pra-spawn dan stop.
  - exit 3 = ada rekaman `fail`; 1 = ada rekaman inconclusive/not-run/no-slots; 0 = semua
    pass, atau `skipped` (Docker absen / anak melaporkan skipped, tanpa `fail`); 2 = error
    input (sebelum spawn, tanpa baris output) ATAU anak exit 2 (sel antre not-run, baris output
    `ran`); 143 = dihentikan `--stop-job` (rekaman yang sudah di-append tetap; tanpa baris output).
  - `--merge-only --layer e2e` (hanya `--module`, `--reports-dir`, `--config`) menulis TAMPILAN
    laporan `<module>-e2e.json` = {module, view: true, cells: {ver: {browser: rekaman terbaru|null}}}
    — bukan bukti; plan & agregat membaca histori.

Contoh:
  uv run scripts/ps-run-layer.py --layer e2e --module modules/mymod --session <token> \\
      --tier 1 --cells 1.7.8:chromium+firefox,9.1:firefox --reports-dir reports \\
      --config reports/psm-config.json -- --tag-map 1.7.8=1.7.8.11,8.1=8.1.6-nginx,9.1=9.1.4-nginx
  uv run scripts/ps-run-layer.py --layer flashlight --module modules/mymod \\
      --versions 1.7.8,8.1,9.1 --reports-dir reports --config reports/psm-config.json
"""
import argparse
import contextlib
import fcntl
import json
import os
import re
import shutil
import sys
import tempfile
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
from datetime import datetime, timezone
from pathlib import Path

_HERE = Path(__file__).resolve().parent

# Lapis yang memang dijalankan per versi. static murah dan sekali jalan di orkestrator;
# adversarial adalah judgment satu reviewer atas seluruh cakupan — memaralelkan keduanya
# bukan optimasi, dan file-nya tak berbentuk {versi: {...}} yang bisa disatukan.
PARALLEL_LAYERS = {"flashlight": "ps-flashlight-run.py", "e2e": "ps-e2e-run.py",
                   "scenario": "ps-scenario-run.py"}
SERIAL_LAYERS = {
    "static": "lapis static murah dan dijalankan sekali di orkestrator untuk semua versi",
    "adversarial": "lapis adversarial adalah satu reviewer atas seluruh cakupan, bukan per versi",
}

# Flag yang dimiliki skrip ini. Diteruskan lagi lewat passthrough = dua sumber kebenaran
# untuk hal yang sama, dan anak akan menimpa apa yang sudah dijamin di sini.
# `--cleanup-orphans` bukan milik skrip ini tapi MENGGANTI pekerjaan anak: tiap anak akan
# menjalankan pembersihan destruktif alih-alih memvalidasi, lalu keluar 0 — dan operator cuma
# diberitahu "versi tak berbukti", tak pernah bahwa mode lain yang jalan.
# `--config`, `--browsers`, `--engines`: ps-run-layer meneruskan `--config` sendiri ke tiap anak
# dan memilih engine tiap versi (`--engines`) dari `--cells`/config — salinan di passthrough
# akan diam-diam mengganti himpunan yang di-drive di bawah himpunan yang dicatat di histori.
# `--run-id`, `--slot-cost`, `--progress-append`, `--sequential-browsers`: diset skrip ini pada
# tiap anak E2E (klaim slot, biaya, log wait-slots, mode sekuensial) — salinan di passthrough
# memalsukan klaim/biaya yang dihitung seluruh daemon.
# `--engine-worker`: mode internal anak (subproses per engine milik proses versi, CAP-7) —
# dari passthrough ia akan menjalankan anak sebagai worker tanpa spec, bukan sebagai versi.
# `--tier`: distempel skrip ini di tiap rekaman histori; anak tak mengenalnya, jadi salinan di
# passthrough hanya bisa jadi salah ketik yang menyesatkan pembaca log.
RESERVED_PASSTHROUGH = ("--versions", "-o", "--output", "--cleanup-orphans", "--progress-file",
                        "--job-id", "--stop-job", "--list-jobs", "--config", "--browsers",
                        "--engines", "--run-id", "--slot-cost", "--progress-append",
                        "--sequential-browsers", "--engine-worker", "--tier")
# Panjang singkatan awalan MINIMUM per flag reserved (default 4, mis. `--co`). `--tier` baru
# tertangkap mulai `--tie`: `--ti` adalah singkatan `--timeout` milik anak yang sah dan harus
# tetap sampai ke anak.
RESERVED_MIN_PREFIX = {"--tier": len("--tie")}

DEFAULT_JOBS = 3  # Lapis 2/5: tiap job mem-boot container PS + DB
# Lapis 4: admisi per SLOT sedaemon (cell-contract.md > Config keys > psm_e2e_slots), bukan
# --jobs. Default dikunci ke PSM_DEFAULTS resolver lewat test drift.
DEFAULT_E2E_SLOTS = 6
SLOT_POLL = 5  # detik antar-pass admisi bila tak ada anak yang selesai

# --- Penggabungan bukti per-versi ---------------------------------------------------------
# Aturannya tinggal di sini, bersama satu-satunya yang menggabungkan. Sebelumnya ia CLI
# tersendiri yang menerima daftar file yang diketik model; bentuk itu melucuti tiap gerbang
# yang menjaga file lapis (penggabung yang cuma diberi path tak tahu module/lapis/versi apa
# yang seharusnya ada) dan file kanonik hasilnya selalu ber-mtime baru, yang membatalkan
# gerbang kesegaran ps-plan-layers atas bukti selama apa pun.
_AND_KEYS = ("pass",)                                    # AND: lolos hanya bila semua lolos
_OR_KEYS = ("e2e_available", "docker_available")         # OR: lapis tersedia bila ADA yang bisa
_PREFER_RAN_KEYS = ("status",)                           # "ran" bila ada satu pun yang jalan
# UNION: kunci yang SAH berbeda antar invokasi orkestrator, jadi konflik skalar salah alamat.
# `screenshot_dir` distempel run-<ts> BARU tiap invokasi (ps-e2e-run.run_shot_dir), dan alur
# terdokumentasi mengonvergensikan versi SATU PER SATU — jadi N versi = N invokasi = N stempel,
# lalu --merge-only meledak exit 2 atas bukti yang justru sehat, tanpa input yang bisa diperbaiki.
# Dikumpulkan jadi daftar: tiap folder run tetap terjangkau peninjau visual, nol yang dibuang.
_UNION_KEYS = ("screenshot_dir",)

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


def plan_layers():
    """ps-plan-layers milik ps-aggregate (satu salinan: fingerprint, histori, aturan State)."""
    agg = aggregate()
    pl = getattr(agg, "pl", None)
    if pl is None:
        pl = _sibling("ps-plan-layers.py", "ps_plan_layers")
        agg.pl = pl
    return pl


def flashlight():
    """ps-flashlight-run yang SAMA dengan milik ps-plan-layers — satu salinan per proses, jadi
    stub test (mis. docker_available) dan JobStopped berlaku di semua jalur."""
    return plan_layers().fl


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
        elif k in _UNION_KEYS:
            seen, acc = set(), []
            for v in present:
                for item in (v if isinstance(v, list) else [v]):
                    if item is None:
                        continue
                    c = _canon(item)
                    if c not in seen:
                        seen.add(c)
                        acc.append(item)
            out[k] = acc
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
        elif head.startswith("--") and len(head) >= 4:
            # Seluruh tuple, bukan daftar tangan: tiap flag milik skrip ini juga terjangkau
            # lewat singkatan awalan yang argparse anak terima (`--conf`, `--brow`, `--eng`).
            for full in RESERVED_PASSTHROUGH:
                if (full.startswith("--") and full.startswith(head)
                        and len(head) >= RESERVED_MIN_PREFIX.get(full, 4)):
                    hits.append(full)
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
        head = tok.split("=", 1)[0]
        # argparse anak juga menerima singkatan awalan (`--screenshot-d`, `--screen`); yang
        # lolos dari sini melewati stempel run & gerbang path-di-dalam-module. Ambang 4 karakter
        # sama dgn reserved_in_passthrough.
        if len(head) >= 4 and "--screenshot-dir".startswith(head) and head.startswith("--"):
            if "=" in tok:
                base = tok.split("=", 1)[1]
                i += 1
                continue
            if i + 1 < len(extra):
                base = extra[i + 1]
                i += 2
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


def progress_file(reports_dir, module_path, layer, ver):
    """Path log kemajuan anak — `<reports>/<module>-<lapis>-<versi>.progress.log`, DITURUNKAN.

    Bukti anak mendarat di folder temp, tapi log kemajuan harus terlihat pemanggil SELAMA run
    (untuk memantau macet), jadi ia ditulis di reports dir dengan nama yang bisa ditebak.
    Akhiran `.progress.log` tak pernah dibaca agregat/plan sebagai file lapis.
    """
    return str(Path(reports_dir) / f"{Path(module_path).resolve().name}-{layer}-{ver}.progress.log")


def plan_children(script, module_path, versions, out_dir, extra, progress=None, job_id=None):
    """(versi, cmd, out_path) untuk tiap versi. Murni — bisa diuji tanpa men-spawn apa pun.

    `progress` = (reports_dir, layer) → tiap anak diberi `--progress-file` turunan.
    `job_id` → SEMUA anak berbagi satu job, supaya `--stop-job` menghentikan seluruh
    pemanggilan ini (dan hanya ini)."""
    plan = []
    for ver in versions:
        out = str(Path(out_dir) / f"{ver}.json")
        cmd = ["uv", "run", str(script), str(module_path),
               "--versions", ver, "-o", out, *extra]
        if progress:
            cmd += ["--progress-file", progress_file(progress[0], module_path, progress[1], ver)]
        if job_id:
            cmd += ["--job-id", job_id]
        plan.append((ver, cmd, out))
    return plan


def _spawn(cmd):
    """Runner nyata: jalankan anak, kembalikan exit code-nya. Diganti test lewat injeksi.

    stdout anak dialihkan ke stderr: bukti anak ditulis ke `-o`, dan stdout skrip ini memikul
    baris output JSON Lapis 4 yang dibaca orkestrator."""
    import subprocess
    try:
        out = sys.stderr.fileno()
    except (AttributeError, OSError, ValueError):
        out = None
    return subprocess.run(cmd, stdout=out).returncode


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


# --- Lapis E2E: histori per sel (cell-contract.md > Evidence record, Runner) ----------------
# Satu rekaman = TEPAT kunci Fields kontrak + `boot_wall_clock` & `boot_log` (tambahan yang
# disetujui Budi). Urutan di sini = urutan kunci di baris histori.
RECORD_KEYS = (
    "version", "browser", "started_at", "finished_at", "boot", "boot_id", "session",
    "browser_mode", "scenario_set", "scenarios_run", "source_fingerprint", "image_tag", "run_id",
    "job_id", "tier", "state", "conclusive", "reason", "errors", "install", "launch_error",
    "bo_authed", "findings", "inconclusive", "authored_assertions", "scenario_notes",
    "browser_notes", "parallel_only", "console_errors", "screenshots", "scenario_spans",
    "phase_durations", "boot_phases", "keeper_boot", "wall_clock", "boot_wall_clock", "boot_log")
# Field level-versi anak, disalin ke SETIAP rekaman versi itu (browser-unavailable termasuk).
VERSION_KEYS = ("run_id", "boot", "boot_id", "boot_phases", "boot_wall_clock", "boot_log",
                "image_tag", "browser_mode", "errors", "install", "scenario_notes")
# Field per sel dari `cells.<engine>` anak.
CELL_KEYS = ("started_at", "finished_at", "scenario_set", "scenarios_run", "findings",
             "inconclusive", "authored_assertions", "bo_authed", "launch_error", "browser_notes",
             "console_errors", "screenshots", "phase_durations", "scenario_spans", "parallel_only")
# State sel yang DISET anak (ps-e2e-run CHILD_SET_REASONS): `inconclusive` ber-reason ini
# dipertahankan apa adanya, tanpa derive_state (seperti `not-run`). Hanya dua yang terakhir
# membawa `errors` level-sel (sub-fase yang gagal).
CHILD_SET_REASONS = ("crash", "parallel-unconfirmed", "sequential-reset")
CELL_ERROR_REASONS = ("parallel-unconfirmed", "sequential-reset")
UNCONFIRMED_REASON = "parallel-unconfirmed"  # rekaman terbaru begini -> admisi biaya 1 sekuensial
STOPPED_CODES = (143, -15)  # anak yang di-reap dgn SIGTERM = dihentikan, tak pernah `crash`
DOCKER_SKIP_REASON = "Docker tidak tersedia — Lapis 4 butuh flashlight; lewati, andalkan lapis lain."
_CELL_TOKEN = re.compile(r"^([^:+,\s]+):([^:+,\s]+(?:\+[^:+,\s]+)*)$")


class InputError(Exception):
    """Error input pra-spawn Lapis 4: pesan ke stderr, exit 2, TANPA baris output."""


def utc_now():
    """Timestamp rekaman: UTC ISO-8601 bermikrodetik (`+00:00`)."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def parse_cells(raw, cfg_versions, cfg_browsers):
    """`--cells` -> [(ver, [engine...])] urut tertulis; engine diurut psm_e2e_browsers.

    Error input (InputError): token kosong / bukan `<ver>:<browser>[+<browser>]...`, browser
    berulang dalam satu sel, versi berulang, atau sel di luar himpunan terkonfigurasi (versi
    harus PERSIS string terkonfigurasi).
    """
    out, seen = [], set()
    for tok in raw.split(","):
        tok = tok.strip()
        if not tok:
            raise InputError("--cells: token kosong — bentuk <ver>:<browser>[+<browser>],...")
        m = _CELL_TOKEN.match(tok)
        if not m:
            raise InputError(f"--cells: token {tok!r} bukan bentuk <ver>:<browser>[+<browser>]")
        ver, engines = m.group(1), [e.lower() for e in m.group(2).split("+")]
        if len(set(engines)) != len(engines):
            raise InputError(f"--cells: browser berulang di sel {tok!r}")
        if ver in seen:
            raise InputError(f"--cells: versi {ver} berulang — satu token per versi "
                             "(gabungkan browsernya dgn '+')")
        seen.add(ver)
        if ver not in cfg_versions:
            raise InputError(f"--cells: versi {ver} bukan versi terkonfigurasi — harus PERSIS "
                             f"salah satu dari: {', '.join(cfg_versions)}")
        outside = [e for e in engines if e not in cfg_browsers]
        if outside:
            raise InputError(f"--cells: sel {', '.join(f'{ver}:{e}' for e in outside)} di luar "
                             f"himpunan terkonfigurasi (browser: {', '.join(cfg_browsers)})")
        out.append((ver, [b for b in cfg_browsers if b in engines]))
    return out


def _passthrough_value(extra, full, min_len=5):
    """Nilai TERAKHIR flag `full` di passthrough (bentuk `--f v`, `--f=v`, singkatan awalan)."""
    val = None
    i = 0
    while i < len(extra):
        tok = extra[i]
        head, eq, rest = tok.partition("=")
        if head.startswith("--") and len(head) >= min_len and full.startswith(head):
            if eq:
                val = rest
            elif i + 1 < len(extra):
                val = extra[i + 1]
                i += 1
        i += 1
    return val


def read_e2e_config(path, fl):
    """Peta key ps-run-layer atas `--config` (bukan apply_config_file): himpunan sel,
    `psm_flashlight_tag_map`, `psm_flashlight_startup_timeout`, `psm_e2e_slots` (kosong =
    default; bukan bilangan bulat >= 1 = error, juga bila --slots diberikan), `psm_e2e_canary`
    (normalizer bersama ps-flashlight-run; tak sah = error menyebut key-nya, apa pun
    `psm_e2e_enabled` — run ini tak membacanya). Error -> InputError."""
    try:
        cfg = fl.read_config_json(path) if path else {}
        versions = fl.normalize_versions(cfg.get("psm_target_versions"))
        browsers = fl.normalize_engines(cfg.get("psm_e2e_browsers"))
    except fl.CellConfigError as e:
        raise InputError(f"himpunan sel terkonfigurasi tak sah: {e}") from None
    try:
        canary = fl.normalize_canary(cfg.get(fl.CANARY_KEY), versions, browsers)
    except fl.CellConfigError as e:
        raise InputError(f"--config: {e}") from None
    tag_map = cfg.get("psm_flashlight_tag_map")
    if tag_map is not None and not isinstance(tag_map, str):
        raise InputError(f"--config: psm_flashlight_tag_map={tag_map!r} harus string versi=tag,...")
    timeout = cfg.get("psm_flashlight_startup_timeout")
    if timeout is not None:
        try:
            if isinstance(timeout, bool):
                raise ValueError
            timeout = int(timeout)
        except (TypeError, ValueError):
            raise InputError(f"--config: psm_flashlight_startup_timeout={timeout!r} bukan "
                             "bilangan") from None
    slots = cfg.get("psm_e2e_slots")
    if isinstance(slots, str) and not slots.strip():
        slots = None  # kosong = default
    if slots is not None:
        try:
            slots = parse_slots(slots)
        except ValueError:
            raise InputError(f"--config: psm_e2e_slots={cfg.get('psm_e2e_slots')!r} harus "
                             "bilangan bulat >= 1") from None
    return {"versions": versions, "browsers": browsers, "tag_map": tag_map,
            "startup_timeout": timeout, "slots": slots, "canary": canary}


def parse_slots(raw):
    """Nilai slot (str/int) -> int >= 1. Bukan bilangan bulat / < 1 -> ValueError."""
    if isinstance(raw, bool):
        raise ValueError(raw)
    if isinstance(raw, int):
        val = raw
    elif isinstance(raw, str) and re.fullmatch(r"\s*-?[0-9]+\s*", raw):
        val = int(raw)
    else:
        raise ValueError(raw)
    if val < 1:
        raise ValueError(raw)
    return val


def parse_tier(raw):
    """`--tier` run Lapis 4 -> int 0/1 (= `e2e_tier` plan). Absen / selain `0`/`1` -> InputError."""
    if raw is None:
        raise InputError("--tier wajib untuk lapis e2e — beri `e2e_tier` dari ps-plan-layers.py "
                         "(0 = fix loop, 1 = gerbang rilis)")
    if raw not in ("0", "1"):
        raise InputError(f"--tier {raw!r} harus 0 atau 1 (`e2e_tier` dari ps-plan-layers.py)")
    return int(raw)


def resolve_tags(extra, cfg_tag_map, versions, fl):
    """Tag image tiap versi: `--tag-map` passthrough, else psm_flashlight_tag_map; + `--extra-tag-map`."""
    raw = _passthrough_value(extra, "--tag-map")
    if raw is None:
        raw = cfg_tag_map
    tag_map = fl.parse_tag_map(raw, _passthrough_value(extra, "--extra-tag-map"))
    return {v: fl.resolve_tag(tag_map, v) for v in versions}


def _inside(path_real, root_real):
    rel = os.path.relpath(path_real, root_real)
    return not (rel == os.pardir or rel.startswith(os.pardir + os.sep) or os.path.isabs(rel))


def check_e2e_paths(module, reports_dir, shot_base):
    """psm_reports_dir == akar module, atau --screenshot-dir di dalam module tapi di luar
    psm_reports_dir -> InputError (fingerprint tak bisa memisahkan bukti dari source)."""
    root = os.path.realpath(module)
    rep = os.path.realpath(reports_dir)
    if rep == root:
        raise InputError(f"psm_reports_dir sama dengan akar module ({root}) — taruh laporan di "
                         "luar module atau di sub-foldernya")
    if shot_base:
        shot = os.path.realpath(shot_base)
        if _inside(shot, root) and not _inside(shot, rep):
            raise InputError(f"--screenshot-dir {shot_base} berada di dalam module tapi di luar "
                             f"psm_reports_dir ({reports_dir}) — screenshot akan mengubah "
                             "source_fingerprint")


def child_shape_ok(payload, ver):
    """Bentuk sah: objek JSON yang `versions` = {ver: {..., cells: {engine: {...}}}} PERSIS."""
    if not isinstance(payload, dict):
        return False
    versions = payload.get("versions")
    if not isinstance(versions, dict) or set(versions) != {ver}:
        return False
    vres = versions[ver]
    if not isinstance(vres, dict):
        return False
    cells = vres.get("cells")
    return isinstance(cells, dict) and all(isinstance(c, dict) for c in cells.values())


def build_record(pl, ver, engine, *, vres, cell, reason, admitted, ctx, run_id=None,
                 state="inconclusive", errors=None, wait=None):
    """Satu rekaman histori (RECORD_KEYS persis). `reason` terisi = sel tanpa hasil anak
    (`crash`/`browser-unavailable`/`no-slots` dgn `state` inconclusive, atau `not-run`).
    State yang DISET anak dipertahankan apa adanya, tanpa derive_state: `not-run` (fail-fast
    antar-engine) dan `inconclusive` ber-reason CHILD_SET_REASONS (`crash` worker,
    `parallel-unconfirmed`, `sequential-reset`); selain itu state dihitung dgn derive_state.
    `errors` level-sel anak (hanya `parallel-unconfirmed`/`sequential-reset`) ditambahkan
    SESUDAH `errors` level-versi — tak pernah menggantinya, tak pernah ke sel saudara.

    `run_id` = RUN_ID klaim versi yang diadmisi (semua rekamannya, crash termasuk); tanpa itu
    `ctx["run_id"]` (milik ps-run-layer: not-run/no-slots). `wait` = hasil `wait-slots`
    ({seconds, outcome}) yang digabung ke `phase_durations` (dict baru bila null). `tier` =
    `ctx["tier"]` (int `--tier`) di SETIAP jenis rekaman — semua lewat fungsi ini.
    """
    rec = dict.fromkeys(RECORD_KEYS)
    if vres is not None:
        for k in VERSION_KEYS:
            rec[k] = vres.get(k)
    else:
        rec["run_id"] = ctx["run_id"]
        rec["image_tag"] = ctx["tags"][ver]
    if run_id:
        rec["run_id"] = run_id
    if errors is not None:
        rec["errors"] = list(errors)
    if cell is not None:
        for k in CELL_KEYS:
            rec[k] = cell.get(k)
    rec.update(version=ver, browser=engine, session=ctx["session"],
               source_fingerprint=ctx["fingerprint"], job_id=ctx["job_id"],
               tier=ctx["tier"], keeper_boot=None)
    child_set = cell is not None and (
        cell.get("state") == "not-run"
        or (cell.get("state") == "inconclusive" and cell.get("reason") in CHILD_SET_REASONS))
    if child_set and cell.get("reason") in CELL_ERROR_REASONS \
            and isinstance(cell.get("errors"), list):
        base = rec["errors"] if isinstance(rec["errors"], list) else []
        rec["errors"] = [*base, *cell["errors"]]
    if reason:
        rec.update(state=state, conclusive=False, reason=reason)
    elif child_set:
        rec.update(state=cell["state"], conclusive=False, reason=cell.get("reason"))
    else:
        st = pl.derive_state(rec, engine)
        rec.update(state=st["state"], conclusive=st["conclusive"], reason=st["reason"])
    if wait is not None:
        pd = rec["phase_durations"]
        rec["phase_durations"] = {**(pd if isinstance(pd, dict) else {}), "wait-slots": wait}
    # Sel yang engine-nya tak pernah jalan: started_at = saat diadmisi, finished_at = saat ditulis.
    if pl.parse_utc(rec["started_at"]) is None:
        rec["started_at"] = admitted
    if pl.parse_utc(rec["finished_at"]) is None:
        rec["finished_at"] = utc_now()
    t0, t1 = pl.parse_utc(rec["started_at"]), pl.parse_utc(rec["finished_at"])
    rec["wall_clock"] = round((t1 - t0).total_seconds(), 3)
    return rec


def records_for_child(pl, ver, engines, payload, admitted, ctx, log, *, run_id=None, wait=None):
    """Rekaman untuk satu anak yang selesai (bukan exit 2/stop/skipped). Return [record]."""
    kw = {"admitted": admitted, "ctx": ctx, "run_id": run_id, "wait": wait}
    if not child_shape_ok(payload, ver):
        log(f"versi {ver}: output anak tak ada/tak terbaca/salah bentuk — sel diadmisi = crash")
        return [build_record(pl, ver, e, vres=None, cell=None, reason="crash", **kw)
                for e in engines]
    vres = payload["versions"][ver]
    cells = vres["cells"]
    available = payload.get("browsers_available")
    stray = [e for e in cells if e not in engines]
    if stray:
        log(f"versi {ver}: anak memancarkan sel di luar yang diadmisi ({', '.join(stray)}) — "
            "tak di-append")
    out = []
    for e in engines:
        if e in cells:
            out.append(build_record(pl, ver, e, vres=vres, cell=cells[e], reason=None, **kw))
        else:
            why = ("browser-unavailable" if isinstance(available, list) and e not in available
                   else "crash")
            out.append(build_record(pl, ver, e, vres=vres, cell=None, reason=why, **kw))
    return out


def _e2e_input(args, extra, fl, log):
    """Validasi input run Lapis 4 (semua sebelum spawn). Return dict konteks; InputError."""
    if args.per_version:
        raise InputError("--per-version tak berlaku untuk lapis e2e — buktinya histori per sel, "
                         "bukan file per-versi")
    if bool(args.cells) == bool(args.versions):
        raise InputError("lapis e2e butuh TEPAT SATU dari --cells atau --versions")
    tier = parse_tier(args.tier)
    if args.session is None:
        raise InputError("--session wajib untuk lapis e2e — buat token sekali per run dengan "
                         "`ps-plan-layers.py --new-session`")
    pl = plan_layers()
    if not pl.valid_session(args.session):
        raise InputError(f"--session tak valid: {args.session!r} — harus [a-z0-9]{{16}} "
                         "(dari ps-plan-layers.py --new-session)")
    try:
        fl.require_config(args.config, args.reports_dir)
    except fl.CellConfigError as e:
        raise InputError(str(e)) from None
    cfg = read_e2e_config(args.config, fl)
    if args.slots is not None:
        try:
            slots = parse_slots(args.slots)
        except ValueError:
            raise InputError(f"--slots {args.slots!r} harus bilangan bulat >= 1") from None
    else:
        slots = cfg["slots"] if cfg["slots"] is not None else DEFAULT_E2E_SLOTS
    if args.cells:
        cells = parse_cells(args.cells, cfg["versions"], cfg["browsers"])
    else:
        versions = parse_versions(args.versions)
        if not versions:
            raise InputError("--versions kosong — tak ada sel yang bisa dijalankan")
        outside = [v for v in versions if v not in cfg["versions"]]
        if outside:
            raise InputError(f"--versions {', '.join(outside)} bukan versi terkonfigurasi — tiap "
                             f"entri harus PERSIS salah satu dari: {', '.join(cfg['versions'])}")
        cells = [(v, list(cfg["browsers"])) for v in versions]
    extra, shot_base = split_screenshot_dir(extra)
    # Batas tunggu `no-slots` = batas startup kontrak: --startup-timeout passthrough, else
    # psm_flashlight_startup_timeout, else default skrip. <= 0 diterima (tanpa jatah tunggu).
    raw_timeout = _passthrough_value(extra, "--startup-timeout")
    if raw_timeout is not None:
        try:
            startup_timeout = int(raw_timeout)
        except ValueError:
            raise InputError(f"--startup-timeout {raw_timeout!r} (passthrough) bukan bilangan "
                             "bulat") from None
    elif cfg["startup_timeout"] is not None:
        startup_timeout = cfg["startup_timeout"]
    else:
        startup_timeout = fl.DEFAULT_STARTUP_TIMEOUT
    agg = aggregate()
    ss = agg.load_sibling(_HERE / "ps-static-scan.py", "ps_static_scan")
    bad = ss.unresolved_path_args([("--reports-dir", args.reports_dir),
                                   ("--screenshot-dir", shot_base), ("--module", args.module),
                                   ("--config", args.config)])
    if bad:
        raise InputError("; ".join(f"token '{{project-root}}' belum diresolve di {n}: {v} — "
                                   "resolve dulu di pemanggil" for n, v in bad))
    check_e2e_paths(args.module, args.reports_dir, shot_base)
    tags = resolve_tags(extra, cfg["tag_map"], [v for v, _e in cells], fl)
    try:
        fingerprint = pl.source_fingerprint(args.module, args.reports_dir)
    except pl.PlanInputError as e:
        raise InputError(str(e)) from None
    return {"cells": cells, "extra": extra, "shot_base": shot_base, "tags": tags,
            "fingerprint": fingerprint, "slots": slots, "startup_timeout": startup_timeout,
            "tier": tier, "browsers": list(cfg["browsers"])}


def _count_error_tail(err):
    """Ekor galat hitungan docker: 200 karakter terakhir, whitespace diringkas jadi satu spasi."""
    return " ".join(str(err).split())[-200:]


class _SlotRun:
    """Satu run Lapis 4 di bawah admisi slot sedaemon (cell-contract.md > Config keys >
    psm_e2e_slots, Runner > Fail-fast, not-run (CAP-3)).

    Antrean = urutan tertulis `--cells`/`--versions`. Tiap versi yang diantre: log kemajuannya
    dikosongkan lalu fase `wait-slots` dibuka (START, denyut ALIVE, tak pernah SLOW). Di dalam
    fase itu `--cleanup-orphans` jalan SEKALI, lalu loop: reap anak yang selesai (urutan
    selesai; satu batch urut rencana), lalu — selama belum ada pemicu fail-fast/exit 2/galat
    append — pegang `slots.lock`, baca klaim registry, hitung sekali, dan admisi kepala antrean
    selama muat (klaim ditulis dulu, `END wait-slots ok`, lalu spawn; biaya n paralel bila n
    slot bebas, else biaya 1 sekuensial — lihat `_admit_cost`). Jam `no-slots` satu
    akumulator sepanjang run: maju hanya saat ada versi menunggu dan tak ada anak sendiri yang
    jalan; habis -> tiap sel yang masih antre `no-slots`.
    """

    def __init__(self, args, inp, extra, script, job_id, module_name, log, fl, pl):
        self.args, self.log, self.fl, self.pl = args, log, fl, pl
        self.module_name = module_name
        self.versions = [v for v, _e in inp["cells"]]
        self.engines_of = dict(inp["cells"])
        self.order = {v: i for i, v in enumerate(self.versions)}
        self.slots = inp["slots"]
        self.limit = max(0, inp["startup_timeout"])
        self.ctx = {"session": args.session, "fingerprint": inp["fingerprint"],
                    "job_id": job_id, "run_id": fl.RUN_ID, "tags": inp["tags"],
                    "tier": inp["tier"]}
        self.claim_of = {v: uuid.uuid4().hex[:12] for v in self.versions}
        self.logs = {v: progress_file(args.reports_dir, args.module, "e2e", v)
                     for v in self.versions}
        self.tmp = tempfile.mkdtemp(prefix="psm-layer-")
        # argv dasar; `--slot-cost <biaya>` (+ `--sequential-browsers`) ditambahkan SAAT admisi.
        self.base_cmds, self.cmds, self.outs = {}, {}, {}
        for ver, cmd, out in plan_children(script, args.module, self.versions, self.tmp, extra,
                                           progress=(args.reports_dir, "e2e"), job_id=job_id):
            self.base_cmds[ver] = [*cmd, "--engines", ",".join(self.engines_of[ver]),
                                   "--run-id", self.claim_of[ver], "--progress-append"]
            self.outs[ver] = out
        self.forced_seq = self._unconfirmed_versions(inp["browsers"])
        self.waits, self.wait_res = {}, {}
        self.queue = []
        self.running = {}            # future -> versi
        self.reaped = {}             # versi -> rc anak (None = runner meledak)
        self.done_written = set()    # versi yang log-nya sudah diberi DONE oleh skrip ini
        self.own_claims = {}         # versi -> {"run", "cost"} (memori; tak dibaca ulang dari file)
        self.admitted = {}
        self.trigger = None
        self.appended, self.states, self.skipped, self.child_stopped = [], [], [], []
        self.exit2 = self.keep = False
        self.append_error = None
        self.registry_warned = False
        self.note = None             # detail ALIVE sebelum hitungan pertama
        self.tokens = []
        self.budget, self.accum, self.last_tick, self.last_pass = 0.0, False, None, None

    def _unconfirmed_versions(self, cfg_browsers):
        """Versi yang WAJIB diadmisi biaya 1 sekuensial: salah satu sel terkonfigurasinya
        (browser terkonfigurasi x versi itu, bukan cuma engine yang diminta `--cells`) punya
        rekaman TERBARU ber-reason `parallel-unconfirmed` (cell-contract.md > Parallel browsers
        > Parallel-only failures). Dibaca SEKALI, sebelum admisi.

        Histori tak terbaca, atau ber-ekor rusak (rekaman terbaru sel itu tak diketahui),
        juga memaksa sekuensial — mode yang temuannya tak butuh konfirmasi, jadi tebakan yang
        salah hanya memperlambat, tak pernah menyembunyikan temuan — dengan satu baris log."""
        forced = set()
        for ver in self.versions:
            for b in cfg_browsers:
                path = self.pl.history_path(self.args.reports_dir, self.module_name, ver, b)
                try:
                    records, tail = self.pl.read_history(path, ver, b)
                except self.pl.PlanInputError as e:
                    self.log(f"peringatan: {e} — versi {ver} diadmisi biaya 1 sekuensial")
                    forced.add(ver)
                    break
                if tail:
                    self.log(f"peringatan: histori {ver}:{b} berekor rusak ({path}) — rekaman "
                             f"terbarunya tak diketahui; versi {ver} diadmisi biaya 1 sekuensial")
                    forced.add(ver)
                    break
                if records and records[-1].get("reason") == UNCONFIRMED_REASON:
                    self.log(f"versi {ver}: rekaman terbaru {ver}:{b} = {UNCONFIRMED_REASON} — "
                             "diadmisi biaya 1 sekuensial (--sequential-browsers)")
                    forced.add(ver)
                    break
        return forced

    def _admit_cost(self, ver, free):
        """(biaya, sekuensial?) untuk kepala antrean dgn `free` slot bebas; None = tak muat.
        n engine: biaya n paralel bila n slot bebas (dan versi tak dipaksa sekuensial), else
        biaya 1 — `--sequential-browsers` bila n > 1."""
        n = len(self.engines_of[ver])
        if n > 1 and ver not in self.forced_seq and free >= n:
            return n, False
        if free >= 1:
            return 1, n > 1
        return None

    # --- log & detail ------------------------------------------------------------------
    def _budget_now(self):
        extra = (time.monotonic() - self.last_tick) if (self.accum and self.last_tick) else 0.0
        return self.budget + extra

    def _wait_detail(self):
        if self.note:
            return self.note
        base = ", ".join(self.tokens) or "-"
        if self.running:
            tail = "own queue"
        else:
            tail = f"budget {max(0, int(self.limit - self._budget_now()))}s left"
        ago = int(time.monotonic() - self.last_pass) if self.last_pass else 0
        return f"{base}; {tail}; last pass {ago}s ago"

    def _close_wait(self, ver, outcome):
        w = self.waits.get(ver)
        if w is None:
            return None
        res = w.end(outcome)
        self.wait_res.setdefault(ver, res)
        return self.wait_res[ver]

    def _done_line(self, ver, detail, truncate=False):
        self.fl.progress_to(self.logs[ver], ver, "DONE", "", detail, truncate=truncate)
        self.done_written.add(ver)

    # --- registry & lock ----------------------------------------------------------------
    @contextlib.contextmanager
    def _slots_lock(self):
        """`<tmp>/psm-locks/slots.lock`, flock blok. OSError = ps-run-layer sendiri meledak."""
        lock_dir = self.fl.LOCK_DIR
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_path = lock_dir / "slots.lock"
        fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o666)
        # /tmp dibagi lintas user: tanpa ini user kedua tak bisa membuka lock (umask 022) dan
        # tiap run E2E-nya crash. Best-effort — hanya pemilik yang bisa chmod.
        for path, mode in ((lock_dir, 0o1777), (lock_path, 0o666)):
            try:
                os.chmod(path, mode)
            except OSError:
                pass
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            yield
        finally:
            os.close(fd)  # menutup fd melepas flock

    def _write_claims(self):
        claims = [dict(self.own_claims[v]) for v in self.versions if v in self.own_claims]
        if not self.fl.job_update(slot_claims=claims) and not self.registry_warned:
            self.registry_warned = True
            self.log("peringatan: klaim slot gagal ditulis ke registry job — run lain baru "
                     "melihat klaim ini begitu container-nya jalan")

    def _foreign_claims(self):
        """[(job, run, cost)] klaim entri registry HIDUP selain milik proses ini."""
        out = []
        try:
            registry = self.fl._registry_entries()
        except OSError as e:  # registry tak terbaca: klaim asing tak terlihat, admisi jalan terus
            if not self.registry_warned:
                self.registry_warned = True
                self.log(f"peringatan: registry job tak terbaca ({e}) — klaim run lain tak dihitung")
            return out
        for job, entries in registry.items():
            for e in entries:
                claims = e.get("slot_claims")
                if e.get("pid") == self.fl.OWNER_PID or not isinstance(claims, list) or not claims:
                    continue
                try:
                    alive = self.fl.entry_state(e)[0] == "alive"
                except Exception:  # noqa: BLE001 — entri asing rusak tak boleh mematikan admisi
                    alive = False
                if not alive:
                    continue
                for c in claims:
                    if isinstance(c, dict) and c.get("run"):
                        out.append((e.get("job") or job, str(c["run"]), c.get("cost")))
        return out

    # --- rekaman ------------------------------------------------------------------------
    def _append(self, rec, force=False):
        """Append satu rekaman. Sesudah galat append pertama hanya `force` (rekaman anak yang
        di-reap) yang masih dicoba; not-run/no-slots tidak lagi."""
        if self.append_error and not force:
            return False
        path = self.pl.history_path(self.args.reports_dir, self.module_name, rec["version"],
                                    rec["browser"])
        try:
            self.pl.append_record(path, rec)
        except self.pl.PlanInputError as e:
            if self.append_error is None:
                self.append_error = str(e)
                # Admisi berhenti; tak ada not-run/no-slots menyusul; tunggu terbuka = cancelled.
                for v in list(self.queue):
                    self._close_wait(v, "cancelled")
                self.queue = []
            return False
        self.appended.append(f"{rec['version']}:{rec['browser']}")
        self.states.append(rec["state"])
        if self.args.verbose:
            self.log(f"  {rec['version']}:{rec['browser']} -> {rec['state']}"
                     + (f" ({rec['reason']})" if rec["reason"] else ""))
        return True

    def _unstarted_records(self, reason, state, errors=None, outcome="cancelled"):
        """Rekaman tiap sel yang masih antre (urutan rencana); antrean dikosongkan. Return
        [(versi, semua-tertulis?)]."""
        out = []
        for ver in list(self.queue):
            if self.append_error:
                break
            wait = self._close_wait(ver, outcome)
            decided = utc_now()
            ok = True
            for e in self.engines_of[ver]:
                rec = build_record(self.pl, ver, e, vres=None, cell=None, reason=reason,
                                   admitted=decided, ctx=self.ctx, state=state, errors=errors,
                                   wait=wait)
                ok = self._append(rec) and ok
            out.append((ver, ok))
        self.queue = []
        return out

    def _fire(self, reason):
        """Pemicu fail-fast / exit 2: sel yang belum dimulai -> not-run (alasan PERTAMA menang)."""
        if self.trigger is not None:
            return
        self.trigger = reason
        if self.append_error:
            return
        self.log(f"{reason}: {len(self.queue)} versi antre tak dimulai (not-run); anak yang "
                 "sedang jalan ditunggu")
        for ver, ok in self._unstarted_records(reason, "not-run"):
            if ok:
                # wait-slots (cancelled) sudah ditutup; log versi yang tak satu sel pun mulai
                # dikosongkan jadi satu baris DONE, tanpa sisa baris run lain.
                self._done_line(ver, f"rc=not-run {reason}", truncate=True)

    def _no_slots(self):
        errors = list(self.tokens)
        self.log(f"no-slots: cap {self.slots} slot penuh selama {self.limit}s — "
                 f"{len(self.queue)} versi tak dimulai ({', '.join(errors) or '-'})")
        for ver, ok in self._unstarted_records("no-slots", "inconclusive", errors=errors,
                                               outcome="no-slots"):
            if ok:
                self._done_line(ver, "rc=no-slots")

    # --- reap ---------------------------------------------------------------------------
    def _release_claim(self, ver):
        if ver in self.own_claims:
            try:
                with self._slots_lock():
                    del self.own_claims[ver]
                    self._write_claims()
            except OSError as e:
                # Lock tak bisa dibuka: klaim tetap dilepas di memori; rekaman anak tetap di-append.
                self.own_claims.pop(ver, None)
                self.log(f"peringatan: klaim slot {ver} dilepas tanpa slots.lock ({e})")

    def _on_reaped(self, ver, rc):
        self.reaped[ver] = rc
        self._release_claim(ver)
        if rc in STOPPED_CODES:
            # SIGTERM ke SATU anak (bukan --stop-job pemanggil ini) hanya membuat versi itu tak
            # berbukti: saudaranya tetap jalan & di-append. Hanya JobStopped milik proses ini
            # sendiri yang menghentikan seluruh run (exit 143).
            self.log(f"versi {ver}: anak dihentikan (rc={rc}) — tak ada rekaman untuk versi ini")
            self.child_stopped.append(ver)
            return
        if rc == 2:
            self.log(f"error: versi {ver}: anak menolak input (exit 2) — baca stderr-nya; tak ada "
                     "anak baru dimulai")
            self.exit2 = self.keep = True
            self._fire(f"input-error after {ver}")
            return
        payload = None
        if rc is not None:
            try:
                payload = json.loads(Path(self.outs[ver]).read_text(encoding="utf-8"))
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                payload = None
        if isinstance(payload, dict) and payload.get("status") == "skipped":
            reason = payload.get("reason")
            self.log(f"versi {ver}: anak melaporkan skipped ({reason}) — tak ada rekaman")
            self.skipped.append(reason)
            return
        records = records_for_child(self.pl, ver, self.engines_of[ver], payload,
                                    self.admitted[ver], self.ctx, self.log,
                                    run_id=self.claim_of[ver], wait=self.wait_res.get(ver))
        if any(r["reason"] == "crash" for r in records):
            self.keep = True
        failed = None
        for rec in records:
            # Rekaman anak yang di-reap tetap DICOBA walau append lain sudah gagal.
            if self._append(rec, force=True) and rec["state"] == "fail" and failed is None:
                failed = rec["browser"]  # engine gagal pertama, urutan psm_e2e_browsers
        if failed is not None:
            self._fire(f"fail-fast after {ver}:{failed}")

    # --- admisi -------------------------------------------------------------------------
    def _admitting(self):
        return self.trigger is None and self.append_error is None

    def _pass(self, ex):
        """Satu pass admisi di bawah slots.lock: klaim + SATU hitungan, admisi kepala antrean."""
        with self._slots_lock():
            claims = self._foreign_claims()
            used, counted, err = self.fl.daemon_slot_usage()
            self.last_pass = time.monotonic()
            self.note = None
            if err is not None:
                # Hitungan gagal/timeout = cap penuh (tak ada yang diadmisi).
                self.tokens = [f"docker count failed: {_count_error_tail(err)}"]
                return
            live_runs = {c["run"] for c in counted if c.get("run")}
            tokens = [f"{c.get('job') or '?'}@{c.get('host') or '?'}={c['cost'] or '?'}"
                      for c in counted]
            total = used
            own = [(self.ctx["job_id"], c["run"], c["cost"]) for c in self.own_claims.values()]
            for job, run, cost in claims + own:
                if run in live_runs:
                    continue  # container-nya sudah jalan & terhitung lewat psm.slots
                val = self.fl.slot_cost_value(cost)
                total += val or 1
                tokens.append(f"claim:{job}/{run}={val or '?'}")
            while self.queue:
                ver = self.queue[0]
                adm = self._admit_cost(ver, self.slots - total)
                if adm is None:
                    break
                cost, seq = adm
                self.queue.pop(0)
                self.cmds[ver] = [*self.base_cmds[ver], "--slot-cost", str(cost),
                                  *(["--sequential-browsers"] if seq else [])]
                if seq and ver not in self.forced_seq:
                    self.log(f"versi {ver}: {self.slots - total} slot bebas < "
                             f"{len(self.engines_of[ver])} engine — diadmisi biaya 1, browser "
                             "berurutan (--sequential-browsers)")
                self.own_claims[ver] = {"run": self.claim_of[ver], "cost": cost}
                self._write_claims()
                total += cost
                tokens.append(f"claim:{self.ctx['job_id']}/{self.claim_of[ver]}={cost}")
                self._close_wait(ver, "ok")
                self.admitted[ver] = utc_now()
                self.running[ex.submit(_spawn, self.cmds[ver])] = ver
            self.tokens = tokens

    def _cleanup(self):
        """`--cleanup-orphans` SEKALI per run, di dalam wait-slots, sebelum hitungan pertama.
        Hanya menghapus yang pemiliknya terbukti mati; galatnya tak pernah menggagalkan run."""
        try:
            res = self.fl.cleanup_orphans()
            self.log(f"cleanup-orphans otomatis: {res.get('status')} — dihapus "
                     f"{len(res.get('removed') or [])}, dilewati {len(res.get('skipped') or [])}, "
                     f"galat {len(res.get('errors') or [])}")
        except Exception as e:  # noqa: BLE001 — pembersihan tak boleh menggagalkan run
            self.log(f"cleanup-orphans otomatis gagal (diabaikan): {e}")

    def _tick(self):
        now = time.monotonic()
        if self.accum and self.last_tick is not None:
            self.budget += now - self.last_tick
        self.last_tick = now

    def loop(self):
        """Jalankan run; JobStopped/exception merambat ke pemanggil (finish() menutup log)."""
        # Tiap log versi antre dikosongkan lalu LANGSUNG membuka wait-slots, jadi log antre tak
        # pernah sunyi; pembersihan jalan di dalam fase itu (di luar jam no-slots).
        self.note = "cleanup-orphans running"
        for ver in self.versions:
            self.fl.progress_reset(self.logs[ver])
            self.queue.append(ver)
            self.waits[ver] = self.fl.wait_phase(self.logs[ver], ver, "wait-slots",
                                                 self._wait_detail).start()
        self._cleanup()
        self.note = "first count pending"
        self.ex = ThreadPoolExecutor(max_workers=max(1, len(self.versions)))
        first = True
        while self.queue or self.running:
            if not first:
                if self.running:
                    wait(list(self.running), timeout=SLOT_POLL, return_when=FIRST_COMPLETED)
                else:
                    time.sleep(SLOT_POLL)
            first = False
            self._tick()
            done = sorted((f for f in self.running if f.done()),
                          key=lambda f: self.order[self.running[f]])
            for fut in done:
                ver = self.running.pop(fut)
                try:
                    rc = fut.result()
                except Exception:  # runner meledak = anak tanpa output (crash), bukan crash kita
                    rc = None
                self._on_reaped(ver, rc)
            if self.queue and self._admitting():
                self._pass(self.ex)
            if self.queue and self._admitting() and not self.running \
                    and self.budget >= self.limit:
                self._no_slots()
            self.accum = bool(self.queue) and not self.running and self._admitting()

    def finish(self, mode, run_rc=None):
        """Tutup tunggu yang masih terbuka, lalu beri DONE pada log yang skrip ini kosongkan
        dan belum ber-DONE — hanya bila tak ada anak versi itu yang masih jalan."""
        in_flight = set(self.running.values())
        for ver in self.versions:
            if ver in self.done_written or ver in in_flight:
                continue
            self._close_wait(ver, "stopped" if mode == "stopped" else "cancelled")
            if self._log_has_done(ver):
                continue
            if ver in self.reaped:
                rc = self.reaped[ver]
                if rc in STOPPED_CODES:
                    detail = "rc=stopped"
                elif rc is None or rc < 0 or rc > 128:
                    detail = "rc=crash"
                else:
                    detail = f"rc={rc}"
            else:
                detail = {"stopped": "rc=stopped", "crash": "rc=crash"}.get(mode, f"rc={run_rc}")
            self._done_line(ver, detail)
        ex = getattr(self, "ex", None)
        if ex is not None:
            ex.shutdown(wait=False, cancel_futures=True)

    def _log_has_done(self, ver):
        try:
            text = Path(self.logs[ver]).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return False
        # Baris: <iso> job=.. pid=.. run=.. v=.. TOKEN ... -> token di kolom ke-6.
        return any(ln.split()[5:6] == ["DONE"] for ln in text.splitlines())


def run_e2e(args, extra, log):
    """Mode histori Lapis 4. Return exit code (0/1/2/3/143)."""
    fl = flashlight()
    pl = plan_layers()
    try:
        inp = _e2e_input(args, extra, fl, log)
    except InputError as e:
        log(f"error: {e}")
        return 2
    script = _HERE / PARALLEL_LAYERS["e2e"]
    if not script.is_file():
        log(f"error: skrip lapis tak ada: {script}")
        return 2
    module_name = Path(args.module).resolve().name
    job_id = args.job_id or fl.make_job_id(module_name, "e2e")
    if not fl.valid_job_id(job_id):
        log(f"error: --job-id tak valid: {job_id!r} — huruf kecil/angka/'-', 3-63 karakter")
        return 2

    def emit(status, reason, appended):
        print(json.dumps({"e2e_status": status, "reason": reason, "appended": appended,
                          "source_fingerprint": inp["fingerprint"]}, ensure_ascii=False),
              flush=True)

    # Docker absen: dicek PERTAMA — sebelum registrasi job, pengosongan log, wait-slots atau
    # pembersihan; run yang dilewati tak menyentuh log kemajuan mana pun.
    if not fl.docker_available():
        log(f"lapis e2e tak dijalankan: {DOCKER_SKIP_REASON}")
        emit("skipped", DOCKER_SKIP_REASON, [])
        return 0

    extra = list(inp["extra"])
    if inp["shot_base"]:
        # Distempel SEKALI; semua anak menerima folder yang sama (run_shot_dir anak idempoten).
        shot_dir = e2e_module().run_shot_dir(inp["shot_base"])
        extra += ["--screenshot-dir", shot_dir]
        log(f"screenshots: {shot_dir}")
    if args.config:
        extra += ["--config", args.config]

    fl.job_register(job_id, module=module_name, layer="e2e",
                    versions=",".join(v for v, _e in inp["cells"]))
    run = _SlotRun(args, inp, extra, script, job_id, module_name, log, fl, pl)
    log(f"log kemajuan: {progress_file(args.reports_dir, args.module, 'e2e', '<versi>')}")
    if args.verbose:
        log(f"lapis e2e: {len(run.versions)} versi, {run.slots} slot sedaemon, batas tunggu "
            f"{run.limit}s")
    try:
        try:
            run.loop()
        except BaseException as e:
            if type(e).__name__ != "JobStopped":
                run.finish("crash")
                raise
            run.finish("stopped")
            log("dihentikan: job ini (--stop-job) — rekaman yang sudah di-append tetap")
            return 143
        rc = _e2e_exit(run, emit, log)
        run.finish("normal", rc)
        return rc
    finally:
        # Dipertahankan hanya bila ada output anak yang bisa didiagnosis (crash / exit 2).
        if run.keep and any(Path(run.tmp).iterdir()):
            log(f"bukti per-versi DIPERTAHANKAN untuk diagnosis: {run.tmp}")
        else:
            shutil.rmtree(run.tmp, ignore_errors=True)


def _e2e_exit(run, emit, log):
    """Exit code + baris output atas semua rekaman yang di-append run ini."""
    if run.append_error:
        # Tanpa baris output: ini galat lingkungan (disk/izin), bukan anak yang menolak input,
        # jadi orkestrator membacanya seperti exit 2 pra-spawn (perbaiki lalu ulangi) dan tak
        # mengakhiri loop E2E. Rekaman yang sudah ter-append tetap sah.
        log(f"error: {run.append_error}")
        log(f"rekaman yang sudah di-append: {', '.join(run.appended) or '(tak ada)'}")
        return 2
    if run.exit2:
        emit("ran", None, run.appended)
        return 2
    if "fail" in run.states:
        emit("ran", None, run.appended)
        return 3
    if run.skipped:
        emit("skipped", run.skipped[0], run.appended)
        return 0
    emit("ran", None, run.appended)
    # Versi yang anaknya dihentikan tak berbukti: exit tak boleh 0 walau saudaranya lulus.
    # not-run / no-slots / inconclusive = bukan pass -> 1.
    if not run.states or run.child_stopped or any(s != "pass" for s in run.states):
        return 1
    return 0


def merge_only_e2e(args, log):
    """Tampilan laporan `<module>-e2e.json` dari histori (bukan bukti). Return exit code."""
    fl = flashlight()
    pl = plan_layers()
    agg = aggregate()
    ss = agg.load_sibling(_HERE / "ps-static-scan.py", "ps_static_scan")
    bad = ss.unresolved_path_args([("--reports-dir", args.reports_dir), ("--module", args.module),
                                   ("--config", args.config)])
    for name, val in bad:
        log(f"error: token '{{project-root}}' belum diresolve di {name}: {val}")
    if bad:
        return 2
    try:
        fl.require_config(args.config, args.reports_dir)
        cfg_versions, cfg_browsers = fl.configured_cells(args.config)
    except fl.CellConfigError as e:
        log(f"error: himpunan sel terkonfigurasi tak sah: {e}")
        return 2
    if not Path(args.module).is_dir():
        log(f"error: --module bukan folder: {args.module}")
        return 2
    module_name = Path(args.module).resolve().name
    cells = {}
    for ver in cfg_versions:
        row = {}
        for b in cfg_browsers:
            try:
                records, _tail = pl.read_history(
                    pl.history_path(args.reports_dir, module_name, ver, b), ver, b)
            except pl.PlanInputError as e:
                log(f"error: {e}")
                return 2
            row[b] = records[-1] if records else None
        cells[ver] = row
    output = layer_file(args.reports_dir, args.module, "e2e")
    view = {"module": module_name, "view": True, "cells": cells}
    try:
        Path(output).write_text(json.dumps(view, indent=2, ensure_ascii=False), encoding="utf-8")
    except OSError as e:
        log(f"error: gagal menulis {output}: {e}")
        return 2
    log(f"ditulis: {output} (tampilan laporan, bukan bukti)")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(
        description="Jalankan satu lapis mahal untuk banyak versi serentak: file lapis kanonik "
                    "(Lapis 2/5) atau histori per sel (Lapis 4).",
        epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--layer", required=True,
                    help="Lapis yang dijalankan per versi: " + "|".join(PARALLEL_LAYERS))
    ap.add_argument("--module", required=True, help="Path folder module PrestaShop")
    ap.add_argument("--versions", help="Versi target, dipisah koma (wajib kecuali lapis e2e; "
                                       "e2e: versi itu x semua browser terkonfigurasi)")
    ap.add_argument("--cells", help="Lapis e2e saja: <ver>:<browser>[+<browser>],... — sel yang "
                                    "dijalankan (eksklusif dgn --versions)")
    ap.add_argument("--session", help="Lapis e2e saja (WAJIB): token sesi validasi [a-z0-9]{16} "
                                      "dari ps-plan-layers.py --new-session")
    ap.add_argument("--tier", help="Lapis e2e saja (WAJIB kecuali --merge-only): 0|1 = `e2e_tier` "
                                   "dari ps-plan-layers.py; distempel di tiap rekaman histori")
    ap.add_argument("--config", help="JSON psm-config (resolve-psm-config.py) — diteruskan apa "
                                     "adanya ke tiap anak. Lapis e2e membaca himpunan sel, "
                                     "psm_flashlight_tag_map dan psm_flashlight_startup_timeout")
    ap.add_argument("--jobs", type=int, default=None,
                    help=f"Lapis 2/5: versi yang boot serentak (default {DEFAULT_JOBS}; tiap job "
                         "mem-boot container PS + DB). Lapis e2e: exit 2 — pakai --slots")
    ap.add_argument("--slots",
                    help="Lapis e2e saja (override manual): cap slot SEDAEMON — jumlah label "
                         "psm.slots semua container yang jalan + klaim run lain (default "
                         f"psm_e2e_slots dari --config, else {DEFAULT_E2E_SLOTS}); bilangan bulat "
                         ">= 1")
    ap.add_argument("--reports-dir", required=True,
                    help="Folder laporan (psm_reports_dir). Nama file lapis DITURUNKAN dari "
                         "module & lapis — tak bisa diketik, supaya bukti tak bisa mendarat "
                         "di file module atau lapis lain")
    ap.add_argument("--verbose", action="store_true", help="Jejak per versi ke stderr")
    ap.add_argument("--per-version", action="store_true",
                    help="Lapis 2/5: persist bukti tiap versi sebagai file lapis PER-VERSI "
                         "`<module>-<lapis>-<versi>.json` (nama diturunkan) alih-alih menulis satu "
                         "file kanonik. Lapis e2e: exit 2 (buktinya histori per sel).")
    ap.add_argument("--merge-only", action="store_true",
                    help="JANGAN jalankan lapis. Lapis 2/5: satukan file per-versi persisten "
                         "`<module>-<lapis>-<versi>.json` untuk --versions jadi kanonik (mtime = "
                         "bukti TERTUA). Lapis e2e: tulis tampilan laporan <module>-e2e.json dari "
                         "histori (hanya --module, --reports-dir, --config).")
    ap.add_argument("--job-id",
                    help="ID job (default dibuat: <module>-<lapis>-<HHMM>-<hex>) — dibagikan ke semua "
                         "anak versi; hentikan terarah: ps-flashlight-run.py --stop-job <id>")
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
    if args.layer != "e2e":
        for flag, val in (("--cells", args.cells), ("--session", args.session),
                          ("--slots", args.slots), ("--tier", args.tier)):
            if val is not None:
                log(f"error: {flag} hanya untuk lapis e2e")
                return 2
    else:
        if args.jobs is not None:
            log("error: --jobs tak berlaku untuk lapis e2e — konkurensi E2E diatur slot sedaemon: "
                "--slots (atau psm_e2e_slots di --config)")
            return 2
        if args.slots is not None and args.merge_only:
            log("error: --slots tak berlaku dengan --merge-only (tak ada yang di-boot)")
            return 2
    if args.jobs is not None and args.jobs < 1:
        log(f"error: --jobs harus >= 1 (diberi {args.jobs})")
        return 2
    if args.jobs is None:
        args.jobs = DEFAULT_JOBS

    extra = list(args.extra)
    if extra and extra[0] == "--":
        extra = extra[1:]

    if args.merge_only:
        if args.layer == "e2e":
            given = [f for f, v in (("--cells", args.cells), ("--versions", args.versions),
                                    ("--session", args.session), ("--tier", args.tier))
                     if v is not None]
            if extra:
                given.append("passthrough sesudah `--`")
            if given:
                log(f"error: --merge-only --layer e2e hanya menerima --module, --reports-dir, "
                    f"--config — hapus: {', '.join(given)}")
                return 2
            return merge_only_e2e(args, log)
        # Tak men-spawn apa pun: flag passthrough setelah `--` tak punya tujuan, dan menerimanya
        # diam-diam menyembunyikan salah pakai.
        if extra:
            log("error: --merge-only tak menjalankan lapis apa pun — flag passthrough setelah "
                "`--` tak bermakna; hapus")
            return 2
        versions = parse_versions(args.versions)
        if not versions:
            log("error: --versions kosong — tak ada yang bisa dijalankan maupun divonis")
            return 2
        return merge_only(args.reports_dir, args.module, args.layer, versions, log)

    hits = reserved_in_passthrough(extra)
    if hits:
        log(f"error: flag milik skrip ini ada di passthrough: {', '.join(sorted(set(hits)))}")
        log("--versions, -o, --config dan pilihan browser ditentukan di sini supaya tiap anak "
            "tak bisa menimpanya")
        return 2

    if args.layer == "e2e":
        return run_e2e(args, extra, log)

    versions = parse_versions(args.versions)
    if not versions:
        log("error: --versions kosong — tak ada yang bisa dijalankan maupun divonis")
        return 2

    extra, shot_base = split_screenshot_dir(extra)

    agg = aggregate()
    ss = agg.load_sibling(_HERE / "ps-static-scan.py", "ps_static_scan")
    bad = ss.unresolved_path_args([("--reports-dir", args.reports_dir),
                                   ("--screenshot-dir", shot_base),
                                   ("--module", args.module),
                                   ("--config", args.config)])
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
    if args.config:
        extra = [*extra, "--config", args.config]  # diteruskan apa adanya, tak divalidasi di sini

    script = _HERE / PARALLEL_LAYERS[args.layer]
    if not script.is_file():
        log(f"error: skrip lapis tak ada: {script}")
        return 2

    fl = flashlight()
    job_id = args.job_id or fl.make_job_id(Path(args.module).resolve().name, args.layer)
    if not fl.valid_job_id(job_id):
        log(f"error: --job-id tak valid: {job_id!r} — huruf kecil/angka/'-', 3-63 karakter")
        return 2
    # Orkestrator ikut terdaftar di job: --stop-job menyinyal anak DAN pemanggil ini.
    fl.job_register(job_id, module=Path(args.module).resolve().name, layer=args.layer,
                    versions=",".join(versions))

    output = layer_file(args.reports_dir, args.module, args.layer)

    # Direktori bukti dibuat manual, bukan lewat context manager: pada kegagalan pasca-spawn
    # ia SENGAJA dipertahankan. Run empat lapis bisa berarti puluhan menit boot Docker, dan
    # membuang seluruhnya karena satu anak menulis payload cacat membuat kegagalan itu tak
    # bisa dipulihkan maupun didiagnosis. Pada jalur sukses ia dihapus.
    started = time.time()
    tmp = tempfile.mkdtemp(prefix="psm-layer-")
    keep = False
    try:
        plan = plan_children(script, args.module, versions, tmp, extra,
                             progress=(args.reports_dir, args.layer), job_id=job_id)
        log(f"log kemajuan: {progress_file(args.reports_dir, args.module, args.layer, '<versi>')}")
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


def _run():
    try:
        return main()
    except BaseException as e:  # JobStopped milik ps-flashlight-run (dimuat lazy)
        if type(e).__name__ == "JobStopped":
            print("dihentikan: job ini (SIGTERM dari --stop-job)", file=sys.stderr)
            return 143
        raise


if __name__ == "__main__":
    sys.exit(_run())
