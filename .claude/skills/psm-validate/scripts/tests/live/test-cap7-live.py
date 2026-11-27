#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# dependencies = ["playwright"]
# ///
"""Uji LIVE CAP-7 (browser paralel dalam satu boot) — butuh Docker, image & browser nyata.

cell-contract.md > paragraf pembuka (uji live), Parallel browsers (CAP-7) incl. Identical
findings, Runner, Evidence record. Dijalankan: `uv run scripts/tests/live/test-cap7-live.py`.

SKIP (satu baris `SKIPPED: <alasan>`, exit 0) kecuali SEMUA ada lokal: Docker, playwright +
binary chromium & firefox, image flashlight bertag default (`1.7.8.11`, `8.1.6-nginx`,
`9.1.4-nginx`) dan image DB `mariadb:lts`. Tak pernah pull (tanpa `--allow-image-pull`).

Semua run memakai salinan temp POLOS (bukan git) `{project-root}/modules/bankwire` dengan satu
fault: `checkout-with-bank.json` step 55 (FO `expect_text` "Please send us your payment by bank
transfer") diganti teks yang tak pernah tampil, jadi gagal di tiap engine.

Per versi target (`PSM_LIVE_VERSIONS=9.1,...` boleh menyempitkan):
  (a) dua sesi BO admin yang sama berbarengan: engine A (chromium) login, lalu B (firefox),
      lalu masing-masing memuat `AdminModules` dan masih ter-auth (cek `_bo_login`: URL bukan
      `controller=AdminLogin` dan field passwd hilang). Boot sendiri lewat helper
      ps-flashlight-run (Job ID terdaftar, teardown di `finally`).
  (b) Identical findings: run paralel `ps-run-layer.py --layer e2e --cells V:chromium+firefox`,
      lalu baseline `--cells V:chromium`, lalu `--cells V:firefox` (tiap run folder laporan
      temp BARU & kosong, jadi admisi tak pernah dipaksa histori). Himpunan (versi, browser,
      skenario, step, aksi) temuan terkonfirmasi paralel == gabungan baseline, dan tak kosong.
      Mismatch diulang SEKALI (attempt baru, folder baru), gagal hanya bila berulang. Kedua
      rekaman paralel wajib `browser_mode: parallel` (jatuh ke sekuensial = gagal, menyebut
      slot yang terhitung), satu `boot_id`, dan overlap AC1: start span paling awal tiap engine
      < akhir span paling akhir engine lain.
  (c) dari rekaman paralel (b): span skenario BO tak pernah overlap span engine lain; tiap span
      step k+1 mulai sesudah SEMUA span step k selesai.

Exit 0 = semua lolos (atau SKIPPED); 1 = ada yang gagal (folder kerja dipertahankan).
"""
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
import traceback
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent.parent
REPO = SCRIPTS.parents[3]
BANKWIRE = REPO / "modules" / "bankwire"
RUN_LAYER = SCRIPTS / "ps-run-layer.py"
PLAN_LAYERS = SCRIPTS / "ps-plan-layers.py"

_spec = importlib.util.spec_from_file_location("ps_e2e_run", SCRIPTS / "ps-e2e-run.py")
e2e = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(e2e)
fl = e2e.fl

DEFAULT_VERSIONS = ("1.7.8", "8.1", "9.1")
BROWSERS = ("chromium", "firefox")
TAG_MAP = "1.7.8=1.7.8.11,8.1=8.1.6-nginx,9.1=9.1.4-nginx"
DB_IMAGE = "mariadb:lts"
FAULT_SPEC = "checkout-with-bank.json"
FAULT_STEP = 55
FAULT_ORIG = "Please send us your payment by bank transfer"
FAULT_TEXT = "PSM-LIVE-CAP7 teks ini tak pernah tampil di halaman"
STARTUP_TIMEOUT = 300
OP_TIMEOUT = 600
RUN_TIMEOUT = 3600       # batas satu invokasi ps-run-layer (boot + 2 engine + konfirmasi)
NAV_TIMEOUT_MS = 60000

FAILS = []
FAULT_NAME = {"name": None}   # `name` spec fault, diisi make_copy


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}: {name}" + (f" — {detail}" if detail and not cond else ""),
          flush=True)
    if not cond:
        FAILS.append(name)
    return cond


