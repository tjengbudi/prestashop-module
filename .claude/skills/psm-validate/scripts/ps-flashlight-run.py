#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Jalankan validasi module di dalam Docker prestashop-flashlight, per versi.

Lapisan akurasi #2: menguji module terhadap PrestaShop core ASLI tiap versi —
instalasi module + analisis statis (phpstan) di dalam core yang benar-benar boot.
Deterministik per (module, versi, image). Output JSON per versi.

PENTING — flashlight butuh DATABASE. Image `prestashop/prestashop-flashlight`
adalah web-tier saja (nginx + php-fpm), TANPA server MySQL: entrypoint-nya menunggu
host DB bernama `mysql`/sesuai `MYSQL_HOST` selamanya. Karena itu skrip ini TIDAK
menjalankan `docker run` telanjang (yang pasti gagal "no database"), melainkan
membangun DB + flashlight berpasangan:
  - orchestrator `compose` : generate docker-compose ephemeral (mariadb + flashlight,
    di-gate lewat healthcheck DB) lalu `docker compose up -d`.
  - orchestrator `manual`  : `docker network` + dua `docker run` (mariadb lalu
    flashlight) pada network yang sama; hanya butuh CLI `docker`.
  - `auto` (default)       : compose bila tersedia, jika tidak manual.

Tiap container/network dicap label kepemilikan (`psm.run`/`psm.owner-pid`/`psm.owner-host`).
Run normal membongkar miliknya sendiri; run yang di-kill paksa meninggalkan artefak yatim —
`--cleanup-orphans` menghapus HANYA yang proses pemiliknya sudah mati, jadi run sesi lain
yang sedang jalan dilewati (dilaporkan beserta alasannya), bukan dibunuh.

Env runtime flashlight yang dibaca: MYSQL_HOST/PORT/USER/PASSWORD/DATABASE + PS_DOMAIN
(bukan DB_SERVER/DB_NAME — itu milik image produksi prestashop/prestashop, diabaikan).
Kesiapan diukur dari HEALTHCHECK container flashlight (status `healthy`), bukan port.

Coding-standard: image punya `phpstan` (canonical PrestaShop), BUKAN `phpcs`. Bila
module membawa `phpstan.neon`(.dist) sendiri, hasilnya KONKLUSIF (memblok bila error).
Bila tidak, skrip meng-auto-generate neon yang menyertakan extension resmi PrestaShop
(`ps-module-extension.neon`: stub Module/Tab + bootstrap, akurat; fallback
scanDirectories bila absen). Hasil auto-neon bersifat ADVISORY (errors=0, tak memblok)
— kita tak menjatuhkan rilis atas config buatan sendiri, hanya surface sebagai warning.

