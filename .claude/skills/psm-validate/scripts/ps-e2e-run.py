#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright"]
# ///
"""Lapis 4 — uji perilaku browser (E2E) module PrestaShop, per versi & per browser.

Men-drive PrestaShop core ASLI yang boot di Docker flashlight lewat Playwright di
Chromium & Firefox: jalankan smoke universal (module ter-install → FO home render
tanpa fatal/white-screen → BO module manager tanpa fatal) plus skenario klik/use-case
yang di-authored module (`<module>/tests/e2e/*.json`). Output JSON temuan per versi,
setara lapis lain untuk ps-aggregate.py.

Meniru pola ps-flashlight-run.py: SELF-CONTAINED — membangun DB+flashlight (dengan
port HTTP terpublish agar Playwright di host bisa menjangkaunya), install module,
drive browser, teardown. Orkestrasi Docker DIPAKAI-ULANG lewat impor sibling
ps-flashlight-run.py (satu implementasi, tak diduplikasi).

DEGRADE JUJUR (tak pernah mengklaim lolos atas yang tak diuji):
  - Playwright tak terpasang           → status `skipped` (vonis jatuh ke lapis lain).
  - Docker tak tersedia                → status `skipped`.
  - image flashlight belum ada lokal   → `skipped_image` (tak auto-pull tanpa izin).
  - binary browser belum di-`install`  → engine itu `skipped_browser` (tak auto-download).
  - container tak `healthy` / PS tak terjangkau / module gagal install / timeout
                                       → infra error (versi itu TAK KONKLUSIF, tak memblok).

KONKLUSIF MEMBLOK: bila browser+container naik bersih & module ter-install, lalu
sebuah assertion (smoke/skenario) gagal → temuan severity `error` yang memblok versi
itu — persis seperti flashlight install-fail. Assertion di area BO hanya konklusif bila
login admin berhasil; bila gagal login, temuan BO jadi `inconclusive` (tak memblok).
Peran lapis dijaga rapi: install/coding-standard divonis Lapis 2 (flashlight); Lapis 4
memvonis PERILAKU browser.

VERIFIKASI VISUAL ("cek web asli" — lihat render seperti user, bukan cuma assertion):
  - `--screenshot-dir DIR` → simpan PNG per halaman (sesudah goto) & pada kegagalan;
    path terkumpul di hasil (`screenshots`) untuk dilihat mata / dinilai model-vision.
  - error JS/console (`console`+`pageerror`) ditangkap per skenario: dihitung & disurface
    sebagai advisory (`console_errors`, browser_notes) — TAK memblok; pakai aksi
    `expect_no_console_error` di skenario bila mau menegakkan (konklusif → memblok).
  - `--headed` → browser TAMPIL live (headless=False) untuk inspeksi manual; butuh display,
    opt-in eksplisit, JANGAN di headless/CI (tanpa display → skipped_browser).

OUTPUT PER SEL & EXIT CODE (cell-contract.md > Evidence record, Runner):
  - tiap versi memancarkan `cells.<engine>` untuk tiap engine yang lolos probe (juga saat
    boot/install gagal) plus field level-versi (`run_id`, `boot`, `boot_id`, `image_tag`,
    `boot_phases`, `boot_wall_clock`, ...); ps-run-layer menggabungkannya jadi rekaman histori.
  - exit 0 = E2E skipped, atau tiap sel yang dipancarkan `pass`; 3 = ada sel `fail`;
    1 = selain itu (infra / sel inconclusive / versi tanpa sel); 2 = input error.

FLAG ANAK (diset ps-run-layer, cell-contract.md > Runner > Child flags; CAP-3):
  - `--run-id <hex12>` = RUN_ID klaim slot yang sudah dibuat ps-run-layer; dipasang sebagai
    RUN_ID proses SEBELUM log kemajuan, registry job, maupun label (`psm.run`). Bukan
    `[0-9a-f]{12}` = exit 2.
  - `--slot-cost <n>` (int >= 1) dicap apa adanya sebagai label `psm.slots=<n>` di container PS
    SAJA. Absen (run langsung) = jumlah engine yang di-drive PARALEL, atau 1 bila satu engine /
    `--sequential-browsers` — run langsung ikut terhitung di slot seluruh daemon (tapi melewati
    admisi). Bukan int >= 1 = exit 2.
  - `--progress-append` = log kemajuan TIDAK dikosongkan (baris `wait-slots` milik ps-run-layer).
  - `--sequential-browsers` = engine di-drive berurutan (admisi cost 1) dgn fail-fast antar-engine:
    sesudah `fail` satu engine, engine berikutnya tak dimulai dan selnya `state: not-run`,
    `reason: fail-fast after <ver>:<engine>`. Dgn > 1 engine: `snapshot-db` sesudah `warmup-bo`,
    lalu reset penuh (`reset-db`, `reset-files`, `reset-opcache`, `wait-http`, `warmup-bo`)
    sebelum tiap engine berikutnya; snapshot/reset gagal = engine yang belum jalan
    `inconclusive`, reason `sequential-reset`, sub-fase gagal di `errors` sel itu.

BROWSER PARALEL (CAP-7, cell-contract.md > Parallel browsers):
  - >= 2 engine terprobe tanpa `--sequential-browsers` (run langsung termasuk) = mode paralel
    (`browser_mode: parallel`): proses versi mengambil `snapshot-db`, lalu menelurkan satu
    subproses `--engine-worker <spec.json>` per engine (Job ID & RUN_ID sama, ctx sendiri,
    screenshot `<shots>/<ver>/<engine>`, baris log kemajuan ke log versi, tak pernah `DONE`).
    Satu engine / `--sequential-browsers` = di-drive dalam proses (`browser_mode: sequential`).
  - Worker: tiap skenario memegang `flock` `<tmp>/psm-locks/<job>-<ver>.bo.lock` (LOCK_EX bila
    ada `goto` BO, else LOCK_SH; tunggu = fase `lock-wait:<engine>`) dan maju lockstep per
    skenario lewat penanda `<job>-<ver>.step/<engine>.<k>` (tunggu = `barrier-wait:<engine>`).
    Kedua tunggu tanpa batas waktu sendiri, tak pernah SLOW. Worker tanpa hasil terbaca = sel
    `inconclusive`, reason `crash`, exit code di `browser_notes`.
  - Konfirmasi sekuensial sesudah semua worker selesai (urut `psm_e2e_browsers`, maks satu pass
    per engine, tiap pass diawali reset penuh ke snapshot): login BO engine gagal sementara
    engine lain sukses → pass ulang `browser:<engine>#2` yang menggantikan pass pertama; engine
    bertemuan, atau yang men-drive skenario bertemuan di engine mana pun → `rerun-seq:<engine>`.
    Temuan paralel yang tak terulang pindah ke `parallel_only` (tak memblok); snapshot/health/
    reset gagal = `inconclusive`, reason `parallel-unconfirmed`. Exit code melihat hasil terkonfirmasi.

Format spec skenario authored (`<module>/tests/e2e/*.json`):
  {"name": "configure-save",
   "steps": [
     {"action": "goto", "area": "bo", "path": "/index.php?controller=AdminModules"},
     {"action": "expect_no_fatal"},
     {"action": "expect_no_console_error"},
     {"action": "fill", "selector": "#PSM_FIELD", "value": "42"},
     {"action": "click", "selector": "button[name=submitSave]"},
     {"action": "click_optional", "selector": "#warn-close"},
     {"action": "expect_text", "text": "successful"},
     {"action": "screenshot"},
     {"action": "goto", "area": "fo", "path": "/"},
     {"action": "expect_visible", "selector": "#header"}
   ]}
Placeholder yang disubstitusi di `path`/`url`/`text`/`value`: {mod} {fo} {bo} {browser}.
Area default `fo`. {browser} = engine aktif — pakai untuk nama data unik per-browser
(dalam satu step lockstep engine berbagi satu DB; duplikat data = temuan memblok palsu).
Hanya di pass konfirmasi sesudah run paralel (`rerun-seq`, fallback login BO) {browser} =
`<engine>-seq`, supaya data pass itu tak bertabrakan dgn pass pertama.

Prasyarat browser (sekali, host): `uv run --with playwright playwright install chromium firefox`
— lewat playwright yang sama dgn yang diprovisi header PEP723 skrip ini, supaya build browser
yang di-install cocok dgn yang di-drive.
"""
import argparse
import contextlib
import fcntl
import importlib.util
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

# Pakai-ulang orkestrasi Docker dari sibling ps-flashlight-run.py (impor by-path
# karena nama file ber-tanda-hubung) — satu implementasi spin/wait/exec/teardown.
_FL_PATH = Path(__file__).resolve().parent / "ps-flashlight-run.py"
_spec = importlib.util.spec_from_file_location("ps_flashlight_run", _FL_PATH)
assert _spec and _spec.loader, f"tak bisa memuat sibling {_FL_PATH}"
fl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fl)

DEFAULT_BROWSERS = "chromium,firefox"
RUN_ID_RE = re.compile(r"^[0-9a-f]{12}$")  # bentuk fl.RUN_ID (uuid4 hex 12)
SUPPORTED_ENGINES = fl.SUPPORTED_ENGINES  # pemilik tunggal: ps-flashlight-run (normalizer sel)
SUPPORTED_ACTIONS = ("goto", "expect_no_fatal", "expect_visible", "expect_text",
                     "expect_no_console_error", "click", "click_optional", "fill", "select",
                     "wait_for_text", "screenshot")
# Aksi yang benar-benar MENEGAKKAN sesuatu. goto/click/fill/screenshot menggerakkan browser
# tapi tak menyatakan apa pun soal benar/salah — `click` cuma membuktikan tombolnya ADA, bukan
# hasilnya benar. Diturunkan dari SUPPORTED_ACTIONS supaya aksi expect_* yang ditambahkan nanti
# ikut terhitung tanpa daftar kedua yang bisa melenceng.
ASSERT_ACTIONS = tuple(a for a in SUPPORTED_ACTIONS
                       if a.startswith("expect_") or a in ("wait_for_text",))
# `wait_for_text` ikut dihitung MESKI tak berawalan expect_: ia gagal bila teksnya tak pernah
# muncul dalam batas waktu, jadi ia menegakkan sesuatu persis seperti expect_text — hanya
# dengan kesabaran. Meninggalkannya di luar akan mengecilkan authored_assertions dan melemahkan
# gerbang e2e_smoke_only tepat pada skenario paling berharga (konfirmasi pembayaran).
# Aksi yang menilai RESPONS server (status + fatal) di URL yang dituju: konklusif tanpa login
# BO. Dulu konklusivitas dikunci per-AREA, jadi BO yang 500-fatal → login gagal → bo_authed
# False → SETIAP assertion BO tak konklusif, TERMASUK expect_no_fatal yang ada persis untuk
# menangkap fatal itu → pass palsu atas BO mati. BO PS sehat me-redirect request tanpa-auth ke
# AdminLogin (200/302, tanpa fatal), jadi goto/expect_no_fatal tak false-block tanpa login.
# SENGAJA TAK memuat expect_no_console_error: ia menilai console HALAMAN YANG TERMUAT — saat
# login gagal itu halaman login, bukan halaman BO module → memblok atas derau console login =
# misattribusi. Ia konklusif hanya lewat bo_authed (halaman authed benar-benar tercapai).
# Sisanya (expect_visible/expect_text/click/fill) butuh sesi & tetap tak konklusif tanpa auth.
SESSION_INDEPENDENT_ACTIONS = ("goto", "expect_no_fatal")
CONTAINER_HTTP_PORT = 80          # nginx/apache flashlight mendengarkan di 80
DEFAULT_HOST_PORT = 8000
# Default admin flashlight (BO folder `admin-dev`); override lewat flag. Login BO
# bersifat best-effort — gagal login TAK memvonis, hanya menandai BO tak konklusif.
DEFAULT_ADMIN_PATH = "admin-dev"
DEFAULT_ADMIN_EMAIL = "admin@prestashop.com"
DEFAULT_ADMIN_PASSWORD = "prestashop"
DEFAULT_NAV_TIMEOUT_S = 60        # timeout per navigasi/aksi Playwright; flashlight dingin
                                  # butuh >20s di load pertama (kompilasi Smarty/Symfony)
WAIT_TEXT_TIMEOUT_MS = 15000      # default `wait_for_text`; step boleh menimpanya via timeout_ms
WAIT_TEXT_POLL_MS = 250           # jeda antar-cek; polling dipilih agar permukaan `page` yang
                                  # dituntut tetap sama dengan aksi lain (count() saja), jadi
                                  # logika ini tetap teruji dengan page-tiruan.
SETTLE_TIMEOUT_MS = 15000         # batas tunggu settle (networkidle login BO / 'load'
                                  # sebelum expect_text) — BO polling XHR, jangan tunggu selamanya

# --- Browser paralel (CAP-7, cell-contract.md > Parallel browsers) -------------------------
WORKER_FLAG = "--engine-worker"
# Perintah worker engine; path spec.json ditambahkan di belakangnya. Seam test: diganti wrapper
# yang memuat skrip ini, men-stub drive_engine, lalu memanggil worker_main yang asli.
WORKER_CMD = [sys.executable, str(Path(__file__).resolve()), WORKER_FLAG]
LOCKSTEP_POLL = 0.25          # detik antar-poll kunci BO & barrier lockstep
WORKER_REAP_GRACE = 10        # detik total menunggu worker sesudah SIGTERM sebelum SIGKILL —
                              # jauh di dalam JOB_STOP_GRACE stop_job
# Sel yang state-nya DISET anak dan dipertahankan apa adanya (tanpa derive_state).
CHILD_SET_REASONS = ("crash", "parallel-unconfirmed", "sequential-reset")
PS_DOCROOT = "/var/www/html"  # docroot flashlight (sama dgn INSTALL_BLOCK_SH)

# Tanda PHP fatal / error server yang bikin "shop rusak" (white-screen / 500).
FATAL_SIGNS = (
    "Fatal error", "PrestaShopException", "There was an error",
    "Whoops, looks like something went wrong", "500 Internal Server Error",
    "Uncaught Error", "Parse error", "syntax error, unexpected",
)
_SCRIPT_RE = re.compile(r"<script\b.*?</script>", re.IGNORECASE | re.DOTALL)


def fatal_sign_in(raw_body):
    """Tanda fatal pertama di body respons MENTAH, atau None.

    WAJIB diberi body mentah (`response.text()`), BUKAN `page.content()`.
    content() adalah DOM TERSERIALISASI: parser menutup setiap tag yang terbuka,
    jadi fatal yang memotong render di tengah `<script>` justru ikut tersapu regex
    di bawah dan terbaca "tak ada fatal" — lolos konklusif atas toko rusak.
    Di body mentah, script terpotong TAK punya `</script>` sehingga tak match
    _SCRIPT_RE dan fatalnya tetap terlihat.

    Blok script yang benar-benar tertutup dibuang: halaman PS sehat meng-embed
    kamus terjemahan/JSON yang bisa memuat frasa ini — match di sana = temuan
    memblok palsu atas module sehat.
    """
    visible = _SCRIPT_RE.sub("", raw_body or "")
    for s in FATAL_SIGNS:
        if s in visible:
            return s
    return None


