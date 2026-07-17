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
(browser berbagi satu DB per versi; duplikat data = temuan memblok palsu).

Prasyarat browser (sekali, host): `uv run --with playwright playwright install chromium firefox`
— lewat playwright yang sama dgn yang diprovisi header PEP723 skrip ini, supaya build browser
yang di-install cocok dgn yang di-drive.
"""
import argparse
import importlib.util
import json
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path

# Pakai-ulang orkestrasi Docker dari sibling ps-flashlight-run.py (impor by-path
# karena nama file ber-tanda-hubung) — satu implementasi spin/wait/exec/teardown.
_FL_PATH = Path(__file__).resolve().parent / "ps-flashlight-run.py"
_spec = importlib.util.spec_from_file_location("ps_flashlight_run", _FL_PATH)
assert _spec and _spec.loader, f"tak bisa memuat sibling {_FL_PATH}"
fl = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(fl)

DEFAULT_BROWSERS = "chromium,firefox"
SUPPORTED_ENGINES = ("chromium", "firefox", "webkit")
SUPPORTED_ACTIONS = ("goto", "expect_no_fatal", "expect_visible", "expect_text",
                     "expect_no_console_error", "click", "click_optional", "fill", "screenshot")
CONTAINER_HTTP_PORT = 80          # nginx/apache flashlight mendengarkan di 80
DEFAULT_HOST_PORT = 8000
# Default admin flashlight (BO folder `admin-dev`); override lewat flag. Login BO
# bersifat best-effort — gagal login TAK memvonis, hanya menandai BO tak konklusif.
DEFAULT_ADMIN_PATH = "admin-dev"
DEFAULT_ADMIN_EMAIL = "admin@prestashop.com"
DEFAULT_ADMIN_PASSWORD = "prestashop"
DEFAULT_NAV_TIMEOUT_S = 60        # timeout per navigasi/aksi Playwright; flashlight dingin
                                  # butuh >20s di load pertama (kompilasi Smarty/Symfony)
SETTLE_TIMEOUT_MS = 15000         # batas tunggu settle (networkidle login BO / 'load'
                                  # sebelum expect_text) — BO polling XHR, jangan tunggu selamanya

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
INSTALL_SH = r'''
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


# ---------------------------------------------------------------------------
# Fungsi murni (teruji tanpa Playwright/Docker)
# ---------------------------------------------------------------------------
def parse_browsers(raw):
    """'chromium,firefox' -> ['chromium','firefox']. Filter ke engine didukung, dedup.

    Kosong / semua tak valid -> default keluarga (chromium,firefox).
    """
    out = []
    for b in (raw or "").split(","):
        b = b.strip().lower()
        if b in SUPPORTED_ENGINES and b not in out:
            out.append(b)
    if out:
        return out
    return [e.strip() for e in DEFAULT_BROWSERS.split(",")]


def host_port_from_domain(ps_domain, default=DEFAULT_HOST_PORT):
    """Ambil port host dari PS_DOMAIN 'localhost:8000' -> 8000. Tanpa port -> default."""
    if ps_domain and ":" in ps_domain:
        tail = ps_domain.rsplit(":", 1)[1]
        if tail.isdigit():
            return int(tail)
    return default


def publish_spec(ps_domain):
    """Spesifikasi publish port docker: '<host>:80' agar PS terjangkau dari host."""
    return f"{host_port_from_domain(ps_domain)}:{CONTAINER_HTTP_PORT}"


def base_urls(ps_domain, admin_path):
    """(fo_base, bo_base) dari PS_DOMAIN + folder admin flashlight."""
    host = ps_domain or f"localhost:{DEFAULT_HOST_PORT}"
    fo = f"http://{host}"
    bo = f"{fo}/{(admin_path or DEFAULT_ADMIN_PATH).strip('/')}"
    return fo, bo


def substitute(text, ctx):
    """Substitusi placeholder {mod}/{fo}/{bo}/{browser} di string spec.

    {browser} = engine aktif (ctx['engine']) — dipakai spec pembuat data supaya
    nama unik per-browser: chromium & firefox berbagi satu DB per versi, data
    duplikat dari browser pertama bikin browser kedua gagal palsu (memblok).
    """
    if not text:
        return text
    return (text.replace("{mod}", ctx["mod"])
                .replace("{fo}", ctx["fo"])
                .replace("{bo}", ctx["bo"])
                .replace("{browser}", ctx.get("engine", "")))


def universal_smoke():
    """Skenario built-in yang berlaku ke SEMUA module: shop tak rusak dgn module aktif.

    FO home (no-auth, selalu konklusif) + BO module manager (konklusif hanya bila
    login admin berhasil). Assertion inti: tak ada fatal/500 & halaman benar-benar
    ter-render. Placeholder {mod} tersedia untuk skenario authored, bukan smoke ini.
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