def say(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------------------
# Gerbang skip
# ---------------------------------------------------------------------------
def skip_reason():
    """Alasan skip (str) atau None. Tak pernah pull apa pun."""
    if not fl.docker_available():
        return "Docker tak tersedia"
    if not e2e.playwright_available():
        return "paket playwright tak terpasang"
    missing_b = [b for b in BROWSERS if not e2e.browser_available(b)]
    if missing_b:
        return f"binary browser Playwright belum di-install: {', '.join(missing_b)}"
    tags = fl.parse_tag_map(TAG_MAP)
    images = [f"{fl.IMAGE}:{fl.resolve_tag(tags, v)}" for v in DEFAULT_VERSIONS] + [DB_IMAGE]
    missing_i = [i for i in images if not fl.image_present(i)]
    if missing_i:
        return f"image belum ada lokal (tak di-pull): {', '.join(missing_i)}"
    if not BANKWIRE.is_dir():
        return f"module sumber tak ada: {BANKWIRE}"
    return None


def live_versions():
    raw = os.environ.get("PSM_LIVE_VERSIONS", "").strip()
    if not raw:
        return list(DEFAULT_VERSIONS)
    vers = [v.strip() for v in raw.split(",") if v.strip()]
    bad = [v for v in vers if v not in DEFAULT_VERSIONS]
    if bad or not vers:
        raise SystemExit(f"error: PSM_LIVE_VERSIONS hanya boleh menyempitkan "
                         f"{','.join(DEFAULT_VERSIONS)} (dapat: {raw!r})")
    return [v for v in DEFAULT_VERSIONS if v in vers]


# ---------------------------------------------------------------------------
# Salinan module + fault
# ---------------------------------------------------------------------------
def make_copy(work):
    """Salinan polos (tanpa .git) modules/bankwire + fault step 55. Return path module."""
    dst = work / "src" / "bankwire"
    shutil.copytree(BANKWIRE, dst, ignore=shutil.ignore_patterns(".git", "__pycache__"))
    spec_path = dst / "tests" / "e2e" / FAULT_SPEC
    data = json.loads(spec_path.read_text(encoding="utf-8"))
    step = data["steps"][FAULT_STEP]
    if step.get("action") != "expect_text" or step.get("text") != FAULT_ORIG:
        raise SystemExit(f"error: {FAULT_SPEC} step {FAULT_STEP} bukan expect_text "
                         f"{FAULT_ORIG!r} (dapat {step!r}) — fault tak bisa disuntik")
    step["text"] = FAULT_TEXT
    spec_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    FAULT_NAME["name"] = data.get("name")
    return dst


def write_config(reports):
    reports.mkdir(parents=True, exist_ok=True)
    cfg = {"psm_target_versions": ",".join(DEFAULT_VERSIONS),
           "psm_e2e_browsers": ",".join(BROWSERS),
           "psm_flashlight_tag_map": TAG_MAP}
    path = reports / fl.CONFIG_BASENAME
    path.write_text(json.dumps(cfg, indent=2) + "\n", encoding="utf-8")
    return path


def new_session():
    cp = subprocess.run(["uv", "run", str(PLAN_LAYERS), "--new-session"],
                        capture_output=True, text=True, timeout=300)
    tok = (cp.stdout or "").strip()
    if cp.returncode != 0 or len(tok) != 16:
        raise SystemExit(f"error: ps-plan-layers.py --new-session gagal (rc={cp.returncode}): "
                         f"{(cp.stderr or '')[-300:]}")
    return tok


# ---------------------------------------------------------------------------
# (a) Sesi BO admin yang sama berbarengan
# ---------------------------------------------------------------------------
def _authed(page):
    return (page.locator("input[name=passwd]").count() == 0
            and "controller=AdminLogin" not in (page.url or ""))


def bo_sessions_check(ver, module):
    """Boot sendiri, login A lalu B, lalu masing-masing memuat AdminModules. Return dict hasil."""
    from playwright.sync_api import sync_playwright

    tag = fl.resolve_tag(fl.parse_tag_map(TAG_MAP), ver)
    image_ref = f"{fl.IMAGE}:{tag}"
    port = e2e.pick_free_host_port(0)
    ps_domain = f"localhost:{port}"
    publish = f"{port}:{e2e.CONTAINER_HTTP_PORT}"
    session = None
    out = {"error": None, "login": {}, "authed": {}, "url": {}}
    try:
        if fl.compose_available():
            session, err = fl._bring_up_compose(module, ver, image_ref, DB_IMAGE, ps_domain,
                                                OP_TIMEOUT, publish, slot_cost=1)
        else:
            session, err = fl._bring_up_manual(module, image_ref, DB_IMAGE, ps_domain,
                                               STARTUP_TIMEOUT, publish, slot_cost=1)
        if err:
            out["error"] = f"bring-up: {err}"
            return out
        ok, status = fl.wait_healthy(session["ps_container"], STARTUP_TIMEOUT)
        if not ok:
            out["error"] = f"container tak healthy ({status})"
            return out
        fo, bo = e2e.base_urls(ps_domain, e2e.DEFAULT_ADMIN_PATH)
        reach, rstatus, responded = e2e.wait_http(fo + "/", STARTUP_TIMEOUT)
        if not responded:
            out["error"] = f"PS tak terjangkau di {fo} ({rstatus})"
            return out
        e2e.wait_http(f"{bo}/index.php?controller=AdminLogin", STARTUP_TIMEOUT)  # warm-up BO
        ctx = {"bo": bo, "admin_email": e2e.DEFAULT_ADMIN_EMAIL,
               "admin_password": e2e.DEFAULT_ADMIN_PASSWORD}
        with sync_playwright() as p:
            launched, pages = [], {}
            try:
                for eng in BROWSERS:
                    b = getattr(p, eng).launch(headless=True)
                    launched.append(b)
                    page = b.new_context(ignore_https_errors=True).new_page()
                    page.set_default_timeout(NAV_TIMEOUT_MS)
                    pages[eng] = page
                for eng in BROWSERS:   # A login, lalu B login (sesi A tetap hidup)
                    out["login"][eng] = e2e._bo_login(pages[eng], ctx)
                for eng in BROWSERS:   # lalu masing-masing memuat AdminModules
                    page = pages[eng]
                    page.goto(bo + "/index.php?controller=AdminModules")
                    page.wait_for_load_state("load")
                    out["url"][eng] = page.url
                    out["authed"][eng] = _authed(page)
            finally:
                for b in launched:
                    try:
                        b.close()
                    except Exception:  # noqa: BLE001
                        pass
    except Exception as e:  # noqa: BLE001
        out["error"] = f"{type(e).__name__}: {e}"
    finally:
        fl._teardown(session)
    return out


# ---------------------------------------------------------------------------
# (b)/(c) lewat ps-run-layer
# ---------------------------------------------------------------------------
def run_cells(module, reports, cells, session_tok):
    """Satu invokasi `ps-run-layer.py --layer e2e` di folder laporan BARU. Return dict."""
    cfg = write_config(reports)
    log = reports.parent / f"{reports.name}.stderr.log"
    used_before = fl.daemon_slot_usage()
    cmd = ["uv", "run", str(RUN_LAYER), "--layer", "e2e", "--module", str(module),
           "--session", session_tok, "--tier", "1", "--cells", cells,
           "--reports-dir", str(reports), "--config", str(cfg)]
    t0 = time.monotonic()
    with open(log, "w", encoding="utf-8") as err:
        cp = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=err, text=True,
                            timeout=RUN_TIMEOUT)
    wall = time.monotonic() - t0
    line = None
    for raw in reversed((cp.stdout or "").splitlines()):
        try:
            obj = json.loads(raw)
        except ValueError:
            continue
        if isinstance(obj, dict) and "e2e_status" in obj:
            line = obj
            break
    say(f"    run {cells}: rc={cp.returncode} {wall:.0f}s out={json.dumps(line)}")
    return {"rc": cp.returncode, "out": line, "log": log, "reports": reports,
            "slots_before": used_before, "wall": wall}