def _track_document(sink, resp):
    """Simpan body MENTAH tiap respons dokumen, dikunci URL-nya, ke `sink`.

    Dikunci URL supaya expect_no_fatal mengambil body milik halaman yang SEDANG
    dibuka (page.url) — bukan body basi navigasi sebelumnya, bukan body iframe
    (URL-nya beda). Ini jalur BEST-EFFORT untuk navigasi yang dipicu klik; jalur
    utama (goto) menyimpan body langsung lewat _capture_body, karena Playwright
    sync baru mendispatch event saat ada panggilan API yang memompa event loop —
    listener saja TAK deterministik.
    """
    try:
        if resp.request.resource_type != "document":
            return
        sink[resp.url] = resp.text()
    except Exception:  # noqa: BLE001 — body tak tersedia; degrade jujur di titik pakai
        pass


def _capture_body(ctx, resp):
    """Ambil body MENTAH langsung dari respons goto — deterministik, tanpa event."""
    sink = ctx.get("doc")
    if sink is None or resp is None:
        return
    try:
        sink[resp.url] = resp.text()
    except Exception:  # noqa: BLE001 — body tak terbaca (redirect/non-teks); degrade jujur
        pass

# Dijalankan DI DALAM container flashlight setelah healthy: salin + install module
# (TANPA phpstan — coding-standard adalah wilayah Lapis 2). $MOD_NAME dari env.
# Blok yang SAMA dengan yang dipakai Lapis 2, dari pemiliknya — bukan salinan. Sentinelnya
# berpasangan dgn fl.parse_install yang sudah kita impor: reader dibagi, jadi writer-nya
# harus dibagi juga. Dua salinan yang kebetulan cocok tak menahan apa pun.
INSTALL_SH = fl.INSTALL_BLOCK_SH


# ---------------------------------------------------------------------------
# Fungsi murni (teruji tanpa Playwright/Docker)
# ---------------------------------------------------------------------------
def parse_browsers(raw, key="--browsers"):
    """'chromium,firefox' -> ['chromium','firefox'] lewat normalizer sel bersama.

    Huruf kecil, dedup, urutan tertulis. Engine tak didukung atau daftar kosong ->
    fl.CellConfigError (main: exit 2). Dulu jatuh diam-diam ke default, jadi typo
    `--browsers firefx` menjalankan chromium+firefox dan terbaca sebagai cakupan yang diminta.
    """
    return fl.normalize_engines(raw, key=key)


def host_port_from_domain(ps_domain, default=DEFAULT_HOST_PORT):
    """Ambil port host dari PS_DOMAIN 'localhost:8000' -> 8000. Tanpa port -> default."""
    if ps_domain and ":" in ps_domain:
        tail = ps_domain.rsplit(":", 1)[1]
        if tail.isdigit():
            return int(tail)
    return default


def host_from_domain(ps_domain, default="localhost"):
    """Ambil komponen host dari PS_DOMAIN 'shop.local:9100' -> 'shop.local'. Kosong -> default.

    PS_DOMAIN dipakai PrestaShop untuk membangun URL absolut (link, cookie domain), jadi host
    yang di-set operator adalah domain yang dikira toko itu miliknya. Lapis 4 harus men-drive
    host YANG SAMA — kalau tidak, ia menguji toko yang dikonfigurasi berbeda dari yang di-boot.
    Hanya PORT yang mengambang (bebas-bind); host dipertahankan.
    """
    if not ps_domain:
        return default
    return ps_domain.rsplit(":", 1)[0] if ":" in ps_domain else ps_domain


def pick_free_host_port(preferred=0):
    """Port host yang BEBAS: pakai `preferred` bila kosong, else port ephemeral OS.

    Dua sesi validasi paralel dulu sama-sama menurunkan port dari
    psm_flashlight_ps_domain (default 8000) → keduanya publish `:8000` → sesi kedua
    gagal `docker` bind. Port harus dipilih SEBELUM boot karena PrestaShop membangun
    URL absolut dari PS_DOMAIN saat container dibuat, dan Playwright mengikuti link
    nyata: host:port publish HARUS sama dengan PS_DOMAIN. Port ephemeral yang baru
    diketahui SESUDAH boot (docker `-p :80`) tak bisa dipakai — PS sudah memancarkan
    link ke port yang salah. Jadi kita bind socket di muka untuk menemukan port bebas.

    `preferred=0` (atau port yang sedang terpakai) → OS memilih port ephemeral bebas
    lewat bind(('', 0)). Socket ditutup sebelum return; ada jendela race kecil (TOCTOU)
    antara tutup socket & docker bind — pemanggil menutupnya dengan satu retry.
    """
    if preferred:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            s.bind(("", preferred))
            return s.getsockname()[1]
        except OSError:
            pass  # preferred terpakai → jatuh ke ephemeral di bawah
        finally:
            s.close()
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("", 0))
        return s.getsockname()[1]
    finally:
        s.close()


# Tanda docker gagal bind port host — sesi lain menyambar port di jendela race (TOCTOU)
# antara kita menutup socket probe dan docker mem-bind. Pemanggil mundur ke port ephemeral.
_PORT_CONFLICT_SIGNS = ("already allocated", "address already in use",
                        "ports are not available", "failed to bind host port",
                        "bind: address already in use")


def _is_port_conflict(err):
    """True bila pesan error bring-up menandakan tabrakan port host (bukan kegagalan lain)."""
    low = (err or "").lower()
    return any(sign in low for sign in _PORT_CONFLICT_SIGNS)


def base_urls(ps_domain, admin_path):
    """(fo_base, bo_base) dari PS_DOMAIN + folder admin flashlight."""
    host = ps_domain or f"localhost:{DEFAULT_HOST_PORT}"
    fo = f"http://{host}"
    bo = f"{fo}/{(admin_path or DEFAULT_ADMIN_PATH).strip('/')}"
    return fo, bo


def substitute(text, ctx):
    """Substitusi placeholder {mod}/{fo}/{bo}/{browser} di string spec.

    {browser} = engine aktif (ctx['engine']) — dipakai spec pembuat data supaya
    nama unik per-browser: dalam satu step lockstep engine berbagi satu DB, data
    duplikat dari browser pertama bikin browser kedua gagal palsu (memblok). Pass
    konfirmasi (`rerun-seq`, fallback login BO) memasang ctx['browser_token'] =
    `<engine>-seq`, satu-satunya yang membacanya adalah substitusi ini.
    """
    if not text:
        return text
    return (text.replace("{mod}", ctx["mod"])
                .replace("{fo}", ctx["fo"])
                .replace("{bo}", ctx["bo"])
                .replace("{browser}", ctx.get("browser_token") or ctx.get("engine", "")))


def universal_smoke():
    """Skenario built-in yang berlaku ke SEMUA module: shop tak rusak dgn module aktif.

    FO home (no-auth, selalu konklusif) + BO module manager. Di BO, goto/expect_no_fatal
    menilai RESPONS server (status + fatal) → konklusif tanpa login: BO PS sehat me-redirect
    request tanpa-auth ke AdminLogin (200, tanpa fatal), jadi hanya BO yang benar-benar 500/
    fatal yang memblok. Assertion isi ber-auth (expect_visible/expect_text) butuh login berhasil.
    Placeholder {mod} tersedia untuk skenario authored, bukan smoke ini.
    """
    return {
        "name": "psm-universal-smoke",
        "source": "builtin",
        "steps": [
            {"action": "goto", "area": "fo", "path": "/"},
            {"action": "expect_no_fatal"},
            {"action": "expect_visible", "selector": "body"},
            {"action": "goto", "area": "bo", "path": "/index.php?controller=AdminModules"},
            {"action": "expect_no_fatal"},
        ],
    }