Bila Docker/compose tak tersedia, keluar dengan status terstruktur (`skipped` /
`skipped_image`) — bukan crash — supaya pemanggil bisa degrade ke ps-static-scan.
Pemetaan tag default mengikuti tag resmi Docker Hub prestashop/prestashop-flashlight.
"""
import argparse
import atexit
import json
import os
import pathlib
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

DEFAULT_TAG_MAP = {"1.7.8": "1.7.8.11", "8.1": "8.1.6-nginx", "9.1": "9.1.4-nginx"}
# Kontrol positif cakupan phpstan. Namanya dipakai DUA sisi — INNER_SH menulis filenya,
# parse_phpstan mengenalinya di laporan — jadi ia disulih ke INNER_SH lewat token di bawah,
# bukan diketik ulang di sana. Mengetiknya ulang membuat komentar ini bohong: rename konstanta
# akan memalsukan error yang memblok (temuan canary tak dikenali lalu dihitung sbg milik module)
# SEKALIGUS memvoidkan cakupan (canary "tak muncul") — dua cacat dari satu refactor yang tampak
# tak berbahaya, persis kelas rename CONTAINER_PREFIX.
CANARY_BASENAME = "psm-coverage-canary.php"
_CANARY_TOKEN = "__PSM_CANARY_BASENAME__"
IMAGE = "prestashop/prestashop-flashlight"
DEFAULT_DB_IMAGE = "mariadb:lts"
DEFAULT_PS_DOMAIN = "localhost:8000"
DEFAULT_STARTUP_TIMEOUT = 180  # detik menunggu container jadi healthy
DEFAULT_ORCHESTRATOR = "auto"   # auto = compose bila ada, else manual
# Kredensial DB — harus cocok di sisi flashlight & DB; nilai internal, bukan setelan.
DB_USER = "prestashop"
DB_PASSWORD = "prestashop"
DB_NAME = "prestashop"

# Awalan SEMUA sentinel fase phpstan (PSM_PHPSTAN_GEN=/_JSON_START/_JSON_END/_ABSENT). Dipakai
# untuk memotong ekor phpstan dari log install; dinamai supaya kopling ke awalannya terlihat,
# dan dikunci test yang memeriksa tiap sentinel fase itu benar-benar berawalan ini.
PHPSTAN_SENTINEL_PREFIX = "PSM_PHPSTAN"

# Blok install yang dijalankan DI DALAM container. Dipakai KEDUA lapis: Lapis 2 (INNER_SH, +
# phpstan) dan Lapis 4 (ps-e2e-run.INSTALL_SH, tanpa phpstan). SATU konstanta, karena sentinel
# di sini berpasangan dengan parse_install di bawah. Seam-nya dulu asimetris — reader dibagi
# lewat impor, writer disalin — jadi rename satu sentinel di satu sisi bikin install dilaporkan
# GAGAL untuk module yang sebenarnya sukses, lalu jatuh jadi tak-konklusif berbentuk infra dan
# `ready` turun tanpa ada yang menyebut sebabnya. $MOD_NAME dari env.
INSTALL_BLOCK_SH = r'''
if ! cp -r /ps-module-src "/var/www/html/modules/$MOD_NAME" 2>&1; then echo PSM_COPY_FAIL; fi
cd /var/www/html || echo PSM_NO_PSROOT
if [ ! -f bin/console ]; then
  echo PSM_NO_CONSOLE
elif php -d memory_limit=-1 bin/console prestashop:module --no-interaction install "$MOD_NAME" 2>&1; then
  echo PSM_INSTALL_OK
else
  echo PSM_INSTALL_FAIL
fi
'''

# Skrip yang dijalankan DI DALAM container flashlight setelah healthy: salin module,
# install via PS console, lalu phpstan (neon module bila ada, else auto-generate).
INNER_SH = INSTALL_BLOCK_SH + r'''
NEON=""
for c in "modules/$MOD_NAME/phpstan.neon" "modules/$MOD_NAME/phpstan.neon.dist"; do
  if [ -f "$c" ]; then NEON="$c"; break; fi
done
GEN=0
if [ -z "$NEON" ]; then
  GEN=1
  NEON=/tmp/psm-phpstan.neon
  EXT=/var/opt/prestashop/coding-standards/phpstan/ps-module-extension.neon
  if [ -f "$EXT" ]; then
    # Extension resmi PrestaShop (stub Module/Tab + bootstrap) -> analisis akurat.
    printf 'includes:\n    - %s\nparameters:\n    level: 2\n    paths:\n        - /var/www/html/modules/%s\n' "$EXT" "$MOD_NAME" > "$NEON"
  else
    # Fallback bila extension resmi tak ada: scanDirectories (best-effort, bisa noisy).
    printf 'parameters:\n    level: 2\n    paths:\n        - /var/www/html/modules/%s\n    scanDirectories:\n        - /var/www/html/classes\n        - /var/www/html/src\n        - /var/www/html/vendor/prestashop\n' "$MOD_NAME" > "$NEON"
  fi
fi
if command -v phpstan >/dev/null 2>&1; then
  echo "PSM_PHPSTAN_GEN=$GEN"
  # CANARY / kontrol positif. Laporan JSON phpstan TAK bisa membedakan "bersih" dari "tak
  # menganalisis apa-apa": map `files` hanya memuat file YANG BER-ERROR, jadi module bersih dan
  # module yang neon-nya mengecualikan dirinya sendiri sama-sama menghasilkan files:{} &
  # file_errors:0 — dan yang kedua dulu diklaim "coding standard bersih, konklusif". File ini
  # dijamin ber-error di level berapa pun (fungsi tak dikenal); kalau ia TAK muncul di laporan,
  # berarti phpstan tak menyentuh pohon module dan vonis CS tak boleh diklaim. Ditulis ke
  # SALINAN dalam container (module di-cp di atas), jadi pohon module di host tak tersentuh.
  printf '<?php\npsm_canary_undefined_fn_xyz();\n' > "modules/$MOD_NAME/__PSM_CANARY_BASENAME__"
  echo PSM_PHPSTAN_JSON_START
  phpstan analyse --no-progress --error-format=json --memory-limit=-1 -c "$NEON" "modules/$MOD_NAME" 2>/dev/null || true
  echo PSM_PHPSTAN_JSON_END
  rm -f "modules/$MOD_NAME/__PSM_CANARY_BASENAME__"
else
  echo PSM_PHPSTAN_ABSENT
fi
'''.replace(_CANARY_TOKEN, CANARY_BASENAME)


def docker_available():
    if not shutil.which("docker"):
        return False
    try:
        r = subprocess.run(["docker", "info"], capture_output=True, timeout=20)
        return r.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def compose_available():
    """True bila plugin `docker compose` (v2) tersedia."""
    try:
        r = subprocess.run(["docker", "compose", "version"], capture_output=True, timeout=20)
        return r.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def image_present(image_ref):
    """True bila image sudah ada lokal (tak perlu pull)."""
    try:
        r = subprocess.run(["docker", "image", "inspect", image_ref],
                           capture_output=True, timeout=20)
        return r.returncode == 0
    except (subprocess.SubprocessError, OSError):
        return False


def _parse_pairs(raw):
    """'1.7.8=1.7.8.11,8.1=8.1.6-nginx' -> dict. Tanpa pasangan valid -> {}."""
    out = {}
    for pair in (raw or "").split(","):
        if "=" in pair:
            k, v = pair.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def parse_tag_map(raw, extra=None):
    """Peta versi->tag. `raw` MENGGANTI peta default; `extra` MENAMBAH di atasnya.

    Dua kanal karena dua maksud berbeda: --tag-map memasang peta lengkap (mis. dari
    config psm_flashlight_tag_map), --extra-tag-map menambal satu-dua versi tanpa
    menjatuhkan sisanya. Dulu hanya ada kanal pengganti, sehingga satu tag tambahan
    membuang tag versi lain -> tag telanjang -> image tak ada -> lapis void diam-diam.
    """
    base = _parse_pairs(raw) or dict(DEFAULT_TAG_MAP)
    base.update(_parse_pairs(extra))
    return base


def resolve_tag(tag_map, full_ver):
    """Tag image untuk satu versi target: cocokkan versi penuh, lalu bentuk yang dipendekkan.

    Satu pemilik untuk aturan ini. Ekspresinya sempat disalin di dua main() (flashlight & e2e),
    dan pra-pass kesegaran butuh jawaban yang SAMA untuk tahu apakah file lapis diproduksi image
    yang sama — implementasi ketiga yang mendrift akan membuat gerbangnya menolak reuse yang sah
    atau, lebih buruk, menerima bukti dari core yang lain.
    """
    return tag_map.get(full_ver) or tag_map.get(full_ver.rsplit(".", 1)[0]) or full_ver


def parse_install(out):
    """Baca penanda hasil install dari output inner-script.

    `no_console`/`no_psroot` = kondisi INFRASTRUKTUR (image tanpa bin/console, PS root
    tak ada): pemanggil memperlakukannya tak konklusif, bukan module gagal install.
    Keduanya benar-benar diemit inner-script — sentinel yang dibaca tapi tak pernah
    ditulis = jalur degrade mati, dan infra jatuh jadi vonis memblok palsu.

    `no_verdict` = installer TAK PERNAH mencapai vonisnya: baik PSM_INSTALL_OK maupun
    PSM_INSTALL_FAIL absen (docker exec mati sesudah healthy / output terpotong / sh gagal).
    Dulu PSM_INSTALL_FAIL DITULIS tapi tak pernah DIBACA — jadi 'exec mati' dan 'installer
    menolak module' jatuh ke ok=False yang sama, dan infra murni dijual sbg vonis memblok
    'modul gagal install di core asli'. Membaca PSM_INSTALL_FAIL memisahkan keduanya: hanya
    ia bukti installer BENAR-BENAR menjalankan lalu menolak (satu-satunya yang boleh memblok).
    """
    if "PSM_COPY_FAIL" in out:
        return {"ok": False, "no_console": False, "no_psroot": False,
                "copy_fail": True, "no_verdict": False}
    ran = ("PSM_INSTALL_OK" in out) or ("PSM_INSTALL_FAIL" in out)
    return {"ok": "PSM_INSTALL_OK" in out, "no_console": "PSM_NO_CONSOLE" in out,
            "no_psroot": "PSM_NO_PSROOT" in out, "copy_fail": False, "no_verdict": not ran}


def parse_phpstan(out):
    """Ambil hitungan error EXACT dari laporan JSON phpstan (bukan tebak substring).

    phpstan --error-format=json -> {"totals":{"file_errors":N,...}, "files":{...}, "errors":[...]}.
    Neon auto-generate (GEN=1) bersifat ADVISORY: errors dipetakan ke warnings agar
    TAK memblok vonis (tanpa bootstrap module, phpstan bisa false-positive). Neon milik
    module (GEN=0) bersifat konklusif: errors tetap errors (memblok).
    """
    if "PSM_PHPSTAN_ABSENT" in out:
        return {"available": False}
    if "PSM_PHPSTAN_JSON_START" not in out or "PSM_PHPSTAN_JSON_END" not in out:
        return {"available": True, "parse_ok": False, "note": "penanda laporan phpstan tak ditemukan"}
    generated = "PSM_PHPSTAN_GEN=1" in out
    raw = out.split("PSM_PHPSTAN_JSON_START", 1)[1].split("PSM_PHPSTAN_JSON_END", 1)[0].strip()
    start = raw.find("{")
    if start == -1:
        return {"available": True, "parse_ok": False, "generated_config": generated,
                "note": "JSON phpstan kosong/tak valid"}
    try:
        report = json.loads(raw[start:])
    except json.JSONDecodeError:
        return {"available": True, "parse_ok": False, "generated_config": generated,
                "note": "gagal parse JSON phpstan"}
    totals = report.get("totals", {}) or {}
    generic = report.get("errors", []) or []  # error non-file (mis. neon/bootstrap)
    files = report.get("files", {}) or {}
    messages = []
    canary_hits = 0
    for path, fdata in files.items():
        msgs = fdata.get("messages", []) or []
        # Temuan canary BUKAN temuan module: ia cuma membuktikan phpstan benar-benar menyentuh
        # pohon module. Disaring dari vonis lalu dikurangkan dari hitungan supaya kontrol positif
        # ini tak pernah bocor jadi error yang memblok.
        if CANARY_BASENAME in str(path):
            canary_hits += len(msgs)
            continue
        for m in msgs:
            messages.append({"line": m.get("line"), "source": "phpstan",
                             "message": (m.get("message") or "")[:160], "file": path})
    for g in generic:
        messages.append({"line": 0, "source": "phpstan", "message": str(g)[:160]})
    count = totals.get("file_errors", 0) - canary_hits + len(generic)
    # Canary tak muncul = phpstan tak menganalisis satu file pun dari module (mis. neon module
    # meng-excludePaths dirinya sendiri). 0 error di situ bukan "bersih" — itu "tak diukur".
    coverage_ok = canary_hits > 0
    if generated:
        return {"available": True, "parse_ok": True, "generated_config": True,
                "coverage_ok": coverage_ok, "errors": 0, "warnings": count,
                "error_messages": messages[:50],
                "note": "phpstan pakai neon auto-generate (advisory — tak memblok)"}
    return {"available": True, "parse_ok": True, "generated_config": False,
            "coverage_ok": coverage_ok, "errors": count, "warnings": 0,
            "error_messages": messages[:50]}


# --- log kemajuan -----------------------------------------------------------
# Uji Docker bisa diam belasan menit (pull, boot, install+phpstan per versi), dan saat banyak
# sesi berbagi satu daemon, run yang MACET tak bisa dibedakan dari run yang LAMBAT. Skrip
# lapis Docker (flashlight/e2e/scenario) menulis satu baris bertimestamp per kejadian ke file
# log kemajuan supaya pemanggil bisa memantau tanpa menunggu hasil akhir:
#   <iso-waktu> job=<job-id> pid=<pid> run=<id> v=<versi> <TOKEN> <fase> <detail>
# TOKEN (kontrak, dibaca pemanggil — jangan diganti):
#   START  fase mulai            ALIVE  fase masih jalan (denyut tiap PROGRESS_HEARTBEAT detik)
#   SLOW   fase melewati ambang lambat (diduga macet; uji tetap jalan sampai batas waktunya)
#   END    fase selesai (ok|timeout|error|<status>)   DONE  proses selesai (rc=<kode>|crash)
# Tak ada baris baru > ~3 menit tanpa DONE = proses menggantung di luar fase atau mati.
# Log kemajuan tak pernah menggagalkan uji: error tulis ditelan.
PROGRESS_HEARTBEAT = 15          # detik antar denyut ALIVE/SLOW
PROGRESS_SLOW_AFTER = 180        # detik sebelum fase ditandai SLOW
PROGRESS_SLOW_AFTER_PHASE = {"pull": 900}  # unduh image multi-GB memang lama
# Fase TUNGGU (cell-contract.md > Phase timings): lamanya = lamanya fase yang ditunggu, yang
# punya batasnya sendiri — jadi TAK PERNAH ditandai SLOW, apa pun --slow-after.
WAIT_PHASES = ("wait-slots", "keeper-wait")
WAIT_PHASE_PREFIXES = ("lock-wait:", "barrier-wait:")
DOCKER_CMD_TIMEOUT = 120         # perintah docker pendek (run/network/inspect/rm/down) —
                                 # tanpa batas, daemon yang tersendat menggantung run selamanya
_PROGRESS = {"path": None, "version": "-", "slow_after": None}
_PROGRESS_LOCK = threading.Lock()


def is_wait_phase(name):
    """True untuk fase tunggu (wait-slots, keeper-wait, lock-wait:<e>, barrier-wait:<e>)."""
    base = (name or "").split("#", 1)[0]
    return base in WAIT_PHASES or base.startswith(WAIT_PHASE_PREFIXES)


def progress_init(path, slow_after=None, truncate=True):
    """Aktifkan log kemajuan ke `path`. None = nonaktif (no-op).

    `truncate` True (default) mengosongkan file dulu; False (`--progress-append`, anak yang
    dimulai ps-run-layer) mempertahankan baris yang sudah ditulis pemanggil (`wait-slots`).
    """
    _PROGRESS["path"] = Path(path) if path else None
    _PROGRESS["slow_after"] = slow_after
    if path:
        try:
            Path(path).parent.mkdir(parents=True, exist_ok=True)
            if truncate:
                Path(path).write_text("", encoding="utf-8")
        except OSError:
            _PROGRESS["path"] = None


def progress_version(full_ver):
    _PROGRESS["version"] = full_ver or "-"


def progress_line(version, token, phase_name="", detail=""):
    """Satu baris log kemajuan (tanpa newline) — format kontrak di komentar di atas."""
    parts = [datetime.now().isoformat(timespec="seconds"), f"job={_JOB['id'] or '-'}",
             f"pid={OWNER_PID}", f"run={RUN_ID}", f"v={version or '-'}", token, phase_name, detail]
    return " ".join(p for p in parts if p)


def progress_to(path, version, token, phase_name="", detail="", *, truncate=False):
    """Tulis satu baris ke log `path` atas nama `version` — path & versi PER PANGGILAN.

    Dipakai ps-run-layer, yang menulis log tiap versi yang diantre (`wait-slots`, `DONE`)
    tanpa mengaktifkan log global proses. `truncate` = kosongkan file lalu tulis baris itu
    saja. None = no-op; error tulis ditelan (log tak pernah menggagalkan uji).
    """
    if not path:
        return
    line = progress_line(version, token, phase_name, detail)
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with _PROGRESS_LOCK, open(path, "w" if truncate else "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
    except OSError:
        pass


def progress_reset(path):
    """Kosongkan log `path` (buat foldernya bila perlu). Error ditelan."""
    if not path:
        return
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with _PROGRESS_LOCK:
            Path(path).write_text("", encoding="utf-8")
    except OSError:
        pass


def progress(token, phase_name="", detail=""):
    progress_to(_PROGRESS["path"], _PROGRESS["version"], token, phase_name, detail)


class wait_phase:
    """Fase tunggu ke log `path` atas nama `version`: START, denyut ALIVE tiap
    PROGRESS_HEARTBEAT, END <outcome>. TAK PERNAH SLOW (apa pun --slow-after).

    `detail` boleh string atau callable tanpa argumen (dihitung ulang tiap denyut, mis.
    "last pass 3s ago"); boleh diganti selama fase. `end(outcome)` menghentikan denyut,
    MENUNGGU thread-nya selesai, lalu menulis END — jadi tak ada ALIVE sesudah END — dan
    mengembalikan {seconds, outcome}; panggilan berikutnya mengembalikan hasil yang sama.
    Dipakai juga sebagai context manager (exception -> outcome `cancelled`).
    """

    def __init__(self, path, version, name, detail=""):
        self.path, self.version, self.name, self.detail = path, version, name, detail
        self._stop = threading.Event()
        self._thread = None
        self._t0 = None
        self.result = None

    def _detail(self):
        d = self.detail
        if callable(d):
            try:
                d = d()
            except Exception:  # noqa: BLE001 — detail log tak boleh mematikan denyut
                d = ""
        return d or ""

    def _beat(self):
        while not self._stop.wait(PROGRESS_HEARTBEAT):
            elapsed = int(time.monotonic() - self._t0)
            progress_to(self.path, self.version, "ALIVE", self.name,
                        f"{elapsed}s {self._detail()}".rstrip())

    def start(self):
        self._t0 = time.monotonic()
        progress_to(self.path, self.version, "START", self.name, self._detail())
        if self.path:
            self._thread = threading.Thread(target=self._beat, daemon=True)
            self._thread.start()
        return self

    def end(self, outcome="ok"):
        if self.result is not None:
            return self.result
        self._stop.set()
        if self._thread:
            # Berbatas: denyut yang tersangkut di FS macet tak boleh membekukan admisi
            # (end() dipanggil di bawah slots.lock).
            self._thread.join(timeout=PROGRESS_HEARTBEAT + 2)
        seconds = time.monotonic() - (self._t0 if self._t0 is not None else time.monotonic())
        progress_to(self.path, self.version, "END", self.name, f"{outcome} {int(seconds)}s")
        self.result = {"seconds": round(seconds, 3), "outcome": outcome}
        return self.result

    def __enter__(self):
        return self.start()

    def __exit__(self, exc_type, exc, tb):
        self.end("ok" if exc_type is None else "cancelled")
        return False


# --- Sink durasi fase (CAP-6) ---------------------------------------------------
# Log kemajuan dikosongkan tiap run, jadi durasi fase yang mau dibawa ke rekaman bukti
# diukur timer dalam-proses. Sink NONAKTIF secara default: Lapis 2/5 (dan tiap skrip yang
# tak mengaktifkannya) berperilaku persis seperti dulu. ps-e2e-run mengaktifkan satu sink
# per panggilan run_one_version (timing_activate) lalu mengambilnya (timing_deactivate).
# Fase `browser:<engine>` masuk ke phase_durations engine itu, selainnya ke boot_phases;
# fase yang berulang dalam satu sink diberi akhiran `#2`, `#3`, ... (mis. `pull#2` utk
# image DB, `bring-up#2` sesudah retry port).
CELL_PHASE_PREFIX = "browser:"
_TIMING = {"sink": None}
_TIMING_LOCK = threading.Lock()


class TimingSink:
    """Penampung durasi fase satu boot: `boot_phases` + `phase_durations[<engine>]`.

    Tiap entri = {"seconds": float (monotonic, 3 desimal), "outcome": status END}.
    Fase yang tak terjadi tak pernah muncul (bukan 0).
    """

    def __init__(self):
        self.boot_phases = {}
        self.phase_durations = {}
        self._counts = {}

    def record(self, name, seconds, outcome):
        with _TIMING_LOCK:
            n = self._counts.get(name, 0) + 1
            self._counts[name] = n
            key = name if n == 1 else f"{name}#{n}"
            entry = {"seconds": round(float(seconds), 3), "outcome": outcome}
            if name.startswith(CELL_PHASE_PREFIX):
                engine = name[len(CELL_PHASE_PREFIX):]
                self.phase_durations.setdefault(engine, {})[key] = entry
            else:
                self.boot_phases[key] = entry

    def as_dict(self):
        return {"boot_phases": dict(self.boot_phases),
                "phase_durations": {e: dict(p) for e, p in self.phase_durations.items()}}


def timing_activate():
    """Aktifkan sink baru (menggantikan yang aktif, bila ada) dan kembalikan sink itu."""
    sink = TimingSink()
    _TIMING["sink"] = sink
    return sink


def timing_current():
    """Sink yang sedang aktif (None bila tak ada) — dibaca di tengah boot, mis. fail-fast
    antar-engine ps-e2e-run yang menilai sel sebelum sink diambil."""
    return _TIMING["sink"]


def timing_deactivate():
    """Nonaktifkan sink aktif dan kembalikan sink itu (None bila tak ada yang aktif)."""
    sink, _TIMING["sink"] = _TIMING["sink"], None
    return sink


class phase:
    """Context manager satu fase: START, denyut ALIVE/SLOW di thread latar, lalu END.

    `ph.detail` boleh diperbarui selama fase (mis. status health terakhir) — denyut
    menyertakannya; `ph.status` (opsional) menggantikan 'ok' di baris END. Bila sink durasi
    aktif (timing_activate), tiap fase — gagal sekalipun — dicatat {seconds, outcome}
    dengan outcome = status END; baris log kemajuan tak berubah.
    """

    def __init__(self, name, timeout=None, detail=""):
        self.name, self.timeout, self.detail, self.status = name, timeout, detail, None
        self._stop = threading.Event()
        self._thread = None

    def _elapsed(self):
        return int(time.monotonic() - self._t0)

    def _budget(self):
        return f"{self._elapsed()}s" + (f"/{self.timeout}s" if self.timeout else "")

    def _beat(self):
        slow = _PROGRESS["slow_after"] or PROGRESS_SLOW_AFTER_PHASE.get(self.name, PROGRESS_SLOW_AFTER)
        never_slow = is_wait_phase(self.name)
        while not self._stop.wait(PROGRESS_HEARTBEAT):
            token = ("SLOW" if not never_slow and time.monotonic() - self._t0 >= slow
                     else "ALIVE")
            progress(token, self.name, f"{self._budget()} {self.detail}".rstrip())

    def __enter__(self):
        self._t0 = time.monotonic()
        progress("START", self.name, (f"batas {self.timeout}s " if self.timeout else "") + self.detail)
        if _PROGRESS["path"]:
            self._thread = threading.Thread(target=self._beat, daemon=True)
            self._thread.start()
        return self

    def __exit__(self, exc_type, exc, tb):
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
        if exc_type is None:
            st = self.status or "ok"
        elif issubclass(exc_type, subprocess.TimeoutExpired):
            st = "timeout"
        else:
            st = f"error({exc_type.__name__})"
        progress("END", self.name, f"{st} {self._elapsed()}s")
        sink = _TIMING["sink"]
        if sink is not None:
            sink.record(self.name, time.monotonic() - self._t0, st)
        return False


def run_main_with_progress(main_fn):
    """Bungkus main() skrip lapis: baris DONE selalu ditulis, juga saat crash / dihentikan."""
    try:
        rc = main_fn()
    except JobStopped:
        # --stop-job: finally/_teardown di jalur run sudah jalan saat exception ini naik.
        progress("DONE", "", "rc=stopped")
        print(f"dihentikan: job {_JOB['id']} (SIGTERM dari --stop-job)", file=sys.stderr)
        return 143
    except BaseException:
        progress("DONE", "", "rc=crash")
        raise
    progress("DONE", "", f"rc={rc}")
    return rc


# --- Job ID -------------------------------------------------------------------
# Satu pemanggilan = satu JOB yang TERLIHAT: `<module>-<lapis>-<HHMM>-<4hex>`. ps-run-layer
# membuat satu ID dan semua anak per-versinya memakainya. ID ini dicap ke label `psm.job`,
# ke NAMA container/project (terbaca di `docker ps`), ke tiap baris log kemajuan, dan ke
# registry proses lokal. Tujuannya satu: menghentikan run secara TERARAH lewat
# `--stop-job <id>` — bukan lewat pkill/`docker rm` berbasis nama yang ikut membunuh job
# lain (satu sesi banyak job, atau banyak sesi berbagi daemon).
LABEL_JOB = "psm.job"
JOB_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,62}$")
JOB_REGISTRY = Path(tempfile.gettempdir()) / "psm-jobs"
JOB_STOP_GRACE = 60   # detik menunggu job membongkar dirinya sendiri sebelum SIGKILL
_JOB = {"id": None, "entry_path": None, "entry": None}
# Kunci lintas proses (cell-contract.md > Config keys > psm_e2e_slots): `slots.lock` dipegang
# ps-run-layer selama hitung-lalu-klaim slot. Di luar psm-jobs/ (yang *.json-nya entri proses).
LOCK_DIR = Path(tempfile.gettempdir()) / "psm-locks"


class JobStopped(BaseException):
    """SIGTERM dari --stop-job, dilempar di thread utama. BaseException supaya tak ditelan
    `except Exception`; subprocess.run membunuh anaknya, lalu finally/_teardown jalan."""


def _slug(text, limit):
    out = re.sub(r"[^a-z0-9]+", "-", (text or "").lower()).strip("-")[:limit].strip("-")
    return out or "x"


def make_job_id(module, layer):
    return f"{_slug(module, 20)}-{_slug(layer, 12)}-{datetime.now():%H%M}-{uuid.uuid4().hex[:4]}"


def valid_job_id(job_id):
    return bool(job_id) and JOB_RE.match(job_id) is not None


def _name_infix():
    """Sisipan nama container/project: `<job>-` bila job aktif, else kosong."""
    return f"{_JOB['id']}-" if _JOB["id"] else ""


def _on_sigterm(signum, frame):
    raise JobStopped()


def _job_unregister():
    path = _JOB.get("entry_path")
    if not path:
        return
    try:
        path.unlink(missing_ok=True)
        path.parent.rmdir()  # hanya bila kosong — job lain/anak lain masih terdaftar
    except OSError:
        pass


def _write_entry_atomic(path, entry):
    """Tulis entri registry secara atomik: temp `.<pid>.json.tmp` di folder yang SAMA (tak
    pernah cocok `*.json`, jadi pembaca registry tak pernah melihat entri setengah jadi)
    lalu `os.replace`. OSError merambat ke pemanggil."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.parent / f".{OWNER_PID}.json.tmp"
    try:
        tmp.write_text(json.dumps(entry, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def job_register(job_id, *, module, layer, versions=""):
    """Aktifkan job untuk proses ini: label, nama, registry, penangkap SIGTERM.

    Registry `<tmp>/psm-jobs/<job>/<pid>.json` hidup selama proses hidup — --stop-job
    memakainya untuk menemukan PROSES job (container belum ada saat pull/bring-up).
    """
    _JOB["id"] = job_id
    entry = {"job": job_id, "pid": OWNER_PID, "run": RUN_ID, "host": OWNER_HOST,
             "boot": OWNER_BOOT, "ns": OWNER_NS, "script": Path(sys.argv[0]).name,
             "module": module, "layer": layer, "versions": versions,
             "started": datetime.now().isoformat(timespec="seconds"),
             "progress_file": str(_PROGRESS["path"]) if _PROGRESS["path"] else None}
    _JOB["entry"] = entry
    path = JOB_REGISTRY / job_id / f"{OWNER_PID}.json"
    try:
        _write_entry_atomic(path, entry)
        _JOB["entry_path"] = path
        atexit.register(_job_unregister)
    except OSError:
        _JOB["entry_path"] = None
    try:
        signal.signal(signal.SIGTERM, _on_sigterm)
    except (ValueError, OSError):
        pass  # bukan thread utama / platform tanpa SIGTERM — stop-job jatuh ke SIGKILL
    print(f"JOB {job_id}  (hentikan terarah: ps-flashlight-run.py --stop-job {job_id})",
          file=sys.stderr)


def job_update(**fields):
    """Tulis ulang entri registry MILIK proses ini dengan `fields` digabung (mis.
    `slot_claims` ps-run-layer), atomik seperti job_register. Return True bila tertulis;
    False bila job belum terdaftar atau tulis gagal (pemanggil memperingatkan, tak gagal)."""
    entry = _JOB.get("entry")
    if not _JOB.get("id") or entry is None:
        return False
    entry.update(fields)
    path = JOB_REGISTRY / _JOB["id"] / f"{OWNER_PID}.json"
    try:
        _write_entry_atomic(path, entry)
    except OSError:
        return False
    if _JOB.get("entry_path") is None:
        _JOB["entry_path"] = path
        atexit.register(_job_unregister)
    return True


def _registry_entries(job_id=None):
    """{job: [entry...]} dari registry lokal; file rusak dilewati."""
    out = {}
    dirs = [JOB_REGISTRY / job_id] if job_id else (
        sorted(JOB_REGISTRY.iterdir()) if JOB_REGISTRY.is_dir() else [])
    for d in dirs:
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.json")):
            try:
                e = json.loads(f.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if isinstance(e, dict):
                e["_file"] = str(f)
                out.setdefault(d.name, []).append(e)
    return out


def _proc_cmdline(pid):
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\0", b" ").decode(errors="replace")
    except OSError:
        return None


def entry_state(entry):
    """('alive'|'dead'|'foreign', alasan) untuk satu proses terdaftar.

    Hanya 'alive' yang boleh disinyal. PID baru bermakna bila host, boot, dan PID namespace
    sama dengan pemanggil; cmdline harus masih menyebut skripnya (PID daur-ulang = 'dead').
    """
    if entry.get("host") != OWNER_HOST:
        return "foreign", "foreign-host"
    if OWNER_BOOT and entry.get("boot") and entry.get("boot") != OWNER_BOOT:
        return "dead", "owner-boot-gone"
    if OWNER_NS and entry.get("ns") and entry.get("ns") != OWNER_NS:
        return "foreign", "foreign-pid-ns"
    pid = entry.get("pid")
    if not isinstance(pid, int) or pid <= 0:
        return "foreign", "bad-pid"
    if not _pid_alive(pid):
        return "dead", "pid-gone"
    cmd = _proc_cmdline(pid)
    if cmd is not None and entry.get("script") and entry["script"] not in cmd:
        return "dead", "pid-reused"
    return "alive", "alive"


def _job_artifacts(job_id):
    """({'container': [nama], 'network': [nama]}, error) — EKSAK per label psm.job."""
    found, errs = {"container": [], "network": []}, []
    for kind, base in (("container", ["docker", "ps", "-a"]), ("network", ["docker", "network", "ls"])):
        fmt = "{{.Names}}" if kind == "container" else "{{.Name}}"
        try:
            r = subprocess.run([*base, "--filter", f"label={LABEL_JOB}={job_id}", "--format", fmt],
                               capture_output=True, text=True, timeout=DOCKER_CMD_TIMEOUT)
        except (subprocess.SubprocessError, OSError) as e:
            errs.append(f"gagal melisting {kind}: {str(e)[-200:]}")
            continue
        if r.returncode != 0:
            errs.append(f"gagal melisting {kind}: {(r.stderr or '').strip()[-200:]}")
            continue
        found[kind] = [n.strip() for n in (r.stdout or "").splitlines() if n.strip()]
    return found, ("; ".join(errs) or None)


def _labelled_jobs():
    """Job yang punya container berlabel psm.job (termasuk yang prosesnya sudah tiada)."""
    try:
        r = subprocess.run(["docker", "ps", "-a", "--filter", f"label={LABEL_JOB}",
                            "--format", f'{{{{.Label "{LABEL_JOB}"}}}}'],
                           capture_output=True, text=True, timeout=DOCKER_CMD_TIMEOUT)
    except (subprocess.SubprocessError, OSError):
        return set()
    return {j.strip() for j in (r.stdout or "").splitlines() if valid_job_id(j.strip())}


def list_jobs():
    """Ringkas job psm di host ini: proses terdaftar (+status) dan container berlabel."""
    reg = _registry_entries()
    docker_ok = docker_available()
    jobs = sorted(set(reg) | (_labelled_jobs() if docker_ok else set()))
    out = {"mode": "list-jobs", "host": OWNER_HOST, "docker_available": docker_ok, "jobs": []}
    for job in jobs:
        procs = []
        for e in reg.get(job, []):
            state, reason = entry_state(e)
            procs.append({k: e.get(k) for k in ("pid", "script", "layer", "module", "versions",
                                                "started", "progress_file")}
                         | {"state": state, "reason": reason})
        arts = _job_artifacts(job)[0] if docker_ok else {"container": [], "network": []}
        out["jobs"].append({"job": job, "active": any(p["state"] == "alive" for p in procs),
                            "processes": procs, "containers": arts["container"],
                            "networks": arts["network"]})
    return out


def stop_job(job_id, grace=JOB_STOP_GRACE, poll=1.0):
    """Hentikan SATU job: SIGTERM ke prosesnya (bongkar sendiri), SIGKILL bila lewat tenggat,
    lalu hapus artefak berlabel psm.job=<job_id>. Job lain tak tersentuh — pencocokan eksak."""
    res = {"mode": "stop-job", "job": job_id, "signaled": [], "killed": [], "skipped": [],
           "removed": [], "errors": []}
    if not valid_job_id(job_id):
        res["status"] = "rejected"
        res["errors"].append(f"job id tak valid: {job_id!r} (bentuk <module>-<lapis>-<HHMM>-<hex>)")
        return res
    entries = _registry_entries(job_id).get(job_id, [])
    targets = []
    for e in entries:
        state, reason = entry_state(e)
        rec = {"pid": e.get("pid"), "script": e.get("script"), "reason": reason}
        if state != "alive":
            res["skipped"].append(rec)
            if state == "dead":
                try:
                    Path(e["_file"]).unlink(missing_ok=True)
                except OSError:
                    pass
            continue
        try:
            os.kill(e["pid"], signal.SIGTERM)
            res["signaled"].append(rec)
            targets.append(e)
        except ProcessLookupError:
            res["skipped"].append(rec | {"reason": "pid-gone"})
        except OSError as err:
            res["errors"].append(rec | {"error": str(err)})
    deadline = time.monotonic() + grace
    while targets and time.monotonic() < deadline:
        targets = [e for e in targets if entry_state(e)[0] == "alive"]
        if targets:
            time.sleep(poll)
    for e in targets:  # masih hidup sesudah tenggat — cek ulang identitas sebelum SIGKILL
        if entry_state(e)[0] == "alive":
            try:
                os.kill(e["pid"], signal.SIGKILL)
                res["killed"].append({"pid": e["pid"], "script": e.get("script")})
            except OSError:
                pass
    if targets:
        time.sleep(2)
    if docker_available():
        arts, err = _job_artifacts(job_id)
        if err:
            res["errors"].append({"error": err})
        for kind in ("container", "network"):  # container dulu: network tak lepas selama ditempeli
            for name in arts[kind]:
                status, rerr = _remove_artifact(kind, name)
                if status == "error":
                    res["errors"].append({"kind": kind, "name": name, "error": rerr})
                elif status == "removed":
                    res["removed"].append({"kind": kind, "name": name})
    try:
        (JOB_REGISTRY / job_id).rmdir()
    except OSError:
        pass
    if not (res["signaled"] or res["removed"] or res["killed"]):
        res["status"] = "not-found"
    else:
        res["status"] = "partial" if res["errors"] else "stopped"
    return res


def pull_image(image, timeout):
    """`docker pull` berlog kemajuan. Return pesan error, atau None bila sukses."""
    with phase("pull", timeout, image) as ph:
        try:
            p = subprocess.run(["docker", "pull", image], capture_output=True, text=True,
                               timeout=timeout)
        except subprocess.TimeoutExpired:
            ph.status = "timeout"
            return f"timeout pull {image}"
        if p.returncode != 0:
            ph.status = "gagal"
            return f"gagal pull {image}: {p.stderr.strip()[-300:]}"
    return None


def _health_status(container):
    """Status health container: 'healthy'|'unhealthy'|'starting'|'nohealth'|'gone'|'unknown'."""
    try:
        r = subprocess.run(
            ["docker", "inspect", "--format",
             "{{if .State.Health}}{{.State.Health.Status}}{{else}}nohealth{{end}}", container],
            capture_output=True, text=True, timeout=DOCKER_CMD_TIMEOUT)
    except subprocess.TimeoutExpired:
        return "unknown"  # daemon tersendat — poll berikutnya mencoba lagi sampai deadline
    if r.returncode != 0:
        return "gone"
    return (r.stdout or "").strip() or "unknown"


def wait_healthy(container, timeout, poll=3.0):
    """Poll status health sampai 'healthy' / 'unhealthy' / timeout. Return (ok, status)."""
    with phase("wait-healthy", timeout, container) as ph:
        deadline = time.monotonic() + timeout
        last = "unknown"
        while time.monotonic() < deadline:
            last = _health_status(container)
            ph.detail = f"{container} {last}"
            if last == "healthy":
                return True, "healthy"
            if last in ("unhealthy", "gone"):
                ph.status = last
                return False, last
            time.sleep(poll)
        ph.status = f"timeout({last})"
        return False, f"timeout ({last})"


def _logs(container):
    try:
        r = subprocess.run(["docker", "logs", container], capture_output=True, text=True,
                           timeout=DOCKER_CMD_TIMEOUT)
    except subprocess.TimeoutExpired:
        return "(docker logs timeout)"
    return (r.stdout or "") + (r.stderr or "")


def _compose_file_text(db_image, image_ref, ps_domain, module_dir, publish=None, *,
                       slot_cost=None):
    """docker-compose ephemeral: mariadb (healthcheck) + flashlight (depends_on healthy).

    `publish` (opsional, mis. '8000:80') memetakan port HTTP flashlight ke host —
    dipakai pemanggil yang perlu menjangkau PS dari luar container (mis. Lapis 4
    browser E2E lewat Playwright). Default None = tak ada port terpublish (perilaku
    lama; uji phpstan cukup lewat `docker exec`).

    `slot_cost` (keyword) = label `psm.slots=<n>` di service `ps:` SAJA (slot_labels) —
    diberi hanya oleh ps-e2e-run; DB, network dan Lapis 2/5 tak pernah dihitung.
    """
    return (
        "services:\n"
        "  db:\n"
        f"    image: {db_image}\n"
        + _compose_labels_yaml(4) +
        "    healthcheck:\n"
        '      test: ["CMD", "healthcheck.sh", "--connect"]\n'
        "      interval: 5s\n"
        "      timeout: 10s\n"
        "      retries: 20\n"
        "    environment:\n"
        f"      MYSQL_USER: {DB_USER}\n"
        f"      MYSQL_PASSWORD: {DB_PASSWORD}\n"
        f"      MYSQL_ROOT_PASSWORD: {DB_PASSWORD}\n"
        f"      MYSQL_DATABASE: {DB_NAME}\n"
        "  ps:\n"
        f"    image: {image_ref}\n"
        + _compose_labels_yaml(4, slot_labels(slot_cost)) +
        "    depends_on:\n"
        "      db:\n"
        "        condition: service_healthy\n"
        "    environment:\n"
        f"      PS_DOMAIN: {ps_domain}\n"
        "      MYSQL_HOST: db\n"
        '      MYSQL_PORT: "3306"\n'
        f"      MYSQL_USER: {DB_USER}\n"
        f"      MYSQL_PASSWORD: {DB_PASSWORD}\n"
        f"      MYSQL_DATABASE: {DB_NAME}\n"
        + (f'    ports:\n      - "{publish}"\n' if publish else "")
        + "    volumes:\n"
        f"      - {module_dir}:/ps-module-src:ro\n"
        # Network default compose diberi label yang sama: `docker compose down -v` memang
        # membereskannya di jalur normal, tapi run yang di-kill paksa meninggalkannya —
        # dan tanpa label, pembersih tak punya bukti untuk menghapusnya.
        + "networks:\n"
        "  default:\n"
        + _compose_labels_yaml(4)
    )


CONTAINER_PREFIX = "psm-fl"  # SATU prefix untuk KEDUA orkestrator — lihat _project_name

# Label kepemilikan — jawaban mesin untuk "run MANA yang memiliki artefak ini".
# Nama container hanya bisa menjawab "milik psm-validate" (prefix), TAK PERNAH "milik run ini":
# itu sebabnya perintah pembersih lama (`--filter name=psm-fl | xargs docker rm -f`) ikut
# membunuh run sesi lain yang sedang jalan. Tiga label ini yang membuat cleanup_orphans() bisa
# MEMBUKTIKAN kepemilikan sebelum menghapus — prefix cuma menyaring kandidat, label yang memvonis.
LABEL_RUN = "psm.run"                # id run, unik per proses
LABEL_OWNER_PID = "psm.owner-pid"    # PID proses pemilik — probe hidup/mati
LABEL_OWNER_HOST = "psm.owner-host"  # host penulis label; PID lokal tak bermakna lintas host
# PID hanya identitas bila DUA konteks ini sama. Hostname saja TIDAK membuktikannya:
# dua distro WSL2 memakai hostname Windows yang sama dan berbagi satu daemon Docker, tapi
# PID namespace-nya terpisah — PID 4242 yang hidup di distro A tak terlihat dari distro B,
# jadi run yang sedang jalan akan divonis "mati" dan dibunuh (kelas arch-9 yang sama, cuma
# lewat pintu lain). boot-id memisahkan sebelum/sesudah reboot: PID dari boot yang sudah
# lewat MUSTAHIL masih hidup, jadi artefaknya bisa direklaim alih-alih tersangkut selamanya
# karena PID-nya kebetulan didaur-ulang proses lain.
LABEL_OWNER_BOOT = "psm.owner-boot"  # boot-id kernel — beda boot = pemilik pasti sudah mati
LABEL_OWNER_NS = "psm.owner-ns"      # inode PID namespace — beda ns = PID tak bisa dinilai
# Biaya slot Lapis 4 (cell-contract.md > Config keys > psm_e2e_slots): HANYA di container PS
# yang di-boot ps-e2e-run (`--slot-cost`). Dijumlah lintas SELURUH daemon oleh ps-run-layer.
LABEL_SLOTS = "psm.slots"
CLEANUP_FLAG = "--cleanup-orphans"   # disulih ke argparse & dikunci gerbang prosa (lihat test)
RUN_ID = uuid.uuid4().hex[:12]
OWNER_PID = os.getpid()
OWNER_HOST = socket.gethostname()


def _read_boot_id():
    """boot-id kernel, atau None bila platform tak menyediakannya (mis. non-Linux)."""
    try:
        return pathlib.Path("/proc/sys/kernel/random/boot_id").read_text().strip() or None
    except OSError:
        return None


def _read_pid_ns():
    """Inode PID namespace proses ini, atau None bila tak terbaca."""
    try:
        return str(os.stat("/proc/self/ns/pid").st_ino)
    except OSError:
        return None


OWNER_BOOT = _read_boot_id()
OWNER_NS = _read_pid_ns()


def owner_labels():
    """Label kepemilikan run INI — satu sumber untuk kedua orkestrator.

    Compose dan manual WAJIB memakai fungsi ini, bukan menuliskan pasangan label sendiri:
    satu jalur yang tercecer = artefaknya tak bisa dibuktikan mati, lalu bocor selamanya
    (pembersih menolak menghapus apa yang tak berlabel — lihat cleanup_decision).
    """
    lab = {LABEL_RUN: RUN_ID, LABEL_OWNER_PID: str(OWNER_PID), LABEL_OWNER_HOST: OWNER_HOST}
    if _JOB["id"]:
        lab[LABEL_JOB] = _JOB["id"]  # target --stop-job; bukan syarat cleanup_decision
    # Hanya dicap bila platform ini bisa menghasilkannya — supaya syarat kelengkapan di
    # cleanup_decision menuntut persis yang bisa ditulis di sini, tak lebih.
    if OWNER_BOOT:
        lab[LABEL_OWNER_BOOT] = OWNER_BOOT
    if OWNER_NS:
        lab[LABEL_OWNER_NS] = OWNER_NS
    return lab


def slot_labels(slot_cost):
    """Label `psm.slots=<cost>` untuk container PS SAJA, TERPISAH dari owner_labels().

    Hanya proses yang menjalankan bring-up Lapis 4 (ps-e2e-run, `--slot-cost`, default 1)
    yang memberi cost; Lapis 2/5 memanggil tanpa cost -> {} (container mereka tak pernah
    dihitung). Hitungan slot sedaemon (daemon_slot_usage) menjumlah label ini.
    """
    if slot_cost is None:
        return {}
    return {LABEL_SLOTS: str(slot_cost)}


def _label_flags(extra=None):
    """owner_labels() (+ `extra`) sebagai argumen CLI docker (`--label k=v` berulang)."""
    flags = []
    for k, v in {**owner_labels(), **(extra or {})}.items():
        flags += ["--label", f"{k}={v}"]
    return flags


def _compose_labels_yaml(indent, extra=None):
    """owner_labels() (+ `extra`) sebagai blok `labels:` YAML pada indentasi tertentu."""
    pad = " " * indent
    out = f"{pad}labels:\n"
    for k, v in {**owner_labels(), **(extra or {})}.items():
        out += f"{pad}  {k}: {json.dumps(v)}\n"
    return out


def _project_name(full_ver):
    """Nama project compose — ber-prefix sama dgn jalur manual (CONTAINER_PREFIX).

    Dulu compose memakai `psmfl<ver><uid>` sementara jalur manual memakai `psm-fl-ps-<uid>`:
    dua konvensi untuk satu pertanyaan ("container mana milik skrip ini"). Akibatnya perintah
    pembersihan port-bocor `--filter name=psmfl` TIDAK cocok dgn container jalur manual —
    justru jalur yang dipakai saat `docker compose` absen, dan yang memegang port host. Satu
    prefix = satu filter (`--filter name=psm-fl`) menangkap keduanya.
    """
    v = re.sub(r"[^a-z0-9]", "", full_ver.lower())
    return f"{CONTAINER_PREFIX}-{_name_infix()}{v}-{uuid.uuid4().hex[:8]}"


def _bring_up_compose(module_dir, full_ver, image_ref, db_image, ps_domain, op_timeout, publish=None,
                      *, slot_cost=None):
    with phase("bring-up", op_timeout, "compose") as ph:
        session, err = _bring_up_compose_inner(module_dir, full_ver, image_ref, db_image,
                                               ps_domain, op_timeout, publish,
                                               slot_cost=slot_cost)
        if err:
            ph.status = "gagal"
        return session, err


def _bring_up_compose_inner(module_dir, full_ver, image_ref, db_image, ps_domain, op_timeout,
                            publish=None, *, slot_cost=None):
    proj = _project_name(full_ver)
    tmpdir = tempfile.mkdtemp(prefix="psm-fl-")
    compose_path = Path(tmpdir) / "docker-compose.yml"
    compose_path.write_text(_compose_file_text(db_image, image_ref, ps_domain, module_dir, publish,
                                               slot_cost=slot_cost),
                            encoding="utf-8")
    session = {"mode": "compose", "project": proj, "compose_file": str(compose_path),
               "tmpdir": tmpdir, "ps_container": None}
    try:
        up = subprocess.run(["docker", "compose", "-f", str(compose_path), "-p", proj, "up", "-d"],
                            capture_output=True, text=True, timeout=op_timeout)
    except subprocess.TimeoutExpired:
        return session, f"timeout docker compose up ({op_timeout}s) — daemon Docker tersendat?"
    if up.returncode != 0:
        return session, f"docker compose up gagal: {up.stderr.strip()[-300:]}"
    try:
        q = subprocess.run(["docker", "compose", "-f", str(compose_path), "-p", proj, "ps", "-q", "ps"],
                           capture_output=True, text=True, timeout=DOCKER_CMD_TIMEOUT)
    except subprocess.TimeoutExpired:
        return session, "timeout docker compose ps — daemon Docker tersendat?"
    cid = [c for c in (q.stdout or "").strip().splitlines() if c]
    if not cid:
        return session, "tak bisa resolve container flashlight dari compose"
    session["ps_container"] = cid[0]
    return session, None


def _bring_up_manual(module_dir, image_ref, db_image, ps_domain, startup_timeout, publish=None,
                     *, slot_cost=None):
    with phase("bring-up", None, "manual") as ph:
        try:
            session, err = _bring_up_manual_inner(module_dir, image_ref, db_image, ps_domain,
                                                  startup_timeout, publish, slot_cost=slot_cost)
        except subprocess.TimeoutExpired as e:
            # Sesi parsial (network/DB sudah dibuat) tetap dibongkar pemanggil lewat _teardown;
            # nama-namanya deterministik dari uid, jadi direkonstruksi di _MANUAL_PARTIAL.
            session = _MANUAL_PARTIAL.pop("session", None)
            err = f"timeout perintah docker ({' '.join(map(str, e.cmd[:3]))}) — daemon Docker tersendat?"
        if err:
            ph.status = "gagal"
        return session, err


_MANUAL_PARTIAL = {}


def _bring_up_manual_inner(module_dir, image_ref, db_image, ps_domain, startup_timeout, publish=None,
                           *, slot_cost=None):
    uid = uuid.uuid4().hex[:8]
    session = {"mode": "manual", "network": f"{CONTAINER_PREFIX}-{_name_infix()}net-{uid}",
               "db": f"{CONTAINER_PREFIX}-{_name_infix()}db-{uid}", "ps_container": f"{CONTAINER_PREFIX}-{_name_infix()}ps-{uid}"}
    _MANUAL_PARTIAL["session"] = session
    n = subprocess.run(["docker", "network", "create", *_label_flags(), session["network"]],
                       capture_output=True, text=True, timeout=DOCKER_CMD_TIMEOUT)
    if n.returncode != 0:
        return session, f"gagal buat network: {n.stderr.strip()[-200:]}"
    db = subprocess.run(
        ["docker", "run", "-d", "--name", session["db"], *_label_flags(),
         "--network", session["network"], "--network-alias", "db",
         "-e", f"MYSQL_USER={DB_USER}", "-e", f"MYSQL_PASSWORD={DB_PASSWORD}",
         "-e", f"MYSQL_ROOT_PASSWORD={DB_PASSWORD}", "-e", f"MYSQL_DATABASE={DB_NAME}",
         "--health-cmd", "healthcheck.sh --connect", "--health-interval", "5s",
         "--health-timeout", "10s", "--health-retries", "20", db_image],
        capture_output=True, text=True, timeout=DOCKER_CMD_TIMEOUT)
    if db.returncode != 0:
        return session, f"gagal start DB: {db.stderr.strip()[-200:]}"
    ok, status = wait_healthy(session["db"], startup_timeout)
    if not ok:
        return session, f"DB tak jadi healthy ({status})"
    ps = subprocess.run(
        ["docker", "run", "-d", "--name", session["ps_container"],
         *_label_flags(slot_labels(slot_cost)),
         "--network", session["network"],
         "-e", f"PS_DOMAIN={ps_domain}", "-e", "MYSQL_HOST=db", "-e", "MYSQL_PORT=3306",
         "-e", f"MYSQL_USER={DB_USER}", "-e", f"MYSQL_PASSWORD={DB_PASSWORD}",
         "-e", f"MYSQL_DATABASE={DB_NAME}",
         *(["-p", publish] if publish else []),
         "-v", f"{module_dir}:/ps-module-src:ro", image_ref],
        capture_output=True, text=True, timeout=DOCKER_CMD_TIMEOUT)
    _MANUAL_PARTIAL.pop("session", None)
    if ps.returncode != 0:
        return session, f"gagal start flashlight: {ps.stderr.strip()[-200:]}"
    return session, None


def _exec(session, env, inner, timeout):
    env_args = []
    for k, v in env.items():
        env_args += ["-e", f"{k}={v}"]
    if session["mode"] == "compose":
        cmd = ["docker", "compose", "-f", session["compose_file"], "-p", session["project"],
               "exec", "-T", *env_args, "ps", "sh", "-c", inner]
    else:
        cmd = ["docker", "exec", *env_args, session["ps_container"], "sh", "-c", inner]
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)


def _teardown_cmd(cmd, ph):
    """Satu perintah bongkar berbatas waktu. Timeout tak fatal: artefak berlabel milik run ini
    jadi yatim setelah proses keluar, dan `--cleanup-orphans` yang membereskannya."""
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=DOCKER_CMD_TIMEOUT)
    except subprocess.TimeoutExpired:
        ph.status = "timeout(sisa-artefak: jalankan --cleanup-orphans)"


def _teardown(session):
    if not session:
        return
    with phase("teardown", None, session.get("mode", "")) as ph:
        if session.get("mode") == "compose":
            if session.get("compose_file"):
                _teardown_cmd(["docker", "compose", "-f", session["compose_file"],
                               "-p", session["project"], "down", "-v"], ph)
            if session.get("tmpdir"):
                shutil.rmtree(session["tmpdir"], ignore_errors=True)
        else:
            for c in (session.get("ps_container"), session.get("db")):
                if c:
                    _teardown_cmd(["docker", "rm", "-f", c], ph)
            if session.get("network"):
                _teardown_cmd(["docker", "network", "rm", session["network"]], ph)


def _pid_alive(pid):
    """True bila proses `pid` masih hidup di host ini.

    Ketidakpastian dibaca sebagai HIDUP: probe yang tak bisa memutuskan (izin, OSError)
    membuat pembersih melewati artefak itu. Arah gagalnya sengaja: PID daur-ulang cuma
    menyisakan sampah, sedangkan menebak "mati" berarti membunuh run yang sedang jalan.
    """
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except (PermissionError, OSError, OverflowError, ValueError):
        # OverflowError (PID di luar jangkauan C) BUKAN OSError: tanpa disebut di sini ia
        # menembus pemanggil & mematikan seluruh sweep di tengah jalan — sesudah sebagian
        # artefak terlanjur dihapus tapi belum dilaporkan.
        return True


def cleanup_decision(labels):
    """(hapus?, alasan) untuk satu artefak — SATU tempat aturan kepemilikan hidup.

    Default TOLAK: hanya `owner-dead` yang menghapus. Tiap alasan lain adalah kalimat jujur
    tentang APA yang tak bisa dibuktikan, bukan kegagalan.
    """
    if not labels.get(LABEL_RUN):
        return False, "no-owner-label"
    if labels.get(LABEL_OWNER_HOST) != OWNER_HOST:
        return False, "foreign-host"      # PID di label tak bermakna di host ini
    # Konteks PID diperiksa SEBELUM PID-nya sendiri: angka yang sama menunjuk proses berbeda
    # di boot lain / namespace lain. Syaratnya dituntut hanya untuk konteks yang platform ini
    # sendiri bisa tulis (lihat owner_labels), jadi artefak kita sendiri tak pernah tersangkut.
    if OWNER_BOOT:
        boot = labels.get(LABEL_OWNER_BOOT)
        if not boot:
            return False, "incomplete-owner-labels"
        if boot != OWNER_BOOT:
            # Mesin sudah reboot sejak artefak dibuat: pemiliknya MUSTAHIL masih hidup, dan
            # PID-nya kini bisa saja dipakai proses lain — membacanya "hidup" justru salah.
            return True, "owner-boot-gone"
    if OWNER_NS:
        ns = labels.get(LABEL_OWNER_NS)
        if not ns:
            return False, "incomplete-owner-labels"
        if ns != OWNER_NS:
            return False, "foreign-pid-ns"   # PID namespace lain — liveness tak terbaca dari sini
    raw = labels.get(LABEL_OWNER_PID) or ""
    # isdecimal, bukan isdigit: "²".isdigit() True tapi int("²") melempar ValueError — fungsi
    # yang tugasnya MENGKLASIFIKASI label rusak justru mati oleh salah satunya. pid <= 0 juga
    # ditolak: os.kill(0, 0) menyasar process group PEMANGGIL dan selalu sukses, jadi "0" akan
    # dibaca owner-alive selamanya dengan alasan yang bohong.
    if not raw.isdecimal() or int(raw) <= 0:
        return False, "bad-owner-pid"
    if _pid_alive(int(raw)):
        return False, "owner-alive"       # run sesi lain (atau run ini sendiri) masih jalan
    return True, "owner-dead"


OWNER_LABEL_KEYS = (LABEL_RUN, LABEL_OWNER_PID, LABEL_OWNER_HOST, LABEL_OWNER_BOOT,
                    LABEL_OWNER_NS)


def _list_artifacts(kind):
    """([{name, labels}], error) artefak psm-fl — container atau network.

    Prefix nama hanya MENYARING kandidat (batasi ke wilayah psm-validate); yang memvonis
    hapus/lewati tetap label lewat cleanup_decision. Artefak lama tanpa label ikut terjaring
    justru supaya bisa dilaporkan, bukan supaya bisa dihapus.

    Label diambil per-key lewat `{{.Label "k"}}`, BUKAN dengan mem-parse `{{.Labels}}` yang
    menggabungkan semua label (termasuk warisan image) jadi satu string dipisah koma: nilai
    yang memuat koma di sana memecah diri jadi pasangan palsu, dan pasangan palsu bernama
    `psm.*` berarti kepemilikan bisa dikarang.
    """
    name_field = "{{.Names}}" if kind == "container" else "{{.Name}}"
    fmt = "\t".join([name_field] + [f'{{{{.Label "{k}"}}}}' for k in OWNER_LABEL_KEYS])
    if kind == "container":
        cmd = ["docker", "ps", "-a", "--filter", f"name={CONTAINER_PREFIX}", "--format", fmt]
    else:
        cmd = ["docker", "network", "ls", "--filter", f"name={CONTAINER_PREFIX}", "--format", fmt]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
    except (subprocess.SubprocessError, OSError) as e:
        return [], f"gagal melisting {kind}: {str(e)[-200:]}"
    if r.returncode != 0:
        return [], f"gagal melisting {kind}: {(r.stderr or '').strip()[-200:]}"
    items = []
    for line in (r.stdout or "").splitlines():
        if not line.strip():
            continue
        parts = line.split("\t")
        name = parts[0].strip()
        # `--filter name=` docker adalah pencocokan SUBSTRING: container pihak ketiga bernama
        # `my-psm-fl-notes` ikut terjaring. Ia takkan pernah dihapus (tak berlabel), tapi tanpa
        # saringan ini ia muncul di laporan lengkap dengan saran `docker rm -f` — laporan yang
        # menganjurkan menghapus milik orang lain.
        if not name.startswith(CONTAINER_PREFIX + "-"):
            continue
        labels = {k: v.strip() for k, v in zip(OWNER_LABEL_KEYS, parts[1:]) if v.strip()}
        items.append({"name": name, "labels": labels})
    return items, None


def _rm_command(kind, name):
    # `-v` mencerminkan `compose down -v` di jalur teardown normal: container DB membawa
    # volume anonim dari image-nya, dan tanpa ini tiap orphan meninggalkan volume ratusan MB
    # yang tak berlabel, tak terlihat di `docker ps`, dan tak bisa direklaim pembersih ini lagi.
    return (["docker", "rm", "-f", "-v", name] if kind == "container"
            else ["docker", "network", "rm", name])


def _remove_artifact(kind, name):
    """(status, error): 'removed' | 'already-gone' | 'error'."""
    try:
        r = subprocess.run(_rm_command(kind, name), capture_output=True, text=True, timeout=60)
    except (subprocess.SubprocessError, OSError) as e:
        return "error", str(e)[-200:]
    if r.returncode == 0:
        return "removed", None
    err = (r.stderr or "").strip()
    # Balapan normal, bukan kegagalan: run pemilik membongkar sendiri antara kita melisting
    # dan menghapus. Tanpa cabang ini ia mendarat di `errors` dan membuat run sehat tampak rusak.
    if "no such" in err.lower():
        return "already-gone", None
    return "error", err[-200:] or "gagal menghapus"


def cleanup_orphans():
    """Hapus HANYA jejak run yang terbukti mati di host ini; laporkan sisanya + alasannya.

    Pengganti perintah sapuan berbasis prefix yang dulu didokumentasikan: sapuan itu
    menghapus atas dasar NAMA, jadi ia ikut membunuh Lapis 2/4 sesi lain yang sedang jalan.
    Container dulu, baru network — network tak bisa dilepas selama masih ada yang menempel.
    """
    result = {"mode": "cleanup-orphans", "host": OWNER_HOST,
              "removed": [], "skipped": [], "errors": []}
    if not docker_available():
        result["status"] = "skipped"
        result["reason"] = "Docker tidak tersedia — tak ada yang bisa dibersihkan."
        return result
    result["status"] = "ran"
    for kind in ("container", "network"):
        items, err = _list_artifacts(kind)
        if err:
            result["errors"].append({"kind": kind, "error": err})
            continue
        for art in items:
            entry = {"kind": kind, "name": art["name"]}
            run = art["labels"].get(LABEL_RUN)
            if run:
                entry["run"] = run
            # Satu record aneh tak boleh membatalkan sisa sweep: tanpa penjaga ini, artefak
            # yang sudah terhapus tak pernah dilaporkan dan network tak pernah diproses.
            try:
                remove, reason = cleanup_decision(art["labels"])
            except Exception as e:  # noqa: BLE001 — label dari luar, apa pun bisa masuk
                entry["reason"] = "undecidable"
                entry["error"] = f"{type(e).__name__}: {str(e)[-120:]}"
                result["errors"].append(entry)
                continue
            entry["reason"] = reason
            if not remove:
                # Alasan yang butuh keputusan MANUSIA diberi perintah persisnya supaya operator
                # tak buntu. `owner-alive` sengaja TIDAK: menyodorkan perintah bunuh untuk run
                # yang sedang jalan adalah persis tindakan yang mode ini ada untuk mencegah.
                if reason != "owner-alive":
                    entry["manual_command"] = " ".join(_rm_command(kind, art["name"]))
                result["skipped"].append(entry)
                continue
            status, rerr = _remove_artifact(kind, art["name"])
            if status == "error":
                entry["error"] = rerr
                result["errors"].append(entry)
            elif status == "already-gone":
                entry["reason"] = "already-gone"   # pemilik membongkar sendiri saat kita jalan
                result["skipped"].append(entry)
            else:
                result["removed"].append(entry)
    if result["errors"]:
        # Exit tetap 0 (artefak yang tak terbukti mati BUKAN kegagalan — kontrak yang disetujui),
        # tapi konsumen mesin harus bisa membedakan "bersih" dari "ada yang tak tergarap".
        result["status"] = "partial"
    return result


def slot_cost_value(raw):
    """Biaya slot yang sah (int >= 1) dari label/klaim, else None (dihitung 1, tampil `=?`)."""
    if isinstance(raw, bool):
        return None
    if isinstance(raw, int):
        return raw if raw >= 1 else None
    if isinstance(raw, str) and re.fullmatch(r"[0-9]+", raw.strip()):  # ASCII saja
        n = int(raw.strip())
        return n if n >= 1 else None
    return None


def daemon_slot_usage():
    """Jumlah `psm.slots` atas SEMUA container yang JALAN di daemon (satu `docker ps`).

    Return (used, counted, error): `counted` = [{job, host, run, cost}] per container
    berlabel (`cost` None bila label bukan int >= 1 — dihitung 1); `used` = jumlahnya.
    `error` None, atau ekor kegagalan (stderr; teks exception pada timeout/OSError) — maka
    used None & counted [] (pemanggil membacanya "cap penuh"). Container tanpa label tak
    dihitung (skrip lama); yatim berlabel TETAP dihitung sampai dibersihkan.
    """
    fmt = "\t".join(f'{{{{.Label "{k}"}}}}' for k in (LABEL_SLOTS, LABEL_JOB, LABEL_OWNER_HOST,
                                                     LABEL_RUN))
    try:
        r = subprocess.run(["docker", "ps", "--filter", f"label={LABEL_SLOTS}", "--format", fmt],
                           capture_output=True, text=True, timeout=DOCKER_CMD_TIMEOUT)
    except (subprocess.SubprocessError, OSError) as e:
        return None, [], str(e) or type(e).__name__
    if r.returncode != 0:
        return None, [], (r.stderr or "").strip() or f"docker ps exit {r.returncode}"
    counted = []
    for line in (r.stdout or "").splitlines():
        if not line.strip():
            continue
        parts = (line.split("\t") + ["", "", "", ""])[:4]
        cost = slot_cost_value(parts[0])
        counted.append({"job": parts[1].strip() or None, "host": parts[2].strip() or None,
                        "run": parts[3].strip() or None, "cost": cost})
    return sum(c["cost"] or 1 for c in counted), counted, None


def run_one_version(module_dir, mod_name, full_ver, tag, *, orchestrator, db_image,
                    ps_domain, startup_timeout, op_timeout, allow_pull):
    """Bangun DB+flashlight untuk satu versi, install module, jalankan phpstan.

    Kegagalan infrastruktur (image absen tanpa izin pull, compose/DB/boot gagal,
    timeout) → degrade jujur lewat `errors`/`skipped_image` (tak konklusif, tak
    memblok). Install ditolak / phpstan-error (neon module) → sinyal konklusif.
    """
    image_ref = f"{IMAGE}:{tag}"
    progress_version(full_ver)
    res = {"version": full_ver, "tag": tag, "image": image_ref, "orchestrator": None,
           "db_image": db_image, "install": None, "coding_standard": None,
           "errors": [], "pass": False}

    mode = orchestrator
    if mode == "auto":
        mode = "compose" if compose_available() else "manual"
    elif mode == "compose" and not compose_available():
        res["errors"].append("orchestrator=compose diminta tapi 'docker compose' tak tersedia")
        return res
    res["orchestrator"] = mode

    # Gerbang unduh image (flashlight multi-GB + DB) — degrade jujur bila tak diizinkan.
    missing = [i for i in (image_ref, db_image) if not image_present(i)]
    if missing:
        if not allow_pull:
            res["skipped_image"] = True
            res["errors"].append(
                f"image belum ada lokal & pull tak diizinkan: {', '.join(missing)} — lewati versi ini")
            return res
        for i in missing:
            perr = pull_image(i, op_timeout)
            if perr:
                res["errors"].append(perr)
                return res

    if mode == "compose":
        session, err = _bring_up_compose(module_dir, full_ver, image_ref, db_image, ps_domain, op_timeout)
    else:
        session, err = _bring_up_manual(module_dir, image_ref, db_image, ps_domain, startup_timeout)
    if err:
        res["errors"].append(err)
        _teardown(session)
        return res

    try:
        ok, status = wait_healthy(session["ps_container"], startup_timeout)
        if not ok:
            res["errors"].append(
                f"flashlight tak jadi 'healthy' ({status}) — DB/boot gagal, degrade jujur")
            res["boot_log"] = _logs(session["ps_container"])[-2000:]
            return res
        try:
            with phase("install+phpstan", op_timeout):
                cp = _exec(session, {"MOD_NAME": mod_name}, INNER_SH, op_timeout)
        except subprocess.TimeoutExpired:
            res["errors"].append(f"timeout menjalankan uji di container ({image_ref})")
            return res
        out = (cp.stdout or "") + (cp.stderr or "")
        inst = parse_install(out)
        if inst.get("copy_fail"):
            res["errors"].append("gagal menyalin module ke dalam container")
            return res
        res["install"] = {"ok": inst["ok"], "no_console": inst.get("no_console", False),
                          "no_psroot": inst.get("no_psroot", False),
                          "no_verdict": inst.get("no_verdict", False),
                          "log": out.split(PHPSTAN_SENTINEL_PREFIX, 1)[0][-2000:]}
        res["coding_standard"] = parse_phpstan(out)
        cs = res["coding_standard"]
        res["pass"] = bool(res["install"]["ok"]) and \
            (not cs.get("available") or cs.get("parse_ok") is False or cs.get("errors", 0) == 0)
        return res
    finally:
        _teardown(session)


# Peta key config resolved -> dest argparse. Satu definisi, dipakai ketiga skrip yang
# menerima setelan keluarga (flashlight, e2e, plan).
CONFIG_KEY_TO_DEST = {
    "psm_target_versions": "versions",
    "psm_flashlight_tag_map": "tag_map",
    "psm_flashlight_orchestrator": "orchestrator",
    "psm_flashlight_db_image": "db_image",
    "psm_flashlight_ps_domain": "ps_domain",
    "psm_flashlight_startup_timeout": "startup_timeout",
    "psm_e2e_browsers": "browsers",
}

# --- Sel terkonfigurasi (cell-contract.md > Configured cells) ---------------------
# Himpunan sel WAJIB untuk `ready` = psm_target_versions x psm_e2e_browsers, dibaca LANGSUNG
# dari JSON --config (bukan lewat apply_config_file: flag --versions/--browsers cuma
# membentuk apa yang dijalankan, tak pernah menyusutkan himpunan wajib). Satu normalizer,
# dipakai plan, runner dan agregat. Default skrip dikunci ke PSM_DEFAULTS resolver lewat
# test drift; literal argparse lama & DEFAULT_BROWSERS ps-e2e-run tetap ada.
SUPPORTED_ENGINES = ("chromium", "firefox", "webkit")
DEFAULT_TARGET_VERSIONS = "1.7.8,8.1,9.1"
DEFAULT_E2E_BROWSERS = "chromium,firefox"
_VERSION_RE = re.compile(r"^[0-9]+(\.[0-9]+)*$")  # ASCII saja: \d menerima digit Unicode


class CellConfigError(ValueError):
    """Input himpunan sel tak sah — pemanggil CLI mencetak pesannya dan exit 2."""


def version_key(ver):
    """Kunci urut NUMERIK versi bertitik: '10.0' > '9.1' (bukan leksikal).

    Nol di ekor dibuang, jadi dua versi yang setara numerik ('9.1', '9.1.0') berkunci sama —
    normalizer menolak pasangan seperti itu.
    """
    parts = [int(p) for p in str(ver).split(".")]
    while len(parts) > 1 and parts[-1] == 0:
        parts.pop()
    return tuple(parts)


def _config_items(raw, default, key):
    """String koma (bentuk tulisan resolver) atau list string -> item ter-strip, tanpa kosong.

    None -> default skrip. Tipe lain / item non-string -> CellConfigError.
    """
    if raw is None:
        raw = default
    if isinstance(raw, str):
        items = raw.split(",")
    elif isinstance(raw, list):
        if not all(isinstance(x, str) for x in raw):
            raise CellConfigError(f"{key}: tiap item harus string, dapat {raw!r}")
        items = raw
    else:
        raise CellConfigError(f"{key}: harus string dipisah koma atau list string, dapat {raw!r}")
    return [x.strip() for x in items if x.strip()]


def normalize_versions(raw, key="psm_target_versions"):
    """Versi terkonfigurasi -> list string unik, URUT NUMERIK. Error -> CellConfigError.

    Duplikat persis dibuang; list kosong, versi bukan digit-bertitik (`\\d+(\\.\\d+)*`), atau
    dua versi setara numerik ('9.1' & '9.1.0') adalah input error. String versi dipakai apa
    adanya (nama file histori memakai string terkonfigurasi).
    """
    out = []
    for v in _config_items(raw, DEFAULT_TARGET_VERSIONS, key):
        if not _VERSION_RE.match(v):
            raise CellConfigError(f"{key}: versi {v!r} bukan digit bertitik (mis. 9.1, 1.7.8)")
        if v not in out:
            out.append(v)
    if not out:
        raise CellConfigError(f"{key}: daftar versi kosong")
    seen = {}
    for v in out:
        k = version_key(v)
        if k in seen:
            raise CellConfigError(f"{key}: {seen[k]!r} dan {v!r} setara numerik — sebut satu saja")
        seen[k] = v
    return sorted(out, key=version_key)


def normalize_engines(raw, key="psm_e2e_browsers"):
    """Engine terkonfigurasi -> list unik, urutan tertulis, huruf kecil. Error -> CellConfigError.

    Engine di luar SUPPORTED_ENGINES atau list kosong adalah input error — menggantikan
    fallback diam-diam parse_browsers ke default.
    """
    out = []
    for b in _config_items(raw, DEFAULT_E2E_BROWSERS, key):
        b = b.lower()
        if b not in SUPPORTED_ENGINES:
            raise CellConfigError(f"{key}: engine {b!r} tak didukung "
                                  f"(didukung: {','.join(SUPPORTED_ENGINES)})")
        if b not in out:
            out.append(b)
    if not out:
        raise CellConfigError(f"{key}: daftar browser kosong")
    return out


def read_config_json(path):
    """Baca JSON --config sebagai dict. Tak terbaca / bukan objek JSON -> CellConfigError."""
    try:
        cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as e:
        raise CellConfigError(f"gagal baca --config {path}: {e}") from None
    if not isinstance(cfg, dict):
        raise CellConfigError(f"--config {path} bukan objek JSON")
    return cfg


CONFIG_BASENAME = "psm-config.json"  # config resolved yang ditulis orkestrator di psm_reports_dir


def require_config(config_path, reports_dir):
    """Tolak run tanpa --config bila `<reports>/psm-config.json` ADA. Error -> CellConfigError.

    Tanpa --config himpunan sel wajib jatuh ke default skrip; proyek yang menargetkan versi lain
    (mis. menambah 1.7.6) lalu lupa --config akan mendapat `ready` atas himpunan yang lebih sempit
    tanpa satu pun error — penyempitan diam-diam yang dilarang hukum kejujuran. Bila file config
    resolved ada di folder laporan, pemanggil jelas punya config: wajibkan ia diteruskan.
    Tanpa folder laporan / tanpa file itu -> default skrip tetap sah (runner tanpa resolver).
    """
    if config_path or not reports_dir:
        return
    cand = Path(reports_dir) / CONFIG_BASENAME
    if cand.is_file():
        raise CellConfigError(
            f"--config tak diberikan padahal {cand} ada — tanpa --config himpunan sel wajib jatuh "
            f"ke default skrip ({DEFAULT_TARGET_VERSIONS} × {DEFAULT_E2E_BROWSERS}) dan bisa "
            f"menyempit diam-diam; ulangi dengan --config {cand}")


def configured_cells(config_path=None):
    """Himpunan sel terkonfigurasi -> (versions, browsers). Error -> CellConfigError (exit 2).

    Dibaca LANGSUNG dari JSON --config: key absen atau null -> default skrip
    (DEFAULT_TARGET_VERSIONS / DEFAULT_E2E_BROWSERS); tanpa config -> keduanya default.
    `versions` urut numerik, `browsers` urut tertulis. Canary: configured_canary.
    """
    cfg = read_config_json(config_path) if config_path else {}
    return (normalize_versions(cfg.get("psm_target_versions")),
            normalize_engines(cfg.get("psm_e2e_browsers")))


# --- Canary (cell-contract.md > Config keys > psm_e2e_canary) ----------------------
# SATU normalizer canary, dipakai plan, runner dan agregat (lewat `fl` / `pl.fl`). Dinilai
# atas himpunan sel terkonfigurasi, apa pun psm_e2e_enabled — canary salah bentuk = exit 2.
CANARY_KEY = "psm_e2e_canary"


def normalize_canary(raw, versions, browsers, key=CANARY_KEY):
    """Nilai psm_e2e_canary -> `"<versi>:<browser>"` ternormalisasi. Error -> CellConfigError.

    `versions`/`browsers` = himpunan TERKONFIGURASI yang sudah dinormalisasi
    (normalize_versions / normalize_engines). Aturan (spec CAP-1 > Design Notes > Canary):
      - ada & bukan null tapi bukan string -> error;
      - di-strip; absen/null/kosong -> versi terbaru (numerik) x `chromium`, atau browser
        terkonfigurasi PERTAMA bila chromium tak dikonfigurasi;
      - selain itu harus terbelah TEPAT di satu `:` jadi versi ter-strip yang SAMA PERSIS dgn
        string versi terkonfigurasi, dan browser ter-strip + huruf kecil (seperti
        normalize_engines) yang ada di himpunan browser terkonfigurasi.
    Pesan error selalu menyebut key-nya.
    """
    if raw is not None and not isinstance(raw, str):
        raise CellConfigError(f"{key}: harus string <versi>:<browser>, dapat {raw!r}")
    text = (raw or "").strip()
    if not text:
        newest = max(versions, key=version_key)
        browser = "chromium" if "chromium" in browsers else browsers[0]
        return f"{newest}:{browser}"
    parts = text.split(":")
    if len(parts) != 2:
        raise CellConfigError(f"{key}: {raw!r} harus berbentuk <versi>:<browser> "
                              "(tepat satu ':'), mis. 9.1:chromium")
    ver, browser = parts[0].strip(), parts[1].strip().lower()
    if ver not in versions:
        raise CellConfigError(f"{key}: versi {ver!r} bukan versi terkonfigurasi — harus PERSIS "
                              f"salah satu dari: {', '.join(versions)}")
    if browser not in browsers:
        raise CellConfigError(f"{key}: browser {browser!r} bukan browser terkonfigurasi "
                              f"(psm_e2e_browsers: {', '.join(browsers)})")
    return f"{ver}:{browser}"


def configured_canary(config_path=None, versions=None, browsers=None):
    """Canary dari JSON --config -> `"<versi>:<browser>"`. Error -> CellConfigError (exit 2).

    Tanpa config -> canary default atas himpunan default. `versions`/`browsers` (hasil
    configured_cells) boleh diberikan supaya tak dinormalisasi ulang; absen -> dibaca dari
    config yang sama.
    """
    cfg = read_config_json(config_path) if config_path else {}
    if versions is None or browsers is None:
        versions = normalize_versions(cfg.get("psm_target_versions"))
        browsers = normalize_engines(cfg.get("psm_e2e_browsers"))
    return normalize_canary(cfg.get(CANARY_KEY), versions, browsers)


def job_start(args, module, layer):
    """Validasi/buat --job-id lalu daftarkan job. False = ID tak valid (pemanggil exit 2)."""
    job_id = args.job_id or make_job_id(module, layer)
    if not valid_job_id(job_id):
        print(f"error: --job-id tak valid: {job_id!r} — huruf kecil/angka/'-', 3-63 karakter",
              file=sys.stderr)
        return False
    job_register(job_id, module=module, layer=layer, versions=getattr(args, "versions", ""))
    return True


def add_progress_args(ap):
    """Flag log kemajuan — satu definisi untuk ketiga skrip lapis Docker."""
    ap.add_argument("--progress-file",
                    help="Tulis log kemajuan bertimestamp ke file ini (START/ALIVE/SLOW/END/DONE; "
                         "format di komentar 'log kemajuan' skrip ini). ps-run-layer.py mengisinya "
                         "otomatis: <reports>/<module>-<lapis>-<versi>.progress.log")
    ap.add_argument("--job-id",
                    help="ID job yang terlihat (label psm.job, nama container, log kemajuan). "
                         "Default dibuat: <module>-<lapis>-<HHMM>-<hex>; ps-run-layer mengisinya "
                         "sama untuk semua versi. Hentikan terarah: ps-flashlight-run.py --stop-job <id>")
    ap.add_argument("--slow-after", type=int, default=None,
                    help=f"Detik sebelum fase ditandai SLOW (default {PROGRESS_SLOW_AFTER}; "
                         f"pull {PROGRESS_SLOW_AFTER_PHASE['pull']})")


def apply_config_file(args, parser, path):
    """Isi argumen yang TAK diberikan eksplisit dari JSON resolve-psm-config.py.

    Kenapa ada: langkah 1 SKILL.md sudah memuat config resolved, lalu tiap panggilan hilir
    menyatakannya ulang dengan tangan (`--tag-map` dari psm_flashlight_tag_map, `--db-image`,
    `--ps-domain`, `--orchestrator`, `--startup-timeout`). Menyalin key resolved ke flag adalah
    transform dengan satu jawaban benar, dan alur per-versi memanggil skrip lapis O(lapis x
    versi) kali — tiap pengulangan satu kesempatan menjatuhkan `--tag-map`, yang membuat plan
    salah menilai provenance dan bukti dari image lain terbaca segar.

    Flag eksplisit SELALU menang: hanya dest yang masih bernilai default parser yang diisi,
    jadi `--config` tak pernah menimpa niat pemanggil. Key tak dikenal diabaikan diam-diam —
    resolver boleh menambah key baru tanpa memecah skrip lama.
    """
    try:
        cfg = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        print(f"error: gagal baca --config {path}: {e}", file=sys.stderr)
        sys.exit(2)
    if not isinstance(cfg, dict):
        print(f"error: --config {path} bukan objek JSON", file=sys.stderr)
        sys.exit(2)
    for key, dest in CONFIG_KEY_TO_DEST.items():
        if key not in cfg or not hasattr(args, dest):
            continue
        if getattr(args, dest) != parser.get_default(dest):
            continue  # flag eksplisit menang
        val = cfg[key]
        if val is None:
            continue
        cur = parser.get_default(dest)
        if isinstance(cur, int) and not isinstance(cur, bool):
            try:
                val = int(val)
            except (TypeError, ValueError):
                print(f"error: --config: {key}={cfg[key]!r} bukan bilangan", file=sys.stderr)
                sys.exit(2)
        setattr(args, dest, val)
    return args


def main():
    ap = argparse.ArgumentParser(
        description="Validasi module PrestaShop di Docker flashlight (DB-backed), per versi.",
        epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("module_path", nargs="?", help="Path folder module PrestaShop "
                                                   f"(tak dipakai dengan {CLEANUP_FLAG})")
    ap.add_argument("--versions", default="1.7.8,8.1,9.1", help="Versi target dipisah koma")
    ap.add_argument("--config", help="JSON hasil resolve-psm-config.py — setelan keluarga (tag map, image DB, ps-domain, orchestrator, timeout, versi, browser) diisi dari sini untuk argumen yang tak diberikan eksplisit. Flag eksplisit selalu menang.")
    ap.add_argument("--tag-map", default="", help="Peta LENGKAP versi=tag dipisah koma (MENGGANTI default), "
                                                  "mis. '1.7.8=1.7.8.11,8.1=8.1.6-nginx,9.1=9.1.4-nginx'")
    ap.add_argument("--extra-tag-map", default="", help="Tag TAMBAHAN versi=tag (MENAMBAH di atas peta), "
                                                        "mis. '9.2=9.2.0-nginx' — versi lain tak terpengaruh")
    ap.add_argument("--orchestrator", choices=["auto", "compose", "manual"], default=DEFAULT_ORCHESTRATOR,
                    help="Cara menghidupkan DB+flashlight (default: auto = compose bila ada, else manual)")
    ap.add_argument("--db-image", default=DEFAULT_DB_IMAGE, help=f"Image server DB (default: {DEFAULT_DB_IMAGE})")
    ap.add_argument("--ps-domain", default=DEFAULT_PS_DOMAIN, help=f"PS_DOMAIN flashlight (default: {DEFAULT_PS_DOMAIN})")
    ap.add_argument("--startup-timeout", type=int, default=DEFAULT_STARTUP_TIMEOUT,
                    help=f"Maks detik menunggu container healthy (default: {DEFAULT_STARTUP_TIMEOUT})")
    ap.add_argument("--allow-image-pull", action="store_true",
                    help="Izinkan unduh image bila belum ada lokal (default: lewati versi itu, degrade jujur). "
                         "Wajib utk pemanggil non-interaktif yang memang mau menarik image.")
    ap.add_argument("--timeout", type=int, default=600, help="Timeout operasi per versi (detik): pull/up/exec")
    ap.add_argument(CLEANUP_FLAG, action="store_true",
                    help="Bersihkan container/network yatim sisa run yang di-kill paksa, lalu keluar. "
                         "HANYA menghapus yang proses pemiliknya sudah mati di host ini "
                         f"(label {LABEL_OWNER_PID}); run sesi lain yang masih jalan dilewati, "
                         "bukan dibunuh. Eksklusif: tanpa module_path, tanpa -o (laporan ke stdout).")
    ap.add_argument("--list-jobs", action="store_true",
                    help="Tampilkan job psm di host ini (proses terdaftar + container berlabel psm.job), "
                         "lalu keluar. Eksklusif.")
    ap.add_argument("--stop-job", metavar="JOB_ID",
                    help="Hentikan SATU job secara terarah: SIGTERM ke prosesnya (bongkar sendiri), "
                         f"SIGKILL bila lewat {JOB_STOP_GRACE} dtk, lalu hapus container/network "
                         "berlabel psm.job=<JOB_ID>. Job lain tak tersentuh. Eksklusif.")
    ap.add_argument("-o", "--output", help="File output JSON (default: stdout)")
    add_progress_args(ap)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    if args.config:
        apply_config_file(args, ap, args.config)

    exclusive = [f for f, on in ((CLEANUP_FLAG, args.cleanup_orphans), ("--list-jobs", args.list_jobs),
                                 ("--stop-job", args.stop_job)) if on]
    if len(exclusive) > 1:
        print(f"error: {', '.join(exclusive)} saling eksklusif", file=sys.stderr)
        return 2
    if args.list_jobs or args.stop_job:
        if args.module_path or args.output:
            print(f"error: {exclusive[0]} tak menerima module_path maupun -o/--output", file=sys.stderr)
            return 2
        if args.list_jobs:
            print(json.dumps(list_jobs(), indent=2, ensure_ascii=False))
            return 0
        r = stop_job(args.stop_job)
        print(json.dumps(r, indent=2, ensure_ascii=False))
        return 2 if r["status"] == "rejected" else 0

    if args.cleanup_orphans:
        # Mode ini eksklusif. Digabung dgn module_path, validasi diam-diam TAK PERNAH jalan
        # padahal exit 0; digabung dgn -o, laporan pembersih MENIMPA file bukti lapis (agregat
        # lalu melaporkan "Docker tidak tersedia" — sebab yang dikarang). Keduanya ditolak keras.
        if args.module_path or args.output:
            print(f"error: {CLEANUP_FLAG} tak menerima module_path maupun -o/--output "
                  "(laporan ke stdout; ia tak menjalankan validasi & tak boleh menimpa file lapis)",
                  file=sys.stderr)
            return 2
        print(json.dumps(cleanup_orphans(), indent=2, ensure_ascii=False))
        return 0  # melewati artefak yang tak terbukti mati BUKAN kegagalan

    if not args.module_path:
        print(f"error: module_path wajib (kecuali {CLEANUP_FLAG})", file=sys.stderr)
        return 2
    module_dir = Path(args.module_path).resolve()
    if not module_dir.is_dir():
        print(f"error: bukan folder: {module_dir}", file=sys.stderr)
        return 2
    mod_name = module_dir.name
    progress_init(args.progress_file, args.slow_after)
    if not job_start(args, mod_name, "flashlight"):
        return 2

    if not docker_available():
        result = {"module": mod_name, "docker_available": False, "status": "skipped",
                  "reason": "Docker tidak tersedia — lewati uji flashlight, andalkan ps-static-scan.",
                  "versions": {}}
        out = json.dumps(result, indent=2, ensure_ascii=False)
        (Path(args.output).write_text(out, encoding="utf-8") if args.output else print(out))
        return 0  # bukan error: degrade terkontrol

    tag_map = parse_tag_map(args.tag_map, args.extra_tag_map)
    result = {"module": mod_name, "docker_available": True, "status": "ran",
              "orchestrator": args.orchestrator, "versions": {}}
    overall_pass = True
    for full_ver in [v.strip() for v in args.versions.split(",")]:
        tag = resolve_tag(tag_map, full_ver)
        if args.verbose:
            print(f"versi {full_ver} -> {IMAGE}:{tag}", file=sys.stderr)
        r = run_one_version(module_dir, mod_name, full_ver, tag,
                            orchestrator=args.orchestrator, db_image=args.db_image,
                            ps_domain=args.ps_domain, startup_timeout=args.startup_timeout,
                            op_timeout=args.timeout, allow_pull=args.allow_image_pull)
        result["versions"][full_ver] = r
        overall_pass = overall_pass and r["pass"]
    result["pass"] = overall_pass

    out = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(out, encoding="utf-8")
        print(f"ditulis: {args.output}", file=sys.stderr)
    else:
        print(out)
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(run_main_with_progress(main))