def newest(reports, ver, browser):
    path = reports / f"bankwire-e2e-{ver}-{browser}.jsonl"
    if not path.is_file():
        return None
    rec = None
    for raw in path.read_text(encoding="utf-8").splitlines():
        try:
            obj = json.loads(raw)
        except ValueError:
            continue
        if isinstance(obj, dict):
            rec = obj
    return rec


def finding_set(ver, browser, rec):
    return {(ver, browser, f.get("scenario"), f.get("step"), f.get("action"))
            for f in (rec or {}).get("findings") or []}


def _tail(path, n=2500):
    try:
        return path.read_text(encoding="utf-8", errors="replace")[-n:]
    except OSError:
        return ""


def _brief(rec):
    if rec is None:
        return "tanpa rekaman"
    return (f"state={rec.get('state')} reason={rec.get('reason')} mode={rec.get('browser_mode')} "
            f"errors={rec.get('errors')} findings={len(rec.get('findings') or [])} "
            f"parallel_only={len(rec.get('parallel_only') or [])} "
            f"notes={rec.get('browser_notes')}")


def _slots_text(run):
    used, counted, err = run["slots_before"]
    after = fl.daemon_slot_usage()
    prog = ""
    for p in sorted(run["reports"].glob("*.progress.log")):
        lines = [ln for ln in _tail(p, 20000).splitlines() if "wait-slots" in ln]
        prog += " | ".join(lines[-4:])
    return (f"slot terhitung sebelum run: used={used} counted={counted} err={err}; "
            f"sesudah: used={after[0]} counted={after[1]}; log wait-slots: {prog or '-'}")