def deleted_specs(module_dir):
    """Spec E2E yang git tahu ada, tapi tak ada di working tree. Return daftar nama file.

    Spec yang merah membuat vonis jujur: `ready` jatuh karena ada coverage yang diniatkan
    tapi tak jalan. Hapus filenya dan catatannya ikut mati bersamanya — jadi `ready` NAIK
    justru karena uji berkurang. Satu-satunya yang masih mengingat spec itu pernah ada
    adalah git, jadi ke sanalah kita bertanya.

    Lingkupnya sengaja penghapusan yang BELUM di-commit (staged maupun tidak): itulah
    jendela tempat "hapus uji yang merah lalu jalankan ulang validasi" terjadi. Penghapusan
    yang sudah di-commit adalah keputusan yang terekam dan bisa ditinjau lewat diff-nya —
    itu urusan review, bukan skrip ini, dan menandainya selamanya cuma bikin bising.

    Bukan repo git / git tak terpasang / tests/e2e tak pernah dilacak -> [] (tak bisa tahu;
    jangan menebak).
    """
    module_dir = Path(module_dir)
    try:
        r = subprocess.run(["git", "-C", str(module_dir), "status", "--porcelain",
                            "--untracked-files=no", "--", "tests/e2e"],
                           capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return []
    if r.returncode != 0:
        return []
    gone = set()
    for line in r.stdout.splitlines():
        # porcelain v1: "XY <path>" — X=index, Y=working tree. 'D' di salah satunya =
        # file yang dilacak git hilang dari disk.
        if len(line) > 3 and "D" in line[:2]:
            name = Path(line[3:].strip().strip('"')).name
            if name.endswith(".json"):
                gone.add(name)
    return sorted(gone)


def discover_scenarios(module_dir):
    """Muat spec authored dari <module>/tests/e2e/*.json. Return (scenarios, notes).

    Spec tak valid (JSON rusak / tanpa 'steps' list / aksi tak dikenal) DILEWATI
    dengan catatan — tak crash, tak diam-diam hilang. Validasi aksi di sini supaya
    typo (mis. 'expect_visable') tak pernah terbaca hijau. Spec yang DIHAPUS tapi masih
    tercatat git juga dicatat: kalau tidak, menghapus uji yang merah menaikkan `ready`.
    """
    found, notes = [], []
    for name in deleted_specs(module_dir):
        notes.append(f"{name}: spec dihapus dari working tree tapi masih tercatat git — "
                     "pulihkan (git checkout) atau commit penghapusannya sbg keputusan sadar")
    e2e_dir = Path(module_dir) / "tests" / "e2e"
    if not e2e_dir.is_dir():
        return found, notes
    for f in sorted(e2e_dir.glob("*.json")):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            notes.append(f"{f.name}: gagal parse ({str(e)[:80]}) — dilewati")
            continue
        steps = data.get("steps") if isinstance(data, dict) else None
        if not isinstance(steps, list) or not steps:
            notes.append(f"{f.name}: tak ada 'steps' list — dilewati "
                         '(bentuk: {"name": "...", "steps": [{"action": "goto", ...}]})')
            continue
        # Catatan menyebut kosakata yang SAH, bukan cuma yang salah: spec adalah satu-satunya
        # input yang ditulis tangan manusia, dan tanpa daftar ini penulisnya harus menebak
        # atau membuka --help — padahal SUPPORTED_ACTIONS ada tepat di sini.
        unknown = sorted({str((s.get("action") if isinstance(s, dict) else None) or "?")
                          for s in steps
                          if not isinstance(s, dict) or s.get("action") not in SUPPORTED_ACTIONS})
        if unknown:
            notes.append(f"{f.name}: aksi tak dikenal ({', '.join(unknown)}) — dilewati; "
                         f"sah: {', '.join(SUPPORTED_ACTIONS)}")
            continue
        # Spec tanpa satu pun aksi expect_* tak menegakkan apa pun — ia tetap DIJALANKAN
        # (sebuah `goto` yang kena HTTP 500 tetap temuan yang memblok), tapi tak dihitung
        # sebagai cakupan uji perilaku. Catatannya lahir di sini, pemilik tunggal aturan
        # "spec mana yang sah", supaya pra-pass ps-plan-layers ikut memancarkannya SEBELUM
        # container boot — dulu penulisnya baru tahu sesudah N versi x M browser terbakar.
        if not any(isinstance(s, dict) and s.get("action") in ASSERT_ACTIONS for s in steps):
            notes.append(f"{f.name}: tak ada aksi expect_* — skenario ini tak menegakkan apa pun, "
                         f"jadi tak dihitung sebagai cakupan uji perilaku (tetap dijalankan); "
                         f"assertion yang sah: {', '.join(ASSERT_ACTIONS)}")
        found.append({"name": data.get("name") or f.stem, "source": f.name, "steps": steps})
    return found, notes


def _needs_bo(scenarios):
    """True bila ada langkah goto ke area 'bo' — memicu login admin best-effort."""
    for sc in scenarios:
        for step in sc.get("steps", []):
            if step.get("action") == "goto" and step.get("area") == "bo":
                return True
    return False


def _res(action, ok, conclusive, message, location):
    return {"action": action, "ok": bool(ok), "conclusive": bool(conclusive),
            "message": message, "location": location}


def _fatal_message(status, raw_body):
    if status is not None and status >= 500:
        return f"HTTP {status} (server error)"
    sign = fatal_sign_in(raw_body)
    return f"tanda fatal: '{sign}'" if sign else "tak ada fatal"


def _resolve_url(step, ctx, area):
    if step.get("url"):
        return substitute(step["url"], ctx)
    base = ctx["fo"] if area == "fo" else ctx["bo"]
    return base + substitute(step.get("path", ""), ctx)


_RUN_DIR_STAMP = re.compile(r"^run-\d{8}-\d{6}$")


def run_shot_dir(base):
    """Subfolder screenshot khusus run ini — `<base>/run-<YYYYMMDD-HHMMSS>`.

    Idempoten: `base` yang SUDAH berstempel dikembalikan apa adanya. Orkestrator multi-versi
    (ps-run-layer.py) menstempel sekali lalu memberi folder yang sama ke tiap anak; tanpa ini
    tiap anak menstempel ulang, bukti visual N versi pecah jadi N folder, dan hanya satu yang
    sampai ke vonis — persis kelas yang pemisahan per-run ini ada untuk dicegah.

    Idempotensi ini AMAN dari kelas PNG-basi hanya karena stempel dibuat SEGAR tiap invokasi
    orkestrator: ps-run-layer memanggil run_shot_dir dengan base TANPA stempel (dari
    `--screenshot-dir <psm_reports_dir>/e2e-shots`), jadi dua run berbeda selalu dapat folder
    berbeda; anak-anak SATU run memakai ulang stempel induknya. Yang tak boleh: mengumpankan
    balik nilai `screenshot_dir` dari file lapis LAMA (sudah berstempel run lampau) ke run
    baru — itu akan menaruh PNG run baru di folder run lama. Tak ada jalur terdokumentasi yang
    melakukannya (reuse ps-plan-layers tak menjalankan ulang E2E), jadi kelasnya tetap tertutup;
    catat di sini supaya penambah fitur tak membuka seam itu tanpa sadar.

    Nama file screenshot deterministik (`<ver>/<engine>-<skenario>-<label>.png`) dan tak
    pernah dibersihkan, jadi satu folder datar menumpuk PNG dari run-run sebelumnya —
    termasuk versi yang tak lagi dalam cakupan run sekarang. Verifikasi visual Lapis 4
    menyuruh model MEMVONIS dari gambar itu, jadi folder datar membuka jalan: layout rusak
    dari run minggu lalu ditulis jadi `error` yang MEMBLOK module, atas bukti dari run yang
    sudah tak ada. Memisahkan per-run menghapus kelasnya di sumber — lebih baik daripada
    menaruh gotcha yang harus diingat model.
    """
    if not base:
        return None
    if _RUN_DIR_STAMP.match(Path(base).name):
        return str(Path(base))
    return str(Path(base) / f"run-{datetime.now():%Y%m%d-%H%M%S}")


def _snap(page, ctx, label):
    """Simpan screenshot bila ctx['screenshot_dir'] diset — best-effort, tak pernah gagalkan step.

    Artefak visual untuk 'cek web asli' (lihat render seperti user). Nama file:
    <engine>-<scenario>-<label>.png; path terkumpul di ctx['_shots'].
    """
    sdir = ctx.get("screenshot_dir")
    if not sdir:
        return
    safe = re.sub(r"[^A-Za-z0-9_.-]", "_", f"{ctx.get('engine', '?')}-{ctx.get('scenario', '?')}-{label}")
    path = str(Path(sdir) / f"{safe}.png")
    try:
        page.screenshot(path=path, full_page=True)
        ctx.setdefault("_shots", []).append(path)
    except Exception:  # noqa: BLE001 — screenshot best-effort, jangan gagalkan skenario
        pass


def run_steps(page, steps, ctx):
    """Eksekusi langkah skenario terhadap `page` (Playwright-like). Return list hasil.

    `page` cukup mengekspos goto()->response(status), url, content()->str, locator(sel)
    (.first.is_visible()/.count()), get_by_text(txt).filter(visible=True)(.count()),
    click(sel), fill(sel,val), select_option(sel, label=) — sehingga logika ini teruji
    dengan page-tiruan. `wait_for_text` sengaja MEM-POLL count() alih-alih memakai API
    tunggu Playwright, supaya permukaan yang dituntut tak melebar dan ia tetap teruji.
    `expect_no_fatal` menilai body MENTAH dari ctx['doc'][page.url] (diisi
    _track_document lewat listener response); tanpa body itu ia TAK menilai (tak
    konklusif) alih-alih menebak dari DOM. `click_optional` = klik bila elemen ada,
    lewati tanpa gagal bila tidak (interstitial yang muncul hanya di sebagian versi).
    Assertion di area BO konklusif hanya bila ctx['bo_authed'] True. `expect_no_console_error`
    membaca error JS/console yang ditangkap drive_engine (ctx['console_sink'] sejak
    ctx['console_base']). Screenshot otomatis diambil sesudah goto & pada kegagalan bila
    ctx['screenshot_dir'] diset; aksi eksplisit `screenshot` juga tersedia.
    """
    results = []
    area = "fo"
    last_status = None
    for idx, step in enumerate(steps):
        first = len(results)
        action = step.get("action")
        if action == "goto":
            area = step.get("area", area)
        conclusive = ((area != "bo") or ctx.get("bo_authed", False)
                      or action in SESSION_INDEPENDENT_ACTIONS)
        try:
            if action == "goto":
                url = _resolve_url(step, ctx, area)
                resp = page.goto(url)
                last_status = getattr(resp, "status", None) if resp is not None else None
                _capture_body(ctx, resp)
                ok = last_status is None or last_status < 500
                results.append(_res(action, ok, conclusive, f"status={last_status}", url))
                _snap(page, ctx, f"{idx:02d}-goto")
            elif action == "expect_no_fatal":
                if last_status is not None and last_status >= 500:
                    results.append(_res(action, False, conclusive, f"HTTP {last_status} (server error)", area))
                else:
                    try:
                        # Memompa event loop (Playwright sync mendispatch event hanya
                        # saat ada panggilan API) supaya body navigasi-lewat-klik sempat
                        # tertangkap listener, sekaligus menunggu dokumen selesai.
                        page.wait_for_load_state("load", timeout=SETTLE_TIMEOUT_MS)
                    except Exception:  # noqa: BLE001 — pompa best-effort
                        pass
                    body = (ctx.get("doc") or {}).get(getattr(page, "url", None))
                    if body is None:
                        # Tanpa body mentah halaman ini, tak ada penilaian jujur —
                        # jangan menebak dari page.content() (lihat fatal_sign_in).
                        results.append(_res(action, False, False,
                                            "body respons mentah tak tertangkap — fatal tak dinilai", area))
                    else:
                        results.append(_res(action, fatal_sign_in(body) is None, conclusive,
                                            _fatal_message(last_status, body), area))
            elif action == "expect_visible":
                sel = step.get("selector", "")
                vis = page.locator(sel).first.is_visible()
                results.append(_res(action, bool(vis), conclusive, f"visible={bool(vis)} sel={sel}", sel))
            elif action == "expect_text":
                try:
                    # Settle pasca submit/redirect: tanpa ini konten halaman LAMA
                    # terbaca -> false-fail timing yang menggerus kepercayaan run merah.
                    page.wait_for_load_state("load", timeout=SETTLE_TIMEOUT_MS)
                except Exception:  # noqa: BLE001 — settle best-effort, assertion tetap dievaluasi
                    pass
                txt = substitute(step.get("text", ""), ctx)
                # Teks yang BENAR-BENAR TERLIHAT. get_by_text saja tak cukup: ia
                # mencocokkan node teks apa pun termasuk yang display:none, dan BO
                # PrestaShop membawa template growl/modal tersembunyi — 'successful'
                # di sana bikin simpan yang GAGAL terbaca lolos konklusif.
                present = page.get_by_text(txt).filter(visible=True).count() > 0
                results.append(_res(action, present, conclusive, f"text present={present}: {txt[:50]}", area))
            elif action == "expect_no_console_error":
                errs = ctx.get("console_sink", [])[ctx.get("console_base", 0):]
                sample = "; ".join((e.get("text", "") or "")[:60] for e in errs[:3])
                results.append(_res(action, len(errs) == 0, conclusive,
                                    f"{len(errs)} error console/JS" + (f": {sample}" if errs else ""),
                                    "browser-console"))
            elif action == "click":
                page.click(step.get("selector", ""))
                results.append(_res(action, True, conclusive, "clicked", step.get("selector", "")))
            elif action == "click_optional":
                # Utk elemen yang hanya muncul di sebagian versi (mis. interstitial
                # "Invalid security token" BO legacy 1.7/8, absen di Symfony 9):
                # klik bila ada, lewati TANPA gagal bila tidak.
                sel = step.get("selector", "")
                if page.locator(sel).count() > 0:
                    page.click(sel)
                    results.append(_res(action, True, conclusive, "clicked (elemen ada)", sel))
                else:
                    results.append(_res(action, True, conclusive, "dilewati — elemen tak ada", sel))
            elif action == "fill":
                page.fill(step.get("selector", ""), substitute(step.get("value", ""), ctx))
                results.append(_res(action, True, conclusive, "filled", step.get("selector", "")))
            elif action == "select":
                # Dipilih lewat LABEL (teks yang dilihat manusia), bukan value: spec ditulis
                # operator yang membaca dropdown, dan value-nya id numerik yang berbeda antar
                # instalasi (id_country Indonesia tak sama di tiap fixture). Playwright
                # auto-wait pada select_option, jadi field yang baru muncul setelah form
                # di-render ulang (mis. provinsi sesudah ganti negara) tak perlu didahului
                # expect_visible yang menilai seketika.
                sel = step.get("selector", "")
                label = substitute(step.get("value", ""), ctx)
                page.select_option(sel, label=label)
                results.append(_res(action, True, conclusive, f"selected {label}", sel))
            elif action == "wait_for_text":
                txt = substitute(step.get("text", ""), ctx)
                limit_ms = int(step.get("timeout_ms", WAIT_TEXT_TIMEOUT_MS))
                deadline = time.monotonic() + (limit_ms / 1000.0)
                present = False
                while True:
                    # Sama seperti expect_text: hanya yang BENAR-BENAR TERLIHAT. BO PrestaShop
                    # membawa template growl/modal tersembunyi, jadi node teks yang display:none
                    # akan meloloskan halaman yang sebenarnya belum sampai.
                    present = page.get_by_text(txt).filter(visible=True).count() > 0
                    if present or time.monotonic() >= deadline:
                        break
                    time.sleep(WAIT_TEXT_POLL_MS / 1000.0)
                results.append(_res(action, present, conclusive,
                                    f"text present={present} dalam {limit_ms}ms: {txt[:50]}", area))
            elif action == "screenshot":
                _snap(page, ctx, f"{idx:02d}-shot")
                results.append(_res(action, True, conclusive, "screenshot diambil", ctx.get("screenshot_dir", "")))
            else:
                # Backstop discover_scenarios: aksi tak dikenal TIDAK boleh terbaca lolos —
                # ok=False + conclusive=False -> masuk kanal inconclusive, bukan silent pass.
                results.append(_res(action or "?", False, False, "aksi tak dikenal — tak dieksekusi", ""))
        except Exception as e:  # noqa: BLE001 — selector timeout / nav gagal = assertion gagal
            results.append(_res(action or "?", False, conclusive, f"exception: {str(e)[:120]}", ""))
        # Indeks 0-based langkah di list `steps` spec — temuan membawanya (Evidence record >
        # Producers: tiap temuan dapat `action` + `step`), jadi (skenario, step, aksi) unik.
        for r in results[first:]:
            r["step"] = idx
        if results and not results[-1]["ok"]:
            _snap(page, ctx, f"{idx:02d}-FAIL-{action or 'x'}")
    return results


def count_authored_assertions(driven):
    """Berapa assertion authored yang BENAR-BENAR dinilai di versi ini — fakta yang DIHITUNG.

    Dulu pertanyaan "module ini punya uji perilaku?" dijawab dari NAMA skenario: ada `source`
    yang bukan `builtin:` berarti ya. Itu premis STRUKTURAL, dan sebuah spec berisi dua
    `screenshot` — nol assertion — menjawabnya "ya" juga, jadi `ready` naik dari false ke true
    karena sebuah FILE ada. Insentifnya terbalik: cara termurah dapat siap-rilis justru menulis
    spec kosong, kebalikan dari tekanan menuju TDD yang jadi alasan gerbang ini dipilih.

    Yang dihitung: hasil dari skenario authored (bukan builtin), aksinya keluarga expect_*, DAN
    konklusif — assertion yang tak konklusif (mis. area BO tanpa login) tak membuktikan apa pun,
    sejalan aturan "jangan percaya sesi rusak" yang sudah berlaku di seam lain.
    """
    n = 0
    for eng in driven:
        for sc in eng.get("scenarios", []):
            if str(sc.get("source", "")).startswith("builtin"):
                continue
            for r in sc.get("results", []):
                if r.get("action") in ASSERT_ACTIONS and r.get("conclusive"):
                    n += 1
    return n


def assemble_findings(full_ver, driven):
    """Dari hasil tiap engine, pisahkan temuan konklusif (memblok) vs inconclusive.

    driven = list dict per engine: {"browser", "scenarios":[{name,source,results}]}.
    """
    findings, inconclusive = [], []
    for eng in driven:
        engine = eng["browser"]
        for sc in eng.get("scenarios", []):
            for r in sc["results"]:
                if r["ok"]:
                    continue
                if r["conclusive"]:
                    findings.append({
                        "id": f"e2e-{sc['name']}-{r['action']}",
                        "severity": "error",
                        "message": f"[{engine}/{sc['name']}] {r['action']}: {r['message']}",
                        "location": r["location"],
                        "fix": "periksa perilaku module di versi ini / perbaiki skenario E2E",
                        "browser": engine, "scenario": sc["name"], "source": sc["source"],
                        "action": r["action"], "step": r.get("step"),
                        "versions": [full_ver],
                    })
                else:
                    inconclusive.append({
                        "browser": engine, "scenario": sc["name"], "action": r["action"],
                        "step": r.get("step"),
                        "message": r["message"], "location": r["location"],
                    })
    return findings, inconclusive


# ---------------------------------------------------------------------------
# Jembatan runtime (butuh Docker / Playwright) — impor lazy agar unit test bersih
# ---------------------------------------------------------------------------
def playwright_available():
    """True bila paket playwright terpasang (bukan berarti binary browser sudah di-install).

    Catatan: dijalankan lewat `uv run`, paket ini auto-provisioned (header PEP 723),
    jadi degrade nyata biasanya di tingkat BINARY browser (lihat browser_available) —
    yaitu `playwright install chromium firefox` yang belum dijalankan.
    """
    try:
        return importlib.util.find_spec("playwright") is not None
    except (ImportError, ValueError):
        return False


def browser_available(engine):
    """True bila binary engine sudah di-`playwright install` — probe murah tanpa launch.

    Gerbang prasyarat (analog image_present): dicek DULU sebelum membangun container,
    supaya versi tak menghabiskan boot flashlight hanya untuk menemukan browser absen.
    """
    try:
        from playwright.sync_api import sync_playwright
    except Exception:  # noqa: BLE001
        return False
    try:
        with sync_playwright() as p:
            btype = getattr(p, engine, None)
            if btype is None:
                return False
            path = btype.executable_path  # path terhitung; file ADA hanya bila terpasang
            return bool(path) and Path(path).exists()
    except Exception:  # noqa: BLE001
        return False


def wait_http(url, timeout, poll=2.0):
    """Poll GET url sampai respons < 500 (200/redirect) / timeout. Return (ok, status, responded).

    `responded` True begitu server membalas HTTP apa pun — TERMASUK 5xx: nginx+kernel PS
    menjawab, jadi port jelas terpublish & boot berhasil. 5xx yang BERTAHAN sepanjang timeout
    (500 saat cold-start akan resolve jadi 200 lewat poll) adalah bukti MODULE merusak toko,
    bukan infra — pemanggil harus membiarkan browser + expect_no_fatal memvonisnya, jangan
    menyapunya ke kanal infra. `responded` False hanya bila TAK ada respons TCP sama sekali
    (connection refused / timeout tanpa HTTP) = port publish / boot memang gagal.
    """
    deadline = time.monotonic() + timeout
    last = "no-response"
    responded = False
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=10) as r:  # noqa: S310 (localhost)
                return True, r.status, True
        except urllib.error.HTTPError as e:
            responded = True
            if e.code < 500:
                return True, e.code, True
            last = f"HTTP {e.code}"
        except (urllib.error.URLError, OSError) as e:
            last = str(e)[:80]
        time.sleep(poll)
    return False, last, responded