def run_shot_dir(base):
    """Subfolder screenshot khusus run ini — `<base>/run-<YYYYMMDD-HHMMSS>`.

    Nama file screenshot deterministik (`<ver>/<engine>-<skenario>-<label>.png`) dan tak
    pernah dibersihkan, jadi satu folder datar menumpuk PNG dari run-run sebelumnya —
    termasuk versi yang tak lagi dalam cakupan run sekarang. Verifikasi visual Lapis 4
    menyuruh model MEMVONIS dari gambar itu, jadi folder datar membuka jalan: layout rusak
    dari run minggu lalu ditulis jadi `error` yang MEMBLOK module, atas bukti dari run yang
    sudah tak ada. Memisahkan per-run menghapus kelasnya di sumber — lebih baik daripada
    menaruh gotcha yang harus diingat model.
    """
    return str(Path(base) / f"run-{datetime.now():%Y%m%d-%H%M%S}") if base else None


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
    click(sel), fill(sel,val) — sehingga logika ini teruji dengan page-tiruan.
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
        action = step.get("action")
        if action == "goto":
            area = step.get("area", area)
        conclusive = (area != "bo") or ctx.get("bo_authed", False)
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
            elif action == "screenshot":
                _snap(page, ctx, f"{idx:02d}-shot")
                results.append(_res(action, True, conclusive, "screenshot diambil", ctx.get("screenshot_dir", "")))
            else:
                # Backstop discover_scenarios: aksi tak dikenal TIDAK boleh terbaca lolos —
                # ok=False + conclusive=False -> masuk kanal inconclusive, bukan silent pass.
                results.append(_res(action or "?", False, False, "aksi tak dikenal — tak dieksekusi", ""))
        except Exception as e:  # noqa: BLE001 — selector timeout / nav gagal = assertion gagal
            results.append(_res(action or "?", False, conclusive, f"exception: {str(e)[:120]}", ""))
        if results and not results[-1]["ok"]:
            _snap(page, ctx, f"{idx:02d}-FAIL-{action or 'x'}")
    return results


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
                        "versions": [full_ver],
                    })
                else:
                    inconclusive.append({
                        "browser": engine, "scenario": sc["name"], "action": r["action"],
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
    """Poll GET url sampai respons < 500 (200/redirect) / timeout. Return (ok, status)."""
    deadline = time.monotonic() + timeout
    last = "no-response"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=10) as r:  # noqa: S310 (localhost)
                return True, r.status
        except urllib.error.HTTPError as e:
            if e.code < 500:
                return True, e.code
            last = f"HTTP {e.code}"
        except (urllib.error.URLError, OSError) as e:
            last = str(e)[:80]
        time.sleep(poll)
    return False, last


def install_module(session, mod_name, timeout):
    """Salin + install module via PS console di container. Return (info, err_or_None)."""
    try:
        cp = fl._exec(session, {"MOD_NAME": mod_name}, INSTALL_SH, timeout)
    except subprocess.TimeoutExpired:
        return {"ok": False}, "timeout menjalankan install di container"
    out = (cp.stdout or "") + (cp.stderr or "")
    inst = fl.parse_install(out)
    if inst.get("copy_fail"):
        return {"ok": False}, "gagal menyalin module ke dalam container"
    return {"ok": inst["ok"], "no_console": inst.get("no_console", False),
            "no_psroot": inst.get("no_psroot", False)}, None


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
    base["bo_authed"] = _bo_login(page, base) if _needs_bo(scenarios) else False
    out = []
    for sc in scenarios:
        start = len(console_sink)
        local = dict(base)
        local["scenario"] = sc["name"]
        local["console_base"] = start
        local["_shots"] = []
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


def run_one_version(module_dir, mod_name, full_ver, tag, browsers, scenarios, *,
                    requested_browsers=None, orchestrator, db_image, ps_domain, admin_path,
                    admin_email, admin_password, startup_timeout, op_timeout, nav_timeout, allow_pull,
                    headed=False, screenshot_dir=None):
    """Bangun flashlight (port publish) utk satu versi, install module, drive tiap browser.

    `browsers` = engine yang benar-benar akan di-drive (binary terpasang); `requested_browsers`
    = daftar diminta penuh (utk laporan coverage). Kegagalan infrastruktur SELURUH versi
    (image/DB/boot/install/http) → `errors` (tak konklusif, tak memblok). Masalah PER-BROWSER
    (binary absent / gagal luncur satu engine) → `browser_notes` (coverage, TAK memblok & TAK
    membatalkan temuan konklusif engine lain — itu bug false-pass yang harus dihindari).
    Assertion konklusif gagal saat ≥1 browser jalan & module ter-install → temuan yang memblok.
    """
    requested_browsers = requested_browsers if requested_browsers is not None else list(browsers)
    image_ref = f"{fl.IMAGE}:{tag}"
    res = {"version": full_ver, "tag": tag, "image": image_ref, "orchestrator": None,
           "browsers": [], "install": None, "findings": [], "inconclusive": [],
           "errors": [], "browser_notes": [], "console_errors": 0, "screenshots": [],
           "skipped_browser": False, "pass": False}

    # Engine diminta tapi binary-nya tak lolos probe (di-drop di main) — catat coverage, tak memblok.
    probe_missed = [e for e in requested_browsers if e not in browsers]
    if probe_missed:
        res["browser_notes"].append(
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
            try:
                p = subprocess.run(["docker", "pull", i], capture_output=True, text=True, timeout=op_timeout)
            except subprocess.TimeoutExpired:
                res["errors"].append(f"timeout pull {i}")
                return res
            if p.returncode != 0:
                res["errors"].append(f"gagal pull {i}: {p.stderr.strip()[-200:]}")
                return res

    publish = publish_spec(ps_domain)
    if mode == "compose":
        session, err = fl._bring_up_compose(module_dir, full_ver, image_ref, db_image,
                                            ps_domain, op_timeout, publish)
    else:
        session, err = fl._bring_up_manual(module_dir, image_ref, db_image, ps_domain,
                                           startup_timeout, publish)
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
                          "no_psroot": install.get("no_psroot", False)}
        if ierr or not install["ok"]:
            # Install adalah wilayah vonis Lapis 2; di sini cuma prasyarat E2E → tak konklusif.
            # Bedakan infra (image tanpa bin/console / PS root) dari module ditolak core:
            # keduanya tak memblok di sini, tapi alasannya harus jujur, bukan disamarkan.
            if install.get("no_console") or install.get("no_psroot"):
                res["errors"].append(
                    "image tak punya bin/console / PS root — module tak bisa di-install, E2E tak bisa menilai perilaku")
            else:
                res["errors"].append(
                    ierr or "module gagal install — E2E tak bisa menilai perilaku (Lapis 2 flashlight yang memvonis install)")
            return res

        fo, bo = base_urls(ps_domain, admin_path)
        reach_ok, rstatus = wait_http(fo + "/", startup_timeout)
        if not reach_ok:
            res["errors"].append(f"PS tak terjangkau di {fo} ({rstatus}) — port publish/boot gagal")
            return res

        # Warm-up BO sebelum browser men-drive (verified: login cold-container 1.7/8
        # flaky karena kompilasi halaman login lambat) — best-effort, gagal tak memvonis:
        # login tetap best-effort di _bo_login (plus satu retry di sana).
        if _needs_bo(scenarios):
            wait_http(f"{bo}/index.php?controller=AdminLogin", startup_timeout)

        ver_shot_dir = None
        if screenshot_dir:
            ver_shot_dir = str(Path(screenshot_dir) / re.sub(r"[^A-Za-z0-9_.-]", "_", full_ver))
            try:
                Path(ver_shot_dir).mkdir(parents=True, exist_ok=True)
            except OSError:
                ver_shot_dir = None  # gagal buat folder -> lewati screenshot, jangan gagalkan run
        ctx = {"fo": fo, "bo": bo, "mod": mod_name, "nav_timeout": nav_timeout,
               "admin_email": admin_email, "admin_password": admin_password, "bo_authed": False,
               "screenshot_dir": ver_shot_dir}
        driven = []
        for engine in browsers:
            eng = drive_engine(engine, scenarios, ctx, headed=headed)
            if eng.get("launch_error"):
                # Gagal luncur SATU engine = masalah per-browser -> browser_notes (BUKAN errors).
                # Jangan cemari kanal infra version-level: temuan konklusif engine lain harus tetap.
                res["browser_notes"].append(
                    f"browser {engine} gagal diluncurkan: {eng['launch_error']} "
                    f"(jalankan 'playwright install {engine}'{'' if not headed else ' / --headed butuh display'})")
                continue
            res["browsers"].append(engine)
            driven.append(eng)

        if not res["browsers"]:
            # Semua engine yang diprobe lolos ternyata gagal luncur -> tak ada yg teruji.
            res["skipped_browser"] = True
            return res

        # Rollup artefak visual: hitungan error console/JS (advisory, surface visibilitas) + path screenshot.
        res["console_errors"] = sum(len(sc.get("console_errors", []))
                                    for eng in driven for sc in eng.get("scenarios", []))
        res["screenshots"] = [s for eng in driven for sc in eng.get("scenarios", [])
                              for s in sc.get("screenshots", [])]
        if res["console_errors"]:
            res["browser_notes"].append(
                f"{res['console_errors']} error console/JS terdeteksi di browser "
                "(advisory; pakai aksi 'expect_no_console_error' di skenario untuk menegakkan)")

        findings, inconclusive = assemble_findings(full_ver, driven)
        res["findings"] = findings
        res["inconclusive"] = inconclusive
        res["pass"] = len(findings) == 0
        return res
    finally:
        fl._teardown(session)


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
    ap.add_argument("--browsers", default=DEFAULT_BROWSERS,
                    help=f"Engine Playwright dipisah koma (default: {DEFAULT_BROWSERS}; didukung: {','.join(SUPPORTED_ENGINES)})")
    ap.add_argument("--tag-map", default="", help="Peta LENGKAP versi=tag dipisah koma (MENGGANTI default)")
    ap.add_argument("--extra-tag-map", default="", help="Tag TAMBAHAN versi=tag (MENAMBAH di atas peta)")
    ap.add_argument("--orchestrator", choices=["auto", "compose", "manual"], default="auto",
                    help="Cara menghidupkan DB+flashlight (default: auto)")
    ap.add_argument("--db-image", default=fl.DEFAULT_DB_IMAGE, help=f"Image server DB (default: {fl.DEFAULT_DB_IMAGE})")
    ap.add_argument("--ps-domain", default=fl.DEFAULT_PS_DOMAIN,
                    help=f"PS_DOMAIN flashlight = URL yang di-drive Playwright (default: {fl.DEFAULT_PS_DOMAIN})")
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
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args()

    module_dir = Path(args.module_path).resolve()
    if not module_dir.is_dir():
        print(f"error: bukan folder: {module_dir}", file=sys.stderr)
        return 2
    mod_name = module_dir.name

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

    requested = parse_browsers(args.browsers)
    # Probe binary browser SEKALI di muka — versi mewarisi daftar yang benar-benar terpasang.
    usable = [e for e in requested if browser_available(e)]
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
        tag = tag_map.get(full_ver) or tag_map.get(full_ver.rsplit(".", 1)[0]) or full_ver
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
                            headed=args.headed, screenshot_dir=shot_dir)
        result["versions"][full_ver] = r
        overall_pass = overall_pass and r["pass"]
    result["pass"] = overall_pass

    _emit(result, args.output)
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