def parallel_attempt(ver, module, work, attempt, session_tok):
    """Satu attempt (b): run paralel + dua baseline, tiap run folder laporan baru."""
    base = work / "runs" / f"{ver}-a{attempt}"
    par = run_cells(module, base / "parallel", f"{ver}:chromium+firefox", session_tok)
    recs = {b: newest(par["reports"], ver, b) for b in BROWSERS}
    for b in BROWSERS:
        say(f"    paralel {ver}:{b}: {_brief(recs[b])}")
    res = {"par": par, "recs": recs, "fatal": None, "match": False, "sets": None}
    if any(recs[b] is None for b in BROWSERS):
        res["fatal"] = (f"run paralel {ver} tak menulis rekaman kedua sel (rc={par['rc']}); "
                        f"stderr: {_tail(par['log'])}")
        return res
    modes = {b: recs[b].get("browser_mode") for b in BROWSERS}
    if any(m != "parallel" for m in modes.values()):
        res["fatal"] = (f"admisi {ver} jatuh ke sekuensial (browser_mode={modes}) — "
                        + _slots_text(par))
        return res
    base_c = run_cells(module, base / "baseline-chromium", f"{ver}:chromium", session_tok)
    base_f = run_cells(module, base / "baseline-firefox", f"{ver}:firefox", session_tok)
    rc = newest(base_c["reports"], ver, "chromium")
    rf = newest(base_f["reports"], ver, "firefox")
    say(f"    baseline {ver}:chromium: {_brief(rc)}")
    say(f"    baseline {ver}:firefox: {_brief(rf)}")
    par_set = finding_set(ver, "chromium", recs["chromium"]) | finding_set(ver, "firefox",
                                                                            recs["firefox"])
    base_set = finding_set(ver, "chromium", rc) | finding_set(ver, "firefox", rf)
    res["sets"] = (par_set, base_set)
    res["match"] = rc is not None and rf is not None and par_set == base_set
    return res


def span_checks(ver, recs, driven):
    """AC1 overlap + (c) kunci BO & lockstep dari rekaman paralel."""
    names = [sc["name"] for sc in driven]
    bo_names = {sc["name"] for sc in driven if e2e._needs_bo([sc])}
    spans = {b: (recs[b].get("scenario_spans") or {}) for b in BROWSERS}
    complete = all(set(spans[b]) == set(names) for b in BROWSERS)
    check(f"{ver}: scenario_spans kedua engine mencakup tepat skenario ter-drive", complete,
          f"driven={names} spans={ {b: sorted(spans[b]) for b in BROWSERS} }")
    if not complete:
        return
    a, b = BROWSERS
    # AC1: satu boot, mode paralel, fase browser overlap (lewat span lockstep).
    check(f"{ver}: kedua rekaman berbagi boot_id",
          recs[a].get("boot_id") and recs[a].get("boot_id") == recs[b].get("boot_id"),
          f"{recs[a].get('boot_id')} vs {recs[b].get('boot_id')}")
    for x, y in ((a, b), (b, a)):
        first_x = min(s[0] for s in spans[x].values())
        last_y = max(s[1] for s in spans[y].values())
        check(f"{ver}: overlap AC1 — span awal {x} < span akhir {y}", first_x < last_y,
              f"{first_x} !< {last_y}")
    # (c) kunci BO: skenario BO satu engine tak pernah overlap span mana pun engine lain.
    clashes = []
    for x, y in ((a, b), (b, a)):
        for n in bo_names:
            s0, s1 = spans[x][n]
            for m, (t0, t1) in spans[y].items():
                if not (s1 <= t0 or t1 <= s0):
                    clashes.append(f"{x}:{n} ∩ {y}:{m}")
    check(f"{ver}: span skenario BO tak overlap span engine lain ({len(bo_names)} skenario BO)",
          not clashes, "; ".join(clashes))
    # (c) lockstep: tiap span step k+1 mulai sesudah SEMUA span step k selesai.
    late = []
    for k in range(len(names) - 1):
        end_k = max(spans[e][names[k]][1] for e in BROWSERS)
        start_next = min(spans[e][names[k + 1]][0] for e in BROWSERS)
        if not end_k < start_next:
            late.append(f"step {k + 1} ({names[k + 1]}) mulai {start_next} <= akhir step {k} "
                        f"({names[k]}) {end_k}")
    check(f"{ver}: lockstep — step k+1 mulai sesudah semua step k selesai ({len(names)} step)",
          not late, "; ".join(late))
    fo_only = [n for n in names if n not in bo_names]
    if fo_only:
        ov = [n for n in fo_only
              if spans[a][n][0] < spans[b][n][1] and spans[b][n][0] < spans[a][n][1]]
        say(f"    info: skenario FO-only yang overlap antar-engine: {ov or '-'} dari {fo_only}")