def install_module(session, mod_name, timeout):
    """Salin + install module via PS console di container. Return (info, err_or_None)."""
    try:
        with fl.phase("install", timeout):
            cp = fl._exec(session, {"MOD_NAME": mod_name}, INSTALL_SH, timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False}, "timeout menjalankan install di container"
    out = (cp.stdout or "") + (cp.stderr or "")
    inst = fl.parse_install(out)
    if inst.get("copy_fail"):
        return {"ok": False}, "gagal menyalin module ke dalam container"
    return {"ok": inst["ok"], "no_console": inst.get("no_console", False),
            "no_psroot": inst.get("no_psroot", False),
            "no_verdict": inst.get("no_verdict", False)}, None


def _bo_login(page, ctx):
    """Login BO best-effort (form AdminLogin: input email/passwd stabil 1.7/8/9).

    Tombol submit — verified vs flashlight 1.7.8.11/8.1.6/9.1.4: NAME `submitLogin`
    di 1.7 & 8 (form legacy; dan cocok ke DUA tombol — login + "Send reset link"),
    `submit_login` di 9 (Symfony). ID `#submit_login` sama di ketiganya — klik via id,
    satu-satunya selector yang jalan di ketiga versi.

    Sukses = sinyal STRUKTURAL ganda, bukan absen substring di HTML terserialisasi
    (halaman 500 / interstitial token juga tanpa field passwd → cek substring lama
    lapor sukses palsu → assertion BO jadi konklusif-memblok atas kegagalan infra):
    field passwd hilang (locator count 0) DAN URL sudah meninggalkan AdminLogin.
    Dicoba 2x — POST+redirect pertama flaky di cold-container 1.7/8 (verified).
    """
    for _ in range(2):
        try:
            page.goto(ctx["bo"] + "/index.php?controller=AdminLogin")
            page.fill("input[name=email]", ctx["admin_email"])
            page.fill("input[name=passwd]", ctx["admin_password"])
            page.click("#submit_login")
            try:
                # Login 1.7/8 = POST AJAX lalu redirect via JS: di Firefox networkidle bisa
                # tercapai SEBELUM redirect itu (verified 8.1.6 — sesi sudah login, URL masih
                # AdminLogin) → negatif palsu. Tunggu (berbatas) URL meninggalkan AdminLogin dulu.
                page.wait_for_url(lambda u: "controller=AdminLogin" not in u,
                                  timeout=SETTLE_TIMEOUT_MS)
            except Exception:  # noqa: BLE001 — login gagal / page tiruan: cek struktural di bawah
                pass
            try:
                # BO punya polling XHR — networkidle bisa tak pernah tercapai; batasi,
                # lalu fallback ke "load".
                page.wait_for_load_state("networkidle", timeout=SETTLE_TIMEOUT_MS)
            except Exception:  # noqa: BLE001
                page.wait_for_load_state("load")
            if (page.locator("input[name=passwd]").count() == 0
                    and "controller=AdminLogin" not in (getattr(page, "url", "") or "")):
                return True
        except Exception:  # noqa: BLE001 — attempt gagal (nav/selector) → coba sekali lagi
            pass
    return False


def _drive_page(browser, engine, scenarios, ctx):
    """Setup context/page + listener console + jalankan semua skenario. Return (scenarios, bo_authed).

    Terpisah dari drive_engine agar jalur setelah-launch (new_context/new_page/listener/
    _bo_login) teruji dengan browser-tiruan; kegagalannya diangkat & ditangani drive_engine.
    `ctx['scenario_hook']` (opsional) = callable `(k, skenario) -> context manager` yang
    membungkus run tiap skenario k (0-based): span `scenario_spans` pass pertama, dan di worker
    paralel juga kunci lintas-engine + barrier lockstep. `_bo_login` berjalan di luarnya.
    """
    context = browser.new_context(ignore_https_errors=True)
    page = context.new_page()
    page.set_default_timeout(ctx["nav_timeout"])
    console_sink = []
    page.on("console", lambda m: console_sink.append({"type": m.type, "text": (m.text or "")[:200]})
            if getattr(m, "type", "") == "error" else None)
    page.on("pageerror", lambda e: console_sink.append({"type": "pageerror", "text": str(e)[:200]}))
    # Body respons MENTAH per URL — satu-satunya masukan sah expect_no_fatal.
    doc_sink = {}
    page.on("response", lambda r: _track_document(doc_sink, r))
    base = dict(ctx)
    base["engine"] = engine
    base["console_sink"] = console_sink
    base["doc"] = doc_sink
    # Hook per skenario (ScenarioSpans / LockstepHook) — objek proses, tak pernah ke spec.json;
    # dicabut dari base supaya tak ikut ke ctx lokal skenario.
    hook = base.pop("scenario_hook", None)
    base["bo_authed"] = _bo_login(page, base) if _needs_bo(scenarios) else False
    out = []
    for k, sc in enumerate(scenarios):
        start = len(console_sink)
        local = dict(base)
        local["scenario"] = sc["name"]
        local["console_base"] = start
        local["_shots"] = []
        with (hook(k, sc) if hook is not None else contextlib.nullcontext()):
            results = run_steps(page, sc["steps"], local)
        out.append({
            "name": sc["name"], "source": sc["source"], "results": results,
            "console_errors": console_sink[start:], "screenshots": local["_shots"],
        })
    return out, base["bo_authed"]


def drive_engine(engine, scenarios, ctx, headed=False):
    """Luncurkan satu engine Playwright, jalankan semua skenario. Return hasil per engine.

    `headed=True` menampilkan browser (headless=False) untuk inspeksi visual manual —
    butuh display; opt-in eksplisit, JANGAN di headless/CI. Menangkap error console/JS
    (`console`+`pageerror`) per skenario. Kegagalan luncur (binary belum di-`playwright
    install`, atau headed tanpa display) ATAU kegagalan SETELAH launch (browser mati/display
    flaky) -> launch_error (upstream: skipped_browser) — degrade engine ini, JANGAN crash
    seluruh run multi-versi.
    """
    from playwright.sync_api import sync_playwright

    result = {"browser": engine, "scenarios": [], "launch_error": None, "bo_authed": False}
    with sync_playwright() as p:
        btype = getattr(p, engine, None)
        if btype is None:
            result["launch_error"] = f"engine tak dikenal: {engine}"
            return result
        try:
            browser = btype.launch(headless=not headed)
        except Exception as e:  # noqa: BLE001 — binary absent / gagal luncur / headed tanpa display
            result["launch_error"] = str(e)[:200]
            return result
        try:
            result["scenarios"], result["bo_authed"] = _drive_page(browser, engine, scenarios, ctx)
        except Exception as e:  # noqa: BLE001 — gagal SETELAH launch -> degrade engine ini, jangan crash
            result["launch_error"] = f"gagal setelah launch: {str(e)[:180]}"
            result["scenarios"] = []  # jangan percayai hasil parsial dari sesi browser yang rusak
        finally:
            try:
                browser.close()
            except Exception:  # noqa: BLE001 — menutup browser mati bisa raise; abaikan
                pass
    return result


def utc_now():
    """Timestamp sel: UTC ISO-8601 bermikrodetik (`+00:00`), bentuk yang ditulis ke histori."""
    return datetime.now(timezone.utc).isoformat(timespec="microseconds")


def _new_cell():
    """Sel satu engine sebelum engine-nya jalan. Field yang belum diproduksi engine = None.

    Dipancarkan untuk tiap engine yang lolos probe di SETIAP jalur return (boot/install gagal
    termasuk, dengan started_at/finished_at None — ps-run-layer mengisinya). `scenario_spans`
    diisi pass pertama engine; `parallel_only` = [] di mode paralel (sel ber-hasil worker),
    else tetap None. Sel ini tak punya kunci `errors` (hanya sel parallel-unconfirmed /
    sequential-reset yang mendapatkannya).
    """
    return {"started_at": None, "finished_at": None, "scenario_set": "full",
            "scenarios_run": None, "findings": None, "inconclusive": None,
            "authored_assertions": None, "bo_authed": None, "launch_error": None,
            "browser_notes": [], "console_errors": None, "screenshots": None,
            "phase_durations": {}, "scenario_spans": None, "parallel_only": None}


def _not_run_cell(reason):
    """Sel engine yang TAK PERNAH dimulai karena fail-fast antar-engine (--sequential-browsers).

    Semua kunci _new_cell null (scenario_set/browser_notes/phase_durations termasuk) +
    `state: not-run`, `conclusive: false`, `reason`. ps-run-layer mempertahankan state ini
    (tanpa derive_state) dan mengisi sisanya seperti sel yang tak pernah di-drive.
    """
    cell = dict.fromkeys(_new_cell())
    cell.update(state="not-run", conclusive=False, reason=reason)
    return cell


def _fill_cell(cell, eng, full_ver, scenarios):
    """Isi sel dari hasil drive SATU engine — helper yang sama dgn rollup versi, satu engine."""
    findings, inconclusive = assemble_findings(full_ver, [eng])
    scs = eng.get("scenarios", [])
    cell.update({
        # Engine yang gagal luncur tak men-drive apa pun — jangan klaim cakupan skenario.
        "scenarios_run": [] if eng.get("launch_error") else [sc["name"] for sc in scenarios],
        "findings": findings, "inconclusive": inconclusive,
        "authored_assertions": count_authored_assertions([eng]),
        "bo_authed": bool(eng.get("bo_authed")),
        "launch_error": eng.get("launch_error"),
        "console_errors": sum(len(sc.get("console_errors", [])) for sc in scs),
        "screenshots": [s for sc in scs for s in sc.get("screenshots", [])],
    })


# ---------------------------------------------------------------------------
# Lockstep lintas-engine (CAP-7): kunci BO + barrier step. Helper ber-path EKSPLISIT, tanpa
# fase/sink/log — yang membungkusnya dgn fase tunggu adalah LockstepHook di worker.
# ---------------------------------------------------------------------------
def lockstep_paths(full_ver, job_id=None):
    """Path kunci & penanda lockstep satu versi di fl.LOCK_DIR: {lock, holders, step}.

    `<job>-<ver>.bo.lock` (flock lintas-engine), `<job>-<ver>.bo.holders/<engine>` (siapa
    memegangnya, utk detail `lock-wait`), `<job>-<ver>.step/<engine>.<k>` (barrier).
    """
    job = job_id or fl._JOB.get("id") or f"run-{fl.RUN_ID}"
    base = f"{job}-{re.sub(r'[^A-Za-z0-9_.-]', '_', full_ver)}"
    d = Path(fl.LOCK_DIR)
    return {"lock": d / f"{base}.bo.lock", "holders": d / f"{base}.bo.holders",
            "step": d / f"{base}.step"}


def bo_lock_try(lock_path, exclusive):
    """Satu percobaan flock NON-blocking pada `lock_path` (LOCK_EX bila `exclusive`, else
    LOCK_SH). Return fd (kunci dipegang; lepas = os.close) atau None (dipegang engine lain)."""
    fd = os.open(str(lock_path), os.O_RDWR | os.O_CREAT, 0o666)
    try:
        fcntl.flock(fd, (fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH) | fcntl.LOCK_NB)
    except BlockingIOError:
        os.close(fd)
        return None
    except BaseException:
        os.close(fd)
        raise
    return fd


def bo_lock_wait(lock_path, exclusive, poll_hook=None):
    """Poll bo_lock_try tiap LOCKSTEP_POLL sampai dapat. Tanpa batas waktu sendiri: lamanya =
    skenario engine lain yang memegangnya (dibatasi timeout langkahnya). `poll_hook()`
    dipanggil di tiap poll yang masih menunggu (boleh raise utk keluar). Return fd."""
    while True:
        fd = bo_lock_try(lock_path, exclusive)
        if fd is not None:
            return fd
        if poll_hook is not None:
            poll_hook()
        time.sleep(LOCKSTEP_POLL)


def lock_holders(holders_dir):
    """Engine yang penanda pemegangnya ada di `holders_dir` (urut nama); error baca = []."""
    try:
        return sorted(p.name for p in Path(holders_dir).iterdir())
    except OSError:
        return []


def holder_mark(holders_dir, engine):
    """Penanda pemegang `<holders_dir>/<engine>` — best-effort, error diabaikan."""
    try:
        (Path(holders_dir) / engine).touch()
    except OSError:
        pass


def holder_unmark(holders_dir, engine):
    """Hapus penanda pemegang — best-effort, error diabaikan."""
    try:
        (Path(holders_dir) / engine).unlink(missing_ok=True)
    except OSError:
        pass


def step_mark(step_dir, engine, k):
    """Penanda `<step_dir>/<engine>.<k>`: engine ini selesai step k (apa pun hasilnya).
    Best-effort: gagal tulis hanya menahan engine lain sampai worker ini keluar (`.done`)."""
    try:
        (Path(step_dir) / f"{engine}.{k}").touch()
    except OSError:
        pass


def step_done(step_dir, engine):
    """Penanda `<engine>.done` (dibuat proses versi saat worker-nya keluar / gagal ditelurkan)
    = setiap step engine itu selesai, jadi barrier tak pernah menunggu worker yang sudah tiada."""
    try:
        (Path(step_dir) / f"{engine}.done").touch()
    except OSError:
        pass


def barrier_pending(step_dir, engines, engine, k):
    """Engine LAIN yang belum selesai step k (tanpa `<e>.<k>` maupun `<e>.done`)."""
    d = Path(step_dir)
    return [e for e in engines if e != engine
            and not (d / f"{e}.{k}").exists() and not (d / f"{e}.done").exists()]


def barrier_wait(step_dir, engines, engine, k, poll_hook=None):
    """Poll tiap LOCKSTEP_POLL sampai tiap engine lain selesai step k — tanpa batas waktu
    sendiri. `poll_hook(pending)` dipanggil di tiap poll yang masih menunggu (boleh raise)."""
    while True:
        pending = barrier_pending(step_dir, engines, engine, k)
        if not pending:
            return
        if poll_hook is not None:
            poll_hook(pending)
        time.sleep(LOCKSTEP_POLL)


class ScenarioSpans:
    """Hook skenario pass PERTAMA dalam proses (satu engine / fallback sekuensial): catat
    `scenario_spans` saja, distempel tepat di sekitar run skenario.

    `spans` = {nama skenario: [start_ns, end_ns]} dari time.monotonic_ns() — jam seluruh host,
    sebanding lintas proses. Pass konfirmasi tak memakai hook (tak mencatat span).
    """

    def __init__(self):
        self.spans = {}

    @contextlib.contextmanager
    def __call__(self, k, sc):
        start = time.monotonic_ns()
        yield
        self.spans[sc["name"]] = [start, time.monotonic_ns()]


