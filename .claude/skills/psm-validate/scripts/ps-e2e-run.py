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

Format spec skenario authored (`<module>/tests/e2e/*.json`):
  {"name": "configure-save",
   "steps": [
     {"action": "goto", "area": "bo", "path": "/index.php?controller=AdminModules"},
     {"action": "expect_no_fatal"},
     {"action": "fill", "selector": "#PSM_FIELD", "value": "42"},
     {"action": "click", "selector": "button[name=submitSave]"},
     {"action": "expect_text", "text": "successful"},
     {"action": "goto", "area": "fo", "path": "/"},
     {"action": "expect_visible", "selector": "#header"}
   ]}
Placeholder yang disubstitusi di `path`/`url`/`text`: {mod} {fo} {bo}. Area default `fo`.

Prasyarat browser (sekali, host): `playwright install chromium firefox`.
"""
import argparse
import importlib.util
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
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
CONTAINER_HTTP_PORT = 80          # nginx/apache flashlight mendengarkan di 80
DEFAULT_HOST_PORT = 8000
# Default admin flashlight (BO folder `admin-dev`); override lewat flag. Login BO
# bersifat best-effort — gagal login TAK memvonis, hanya menandai BO tak konklusif.
DEFAULT_ADMIN_PATH = "admin-dev"
DEFAULT_ADMIN_EMAIL = "admin@prestashop.com"
DEFAULT_ADMIN_PASSWORD = "prestashop"
DEFAULT_NAV_TIMEOUT_S = 20        # timeout per navigasi/aksi Playwright

# Tanda PHP fatal / error server yang bikin "shop rusak" (white-screen / 500).
FATAL_SIGNS = (
    "Fatal error", "PrestaShopException", "There was an error",
    "Whoops, looks like something went wrong", "500 Internal Server Error",
    "Uncaught Error", "Parse error", "syntax error, unexpected",
)

# Dijalankan DI DALAM container flashlight setelah healthy: salin + install module
# (TANPA phpstan — coding-standard adalah wilayah Lapis 2). $MOD_NAME dari env.
INSTALL_SH = r'''
if ! cp -r /ps-module-src "/var/www/html/modules/$MOD_NAME" 2>&1; then echo PSM_COPY_FAIL; fi
cd /var/www/html || echo PSM_NO_PSROOT
if php -d memory_limit=-1 bin/console prestashop:module --no-interaction install "$MOD_NAME" 2>&1; then
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
    """Substitusi placeholder {mod}/{fo}/{bo} di string spec."""
    if not text:
        return text
    return (text.replace("{mod}", ctx["mod"])
                .replace("{fo}", ctx["fo"])
                .replace("{bo}", ctx["bo"]))


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


def discover_scenarios(module_dir):
    """Muat spec authored dari <module>/tests/e2e/*.json. Return (scenarios, notes).

    Spec tak valid (JSON rusak / tanpa 'steps' list) DILEWATI dengan catatan —
    tak crash, tak diam-diam hilang.
    """
    found, notes = [], []
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
            notes.append(f"{f.name}: tak ada 'steps' list — dilewati")
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


def _fatal_message(status, html):
    if status is not None and status >= 500:
        return f"HTTP {status} (server error)"
    for sign in FATAL_SIGNS:
        if sign in html:
            return f"tanda fatal: '{sign}'"
    return "tak ada fatal"


def _resolve_url(step, ctx, area):
    if step.get("url"):
        return substitute(step["url"], ctx)
    base = ctx["fo"] if area == "fo" else ctx["bo"]
    return base + substitute(step.get("path", ""), ctx)


def run_steps(page, steps, ctx):
    """Eksekusi langkah skenario terhadap `page` (Playwright-like). Return list hasil.

    `page` cukup mengekspos goto()->response(status), content()->str, locator(sel),
    click(sel), fill(sel,val) — sehingga logika ini teruji dengan page-tiruan.
    Assertion di area BO konklusif hanya bila ctx['bo_authed'] True.
    """
    results = []
    area = "fo"
    last_status = None
    for step in steps:
        action = step.get("action")
        if action == "goto":
            area = step.get("area", area)
        conclusive = (area != "bo") or ctx.get("bo_authed", False)
        try:
            if action == "goto":
                url = _resolve_url(step, ctx, area)
                resp = page.goto(url)
                last_status = getattr(resp, "status", None) if resp is not None else None
                ok = last_status is None or last_status < 500
                results.append(_res(action, ok, conclusive, f"status={last_status}", url))
            elif action == "expect_no_fatal":
                html = page.content() or ""
                bad = (last_status is not None and last_status >= 500) or any(s in html for s in FATAL_SIGNS)
                results.append(_res(action, not bad, conclusive, _fatal_message(last_status, html), area))
            elif action == "expect_visible":
                sel = step.get("selector", "")
                vis = page.locator(sel).first.is_visible()
                results.append(_res(action, bool(vis), conclusive, f"visible={bool(vis)} sel={sel}", sel))
            elif action == "expect_text":
                txt = substitute(step.get("text", ""), ctx)
                present = txt in (page.content() or "")
                results.append(_res(action, present, conclusive, f"text present={present}: {txt[:50]}", area))
            elif action == "click":
                page.click(step.get("selector", ""))
                results.append(_res(action, True, conclusive, "clicked", step.get("selector", "")))
            elif action == "fill":
                page.fill(step.get("selector", ""), substitute(step.get("value", ""), ctx))
                results.append(_res(action, True, conclusive, "filled", step.get("selector", "")))
            else:
                results.append(_res(action or "?", True, False, "aksi tak dikenal — dilewati", ""))
        except Exception as e:  # noqa: BLE001 — selector timeout / nav gagal = assertion gagal
            results.append(_res(action or "?", False, conclusive, f"exception: {str(e)[:120]}", ""))
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
    return {"ok": inst["ok"], "no_console": inst.get("no_console", False)}, None


def _bo_login(page, ctx):
    """Login BO best-effort (form AdminLogin: email/passwd/submitLogin stabil 1.7/8/9)."""
    try:
        page.goto(ctx["bo"] + "/index.php?controller=AdminLogin")
        page.fill("input[name=email]", ctx["admin_email"])
        page.fill("input[name=passwd]", ctx["admin_password"])
        page.click("button[name=submitLogin]")
        page.wait_for_load_state("networkidle")
        html = page.content() or ""
        # Berhasil bila form login tak lagi ada (sudah masuk BO).
        return "submitLogin" not in html
    except Exception:  # noqa: BLE001
        return False


def drive_engine(engine, scenarios, ctx):
    """Luncurkan satu engine Playwright, jalankan semua skenario. Return hasil per engine.

    Kegagalan luncur (binary browser belum di-`playwright install`) -> launch_error
    (upstream memperlakukannya sebagai skipped_browser, degrade jujur).
    """
    from playwright.sync_api import sync_playwright

    result = {"browser": engine, "scenarios": [], "launch_error": None, "bo_authed": False}
    with sync_playwright() as p:
        btype = getattr(p, engine, None)
        if btype is None:
            result["launch_error"] = f"engine tak dikenal: {engine}"
            return result
        try:
            browser = btype.launch(headless=True)
        except Exception as e:  # noqa: BLE001 — binary absent / gagal luncur
            result["launch_error"] = str(e)[:200]
            return result
        try:
            context = browser.new_context(ignore_https_errors=True)
            page = context.new_page()
            page.set_default_timeout(ctx["nav_timeout"])
            local = dict(ctx)
            local["bo_authed"] = _bo_login(page, local) if _needs_bo(scenarios) else False
            result["bo_authed"] = local["bo_authed"]
            for sc in scenarios:
                result["scenarios"].append({
                    "name": sc["name"], "source": sc["source"],
                    "results": run_steps(page, sc["steps"], local),
                })
        finally:
            browser.close()
    return result


def run_one_version(module_dir, mod_name, full_ver, tag, browsers, scenarios, *,
                    requested_browsers=None, orchestrator, db_image, ps_domain, admin_path,
                    admin_email, admin_password, startup_timeout, op_timeout, nav_timeout, allow_pull):
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
           "errors": [], "browser_notes": [], "skipped_browser": False, "pass": False}

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
        res["install"] = {"ok": install["ok"], "no_console": install.get("no_console", False)}
        if ierr or not install["ok"]:
            # Install adalah wilayah vonis Lapis 2; di sini cuma prasyarat E2E → tak konklusif.
            res["errors"].append(
                ierr or "module gagal install — E2E tak bisa menilai perilaku (Lapis 2 flashlight yang memvonis install)")
            return res

        fo, bo = base_urls(ps_domain, admin_path)
        reach_ok, rstatus = wait_http(fo + "/", startup_timeout)
        if not reach_ok:
            res["errors"].append(f"PS tak terjangkau di {fo} ({rstatus}) — port publish/boot gagal")
            return res

        ctx = {"fo": fo, "bo": bo, "mod": mod_name, "nav_timeout": nav_timeout,
               "admin_email": admin_email, "admin_password": admin_password, "bo_authed": False}
        driven = []
        for engine in browsers:
            eng = drive_engine(engine, scenarios, ctx)
            if eng.get("launch_error"):
                # Gagal luncur SATU engine = masalah per-browser -> browser_notes (BUKAN errors).
                # Jangan cemari kanal infra version-level: temuan konklusif engine lain harus tetap.
                res["browser_notes"].append(
                    f"browser {engine} gagal diluncurkan: {eng['launch_error']} "
                    f"(jalankan 'playwright install {engine}')")
                continue
            res["browsers"].append(engine)
            driven.append(eng)

        if not res["browsers"]:
            # Semua engine yang diprobe lolos ternyata gagal luncur -> tak ada yg teruji.
            res["skipped_browser"] = True
            return res

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
        description="Lapis 4 — uji perilaku browser (E2E) module di Docker flashlight, per versi & browser.")
    ap.add_argument("module_path", help="Path folder module PrestaShop")
    ap.add_argument("--versions", default="1.7.8,8.1,9.1", help="Versi target dipisah koma")
    ap.add_argument("--browsers", default=DEFAULT_BROWSERS,
                    help=f"Engine Playwright dipisah koma (default: {DEFAULT_BROWSERS}; didukung: {','.join(SUPPORTED_ENGINES)})")
    ap.add_argument("--tag-map", default="", help="Pemetaan versi=tag dipisah koma, mis. '9.1=9.1.4-nginx'")
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

    tag_map = fl.parse_tag_map(args.tag_map)
    result = {"module": mod_name, "e2e_available": True, "status": "ran",
              "orchestrator": args.orchestrator, "browsers": requested, "browsers_available": usable,
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
                            nav_timeout=args.nav_timeout * 1000, allow_pull=args.allow_image_pull)
        result["versions"][full_ver] = r
        overall_pass = overall_pass and r["pass"]
    result["pass"] = overall_pass

    _emit(result, args.output)
    return 0 if overall_pass else 1


if __name__ == "__main__":
    sys.exit(main())