def identical_findings(ver, module, work, session_tok, driven):
    say(f"[b/c] {ver}: identical findings + span lock/lockstep")
    final = None
    for attempt in (1, 2):
        res = parallel_attempt(ver, module, work, attempt, session_tok)
        if res["fatal"]:
            check(f"{ver}: run paralel (attempt {attempt}) memakai mode paralel & menulis rekaman",
                  False, res["fatal"])
            return
        par_set, base_set = res["sets"]
        if res["match"]:
            final = res
            break
        say(f"    MISMATCH attempt {attempt}: hanya-paralel={sorted(par_set - base_set, key=str)} "
            f"hanya-baseline={sorted(base_set - par_set, key=str)}")
        if attempt == 1:
            say("    mismatch → diulang sekali dengan folder laporan baru")
        else:
            check(f"{ver}: temuan paralel terkonfirmasi == gabungan baseline (mismatch berulang)",
                  False)
            return
    par_set, base_set = final["sets"]
    check(f"{ver}: temuan paralel terkonfirmasi == gabungan baseline", par_set == base_set)
    check(f"{ver}: himpunan temuan terkonfirmasi tak kosong", bool(par_set),
          "fault step 55 tak terkonfirmasi di engine mana pun")
    fault = {(ver, b, FAULT_NAME["name"], FAULT_STEP, "expect_text") for b in BROWSERS}
    if not fault <= par_set:
        say(f"    info: tuple fault step {FAULT_STEP} tak lengkap di himpunan: {sorted(par_set, key=str)}")
    for b in BROWSERS:
        check(f"{ver}:{b} rekaman paralel browser_mode=parallel",
              final["recs"][b].get("browser_mode") == "parallel")
    span_checks(ver, final["recs"], driven)


def main():
    reason = skip_reason()
    if reason:
        print(f"SKIPPED: {reason}")
        return 0
    versions = live_versions()
    work = Path(tempfile.mkdtemp(prefix="psm-cap7-live-"))
    say(f"folder kerja: {work} | versi: {','.join(versions)}")
    t_all = time.monotonic()
    job_id = fl.make_job_id("bankwire", "cap7-live")
    fl.job_register(job_id, module="bankwire", layer="e2e", versions=",".join(versions))
    try:
        module = make_copy(work)
        authored, _notes = e2e.discover_scenarios(module)
        driven = [e2e.universal_smoke()] + authored
        session_tok = new_session()
        for ver in versions:
            t0 = time.monotonic()
            say(f"[a] {ver}: dua sesi BO admin yang sama berbarengan")
            out = bo_sessions_check(ver, module)
            if not check(f"{ver}: boot untuk uji sesi BO", out["error"] is None, out["error"] or ""):
                continue
            for eng in BROWSERS:
                check(f"{ver}: login BO {eng} sukses (urutan {'/'.join(BROWSERS)})",
                      out["login"].get(eng) is True)
            for eng in BROWSERS:
                check(f"{ver}: {eng} memuat AdminModules dan masih ter-auth",
                      out["authed"].get(eng) is True, f"url={out['url'].get(eng)}")
            say(f"    (a) {ver}: {time.monotonic() - t0:.0f}s")
        for ver in versions:
            t0 = time.monotonic()
            identical_findings(ver, module, work, session_tok, driven)
            say(f"    (b/c) {ver}: {time.monotonic() - t0:.0f}s")
    except Exception:  # noqa: BLE001
        traceback.print_exc()
        FAILS.append("exception")
    except fl.JobStopped:
        FAILS.append("dihentikan (--stop-job)")
    say(f"total: {time.monotonic() - t_all:.0f}s")
    if FAILS:
        say(f"GAGAL {len(FAILS)}: {FAILS} — folder kerja dipertahankan: {work}")
        return 1
    shutil.rmtree(work, ignore_errors=True)
    say("SEMUA LOLOS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