class ParentGone(BaseException):
    """Proses versi pemilik worker sudah tiada (os.getppid() berubah): worker keluar 1 tanpa hasil."""


class LockstepHook(ScenarioSpans):
    """Hook skenario worker paralel (cell-contract.md > Parallel browsers > lock, Lockstep).

    Per skenario k: tunggu tiap engine lain selesai step k-1 (`barrier-wait:<engine>`), ambil
    kunci BO (LOCK_EX bila skenario punya `goto` BO, else LOCK_SH; fase `lock-wait:<engine>`
    hanya bila percobaan non-blocking gagal), buat penanda pemegang, start_ns, run, end_ns,
    hapus penanda, tutup fd, lalu tulis penanda step k. Lepas kunci di `finally`. Skenario yang
    melempar tak menulis penanda step (drive batal; `<engine>.done` melepas barrier engine
    lain). Sesudah penanda step terakhir tak ada tunggu. Di tiap poll tunggu: proses versi
    hilang → ParentGone.
    """

    def __init__(self, engine, engines, lock, holders_dir, step_dir, parent_pid=None):
        super().__init__()
        self.engine, self.engines = engine, list(engines)
        self.lock, self.holders_dir, self.step_dir = lock, holders_dir, step_dir
        self.parent_pid = parent_pid

    def _check_parent(self, *_):
        if self.parent_pid is not None and os.getppid() != self.parent_pid:
            holder_unmark(self.holders_dir, self.engine)
            raise ParentGone()

    def _barrier(self, k):
        pending = barrier_pending(self.step_dir, self.engines, self.engine, k)
        if not pending:
            return
        with fl.phase(f"barrier-wait:{self.engine}", None,
                      f"step {k} belum selesai: {', '.join(pending)}") as ph:
            def poll(waiting):
                self._check_parent()
                ph.detail = f"step {k} belum selesai: {', '.join(waiting)}"
            barrier_wait(self.step_dir, self.engines, self.engine, k, poll_hook=poll)

    def _acquire(self, exclusive):
        fd = bo_lock_try(self.lock, exclusive)
        if fd is not None:
            return fd
        mode = "LOCK_EX" if exclusive else "LOCK_SH"

        def detail():
            return f"{mode}; dipegang: {', '.join(lock_holders(self.holders_dir)) or '?'}"
        with fl.phase(f"lock-wait:{self.engine}", None, detail()) as ph:
            def poll():
                self._check_parent()
                ph.detail = detail()
            return bo_lock_wait(self.lock, exclusive, poll_hook=poll)

    @contextlib.contextmanager
    def __call__(self, k, sc):
        if k > 0:
            self._barrier(k - 1)
        fd = self._acquire(_needs_bo([sc]))
        try:
            holder_mark(self.holders_dir, self.engine)
            start = time.monotonic_ns()
            yield
            self.spans[sc["name"]] = [start, time.monotonic_ns()]
        finally:
            holder_unmark(self.holders_dir, self.engine)
            os.close(fd)
        step_mark(self.step_dir, self.engine, k)


def _write_json_atomic(path, data):
    """Tulis JSON atomik: temp di folder yang sama lalu os.replace (pembaca tak melihat setengah)."""
    path = Path(path)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, path)


def _worker_on_sigterm(signum, frame):
    """Handler SIGTERM worker: abaikan SIGTERM berikutnya, lalu hentikan (JobStopped)."""
    signal.signal(signal.SIGTERM, signal.SIG_IGN)
    raise fl.JobStopped()


def worker_main(spec_path):
    """Worker engine `ps-e2e-run.py --engine-worker <spec.json>`: drive SATU engine lockstep.

    Dipanggil __main__ SEBELUM run_main_with_progress, jadi worker tak pernah menulis DONE.
    Urutan: fl.RUN_ID = run_id; progress_attach (log versi, tanpa truncate); job_register (Job
    ID yang sama → --stop-job menjangkaunya); timing_activate; ctx sendiri dgn screenshot_dir
    dari spec (null = tanpa screenshot); fase `browser:<engine>` membungkus drive_engine dgn
    LockstepHook, started_at/finished_at distempel tepat di dalamnya. Hasil ditulis atomik ke
    spec['result'] = {engine, started_at, finished_at, result, scenario_spans, timings}
    (timings = events sink, dicatat ulang proses versi). JobStopped: SIGTERM berikutnya
    diabaikan, tanpa hasil, exit 143. Proses versi hilang (ParentGone): tanpa hasil, exit 1.
    """
    spec = json.loads(Path(spec_path).read_text(encoding="utf-8"))
    engine = spec["engine"]
    fl.RUN_ID = spec["run_id"]
    fl.progress_attach(spec.get("progress_file"), spec["version"], spec.get("slow_after"))
    ctx = dict(spec["ctx"])
    if spec.get("job_id"):
        fl.job_register(spec["job_id"], module=ctx["mod"], layer="e2e", versions=spec["version"])
    # Sesudah job_register (yang memasang fl._on_sigterm): SIGTERM pertama langsung memasang
    # SIG_IGN sebelum JobStopped dilempar — SIGTERM kedua (--stop-job + reap proses versi)
    # tak boleh memotong browser.close()/finally LockstepHook/END fase yang sedang berjalan.
    signal.signal(signal.SIGTERM, _worker_on_sigterm)
    try:
        sink = fl.timing_activate()
        ctx["screenshot_dir"] = spec.get("screenshot_dir")
        hook = LockstepHook(engine, spec["engines"], spec["lock"], spec["holders_dir"],
                            spec["step_dir"], spec.get("parent_pid"))
        ctx["scenario_hook"] = hook
        scenarios = spec["scenarios"]
        with fl.phase(f"browser:{engine}", None, f"{len(scenarios)} skenario (worker paralel)"):
            started = utc_now()
            eng = drive_engine(engine, scenarios, ctx, headed=bool(spec.get("headed")))
            finished = utc_now()
        _write_json_atomic(spec["result"], {
            "engine": engine, "started_at": started, "finished_at": finished, "result": eng,
            "scenario_spans": hook.spans, "timings": [list(ev) for ev in sink.events]})
    except fl.JobStopped:
        return 143
    except ParentGone:
        holder_unmark(spec["holders_dir"], engine)
        return 1
    return 0


# ---------------------------------------------------------------------------
# Proses versi, mode paralel: telurkan & panen worker
# ---------------------------------------------------------------------------
def _mkdir_best_effort(path):
    """Buat folder (parents) best-effort. Return path str, atau None bila gagal (screenshot
    dilewati, run tak gagal) — perlakuan yang sama dgn folder screenshot versi."""
    try:
        Path(path).mkdir(parents=True, exist_ok=True)
        return str(path)
    except OSError:
        return None


def read_worker_result(path, engine):
    """Hasil worker bila TERBACA: objek JSON dgn semua kunci kontrak dan `engine` = engine
    worker itu (`result` dict, `timings` list). Selain itu None → sel `crash`."""
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    keys = ("engine", "started_at", "finished_at", "result", "scenario_spans", "timings")
    if not isinstance(data, dict) or any(k not in data for k in keys) or data["engine"] != engine:
        return None
    if not isinstance(data["result"], dict) or not isinstance(data["timings"], list):
        return None
    return data


def _absorb_timings(timings):
    """Catat ulang durasi fase worker ke sink proses versi — akhiran #n berlanjut di sana dan
    tiap fase lockstep mendahului fase pass sekuensial. Entri cacat dilewati."""
    sink = fl.timing_current()
    if sink is None:
        return
    for ev in timings:
        if isinstance(ev, (list, tuple)) and len(ev) == 3 and isinstance(ev[0], str):
            try:
                sink.record(ev[0], float(ev[1]), ev[2])
            except (TypeError, ValueError):
                continue


def reap_workers(procs, grace=None):
    """SATU-SATUNYA cara mengakhiri worker yang masih hidup (finally proses versi, jalur stop
    termasuk): SIGTERM, tunggu total <= WORKER_REAP_GRACE detik, SIGKILL sisanya, lalu tunggu."""
    grace = WORKER_REAP_GRACE if grace is None else grace
    live = [p for p in procs if p.poll() is None]
    for p in live:
        with contextlib.suppress(OSError):
            p.send_signal(signal.SIGTERM)
    deadline = time.monotonic() + grace
    for p in live:
        with contextlib.suppress(subprocess.TimeoutExpired):
            p.wait(timeout=max(0.0, deadline - time.monotonic()))
    for p in live:
        if p.poll() is None:
            with contextlib.suppress(OSError):
                p.kill()
            p.wait()


def _cleanup_lockstep(paths, workdir):
    """Hapus file kunci, folder pemegang & step, dan folder kerja — sesudah SEMUA worker keluar."""
    with contextlib.suppress(OSError):
        Path(paths["lock"]).unlink(missing_ok=True)
    for d in (paths["holders"], paths["step"], workdir):
        if d:
            shutil.rmtree(d, ignore_errors=True)


def run_parallel_workers(full_ver, engines, scenarios, ctx, *, ver_shot_dir=None, headed=False):
    """Pass lockstep paralel: satu worker WORKER_CMD per engine terhadap container yang sama.

    Return {engine: {"result": hasil terbaca | None, "rc": exit code | None, "spawn_error":
    str | None}}. Proses versi sendiri tak men-drive browser dan tak membuka fase `browser:`.
    Sebelum menelurkan: folder kerja privat (mkdtemp, 0700) berisi `<engine>.spec.json` &
    `<engine>.result.json`, folder pemegang & step (dikosongkan: sisa run lama tak boleh
    melepas barrier), dan `<shots>/<ver>/<engine>` (best-effort). Worker berjalan dgn stdout
    DEVNULL dan stderr diwarisi. Dipanen urut selesai (semua di-poll): tiap yang keluar dapat
    `<engine>.done`, penanda pemegangnya dihapus, hasilnya dibaca, durasi fasenya dicatat ulang
    ke sink versi. Worker yang gagal ditelurkan langsung `.done`, yang lain jalan terus.
    `finally` (jalur stop termasuk): reap_workers lalu _cleanup_lockstep.
    """
    paths = lockstep_paths(full_ver)
    workdir, procs = None, {}
    out = {e: {"result": None, "rc": None, "spawn_error": None} for e in engines}
    try:
        workdir = Path(tempfile.mkdtemp(prefix="psm-e2e-workers-"))
        Path(fl.LOCK_DIR).mkdir(parents=True, exist_ok=True)
        with contextlib.suppress(OSError):
            os.chmod(fl.LOCK_DIR, 0o1777)  # /tmp dibagi lintas user (seperti slots.lock)
        for d in (paths["holders"], paths["step"]):
            shutil.rmtree(d, ignore_errors=True)
            d.mkdir(parents=True, exist_ok=True)
        shots = {e: (_mkdir_best_effort(Path(ver_shot_dir) / e) if ver_shot_dir else None)
                 for e in engines}
        base = {"version": full_ver, "engines": list(engines), "scenarios": scenarios,
                "ctx": ctx, "job_id": fl._JOB.get("id"), "run_id": fl.RUN_ID,
                "parent_pid": os.getpid(),
                "progress_file": str(fl._PROGRESS["path"]) if fl._PROGRESS.get("path") else None,
                "slow_after": fl._PROGRESS.get("slow_after"), "lock": str(paths["lock"]),
                "holders_dir": str(paths["holders"]), "step_dir": str(paths["step"]),
                "headed": bool(headed)}
        for e in engines:
            spec_path = workdir / f"{e}.spec.json"
            spec = dict(base, engine=e, screenshot_dir=shots[e],
                        result=str(workdir / f"{e}.result.json"))
            try:
                spec_path.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
                procs[e] = subprocess.Popen([*WORKER_CMD, str(spec_path)],
                                            stdout=subprocess.DEVNULL)
            except (OSError, ValueError, TypeError) as err:
                out[e]["spawn_error"] = f"worker gagal ditelurkan: {str(err)[:180]}"
                step_done(paths["step"], e)
        live = dict(procs)
        while live:
            for e, proc in list(live.items()):
                rc = proc.poll()
                if rc is None:
                    continue
                del live[e]
                step_done(paths["step"], e)
                holder_unmark(paths["holders"], e)
                out[e]["rc"] = rc
                res = read_worker_result(workdir / f"{e}.result.json", e)
                out[e]["result"] = res
                if res is not None:
                    _absorb_timings(res["timings"])
            if live:
                time.sleep(LOCKSTEP_POLL)
    finally:
        reap_workers(list(procs.values()))
        _cleanup_lockstep(paths, workdir)
    return out


# ---------------------------------------------------------------------------
# Snapshot & reset ke snapshot (shell di container PS) — rutin reset BERSAMA dipakai pass
# konfirmasi paralel dan fallback sekuensial (CAP-5 bisa memakainya ulang; belum ada jalur warm)
# ---------------------------------------------------------------------------
# Kepala tiap skrip: `sh` bisa dash — tanpa pipe yang statusnya penting, tanpa process
# substitution; LC_ALL=C supaya `sort` dan `comm` sepakat soal urutan.
_SH_HEAD = r'''set -e
: "${MOD_NAME:?}"
export LC_ALL=C
'''
SNAPSHOT_SQL = "/tmp/psm-e2e-snapshot.sql"      # di luar docroot; terpisah dari baseline Lapis 5
SNAPSHOT_FILES = "/tmp/psm-e2e-snapshot.files"
CURRENT_FILES = "/tmp/psm-e2e-current.files"
NEW_FILES = "/tmp/psm-e2e-new.files"
# Daftar docroot (file & folder; nama ber-newline tak didukung), dijalankan DI docroot.
_LIST_DOCROOT_SH = r'''find . \( -path ./var/cache -o -path "./modules/$MOD_NAME" \) -prune -o -print > /tmp/psm-e2e-list.tmp
sort /tmp/psm-e2e-list.tmp > @OUT@
'''
_DB_CREDS = "-h $DBH -P $DBPORT -u $DBU -p$DBPW"


def _list_docroot_sh(out):
    return _LIST_DOCROOT_SH.replace("@OUT@", out)


def snapshot_db_sh(prelude):
    """`snapshot-db`: dump DB (--databases: dump-nya membuat ulang DB) + daftar docroot."""
    return (_SH_HEAD + prelude + f"cd {PS_DOCROOT}\n"
            + f"$MYSQLDUMP_BIN {_DB_CREDS} --single-transaction --routines --databases $DBN"
              f" > {SNAPSHOT_SQL}\n"
            + _list_docroot_sh(SNAPSHOT_FILES) + "echo PSM_SNAPSHOT_DB_OK\n")


def reset_db_sh(prelude):
    """`reset-db`: DROP DATABASE lalu muat dump (yang membuat ulang DB). Dump harus ada dulu."""
    return (_SH_HEAD + prelude + f"[ -s {SNAPSHOT_SQL} ]\n"
            + f'$MYSQL_BIN {_DB_CREDS} -e "DROP DATABASE \\`$DBN\\`"\n'
            + f"$MYSQL_BIN {_DB_CREDS} < {SNAPSHOT_SQL}\n" + "echo PSM_RESET_DB_OK\n")


# `reset-files`: buang modules/<mod>, hapus apa pun yang lahir sesudah snapshot, kosongkan
# var/cache (foldernya tetap), lalu salin module segar TANPA install — DB yang dipulihkan sudah
# memuat state ter-install. File docroot yang ADA saat snapshot lalu diubah tak dipulihkan.
RESET_FILES_SH = (_SH_HEAD + f"cd {PS_DOCROOT}\n" + 'rm -rf "modules/$MOD_NAME"\n'
                  + _list_docroot_sh(CURRENT_FILES)
                  + f"comm -13 {SNAPSHOT_FILES} {CURRENT_FILES} > {NEW_FILES}\n"
                  + f'while IFS= read -r p; do rm -rf -- "$p"; done < {NEW_FILES}\n'
                  + "if [ -d var/cache ]; then find var/cache -mindepth 1 -maxdepth 1"
                    " -exec rm -rf -- {} +; fi\n"
                  + 'cp -r /ps-module-src "modules/$MOD_NAME"\n' + "echo PSM_RESET_FILES_OK\n")

# `reset-opcache`: USR2 ke master php-fpm — SATU proses ber-comm php-fpm* yang induknya (PPid
# dari /proc/<pid>/status; 0 / tak terbaca = bukan php-fpm) bukan php-fpm. Kandidat yang
# comm/status-nya lenyap dilewati. php-fpm jalan tapi master tak tunggal = gagal; tanpa
# php-fpm: `apachectl -k graceful`; selain itu gagal.
RESET_OPCACHE_SH = _SH_HEAD + r'''any=0; n=0; master=""
for d in /proc/[0-9]*; do
  p=${d#/proc/}
  c=$(cat "/proc/$p/comm" 2>/dev/null) || continue
  case "$c" in php-fpm*) ;; *) continue ;; esac
  any=1
  pp=$(sed -n 's/^PPid:[[:space:]]*//p' "/proc/$p/status" 2>/dev/null) || continue
  [ -n "$pp" ] || continue
  pc=""
  if [ "$pp" != "0" ]; then pc=$(cat "/proc/$pp/comm" 2>/dev/null) || pc=""; fi
  case "$pc" in php-fpm*) continue ;; esac
  master=$p; n=$((n + 1))
done
if [ "$any" = "1" ]; then
  if [ "$n" != "1" ]; then echo "master php-fpm tak tunggal ($n)" >&2; exit 1; fi
  kill -USR2 "$master"
elif command -v apachectl >/dev/null 2>&1; then
  apachectl -k graceful
else
  echo "tak ada php-fpm maupun apachectl" >&2; exit 1
fi
echo PSM_RESET_OPCACHE_OK
'''

# DB_PRELUDE dimiliki ps-scenario-run.py (Lapis 5); dimuat MALAS by-path seperti _plan_layers,
# hanya DB_PRELUDE yang dibaca (fl milik ps-e2e-run tetap yang menjalankan _exec/phase).
_SCENARIO_RUN = {}


def _db_prelude():
    if "prelude" not in _SCENARIO_RUN:
        path = Path(__file__).resolve().parent / "ps-scenario-run.py"
        spec = importlib.util.spec_from_file_location("ps_scenario_run", path)
        if not (spec and spec.loader):
            raise ImportError(f"tak bisa memuat sibling {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _SCENARIO_RUN["prelude"] = module.DB_PRELUDE
    return _SCENARIO_RUN["prelude"]


def _step_error(sub_phase, reason):
    """Entri errors `<sub-phase>: <alasan>` — alasan dipadatkan, maks 200 karakter."""
    return f"{sub_phase}: {' '.join(str(reason).split())[:200]}"


def container_step(session, name, script_fn, timeout, mod_name):
    """Satu sub-fase snapshot/reset = SATU fl._exec di fase `name` (timeout `--timeout`, env
    MOD_NAME). Return None bila sukses, else entri errors. Gagal = timeout, exception (memuat
    DB_PRELUDE termasuk, SystemExit juga), exit non-nol, atau sentinel `PSM_<SUB_PHASE>_OK`
    absen; `ph.status` = `timeout` saat timeout, else `gagal` (END & boot_phases menunjukkannya).
    """
    sentinel = "PSM_" + name.upper().replace("-", "_") + "_OK"
    with fl.phase(name, timeout) as ph:
        try:
            cp = fl._exec(session, {"MOD_NAME": mod_name}, script_fn(), timeout)
        except subprocess.TimeoutExpired:
            ph.status = "timeout"
            return _step_error(name, f"timeout ({timeout}s)")
        except (Exception, SystemExit) as e:  # noqa: BLE001 — sub-fase gagal, bukan crash run
            ph.status = "gagal"
            return _step_error(name, f"{type(e).__name__}: {e}")
        if cp.returncode != 0 or sentinel not in (cp.stdout or ""):
            ph.status = "gagal"
            tail = " ".join((cp.stderr or cp.stdout or "").split())[-150:]
            why = f"rc={cp.returncode}" if cp.returncode != 0 else f"{sentinel} tak tercetak"
            return _step_error(name, f"{why} {tail}".strip())
    return None


def snapshot_db(session, mod_name, timeout):
    """Fase `snapshot-db` sesudah `warmup-bo` (hanya boot yang men-drive > 1 engine)."""
    return container_step(session, "snapshot-db", lambda: snapshot_db_sh(_db_prelude()),
                          timeout, mod_name)


def _wait_http_phase(fo, startup_timeout, fail_status=None):
    """Fase `wait-http` boot pertama, dipakai ulang rutin reset (yang memberi `fail_status`
    `gagal` saat tak ada respons sama sekali). Return (ok, status, responded)."""
    with fl.phase("wait-http", startup_timeout, fo) as ph:
        reach_ok, rstatus, responded = wait_http(fo + "/", startup_timeout)
        if not responded and fail_status:
            ph.status = fail_status
    return reach_ok, rstatus, responded


def _warmup_bo(bo, scenarios, startup_timeout):
    """Warm-up BO sebelum browser men-drive (verified: login cold-container 1.7/8 flaky karena
    kompilasi halaman login lambat) — best-effort, gagal tak memvonis."""
    if _needs_bo(scenarios):
        with fl.phase("warmup-bo", startup_timeout):
            wait_http(f"{bo}/index.php?controller=AdminLogin", startup_timeout)


def reset_routine(session, mod_name, fo, bo, scenarios, *, op_timeout, startup_timeout,
                  full_ver=""):
    """Rutin reset BERSAMA ke snapshot: health (`healthy`), `reset-db`, `reset-files`,
    `reset-opcache`, `wait-http` (tanpa respons = gagal), `warmup-bo` (best-effort; 5xx juga
    tetap best-effort seperti boot pertama). Berhenti di kegagalan pertama. Return None bila
    sukses, else entri errors (`health: <status>`, `wait-http: no response`, `<sub>: <alasan>`)
    yang juga dicetak ke stderr. Tak pernah menyentuh `errors` level-versi.
    """
    status = fl._health_status(session["ps_container"])
    err = None if status == "healthy" else _step_error("health", status)
    steps = (("reset-db", lambda: reset_db_sh(_db_prelude())),
             ("reset-files", lambda: RESET_FILES_SH),
             ("reset-opcache", lambda: RESET_OPCACHE_SH))
    for name, fn in steps:
        if err is not None:
            break
        err = container_step(session, name, fn, op_timeout, mod_name)
    if err is None:
        _ok, _st, responded = _wait_http_phase(fo, startup_timeout, fail_status="gagal")
        if responded:
            _warmup_bo(bo, scenarios, startup_timeout)
        else:
            err = "wait-http: no response"
    if err is not None:
        print(f"versi {full_ver}: reset ke snapshot gagal — {err}", file=sys.stderr)
    return err


# ---------------------------------------------------------------------------
# Sel & pass per mode (proses versi)
# ---------------------------------------------------------------------------
def _add_note(res, engines, text):
    """Catatan per-browser: daftar lama (run langsung) + sel engine bersangkutan saja. Engine
    yang di-drop probe tak punya sel, jadi catatannya tak mendarat di sel mana pun."""
    res["browser_notes"].append(text)
    for e in engines:
        if e in res["cells"]:
            res["cells"][e]["browser_notes"].append(text)


def _launch_note(res, engine, launch_error, headed):
    # Gagal luncur SATU engine = masalah per-browser -> browser_notes (BUKAN errors). Jangan
    # cemari kanal infra version-level: temuan konklusif engine lain harus tetap.
    _add_note(res, [engine],
              f"browser {engine} gagal diluncurkan: {launch_error} "
              f"(jalankan 'playwright install {engine}'{'' if not headed else ' / --headed butuh display'})")


def _child_state(cell, reason, errors=None):
    """Sel ber-state yang DISET anak (CHILD_SET_REASONS): inconclusive + reason; `errors` sel
    hanya utk `parallel-unconfirmed`/`sequential-reset` (sub-fase yang gagal)."""
    cell.update(state="inconclusive", conclusive=False, reason=reason)
    if errors is not None:
        cell["errors"] = list(errors)
    return cell


def _finding_key(item):
    return (item.get("scenario"), item.get("step"), item.get("action"))


def _unconfirmed(cell, entry):
    """Temuan paralel yang tak bisa dikonfirmasi: `findings: []`, temuan itu ke `parallel_only`,
    entri kegagalan di `errors` sel; field lain pass paralel dipertahankan."""
    cell["parallel_only"] = list(cell.get("findings") or [])
    cell["findings"] = []
    _child_state(cell, "parallel-unconfirmed", [entry])


def _merge_rerun(cell, eng, full_ver, scenarios, finished):
    """Gabung `rerun-seq` ke sel (Confirmation merge): pass rerun memasok scenarios_run,
    authored_assertions, bo_authed, launch_error, console_errors, screenshots, finished_at;
    started_at & scenario_spans tetap dari lockstep. `findings` = temuan rerun; temuan paralel
    yang (skenario, step, aksi)-nya tak ada di sana pindah ke `parallel_only`; `inconclusive` =
    pass pertama ∪ rerun (dedup pada kunci itu)."""
    first_findings = list(cell.get("findings") or [])
    first_inc = list(cell.get("inconclusive") or [])
    _fill_cell(cell, eng, full_ver, scenarios)
    cell["finished_at"] = finished
    confirmed = {_finding_key(f) for f in cell["findings"]}
    cell["parallel_only"] = [f for f in first_findings if _finding_key(f) not in confirmed]
    seen, merged = set(), []
    for item in first_inc + cell["inconclusive"]:
        if _finding_key(item) not in seen:
            seen.add(_finding_key(item))
            merged.append(item)
    cell["inconclusive"] = merged


def _confirmation_plan(cells, first, scenarios):
    """Pass sekuensial yang dibutuhkan tiap engine ber-hasil-paralel sah (`first`: tanpa crash /
    launch_error). Return ({engine: 'fallback'|'rerun'}, engine yang login BO-nya sukses).

    fallback = login BO-nya gagal (skenario butuh BO, bo_authed false) sementara engine lain
    sukses; rerun = ia punya temuan, atau men-drive (scenario_spans lockstep) skenario yang
    bertemuan di pass paralel engine mana pun (pass pertama yang dibuang termasuk)."""
    needs_bo = _needs_bo(scenarios)
    login_ok = [e for e, eng in first.items() if eng.get("bo_authed")]
    bad = {f.get("scenario") for e in first for f in (cells[e].get("findings") or [])}
    plan = {}
    for e, eng in first.items():
        if needs_bo and not eng.get("bo_authed") and login_ok:
            plan[e] = "fallback"
        elif cells[e].get("findings") or set(cells[e].get("scenario_spans") or {}) & bad:
            plan[e] = "rerun"
    return plan, login_ok


def _confirm_ctx(ctx, engine, ver_shot_dir):
    """ctx pass konfirmasi: `{browser}` = `<engine>-seq`, screenshot ke `<shots>/<ver>/<engine>-seq`."""
    c = dict(ctx, bo_authed=False, browser_token=f"{engine}-seq")
    c["screenshot_dir"] = (_mkdir_best_effort(Path(ver_shot_dir) / f"{engine}-seq")
                           if ver_shot_dir else None)
    return c


def _drive_parallel(res, full_ver, browsers, scenarios, ctx, *, headed, ver_shot_dir, reset,
                    snapshot_err):
    """Mode paralel: pass lockstep lewat worker, lalu pass konfirmasi sekuensial (Design Notes
    CAP-7 > Confirmation passes/merge). `reset()` = rutin reset bersama; `snapshot_err` = entri
    kegagalan `snapshot-db` (pass lockstep tetap jalan, tiap engine yang butuh pass jadi
    `parallel-unconfirmed`)."""
    runs = run_parallel_workers(full_ver, browsers, scenarios, ctx, ver_shot_dir=ver_shot_dir,
                                headed=headed)
    first = {}
    for engine in browsers:
        cell, run = res["cells"][engine], runs.get(engine) or {}
        parsed = run.get("result")
        if parsed is None:
            why = run.get("spawn_error") or f"exit code {run.get('rc')}"
            _child_state(cell, "crash")
            _add_note(res, [engine], f"worker {engine} keluar tanpa hasil terbaca ({why}) — sel crash")
            continue
        eng = parsed["result"]
        _fill_cell(cell, eng, full_ver, scenarios)
        cell.update(started_at=parsed["started_at"], finished_at=parsed["finished_at"],
                    scenario_spans=parsed["scenario_spans"], parallel_only=[])
        if eng.get("launch_error"):
            _launch_note(res, engine, eng["launch_error"], headed)
        else:
            first[engine] = eng

    plan, login_ok = _confirmation_plan(res["cells"], first, scenarios)
    fail_entry = snapshot_err
    for engine in browsers:
        kind = plan.get(engine)
        if kind is None:
            continue
        cell = res["cells"][engine]
        if fail_entry is not None:  # snapshot / reset sebelumnya gagal: tak ada reset lagi
            _unconfirmed(cell, fail_entry)
            continue
        cctx = _confirm_ctx(ctx, engine, ver_shot_dir)
        if kind == "rerun":
            with fl.phase(f"rerun-seq:{engine}", None,
                          f"konfirmasi sekuensial: reset + {len(scenarios)} skenario") as ph:
                fail_entry = reset()
                if fail_entry is not None:
                    ph.status = f"{fail_entry.split(':', 1)[0]}-failed"
                else:
                    eng = drive_engine(engine, scenarios, cctx, headed=headed)
                    finished = utc_now()
            if fail_entry is not None:
                _unconfirmed(cell, fail_entry)
                continue
            _merge_rerun(cell, eng, full_ver, scenarios, finished)
        else:
            fail_entry = reset()
            if fail_entry is not None:
                _unconfirmed(cell, fail_entry)
                continue
            msg = (f"fallback login BO: login {engine} gagal di pass paralel sementara "
                   f"{', '.join(login_ok)} sukses — pass pertama dibuang, {engine} di-drive "
                   "ulang sendiri")
            print(f"versi {full_ver}: {msg}", file=sys.stderr)
            with fl.phase(f"browser:{engine}", None, msg):
                eng = drive_engine(engine, scenarios, cctx, headed=headed)
            finished = utc_now()
            _fill_cell(cell, eng, full_ver, scenarios)  # temuan & inconclusive pass ini saja
            cell["finished_at"] = finished
        if eng.get("launch_error"):
            _launch_note(res, engine, eng["launch_error"], headed)


def sequential_notice(engines):
    """Catatan mode sekuensial (stderr sekali per run; detail START `browser:` pertama tiap versi)."""
    return (f"mode browser sekuensial: {', '.join(engines)} di-drive berurutan dalam satu boot, "
            "reset ke snapshot sebelum tiap engine berikutnya; sesudah engine `fail`, engine "
            "berikutnya not-run")


def _drive_sequential(res, full_ver, browsers, scenarios, ctx, *, headed, sequential_browsers,
                      reset, snapshot_err):
    """Satu engine, atau fallback `--sequential-browsers`: engine di-drive dalam proses, urut.

    Fallback dgn > 1 engine: reset ke snapshot sebelum tiap engine sesudah yang pertama;
    snapshot/reset gagal = engine itu & sisanya `sequential-reset` (snapshot gagal: semua).
    Fail-fast: sesudah `fail` satu engine, sisanya `not-run` tanpa reset. Pass pertama tiap
    engine mencatat `scenario_spans`.
    """
    notice = sequential_notice(browsers) if sequential_browsers and len(browsers) > 1 else ""
    fail_entry = snapshot_err
    for idx, engine in enumerate(browsers):
        if fail_entry is None and idx > 0:
            fail_entry = reset()
        if fail_entry is not None:
            for rest in browsers[idx:]:
                res["cells"][rest] = _child_state(_new_cell(), "sequential-reset", [fail_entry])
            break
        cell = res["cells"][engine]
        spans = ScenarioSpans()
        detail = f"{len(scenarios)} skenario" + (f"; {notice}" if idx == 0 and notice else "")
        cell["started_at"] = utc_now()
        with fl.phase(f"browser:{engine}", None, detail):
            eng = drive_engine(engine, scenarios, dict(ctx, scenario_hook=spans), headed=headed)
        cell["finished_at"] = utc_now()
        _fill_cell(cell, eng, full_ver, scenarios)
        if eng.get("launch_error"):
            cell["scenario_spans"] = {}
            _launch_note(res, engine, eng["launch_error"], headed)
            continue
        cell["scenario_spans"] = spans.spans
        if sequential_browsers and _engine_failed(res, engine):
            # Fail-fast antar-engine (cell-contract.md > Runner > Fail-fast): engine
            # berikutnya tak dimulai (tanpa reset); selnya not-run dgn sel penyebab.
            why = f"fail-fast after {full_ver}:{engine}"
            for rest in browsers[idx + 1:]:
                res["cells"][rest] = _not_run_cell(why)
            break


def _counted(cell):
    """Engine yang pass penghitungnya jalan tanpa launch_error (bukan crash / sequential-reset /
    not-run / tak ter-drive) — dasar field lama level-versi."""
    if cell.get("state") == "not-run" or cell.get("reason") in ("crash", "sequential-reset"):
        return False
    return cell.get("scenarios_run") is not None and not cell.get("launch_error")


def _rollup(res):
    """Field lama level-versi dibangun ulang dari sel FINAL (semua mode): `browsers`, `findings`,
    `inconclusive`, `screenshots`, `console_errors`, `authored_assertions`, `pass` (ada engine,
    tanpa temuan, tanpa sel parallel-unconfirmed), `skipped_browser` (tak ada engine teruji).

    Error console SENGAJA TIDAK masuk `browser_notes`: field itu memikul CELAH CAKUPAN yang
    memang menjatuhkan `ready`; error console adalah OBSERVASI yang tak memblok (yang mau
    menegakkan memakai aksi `expect_no_console_error`, konklusif per skenario).
    """
    engines = [e for e, c in res["cells"].items() if _counted(c)]
    cells = [res["cells"][e] for e in engines]
    res["browsers"] = engines
    res["findings"] = [f for c in cells for f in (c.get("findings") or [])]
    res["inconclusive"] = [i for c in cells for i in (c.get("inconclusive") or [])]
    res["screenshots"] = [s for c in cells for s in (c.get("screenshots") or [])]
    res["console_errors"] = sum(c.get("console_errors") or 0 for c in cells)
    res["authored_assertions"] = sum(c.get("authored_assertions") or 0 for c in cells)
    unconfirmed = any(c.get("reason") == "parallel-unconfirmed" for c in res["cells"].values())
    res["pass"] = bool(engines) and not res["findings"] and not unconfirmed
    res["skipped_browser"] = not engines


def run_one_version(module_dir, mod_name, full_ver, tag, browsers, scenarios, *,
                    scenario_notes=(), **kwargs):
    """Satu boot versi + durasi fasenya (cell-contract.md > Phase timings).

    Satu sink durasi per panggilan: diaktifkan di sini, lalu `boot_wall_clock` diukur dari
    masuk sampai fungsi dalam kembali — SESUDAH `_teardown` di `finally`-nya selesai, jadi
    masa hidup container (browser termasuk) terhitung penuh. Fase sel (`browser:`,
    `lock-wait:`, `barrier-wait:`, `rerun-seq:` + engine, `#n`) masuk ke `phase_durations` sel
    engine itu, sisanya ke `boot_phases` (`{}` bila tak ada fase yang jalan). `scenario_notes`
    (catatan spec level-run) disalin ke tiap versi.
    """
    t0 = time.monotonic()
    sink = fl.timing_activate()
    try:
        res = _run_one_version_inner(module_dir, mod_name, full_ver, tag, browsers, scenarios,
                                     **kwargs)
    finally:
        wall = time.monotonic() - t0
        fl.timing_deactivate()
    timing = sink.as_dict()
    res["boot_phases"] = timing["boot_phases"]
    res["boot_wall_clock"] = round(wall, 3)
    res["scenario_notes"] = list(scenario_notes)
    for engine, cell in res["cells"].items():
        if cell.get("state") == "not-run":
            continue  # engine tak pernah dimulai: phase_durations tetap null
        cell["phase_durations"] = timing["phase_durations"].get(engine, {})
    return res


def _run_one_version_inner(module_dir, mod_name, full_ver, tag, browsers, scenarios, *,
                           requested_browsers=None, orchestrator, db_image, ps_domain, admin_path,
                           admin_email, admin_password, startup_timeout, op_timeout, nav_timeout,
                           allow_pull, headed=False, screenshot_dir=None, slot_cost=1,
                           sequential_browsers=False):
    """Bangun flashlight (port publish) utk satu versi, install module, drive tiap browser.

    `browsers` = engine yang benar-benar akan di-drive (binary terpasang); `requested_browsers`
    = daftar diminta penuh (utk laporan coverage). Kegagalan infrastruktur SELURUH versi
    (image/DB/boot/install/http) → `errors` (tak konklusif, tak memblok). Masalah PER-BROWSER
    (binary absent / gagal luncur satu engine) → `browser_notes` (coverage, TAK memblok & TAK
    membatalkan temuan konklusif engine lain — itu bug false-pass yang harus dihindari).
    Assertion konklusif gagal saat ≥1 browser jalan & module ter-install → temuan yang memblok.

    Selain field lama (run langsung, bukan bukti), tiap versi memancarkan field level-versi
    untuk rekaman histori (`run_id`, `boot`, `boot_id`, `image_tag`, `browser_mode`, `errors`,
    `install`, `boot_log`) dan `cells.<engine>` untuk tiap engine yang lolos probe, di setiap
    jalur return (cell-contract.md > Evidence record > Producers).

    Mode (CAP-7): >= 2 engine tanpa `sequential_browsers` = paralel (worker per engine +
    konfirmasi sekuensial), selain itu in-process berurutan. Boot yang men-drive > 1 engine
    mengambil `snapshot-db` sesudah `warmup-bo`.
    """
    requested_browsers = requested_browsers if requested_browsers is not None else list(browsers)
    image_ref = f"{fl.IMAGE}:{tag}"
    parallel = len(browsers) >= 2 and not sequential_browsers
    fl.progress_version(full_ver)
    res = {"version": full_ver, "tag": tag, "image": image_ref, "orchestrator": None,
           "browsers": [], "install": None, "findings": [], "inconclusive": [],
           "errors": [], "browser_notes": [], "console_errors": 0, "screenshots": [],
           "skipped_browser": False, "pass": False,
           "run_id": fl.RUN_ID, "boot": "cold", "boot_id": fl.RUN_ID, "image_tag": tag,
           "browser_mode": "parallel" if parallel else "sequential", "boot_phases": {},
           "boot_wall_clock": None, "boot_log": None,
           "cells": {e: _new_cell() for e in browsers}}

    # Engine diminta tapi binary-nya tak lolos probe (di-drop di main) — catat coverage, tak memblok.
    probe_missed = [e for e in requested_browsers if e not in browsers]
    if probe_missed:
        _add_note(res, probe_missed,
             f"engine tak dijalankan (binary belum di-'playwright install'): {','.join(probe_missed)}")

    # Gerbang browser DULU (termurah): tanpa binary browser sama sekali, boot container sia-sia.
    if not browsers:
        res["skipped_browser"] = True
        res["browser_notes"].append(
            "tak ada binary browser terpasang — jalankan 'playwright install chromium firefox'")
        return res

    mode = orchestrator
    if mode == "auto":
        mode = "compose" if fl.compose_available() else "manual"
    elif mode == "compose" and not fl.compose_available():
        res["errors"].append("orchestrator=compose diminta tapi 'docker compose' tak tersedia")
        return res
    res["orchestrator"] = mode

    # Gerbang unduh image (flashlight multi-GB + DB) — degrade jujur bila tak diizinkan.
    missing = [i for i in (image_ref, db_image) if not fl.image_present(i)]
    if missing:
        if not allow_pull:
            res["skipped_image"] = True
            res["errors"].append(
                f"image belum ada lokal & pull tak diizinkan: {', '.join(missing)} — lewati versi ini")
            return res
        for i in missing:
            perr = fl.pull_image(i, op_timeout)
            if perr:
                res["errors"].append(perr[:300])
                return res

    # Port host dipilih dinamis SEBELUM boot: PS_DOMAIN & publish memakai port yang SAMA
    # (PrestaShop membangun URL absolut dari PS_DOMAIN; Playwright mengikuti link nyata).
    # Basis dari ps_domain config, jatuh ke port ephemeral bila terpakai → dua sesi paralel
    # tak rebutan bind. Satu retry menutup jendela race (TOCTOU): bila docker gagal bind
    # karena tabrakan port, pilih port ephemeral baru lalu ulang sekali.
    preferred_port = host_port_from_domain(ps_domain)
    host = host_from_domain(ps_domain)  # host dipertahankan; hanya port yang mengambang
    session, err, ps_domain_eff = None, None, None
    for attempt in range(2):
        host_port = pick_free_host_port(preferred_port if attempt == 0 else 0)
        ps_domain_eff = f"{host}:{host_port}"
        publish = f"{host_port}:{CONTAINER_HTTP_PORT}"
        if mode == "compose":
            session, err = fl._bring_up_compose(module_dir, full_ver, image_ref, db_image,
                                                ps_domain_eff, op_timeout, publish,
                                                slot_cost=slot_cost)
        else:
            session, err = fl._bring_up_manual(module_dir, image_ref, db_image, ps_domain_eff,
                                               startup_timeout, publish, slot_cost=slot_cost)
        if err and _is_port_conflict(err) and attempt == 0:
            fl._teardown(session)  # port disambar sesi lain di jendela race → coba port lain
            continue
        break
    res["ps_domain"] = ps_domain_eff
    if err:
        res["errors"].append(err)
        fl._teardown(session)
        return res

    try:
        ok, status = fl.wait_healthy(session["ps_container"], startup_timeout)
        if not ok:
            res["errors"].append(f"flashlight tak jadi 'healthy' ({status}) — DB/boot gagal, degrade jujur")
            res["boot_log"] = fl._logs(session["ps_container"])[-1500:]
            return res

        install, ierr = install_module(session, mod_name, op_timeout)
        res["install"] = {"ok": install["ok"], "no_console": install.get("no_console", False),
                          "no_psroot": install.get("no_psroot", False),
                          "no_verdict": install.get("no_verdict", False)}
        if ierr or not install["ok"]:
            # Install adalah wilayah vonis Lapis 2; di sini cuma prasyarat E2E → tak konklusif.
            # Bedakan infra (image tanpa bin/console / PS root, atau installer tak mencapai
            # vonisnya) dari module ditolak core: keduanya tak memblok di sini, tapi alasannya
            # harus jujur, bukan disamarkan.
            if install.get("no_console") or install.get("no_psroot"):
                res["errors"].append(
                    "image tak punya bin/console / PS root — module tak bisa di-install, E2E tak bisa menilai perilaku")
            elif install.get("no_verdict"):
                res["errors"].append(
                    "installer tak mencapai vonis di container (exec/output gagal) — E2E tak bisa menilai perilaku")
            else:
                res["errors"].append(
                    ierr or "module gagal install — E2E tak bisa menilai perilaku (Lapis 2 flashlight yang memvonis install)")
            return res

        fo, bo = base_urls(ps_domain_eff, admin_path)
        reach_ok, rstatus, responded = _wait_http_phase(fo, startup_timeout)
        if not reach_ok and not responded:
            # Tak ada respons TCP sama sekali → port publish / boot memang gagal (infra jujur).
            res["errors"].append(f"PS tak terjangkau di {fo} ({rstatus}) — port publish/boot gagal")
            return res
        # reach_ok False TAPI responded True (mis. 5xx bertahan): nginx+kernel menjawab, port
        # terpublish → JANGAN return. Biarkan smoke universal (goto '/' + expect_no_fatal)
        # men-drive & memvonis toko yang rusak — itu justru yang Lapis 4 ada untuk menangkap.

        # Warm-up BO sebelum browser men-drive — login tetap best-effort di _bo_login (+ retry).
        _warmup_bo(bo, scenarios, startup_timeout)

        # Snapshot hanya bila boot ini men-drive > 1 engine (paralel atau fallback sekuensial).
        # Gagal: dicetak SEKALI di sini, tak pernah ke `errors` level-versi.
        snapshot_err = None
        if len(browsers) > 1:
            snapshot_err = snapshot_db(session, mod_name, op_timeout)
            if snapshot_err is not None:
                print(f"versi {full_ver}: snapshot gagal — {snapshot_err}", file=sys.stderr)

        ver_shot_dir = None
        if screenshot_dir:
            # gagal buat folder -> lewati screenshot, jangan gagalkan run
            ver_shot_dir = _mkdir_best_effort(
                Path(screenshot_dir) / re.sub(r"[^A-Za-z0-9_.-]", "_", full_ver))
        ctx = {"fo": fo, "bo": bo, "mod": mod_name, "nav_timeout": nav_timeout,
               "admin_email": admin_email, "admin_password": admin_password, "bo_authed": False,
               "screenshot_dir": ver_shot_dir}

        def reset():
            return reset_routine(session, mod_name, fo, bo, scenarios, op_timeout=op_timeout,
                                 startup_timeout=startup_timeout, full_ver=full_ver)
        if parallel:
            _drive_parallel(res, full_ver, browsers, scenarios, ctx, headed=headed,
                            ver_shot_dir=ver_shot_dir, reset=reset, snapshot_err=snapshot_err)
        else:
            _drive_sequential(res, full_ver, browsers, scenarios, ctx, headed=headed,
                              sequential_browsers=sequential_browsers, reset=reset,
                              snapshot_err=snapshot_err)
        # Cakupan, temuan & artefak visual level-versi DIHITUNG dari sel final (semua mode).
        _rollup(res)
        return res
    finally:
        fl._teardown(session)


# Aturan State per sel dimiliki ps-plan-layers (derive_state, dipakai ps-run-layer saat merge).
# Dimuat MALAS di sini: ps-plan-layers memuat ps-e2e-run hanya di dalam _e2e_scenario_notes,
# jadi tak ada siklus impor, dan run langsung yang skipped tak perlu memuatnya sama sekali.
_PLAN_LAYERS = {}


def _plan_layers():
    if "mod" not in _PLAN_LAYERS:
        path = Path(__file__).resolve().parent / "ps-plan-layers.py"
        spec = importlib.util.spec_from_file_location("ps_plan_layers", path)
        if not (spec and spec.loader):
            raise ImportError(f"tak bisa memuat sibling {path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        _PLAN_LAYERS["mod"] = module
    return _PLAN_LAYERS["mod"]


def cell_state(vres, engine):
    """State-rule satu sel yang dipancarkan, dgn field level-versi (`errors`, `install`)
    digabung seperti ps-run-layer menggabungkannya ke rekaman. Return {state, conclusive, reason}.
    Sel ber-state yang DISET anak dipertahankan apa adanya (tanpa derive_state), seperti di
    ps-run-layer: `not-run` (fail-fast antar-engine) dan `inconclusive` ber-reason `crash`,
    `parallel-unconfirmed` atau `sequential-reset`."""
    cell = vres.get("cells", {}).get(engine) or {}
    if cell.get("state") == "not-run" or (cell.get("state") == "inconclusive"
                                          and cell.get("reason") in CHILD_SET_REASONS):
        return {"state": cell["state"], "conclusive": False, "reason": cell.get("reason")}
    merged = {"errors": vres.get("errors"), "install": vres.get("install")}
    merged.update(cell)
    return _plan_layers().derive_state(merged, engine)


def _engine_failed(vres, engine):
    """`fail` engine ini SEKARANG, di tengah loop engine. Sink durasi baru disalin ke sel
    sesudah _run_one_version_inner kembali, jadi tanpa salinan ini tiap sel terbaca
    `not-driven`: salin dulu `browser:<engine>` dari sink aktif, baru nilai dgn cell_state."""
    sink = fl.timing_current()
    if sink is not None:
        vres["cells"][engine]["phase_durations"] = dict(sink.phase_durations.get(engine, {}))
    return cell_state(vres, engine)["state"] == "fail"


def exit_code(result):
    """Exit code run yang tak skipped (cell-contract.md > Runner).

    3 bila ada sel `fail` (apa pun state engine lain); 0 bila tiap versi memancarkan ≥1 sel
    dan setiap sel `pass`; selain itu 1 (infra / sel inconclusive / versi tanpa sel).
    """
    states, every_version_has_cells = [], True
    for vres in result.get("versions", {}).values():
        cells = vres.get("cells") or {}
        if not cells:
            every_version_has_cells = False
        states.extend(cell_state(vres, e)["state"] for e in cells)
    if "fail" in states:
        return 3
    if states and every_version_has_cells and all(s == "pass" for s in states):
        return 0
    return 1


def _emit(result, output):
    out = json.dumps(result, indent=2, ensure_ascii=False)
    if output:
        Path(output).write_text(out, encoding="utf-8")
        print(f"ditulis: {output}", file=sys.stderr)
    else:
        print(out)


def main():
    ap = argparse.ArgumentParser(
        description="Lapis 4 — uji perilaku browser (E2E) module di Docker flashlight, per versi & browser.",
        epilog=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("module_path", help="Path folder module PrestaShop")
    ap.add_argument("--versions", default="1.7.8,8.1,9.1", help="Versi target dipisah koma")
    ap.add_argument("--config", help="JSON hasil resolve-psm-config.py — setelan keluarga (tag map, image DB, ps-domain, orchestrator, timeout, versi, browser) diisi dari sini untuk argumen yang tak diberikan eksplisit. Flag eksplisit selalu menang.")
    ap.add_argument("--browsers", default=DEFAULT_BROWSERS,
                    help=f"Engine Playwright dipisah koma (default: {DEFAULT_BROWSERS}; didukung: {','.join(SUPPORTED_ENGINES)})")
    ap.add_argument("--engines",
                    help="Engine versi ini, diset ps-run-layer (mode histori). Menang atas --browsers "
                         "dan --config; engine tak didukung / daftar kosong = exit 2.")
    ap.add_argument("--tag-map", default="", help="Peta LENGKAP versi=tag dipisah koma (MENGGANTI default)")
    ap.add_argument("--extra-tag-map", default="", help="Tag TAMBAHAN versi=tag (MENAMBAH di atas peta)")
    ap.add_argument("--orchestrator", choices=["auto", "compose", "manual"], default=fl.DEFAULT_ORCHESTRATOR,
                    help="Cara menghidupkan DB+flashlight (default: auto)")
    ap.add_argument("--db-image", default=fl.DEFAULT_DB_IMAGE, help=f"Image server DB (default: {fl.DEFAULT_DB_IMAGE})")
    ap.add_argument("--ps-domain", default=fl.DEFAULT_PS_DOMAIN,
                    help=f"PS_DOMAIN flashlight — HOST yang di-drive Playwright; PORT-nya dipilih "
                         f"dinamis per sesi (bebas-bind) sehingga port di sini hanya preferensi "
                         f"(default: {fl.DEFAULT_PS_DOMAIN})")
    ap.add_argument("--admin-path", default=DEFAULT_ADMIN_PATH, help=f"Folder BO flashlight (default: {DEFAULT_ADMIN_PATH})")
    ap.add_argument("--admin-email", default=DEFAULT_ADMIN_EMAIL, help="Email admin BO (best-effort login)")
    ap.add_argument("--admin-password", default=DEFAULT_ADMIN_PASSWORD, help="Password admin BO (best-effort login)")
    ap.add_argument("--startup-timeout", type=int, default=fl.DEFAULT_STARTUP_TIMEOUT,
                    help=f"Maks detik menunggu container healthy / PS terjangkau (default: {fl.DEFAULT_STARTUP_TIMEOUT})")
    ap.add_argument("--nav-timeout", type=int, default=DEFAULT_NAV_TIMEOUT_S,
                    help=f"Timeout per navigasi/aksi Playwright, detik (default: {DEFAULT_NAV_TIMEOUT_S})")
    ap.add_argument("--allow-image-pull", action="store_true",
                    help="Izinkan unduh image bila belum ada lokal (default: lewati versi itu, degrade jujur).")
    ap.add_argument("--headed", action="store_true",
                    help="Tampilkan browser (headless=False) utk inspeksi visual manual — butuh display. "
                         "Opt-in eksplisit; JANGAN dipakai di headless/CI. Tanpa display -> skipped_browser.")
    ap.add_argument("--screenshot-dir", help="Bila diset, simpan screenshot per halaman & pada kegagalan ke "
                                             "folder ini (artefak visual '<ver>/<engine>-<scenario>-...png').")
    ap.add_argument("--timeout", type=int, default=600, help="Timeout operasi per versi (detik): pull/up/exec")
    ap.add_argument("-o", "--output", help="File output JSON (default: stdout)")
    ap.add_argument("--run-id", help="Diset ps-run-layer: RUN_ID klaim slot [0-9a-f]{12} — dipakai "
                                     "untuk label psm.run, registry job & log kemajuan")
    ap.add_argument("--slot-cost", default=None,
                    help="Biaya slot yang dicap sbg label psm.slots di container PS (int >= 1). "
                         "Absen (run langsung): jumlah engine yang di-drive paralel, atau 1 bila "
                         "satu engine / --sequential-browsers")
    ap.add_argument("--progress-append", action="store_true",
                    help="Diset ps-run-layer: jangan kosongkan --progress-file (baris wait-slots)")
    ap.add_argument("--sequential-browsers", action="store_true",
                    help="Diset ps-run-layer (admisi cost 1): drive engine berurutan, reset ke "
                         "snapshot sebelum tiap engine berikutnya; sesudah engine `fail`, engine "
                         "sisanya tak dimulai (sel not-run)")
    fl.add_progress_args(ap)
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()
    # --run-id dipasang SEBELUM apa pun memakai RUN_ID (log kemajuan, registry, label).
    if args.run_id is not None:
        if not RUN_ID_RE.fullmatch(args.run_id):
            print(f"error: --run-id tak valid: {args.run_id!r} — harus [0-9a-f]{{12}}",
                  file=sys.stderr)
            return 2
        fl.RUN_ID = args.run_id
    slot_cost = fl.slot_cost_value(args.slot_cost) if args.slot_cost is not None else 0
    if slot_cost is None:
        print(f"error: --slot-cost tak valid: {args.slot_cost!r} — harus bilangan bulat >= 1",
              file=sys.stderr)
        return 2
    if args.config:
        fl.apply_config_file(args, ap, args.config)
    # --engines di luar CONFIG_KEY_TO_DEST: --config tak pernah menyentuhnya, jadi bila diset
    # ia menang atas --browsers maupun psm_e2e_browsers.
    try:
        requested = (fl.normalize_engines(args.engines, key="--engines") if args.engines is not None
                     else parse_browsers(args.browsers))
    except fl.CellConfigError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    module_dir = Path(args.module_path).resolve()
    if not module_dir.is_dir():
        print(f"error: bukan folder: {module_dir}", file=sys.stderr)
        return 2
    mod_name = module_dir.name
    fl.progress_init(args.progress_file, args.slow_after, truncate=not args.progress_append)
    if not fl.job_start(args, mod_name, "e2e"):
        return 2

    if not playwright_available():
        _emit({"module": mod_name, "e2e_available": False, "status": "skipped",
               "reason": "Playwright tak terpasang — lewati Lapis 4 (uv/pip + 'playwright install chromium firefox'). "
                         "Vonis bersandar pada lapis lain.",
               "versions": {}}, args.output)
        return 0  # degrade terkontrol

    if not fl.docker_available():
        _emit({"module": mod_name, "e2e_available": True, "status": "skipped",
               "reason": "Docker tidak tersedia — Lapis 4 butuh flashlight; lewati, andalkan lapis lain.",
               "versions": {}}, args.output)
        return 0

    # Probe binary browser SEKALI di muka — versi mewarisi daftar yang benar-benar terpasang.
    usable = [e for e in requested if browser_available(e)]
    if not slot_cost:
        # Run langsung tanpa --slot-cost: label = engine yang di-drive PARALEL, else 1.
        slot_cost = len(usable) if len(usable) >= 2 and not args.sequential_browsers else 1
    if args.sequential_browsers and len(usable) > 1:
        # Sekali saja; tak pernah ke browser_notes/errors (bukan celah cakupan).
        print(sequential_notice(usable), file=sys.stderr)
    authored, notes = discover_scenarios(module_dir)
    scenarios = [universal_smoke()] + authored

    tag_map = fl.parse_tag_map(args.tag_map, args.extra_tag_map)
    shot_dir = run_shot_dir(args.screenshot_dir)
    result = {"module": mod_name, "e2e_available": True, "status": "ran",
              "orchestrator": args.orchestrator, "browsers": requested, "browsers_available": usable,
              "headed": args.headed, "screenshot_dir": shot_dir,
              "scenario_sources": ["builtin:psm-universal-smoke"] + [s["source"] for s in authored],
              "scenario_notes": notes, "versions": {}}
    overall_pass = True
    for full_ver in [v.strip() for v in args.versions.split(",")]:
        tag = fl.resolve_tag(tag_map, full_ver)
        if args.verbose:
            print(f"versi {full_ver} -> {fl.IMAGE}:{tag} | browser terpasang: {','.join(usable) or '(none)'}",
                  file=sys.stderr)
        r = run_one_version(module_dir, mod_name, full_ver, tag, usable, scenarios,
                            requested_browsers=requested,
                            orchestrator=args.orchestrator, db_image=args.db_image,
                            ps_domain=args.ps_domain, admin_path=args.admin_path,
                            admin_email=args.admin_email, admin_password=args.admin_password,
                            startup_timeout=args.startup_timeout, op_timeout=args.timeout,
                            nav_timeout=args.nav_timeout * 1000, allow_pull=args.allow_image_pull,
                            headed=args.headed, screenshot_dir=shot_dir, scenario_notes=notes,
                            slot_cost=slot_cost, sequential_browsers=args.sequential_browsers)
        result["versions"][full_ver] = r
        overall_pass = overall_pass and r["pass"]
    result["pass"] = overall_pass  # field lama run langsung; exit code memakai State per sel

    _emit(result, args.output)
    return exit_code(result)


def _entry(argv):
    """Titik masuk skrip: `--engine-worker <spec.json>` (argv[1]) = worker engine CAP-7, TANPA
    run_main_with_progress (worker tak pernah menulis DONE); selain itu run biasa."""
    if len(argv) > 1 and argv[1] == WORKER_FLAG:
        if len(argv) != 3:
            print(f"error: {WORKER_FLAG} butuh tepat satu path spec.json", file=sys.stderr)
            return 2
        return worker_main(argv[2])
    return fl.run_main_with_progress(main)


if __name__ == "__main__":
    sys.exit(_entry(sys.argv))
