#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Unit test untuk ps-e2e-run.py — fungsi murni, eksekusi langkah (page tiruan),
perakitan temuan, & degrade orkestrasi — semua tanpa Playwright/Docker nyata.

Playwright & Docker di-monkeypatch / tak dipanggil; logika langkah diuji dengan
page-tiruan (duck-typed). Jalankan: uv run scripts/tests/test-ps-e2e-run.py
"""
import contextlib
import importlib.util
import io
import json
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

MOD_PATH = Path(__file__).resolve().parent.parent / "ps-e2e-run.py"
spec = importlib.util.spec_from_file_location("ps_e2e_run", MOD_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}: {name}")
    return cond


# --- page tiruan (Playwright-like) untuk menguji run_steps tanpa browser ---
class _Resp:
    def __init__(self, status):
        self.status = status


class _LocFirst:
    def __init__(self, visible):
        self._v = visible

    def is_visible(self):
        return self._v


class _Loc:
    def __init__(self, visible, n=1):
        self.first = _LocFirst(visible)
        self._n = n

    def count(self):
        return self._n


class _TextLoc:
    """Locator teks dengan VISIBILITAS sebagai sumbu nyata, bukan turunan markup.

    Mock lama menurunkan "terlihat" dengan me-regex-strip <script>+tag — yaitu
    mengimplementasi ULANG teknik yang justru diganti, sehingga suite mustahil
    menangkap get_by_text yang tak memfilter visibilitas. Di sini halaman-tiruan
    menyatakan teks terlihat & tersembunyi secara terpisah: `count()` menghitung
    keduanya (persis get_by_text asli), `filter(visible=True)` hanya yang terlihat.
    """
    def __init__(self, vis_hits, hid_hits):
        self._vis, self._hid = vis_hits, hid_hits

    def count(self):
        return self._vis + self._hid

    def filter(self, visible=False):
        return _TextLoc(self._vis, 0 if visible else self._hid)


class _FakeReq:
    def __init__(self, kind):
        self.resource_type = kind


class _FakeResp:
    """Respons dgn body MENTAH — beda kanal dari DOM (page.content())."""
    def __init__(self, url, body, status=200, kind="document"):
        self.url, self._body, self.status = url, body, status
        self.request = _FakeReq(kind)

    def text(self):
        return self._body


class FakePage:
    """Halaman-tiruan. Tiga kanal dipisah sengaja, karena browser asli memisahkannya:
    `raw_body` (yang dikirim server), `html` (DOM terserialisasi), dan teks
    terlihat/tersembunyi. Fatal yang memotong render hanya kelihatan di raw_body."""
    def __init__(self, *, status=200, html="<html><body>halaman ok</body></html>",
                 visible=True, raise_on=None, loc_count=1, url_after_click=None,
                 raw_body="<html><body>halaman ok</body></html>", visible_text="", hidden_text=""):
        self._status = status
        self._html = html
        self._visible = visible
        self._raise_on = set(raise_on or ())
        self._loc_count = loc_count
        self._url_after_click = url_after_click
        self._raw_body = raw_body
        self._visible_text = visible_text
        self._hidden_text = hidden_text
        self._handlers = {}
        self.url = ""
        self.log = []

    def get_by_text(self, txt):
        self.log.append(("get_by_text", txt))
        return _TextLoc(1 if txt and txt in self._visible_text else 0,
                        1 if txt and txt in self._hidden_text else 0)

    def set_default_timeout(self, t):
        pass

    def wait_for_load_state(self, state="load", **k):
        self.log.append(("wait", state))
        if state in self._raise_on:
            raise RuntimeError(f"{state} timeout")

    def emit_response(self, url=None, kind="document"):
        """Picu listener response — meniru navigasi yang dipicu klik (bukan goto)."""
        h = self._handlers.get("response")
        if h and self._raw_body is not None:
            h(_FakeResp(url or self.url, self._raw_body, self._status, kind))

    def goto(self, url):
        self.log.append(("goto", url))
        self.url = url
        if "goto" in self._raise_on:
            raise RuntimeError("nav gagal")
        if self._raw_body is None:
            return _Resp(self._status)          # respons tanpa body terbaca
        return _FakeResp(url, self._raw_body, self._status)

    def content(self):
        return self._html

    def locator(self, sel):
        if "visible" in self._raise_on:
            raise RuntimeError("locator gagal")
        return _Loc(self._visible, self._loc_count)

    def click(self, sel):
        self.log.append(("click", sel))
        if "click" in self._raise_on:
            raise RuntimeError("click gagal")
        if self._url_after_click is not None:
            self.url = self._url_after_click

    def fill(self, sel, val):
        self.log.append(("fill", sel, val))
        if "fill" in self._raise_on:
            raise RuntimeError("fill gagal")

    def select_option(self, sel, label=None, value=None):
        self.log.append(("select_option", sel, label, value))
        if "select" in self._raise_on:
            raise RuntimeError("select gagal")

    def on(self, event, handler):
        self.log.append(("on", event))
        self._handlers[event] = handler

    def screenshot(self, path=None, full_page=False):
        self.log.append(("screenshot", path))
        if "screenshot" in self._raise_on:
            raise RuntimeError("screenshot gagal")


class LatePage(FakePage):
    """Halaman yang teksnya baru TERLIHAT setelah `appear_after` pemeriksaan.

    Ini yang membedakan `wait_for_text` dari `expect_text`: yang kedua menilai seketika
    dan akan merah pada halaman yang masih menyusul. Tanpa page seperti ini, test tak
    bisa membedakan implementasi yang benar-benar menunggu dari yang cuma mengecek sekali.
    """
    def __init__(self, appear_after, text, **kw):
        super().__init__(**kw)
        self._appear_after = appear_after
        self._text = text
        self.checks = 0

    def get_by_text(self, txt):
        self.checks += 1
        hit = 1 if (txt == self._text and self.checks > self._appear_after) else 0
        return _TextLoc(hit, 0)


class _FakeContext:
    def __init__(self, page):
        self._page = page

    def new_page(self):
        return self._page


class _FakeBrowser:
    """Browser-tiruan untuk menguji _drive_page tanpa Playwright. raise_on_context
    mensimulasikan browser mati setelah launch (gap honest-degrade yang ditutup)."""
    def __init__(self, page, raise_on_context=False):
        self._page = page
        self._raise = raise_on_context
        self.closed = False

    def new_context(self, **k):
        if self._raise:
            raise RuntimeError("browser mati setelah launch")
        return _FakeContext(self._page)

    def close(self):
        self.closed = True


def _ctx(bo_authed=False):
    return {"fo": "http://fo", "bo": "http://bo", "mod": "m", "bo_authed": bo_authed}


def _wired(page, bo_authed=False):
    """ctx dgn kanal body mentah dipasang persis seperti _drive_page produksi.

    Penting: sink diisi HANYA lewat listener response nyata, jadi test menempuh
    seam yang sama dengan produksi — bukan menyuapi body langsung ke ctx.
    """
    doc = {}
    page.on("response", lambda r: mod._track_document(doc, r))
    return {**_ctx(bo_authed), "doc": doc}


def _by_action(results, action):
    return [r for r in results if r["action"] == action]


# ---------------------------------------------------------------------------
# Bukti per sel (cell-contract.md > Evidence record > Producers) + durasi fase (CAP-6)
# ---------------------------------------------------------------------------
_TAG = "9.1.4-nginx"


@contextlib.contextmanager
def _infra(fl_over=None, mod_over=None):
    """Tiru seam Docker/Playwright run_one_version. Stub default membuka fase seperti
    implementasi asli, supaya sink durasi menerima nama fase yang sama dgn produksi."""
    def _ph(name, ret):
        def f(*a, **k):
            with mod.fl.phase(name):
                return ret
        return f

    fl_new = {"compose_available": lambda: True, "image_present": lambda ref: True,
              "_bring_up_compose": _ph("bring-up", ({"ps_container": "x", "mode": "compose"}, None)),
              "wait_healthy": _ph("wait-healthy", (True, "healthy")),
              "_teardown": _ph("teardown", None), "_logs": lambda c: "LOG-TAIL",
              "pull_image": _ph("pull", None)}
    mod_new = {"install_module": _ph("install", ({"ok": True, "no_console": False}, None)),
               "wait_http": lambda *a, **k: (True, 200, True),
               "drive_engine": _page_drive({})}
    fl_new.update(fl_over or {})
    mod_new.update(mod_over or {})
    saved_fl = {n: getattr(mod.fl, n) for n in fl_new}
    saved_mod = {n: getattr(mod, n) for n in mod_new}
    try:
        for n, v in fl_new.items():
            setattr(mod.fl, n, v)
        for n, v in mod_new.items():
            setattr(mod, n, v)
        yield
    finally:
        for n, v in saved_fl.items():
            setattr(mod.fl, n, v)
        for n, v in saved_mod.items():
            setattr(mod, n, v)


def _page_drive(pages, launch_error=None):
    """drive_engine tiruan yang menempuh _drive_page + run_steps ASLI di atas FakePage per
    engine (indeks langkah lahir di run_steps, bukan disuapi). `launch_error` = {engine: msg}."""
    launch_error = launch_error or {}

    def drive(engine, scenarios, ctx, headed=False):
        if engine in launch_error:
            return {"browser": engine, "scenarios": [], "launch_error": launch_error[engine],
                    "bo_authed": False}
        page = pages.get(engine) or FakePage()
        out, authed = mod._drive_page(_FakeBrowser(page), engine, scenarios, ctx)
        return {"browser": engine, "scenarios": out, "launch_error": None, "bo_authed": authed}
    return drive


def _rov(browsers, scenarios=None, requested=None, **kw):
    args = dict(orchestrator="auto", db_image="mariadb:lts", ps_domain="localhost:8000",
                admin_path="admin-dev", admin_email="a", admin_password="b",
                startup_timeout=1, op_timeout=1, nav_timeout=1000, allow_pull=False)
    args.update(kw)
    return mod.run_one_version(Path("/tmp"), "m", "9.1", _TAG, browsers,
                               scenarios or [mod.universal_smoke()],
                               requested_browsers=requested if requested is not None else list(browsers),
                               **args)


def _utc_us(ts):
    try:
        d = datetime.fromisoformat(ts)
    except (TypeError, ValueError):
        return None
    return d if d.utcoffset() == timedelta(0) and re.search(r"\.\d{6}\+00:00$", ts) else None


def test_cells_and_timing():
    ok = True
    print("\n[bukti per sel + durasi fase]")
    authored = {"name": "cfg", "source": "cfg.json",
                "steps": [{"action": "goto", "area": "fo", "path": "/"},
                          {"action": "expect_visible", "selector": "#x"}]}
    fatal = "<html><body>Fatal error: boom</body></html>"
    pages = {"chromium": FakePage(raw_body=fatal, visible=False), "firefox": FakePage()}

    # --- sukses: dua engine, temuan hanya di chromium ---
    with _infra(mod_over={"drive_engine": _page_drive(pages)}):
        r = _rov(["chromium", "firefox"], [mod.universal_smoke(), authored],
                 scenario_notes=["cfg.json: catatan"])
    cells = r.get("cells", {})
    ok &= check("sukses: cells untuk tiap engine yang di-drive", list(cells) == ["chromium", "firefox"])
    ok &= check("field level-versi: run_id/boot_id = fl.RUN_ID, boot cold, image_tag = tag, "
                "browser_mode sequential",
                r["run_id"] == mod.fl.RUN_ID and r["boot_id"] == mod.fl.RUN_ID and r["boot"] == "cold"
                and r["image_tag"] == _TAG and r["tag"] == _TAG and r["browser_mode"] == "sequential")
    ok &= check("field level-versi: boot_log null tanpa kegagalan boot, scenario_notes disalin ke versi, "
                "errors/install ada",
                r["boot_log"] is None and r["scenario_notes"] == ["cfg.json: catatan"]
                and r["errors"] == [] and r["install"]["ok"] is True)
    ch, ff = cells.get("chromium", {}), cells.get("firefox", {})
    ts = [_utc_us(c.get(k)) for c in (ch, ff) for k in ("started_at", "finished_at")]
    ok &= check("timestamp sel = UTC ISO-8601 bermikrodetik (+00:00)", all(ts))
    ok &= check("timestamp sel = start/end engine-nya (chromium selesai sebelum firefox mulai)",
                all(ts) and ts[0] <= ts[1] <= ts[2] <= ts[3])
    ok &= check("scenario_set full + scenarios_run = nama spec (smoke termasuk)",
                all(c["scenario_set"] == "full" and c["scenarios_run"] == ["psm-universal-smoke", "cfg"]
                    for c in (ch, ff)))
    got = {(f["scenario"], f["step"], f["action"]) for f in ch.get("findings") or []}
    ok &= check("temuan chromium membawa action + step (indeks 0-based di steps spec-nya)",
                got == {("psm-universal-smoke", 1, "expect_no_fatal"),
                        ("psm-universal-smoke", 2, "expect_visible"),
                        ("psm-universal-smoke", 4, "expect_no_fatal"),
                        ("cfg", 1, "expect_visible")})
    ok &= check("temuan per engine: firefox bersih, semua temuan chromium ber-browser chromium",
                ff["findings"] == [] and all(f["browser"] == "chromium" for f in ch["findings"]))
    ok &= check("daftar temuan lama versi = gabungan temuan sel (run langsung tak berubah)",
                r["findings"] == ch["findings"] + ff["findings"] and r["pass"] is False)
    ok &= check("authored_assertions per sel (1 expect_* authored konklusif tiap engine)",
                ch["authored_assertions"] == 1 and ff["authored_assertions"] == 1)
    ok &= check("bo_authed/launch_error/browser_notes per sel; hook tertunda null",
                ch["bo_authed"] is False and ch["launch_error"] is None and ch["browser_notes"] == []
                and all(c["scenario_spans"] is None and c["parallel_only"] is None for c in (ch, ff)))
    ok &= check("console_errors int & screenshots list per sel",
                isinstance(ch["console_errors"], int) and isinstance(ff["screenshots"], list))
    ok &= check("partisi durasi: browser:<engine> hanya di phase_durations sel-nya",
                set(ch["phase_durations"]) == {"browser:chromium"}
                and set(ff["phase_durations"]) == {"browser:firefox"})
    ok &= check("partisi durasi: boot_phases = fase container, tanpa browser:*",
                set(r["boot_phases"]) == {"bring-up", "wait-healthy", "install", "wait-http",
                                          "warmup-bo", "teardown"}
                and all(set(v) == {"seconds", "outcome"} for v in r["boot_phases"].values()))
    ok &= check("State per sel: chromium fail, firefox pass",
                mod.cell_state(r, "chromium")["state"] == "fail"
                and mod.cell_state(r, "firefox")["state"] == "pass")
    ok &= check("exit code: satu sel fail -> 3", mod.exit_code({"versions": {"9.1": r}}) == 3)
    ok &= check("sink durasi dinonaktifkan sesudah run_one_version", mod.fl._TIMING["sink"] is None)

    # --- launch error satu engine ---
    with _infra(mod_over={"drive_engine": _page_drive({}, {"firefox": "binary hilang"})}):
        rl = _rov(["chromium", "firefox"])
    lf, lc = rl["cells"]["firefox"], rl["cells"]["chromium"]
    ok &= check("launch error: sel tetap ada, launch_error + timestamp engine terisi",
                lf["launch_error"] == "binary hilang" and _utc_us(lf["started_at"])
                and _utc_us(lf["finished_at"]) and lf["findings"] == [])
    ok &= check("launch error: scenarios_run kosong (engine tak men-drive apa pun)",
                lf["scenarios_run"] == [] and lc["scenarios_run"] != [])
    ok &= check("launch error: catatan hanya di sel engine itu",
                any("firefox" in n for n in lf["browser_notes"]) and lc["browser_notes"] == [])
    ok &= check("launch error: State firefox inconclusive/launch-error, chromium pass -> exit 1",
                mod.cell_state(rl, "firefox") == {"state": "inconclusive", "conclusive": False,
                                                  "reason": "launch-error"}
                and mod.cell_state(rl, "chromium")["state"] == "pass"
                and mod.exit_code({"versions": {"9.1": rl}}) == 1)

    # --- install gagal: sel tetap dipancarkan, timestamp null ---
    def _bad_install(*a, **k):
        with mod.fl.phase("install"):
            return {"ok": False}, None
    with _infra(mod_over={"install_module": _bad_install}):
        ri = _rov(["chromium", "firefox"])
    ok &= check("install gagal: cells untuk tiap engine, started_at/finished_at null",
                list(ri["cells"]) == ["chromium", "firefox"]
                and all(c["started_at"] is None and c["finished_at"] is None
                        and c["phase_durations"] == {} and c["findings"] is None
                        for c in ri["cells"].values()))
    ok &= check("install gagal: boot_phases memuat install & teardown, State reason install, exit 1",
                {"install", "teardown"} <= set(ri["boot_phases"])
                and mod.cell_state(ri, "chromium")["reason"] == "install"
                and mod.exit_code({"versions": {"9.1": ri}}) == 1)

    # --- boot gagal (wait-healthy): install null, boot_log terisi ---
    def _unhealthy(*a, **k):
        with mod.fl.phase("wait-healthy"):
            return False, "unhealthy"
    with _infra(fl_over={"wait_healthy": _unhealthy}):
        rb = _rov(["chromium"])
    ok &= check("boot gagal: sel ada (timestamp null), install null, boot_log = tail log, reason errors",
                rb["cells"]["chromium"]["started_at"] is None and rb["install"] is None
                and rb["boot_log"] == "LOG-TAIL"
                and mod.cell_state(rb, "chromium")["reason"] == "errors")

    # --- probe drop: catatan firefox tak mendarat di sel mana pun ---
    with _infra():
        rp = _rov(["chromium"], requested=["chromium", "firefox"])
    ok &= check("probe drop: hanya sel chromium; catatan drop di daftar lama, tidak di sel chromium",
                list(rp["cells"]) == ["chromium"] and rp["cells"]["chromium"]["browser_notes"] == []
                and any("firefox" in n for n in rp["browser_notes"]))

    # --- tak ada engine: cells {}, boot_phases {}, boot_id tetap diset ---
    r0 = _rov([])
    ok &= check("tanpa engine: cells {}, boot_phases {}, boot_id diset, boot_wall_clock angka",
                r0["cells"] == {} and r0["boot_phases"] == {} and r0["boot_id"] == mod.fl.RUN_ID
                and isinstance(r0["boot_wall_clock"], float))
    ok &= check("versi tanpa sel -> exit 1", mod.exit_code({"versions": {"9.1": r0}}) == 1)

    # --- #n: pull image PS + DB, retry port (bring-up#2/teardown#2), browser kedua ---
    bring = {"n": 0}

    def _bring(*a, **k):
        with mod.fl.phase("bring-up"):
            bring["n"] += 1
            if bring["n"] == 1:
                return None, "Bind for 0.0.0.0:8000 failed: port is already allocated"
            return {"ps_container": "x", "mode": "compose"}, None

    def _slow_teardown(*a, **k):
        with mod.fl.phase("teardown"):
            time.sleep(0.2)

    base_drive = _page_drive({})

    def _two_pass(engine, scenarios, ctx, headed=False):
        if engine == "chromium":  # pass browser kedua (mis. fallback login BO, CAP-7)
            with mod.fl.phase("browser:chromium"):
                pass
        return base_drive(engine, scenarios, ctx, headed)

    with _infra(fl_over={"image_present": lambda ref: False, "_bring_up_compose": _bring,
                         "_teardown": _slow_teardown},
                mod_over={"drive_engine": _two_pass}):
        rt = _rov(["chromium", "firefox"], allow_pull=True)
    bp = rt["boot_phases"]
    ok &= check("#n di boot_phases: pull/pull#2, bring-up/bring-up#2, teardown/teardown#2",
                {"pull", "pull#2", "bring-up", "bring-up#2", "teardown", "teardown#2"} <= set(bp)
                and not any(k.startswith("browser:") for k in bp))
    ok &= check("#n di phase_durations: browser:chromium + browser:chromium#2 hanya di sel chromium",
                set(rt["cells"]["chromium"]["phase_durations"]) == {"browser:chromium", "browser:chromium#2"}
                and set(rt["cells"]["firefox"]["phase_durations"]) == {"browser:firefox"})
    ok &= check("outcome fase = status END ('ok')", bp["teardown#2"]["outcome"] == "ok")
    phase_sum = (sum(v["seconds"] for v in bp.values())
                 + sum(v["seconds"] for v in rt["cells"]["firefox"]["phase_durations"].values())
                 + rt["cells"]["chromium"]["phase_durations"]["browser:chromium#2"]["seconds"])
    ok &= check("boot_wall_clock diukur SESUDAH _teardown kembali (>= jumlah fase berurutan, "
                "teardown 2x0.2s termasuk)",
                rt["boot_wall_clock"] >= 0.4 and rt["boot_wall_clock"] + 0.002 >= phase_sum)
    return ok


def _write_cells(versions_states):
    """Hasil run_one_version tiruan: {ver: {engine: 'pass'|'fail'|'launch'}}."""
    out = {}
    for ver, states in versions_states.items():
        cells = {}
        for e, st in states.items():
            cells[e] = {"findings": [{"id": "x"}] if st == "fail" else [],
                        "launch_error": "boom" if st == "launch" else None,
                        "phase_durations": {f"browser:{e}": {"seconds": 0.1, "outcome": "ok"}}}
        out[ver] = {"errors": [], "install": {"ok": True}, "cells": cells, "pass": False}
    return out


def _main(argv, plan=None, playwright=True, docker=True, usable=True):
    """Jalankan mod.main() dgn argv; return (rc, output dict | None, requested engines seen)."""
    seen = {}

    def fake_rov(module_dir, mod_name, full_ver, tag, browsers, scenarios, *,
                 requested_browsers=None, scenario_notes=(), **kw):
        seen.setdefault("browsers", list(browsers))
        seen["requested"] = list(requested_browsers)
        seen["notes"] = list(scenario_notes)
        return (plan or {}).get(full_ver) or {"errors": [], "install": None, "cells": {},
                                               "pass": False}

    saved = (mod.playwright_available, mod.fl.docker_available, mod.browser_available,
             mod.run_one_version, mod.fl.job_start)
    with tempfile.TemporaryDirectory() as td:
        mdir = Path(td) / "m"
        (mdir / "tests" / "e2e").mkdir(parents=True)
        (mdir / "tests" / "e2e" / "broken.json").write_text("{bukan json")
        out = Path(td) / "out.json"
        cfg = Path(td) / "cfg.json"
        cfg.write_text(json.dumps({"psm_e2e_browsers": "firefox"}))
        full = [str(MOD_PATH), str(mdir), "-o", str(out)] + [a.replace("{cfg}", str(cfg)) for a in argv]
        try:
            mod.playwright_available = lambda: playwright
            mod.fl.docker_available = lambda: docker
            mod.browser_available = lambda e: usable
            if plan is not None:
                mod.run_one_version = fake_rov
            mod.fl.job_start = lambda *a, **k: True
            with mock.patch.object(sys, "argv", full), contextlib.redirect_stderr(io.StringIO()):
                rc = mod.main()
        finally:
            (mod.playwright_available, mod.fl.docker_available, mod.browser_available,
             mod.run_one_version, mod.fl.job_start) = saved
        data = json.loads(out.read_text()) if out.exists() else None
    return rc, data, seen


def test_main_engines_and_exit():
    ok = True
    print("\n[--engines + exit code]")
    two = ["--versions", "8.1,9.1"]
    rc, _, _ = _main(two, plan=_write_cells({"8.1": {"chromium": "pass", "firefox": "pass"},
                                              "9.1": {"chromium": "pass", "firefox": "pass"}}))
    ok &= check("exit 0: tiap sel yang dipancarkan pass", rc == 0)
    rc, _, _ = _main(two, plan=_write_cells({"8.1": {"chromium": "pass", "firefox": "launch"},
                                              "9.1": {"chromium": "fail", "firefox": "pass"}}))
    ok &= check("exit 3: ada sel fail (apa pun state sel lain)", rc == 3)
    rc, _, _ = _main(two, plan=_write_cells({"8.1": {"chromium": "pass", "firefox": "launch"},
                                              "9.1": {"chromium": "pass", "firefox": "pass"}}))
    ok &= check("exit 1: sel inconclusive tanpa fail", rc == 1)
    rc, _, _ = _main(two, plan=_write_cells({"8.1": {"chromium": "pass"}, "9.1": {}}))
    ok &= check("exit 1: versi tanpa sel yang di-drive", rc == 1)
    rc, data, _ = _main(["--versions", "9.1"], usable=False)
    ok &= check("exit 1: run_one_version asli tanpa engine terpasang (cells {})",
                rc == 1 and data["versions"]["9.1"]["cells"] == {})
    rc, data, _ = _main(["--versions", "9.1"], playwright=False)
    ok &= check("exit 0: Playwright absen -> skipped", rc == 0 and data["status"] == "skipped")
    rc, data, _ = _main(["--versions", "9.1"], docker=False)
    ok &= check("exit 0: Docker absen -> skipped", rc == 0 and data["status"] == "skipped")

    ok_plan = _write_cells({"9.1": {"chromium": "pass"}})
    rc, data, seen = _main(["--versions", "9.1", "--config", "{cfg}"], plan=ok_plan)
    ok &= check("tanpa --engines: psm_e2e_browsers dari --config dipakai",
                seen.get("requested") == ["firefox"] and data["browsers"] == ["firefox"])
    rc, data, seen = _main(["--versions", "9.1", "--config", "{cfg}", "--browsers", "webkit",
                            "--engines", "Chromium,chromium"], plan=ok_plan)
    ok &= check("--engines menang atas --browsers & --config (dinormalisasi)",
                rc == 0 and seen.get("requested") == ["chromium"] and seen.get("browsers") == ["chromium"])
    ok &= check("scenario_notes run diteruskan ke tiap versi (dan tetap ada di level run)",
                len(seen.get("notes") or []) == 1 and "broken.json" in seen["notes"][0]
                and data["scenario_notes"] == seen["notes"])
    for label, argv in (("--engines safari", ["--engines", "safari"]),
                        ("--engines kosong", ["--engines", ""]),
                        ("--browsers typo", ["--browsers", "chromium,firefx"]),
                        ("--engines tak sah walau --browsers sah",
                         ["--browsers", "chromium", "--engines", "ie"])):
        rc, data, seen = _main(["--versions", "9.1"] + argv, plan=ok_plan)
        ok &= check(f"exit 2: {label} (tak ada versi dijalankan)", rc == 2 and not seen and data is None)
    return ok


def test_sequential_browsers():
    """I/O 'Sequential child': --sequential-browsers + chromium fail -> firefox not-run, tak
    pernah di-drive, anak exit 3. Tanpa flag (run langsung) semua engine tetap jalan."""
    ok = True
    print("\n[--sequential-browsers: fail-fast antar-engine]")
    fatal = "<html><body>Fatal error: boom</body></html>"

    def tracked(pages):
        base = _page_drive(pages)
        seen = []

        def drive(engine, scenarios, ctx, headed=False):
            seen.append(engine)
            return base(engine, scenarios, ctx, headed)
        return drive, seen

    drive, seen = tracked({"chromium": FakePage(raw_body=fatal)})
    with _infra(mod_over={"drive_engine": drive}):
        r = _rov(["chromium", "firefox"], sequential_browsers=True)
    ff, ch = r["cells"]["firefox"], r["cells"]["chromium"]
    ok &= check("sekuensial: chromium fail -> firefox TAK pernah di-drive", seen == ["chromium"])
    ok &= check("sekuensial: sel firefox state not-run, conclusive false, reason fail-fast after 9.1:chromium",
                (ff.get("state"), ff.get("conclusive"), ff.get("reason"))
                == ("not-run", False, "fail-fast after 9.1:chromium"))
    ok &= check("sekuensial: semua kunci _new_cell sel not-run null (scenario_set/browser_notes/"
                "phase_durations termasuk)",
                set(mod._new_cell()) <= set(ff) and all(ff[k] is None for k in mod._new_cell()))
    ok &= check("sekuensial: sel chromium tetap punya browser:chromium & state fail",
                set(ch["phase_durations"]) == {"browser:chromium"}
                and mod.cell_state(r, "chromium")["state"] == "fail")
    ok &= check("sekuensial: cell_state mempertahankan not-run; exit anak 3",
                mod.cell_state(r, "firefox")["state"] == "not-run"
                and mod.exit_code({"versions": {"9.1": r}}) == 3)
    ok &= check("sekuensial: fallback tak menyentuh browser_notes/errors",
                r["browser_notes"] == [] and r["errors"] == [])

    drive, seen = tracked({})
    with _infra(mod_over={"drive_engine": drive}):
        rp = _rov(["chromium", "firefox"], sequential_browsers=True)
    ok &= check("sekuensial: chromium pass -> firefox tetap di-drive (keduanya pass)",
                seen == ["chromium", "firefox"]
                and all(mod.cell_state(rp, e)["state"] == "pass" for e in ("chromium", "firefox")))
    drive, seen = tracked({"chromium": FakePage(raw_body=fatal)})
    with _infra(mod_over={"drive_engine": drive}):
        rd = _rov(["chromium", "firefox"])
    ok &= check("tanpa --sequential-browsers (run langsung): engine lain tetap jalan",
                seen == ["chromium", "firefox"] and "state" not in rd["cells"]["firefox"])

    # main: fallback dicatat SEKALI di stderr bila > 1 engine; tidak bila 1 engine.
    def run_main(extra, engines):
        plan = _write_cells({"9.1": {e: "pass" for e in engines}})
        err = io.StringIO()
        saved = (mod.playwright_available, mod.fl.docker_available, mod.browser_available,
                 mod.run_one_version, mod.fl.job_start)
        seen_kw = {}

        def fake_rov(*a, **kw):
            seen_kw.update(kw)
            return plan["9.1"]
        with tempfile.TemporaryDirectory() as td:
            mdir = Path(td) / "m"
            mdir.mkdir()
            argv = [str(MOD_PATH), str(mdir), "--versions", "9.1", "--engines", ",".join(engines),
                    "-o", str(Path(td) / "o.json"), *extra]
            try:
                mod.playwright_available = lambda: True
                mod.fl.docker_available = lambda: True
                mod.browser_available = lambda e: True
                mod.run_one_version = fake_rov
                mod.fl.job_start = lambda *a, **k: True
                with mock.patch.object(sys, "argv", argv), contextlib.redirect_stderr(err):
                    rc = mod.main()
            finally:
                (mod.playwright_available, mod.fl.docker_available, mod.browser_available,
                 mod.run_one_version, mod.fl.job_start) = saved
        return rc, err.getvalue(), seen_kw
    rc, err, kw = run_main(["--sequential-browsers"], ["chromium", "firefox"])
    ok &= check("main --sequential-browsers (2 engine): fallback dicatat sekali di stderr, "
                "diteruskan ke run_one_version",
                rc == 0 and err.count("mode browser sekuensial") == 1
                and kw.get("sequential_browsers") is True and kw.get("slot_cost") == 1)
    rc, err, kw = run_main(["--sequential-browsers"], ["chromium"])
    ok &= check("main --sequential-browsers (1 engine): tanpa catatan fallback",
                rc == 0 and "mode browser sekuensial" not in err)
    rc, err, kw = run_main([], ["chromium", "firefox"])
    ok &= check("main tanpa flag: sequential_browsers False, tanpa catatan",
                kw.get("sequential_browsers") is False and "mode browser sekuensial" not in err)
    return ok


def test_child_flags():
    """--run-id (bentuk, RUN_ID sebelum log/registry/label), --slot-cost, --progress-append."""
    ok = True
    print("\n[flag anak: --run-id / --slot-cost / --progress-append]")
    for label, argv in (("--run-id XYZ", ["--run-id", "XYZ"]),
                        ("--run-id huruf besar", ["--run-id", "0123456789AB"]),
                        ("--run-id 11 karakter", ["--run-id", "0123456789a"]),
                        ("--run-id newline", ["--run-id", "0123456789ab\n"]),
                        ("--slot-cost 0", ["--slot-cost", "0"]),
                        ("--slot-cost x", ["--slot-cost", "x"])):
        rc, data, seen = _main(["--versions", "9.1"] + argv,
                               plan=_write_cells({"9.1": {"chromium": "pass"}}))
        ok &= check(f"exit 2: {label} (tak ada versi dijalankan)",
                    rc == 2 and not seen and data is None)

    fl = mod.fl
    saved = (fl.RUN_ID, fl.JOB_REGISTRY, dict(fl._JOB), dict(fl._PROGRESS),
             mod.playwright_available, fl.docker_available, mod.browser_available,
             mod.run_one_version)
    rid = "0123456789ab"
    captured = {}

    def fake_rov(*a, **kw):
        captured["label_run"] = fl.owner_labels()[fl.LABEL_RUN]
        captured["slot_cost"] = kw.get("slot_cost")
        fl.progress("START", "probe")
        return _write_cells({"9.1": {"chromium": "pass"}})["9.1"]
    try:
        with tempfile.TemporaryDirectory() as td:
            fl.JOB_REGISTRY = Path(td) / "reg"
            mdir = Path(td) / "mymod"
            mdir.mkdir()
            log = Path(td) / "mymod-e2e-9.1.progress.log"
            for append in (True, False):
                log.write_text("2026-11-26T10:00:00 job=j pid=1 run=x v=9.1 START wait-slots\n",
                               encoding="utf-8")
                argv = [str(MOD_PATH), str(mdir), "--versions", "9.1", "--engines", "chromium",
                        "--run-id", rid, "--job-id", "mymod-e2e-1200-abcd",
                        "--progress-file", str(log), "-o", str(Path(td) / "o.json")]
                if append:
                    argv.append("--progress-append")
                mod.playwright_available = lambda: True
                fl.docker_available = lambda: True
                mod.browser_available = lambda e: True
                mod.run_one_version = fake_rov
                with mock.patch.object(sys, "argv", argv), \
                        contextlib.redirect_stderr(io.StringIO()):
                    rc = mod.main()
                lines = log.read_text(encoding="utf-8").splitlines()
                if append:
                    entry = fl.JOB_REGISTRY / "mymod-e2e-1200-abcd" / f"{fl.OWNER_PID}.json"
                    reg = json.loads(entry.read_text()) if entry.is_file() else {}
                    out = json.loads((Path(td) / "o.json").read_text())
                    ok &= check("--run-id: dipasang sbg RUN_ID -> label psm.run",
                                rc == 0 and captured.get("label_run") == rid and fl.RUN_ID == rid)
                    ok &= check("--run-id: masuk entri registry job & baris log kemajuan",
                                reg.get("run") == rid and f" run={rid} " in lines[-1])
                    ok &= check("--slot-cost absen -> 1 diteruskan ke boot",
                                captured.get("slot_cost") == 1)
                    ok &= check("--progress-append: baris wait-slots pemanggil dipertahankan",
                                "START wait-slots" in lines[0] and "START probe" in lines[-1])
                    ok &= check("output tetap dipancarkan (versi 9.1)", "9.1" in out["versions"])
                    fl._job_unregister()
                else:
                    ok &= check("tanpa --progress-append: log dikosongkan (perilaku lama)",
                                len(lines) == 1 and "START probe" in lines[0])
    finally:
        (fl.RUN_ID, fl.JOB_REGISTRY) = saved[0], saved[1]
        fl._JOB.clear()
        fl._JOB.update(saved[2])
        fl._PROGRESS.clear()
        fl._PROGRESS.update(saved[3])
        (mod.playwright_available, fl.docker_available, mod.browser_available,
         mod.run_one_version) = saved[4:]
        import signal as _sig
        _sig.signal(_sig.SIGTERM, _sig.SIG_DFL)
    return ok


def test_slot_labels():
    """I/O 'Labels': boot ps-e2e-run --slot-cost 2 (compose / manual) = jumlah psm.slots 2;
    tanpa --slot-cost = 1 / 1. Label dibaca dari teks compose ter-render & argv `docker run`."""
    ok = True
    print("\n[label psm.slots ps-e2e-run]")
    fl = mod.fl

    def boot(orch, extra):
        compose, runs = [], []

        def fake_run(cmd, **kw):
            if cmd[:2] == ["docker", "compose"] and "up" in cmd:
                compose.append(Path(cmd[cmd.index("-f") + 1]).read_text(encoding="utf-8"))
            if cmd[:2] == ["docker", "run"]:
                runs.append(list(cmd))
            out = "cid0\n" if ("ps" in cmd and "-q" in cmd) else ""
            return subprocess.CompletedProcess(cmd, 0, out, "")
        saved = (mod.playwright_available, fl.docker_available, mod.browser_available,
                 fl.job_start)
        with tempfile.TemporaryDirectory() as td:
            mdir = Path(td) / "m"
            mdir.mkdir()
            argv = [str(MOD_PATH), str(mdir), "--versions", "9.1", "--engines", "chromium",
                    "--orchestrator", orch, "-o", str(Path(td) / "o.json"), *extra]
            try:
                mod.playwright_available = lambda: True
                fl.docker_available = lambda: True
                mod.browser_available = lambda e: True
                fl.job_start = lambda *a, **k: True
                with _infra(fl_over={"_bring_up_compose": fl.__dict__["_bring_up_compose"],
                                     "wait_healthy": lambda c, t, poll=3.0: (True, "healthy"),
                                     "_teardown": lambda s: None}), \
                        mock.patch.object(fl.subprocess, "run", fake_run), \
                        mock.patch.object(sys, "argv", argv), \
                        contextlib.redirect_stderr(io.StringIO()):
                    rc = mod.main()
            finally:
                (mod.playwright_available, fl.docker_available, mod.browser_available,
                 fl.job_start) = saved
        total = sum(int(n) for t in compose for n in re.findall(r'psm\.slots: "(\d+)"', t))
        for r in runs:
            for i, a in enumerate(r):
                if a == "--label" and r[i + 1].startswith("psm.slots="):
                    total += int(r[i + 1].split("=", 1)[1])
        booted = bool(compose) if orch == "compose" else any(
            r[-1].startswith(f"{fl.IMAGE}:") for r in runs)
        return rc, total, booted
    for extra, want in ((["--slot-cost", "2"], 2), ([], 1)):
        for orch in ("compose", "manual"):
            rc, total, booted = boot(orch, extra)
            ok &= check(f"boot {orch} {' '.join(extra) or 'tanpa --slot-cost'}: psm.slots = {want}",
                        rc == 0 and booted and total == want)
    return ok


def main():
    ok = True

    # --- parse_browsers ---
    ok &= check("browsers 'chromium,firefox'", mod.parse_browsers("chromium,firefox") == ["chromium", "firefox"])
    ok &= check("browsers None -> default skrip", mod.parse_browsers(None) == ["chromium", "firefox"])
    ok &= check("browsers case-insensitif + dedup",
                mod.parse_browsers("Chromium, FIREFOX, chromium") == ["chromium", "firefox"])

    def _cfg_err(raw):
        try:
            mod.parse_browsers(raw)
        except mod.fl.CellConfigError:
            return True
        return False
    # Fallback diam-diam ke default DIGANTI normalizer bersama (cell-contract > Configured
    # cells): typo engine / daftar kosong adalah input error (main: exit 2), bukan cakupan lain.
    ok &= check("browsers kosong -> input error (bukan default diam-diam)", _cfg_err(""))
    ok &= check("browsers dgn satu engine tak didukung -> input error", _cfg_err("chromium,safari"))
    ok &= check("browsers semua invalid -> input error", _cfg_err("safari,ie"))

    # --- default timeout navigasi: flashlight dingin butuh >20s (kompilasi Smarty/Symfony) ---
    ok &= check("DEFAULT_NAV_TIMEOUT_S = 60 (anti false-positive 'halaman rusak' saat cold start)",
                mod.DEFAULT_NAV_TIMEOUT_S == 60)

    # --- tag-map: --extra-tag-map MENAMBAH (mirror --extra-rules), --tag-map MENGGANTI ---
    ok &= check("extra tag-map menambal 1 versi tanpa menjatuhkan sisanya (fix void Lapis 2)",
                mod.fl.parse_tag_map("", "9.2=9.2.0-nginx") ==
                {**mod.fl.DEFAULT_TAG_MAP, "9.2": "9.2.0-nginx"})
    ok &= check("tag-map penuh MENGGANTI peta default",
                mod.fl.parse_tag_map("9.1=custom") == {"9.1": "custom"})
    ok &= check("extra menang atas base utk versi yang sama",
                mod.fl.parse_tag_map("9.1=a", "9.1=b") == {"9.1": "b"})

    # --- host_port_from_domain / host_from_domain ---
    ok &= check("port 'localhost:8000' -> 8000", mod.host_port_from_domain("localhost:8000") == 8000)
    ok &= check("port tanpa ':' -> default 8000", mod.host_port_from_domain("localhost") == 8000)
    ok &= check("port host lain -> 9999", mod.host_port_from_domain("example.com:9999") == 9999)
    # Host DIPERTAHANKAN, cuma port yang mengambang: PS_DOMAIN yang di-set operator adalah
    # domain yang dikira toko miliknya; Lapis 4 harus men-drive host yang sama.
    ok &= check("host 'shop.local:9100' -> 'shop.local'", mod.host_from_domain("shop.local:9100") == "shop.local")
    ok &= check("host tanpa port -> apa adanya", mod.host_from_domain("shop.local") == "shop.local")
    ok &= check("host kosong -> localhost", mod.host_from_domain("") == "localhost")

    # --- pick_free_host_port (port dinamis: dua sesi paralel tak rebutan bind) ---
    import socket as _sock
    p_free = mod.pick_free_host_port(0)
    ok &= check("port 0 -> ephemeral bebas (>0)", isinstance(p_free, int) and p_free > 0)
    # preferred yang BEBAS dikembalikan apa adanya
    probe = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
    probe.bind(("", 0))
    free_pref = probe.getsockname()[1]
    probe.close()
    ok &= check("preferred bebas -> dipakai apa adanya",
                mod.pick_free_host_port(free_pref) == free_pref)
    # preferred yang TERPAKAI -> jatuh ke port lain yang bebas
    held = _sock.socket(_sock.AF_INET, _sock.SOCK_STREAM)
    held.setsockopt(_sock.SOL_SOCKET, _sock.SO_REUSEADDR, 1)
    held.bind(("", 0))
    held.listen(1)
    taken = held.getsockname()[1]
    alt = mod.pick_free_host_port(taken)
    ok &= check("preferred terpakai -> port berbeda & bebas", isinstance(alt, int) and alt > 0)
    held.close()
    # base_urls konsisten dengan port yang dipilih dinamis
    fo_dyn, _ = mod.base_urls(f"localhost:{p_free}", "admin-dev")
    ok &= check("base_urls memakai port dinamis", fo_dyn == f"http://localhost:{p_free}")
    # deteksi tabrakan port utk jalur retry
    ok &= check("_is_port_conflict kenal 'address already in use'",
                mod._is_port_conflict("docker: Error ... address already in use."))
    ok &= check("_is_port_conflict kenal 'already allocated'",
                mod._is_port_conflict("Bind for 0.0.0.0:8000 failed: port is already allocated"))
    ok &= check("_is_port_conflict tolak error lain",
                not mod._is_port_conflict("no such image"))

    # --- base_urls ---
    fo, bo = mod.base_urls("localhost:8000", "admin-dev")
    ok &= check("base fo", fo == "http://localhost:8000")
    ok &= check("base bo (folder admin)", bo == "http://localhost:8000/admin-dev")
    _, bo2 = mod.base_urls("localhost:8000", "/admin-dev/")
    ok &= check("admin_path slash dinormalkan", bo2 == "http://localhost:8000/admin-dev")

    # --- substitute ---
    s = mod.substitute("{fo}/a {bo}/b mod={mod}", _ctx())
    ok &= check("substitute {fo}/{bo}/{mod}", s == "http://fo/a http://bo/b mod=m")
    ok &= check("substitute {browser} -> engine aktif (nama data unik per-browser, DB bersama)",
                mod.substitute("data-{browser}", {**_ctx(), "engine": "firefox"}) == "data-firefox")

    # --- universal_smoke ---
    sm = mod.universal_smoke()
    ok &= check("smoke source builtin & punya langkah", sm["source"] == "builtin" and len(sm["steps"]) >= 4)
    ok &= check("smoke sentuh FO & BO",
                any(st.get("area") == "fo" for st in sm["steps"]) and
                any(st.get("area") == "bo" for st in sm["steps"]))
    ok &= check("smoke memicu login BO (_needs_bo)", mod._needs_bo([sm]) is True)
    ok &= check("_needs_bo False bila hanya FO",
                mod._needs_bo([{"steps": [{"action": "goto", "area": "fo"}]}]) is False)

    # --- run_steps: smoke bersih -> semua ok; BO tak konklusif tanpa login ---
    pg_sm = FakePage()
    res = mod.run_steps(pg_sm, sm["steps"], _wired(pg_sm))
    ok &= check("smoke bersih -> semua langkah ok", all(r["ok"] for r in res))
    fo_nofatal = _by_action(res, "expect_no_fatal")
    ok &= check("FO expect_no_fatal konklusif", fo_nofatal[0]["conclusive"] is True)
    # enh-2 (ronde-6): konklusivitas per-AKSI, bukan per-AREA. expect_no_fatal menilai RESPONS
    # server, sah tanpa auth → BO expect_no_fatal KONKLUSIF walau tak login. Dulu dikunci per-area
    # (tak konklusif tanpa login) sehingga BO 500-fatal → login gagal → assertion yang harusnya
    # menangkap fatal itu dilucuti → pass palsu. Assert lama ("TAK konklusif") membekukan cacat.
    ok &= check("BO expect_no_fatal KONKLUSIF tanpa login (aksi menilai respons server)",
                fo_nofatal[-1]["conclusive"] is True)
    # Aksi yang butuh SESI tetap tak konklusif tanpa auth (isi ber-auth tak bisa diverifikasi):
    bo_vis = mod.run_steps(FakePage(), [{"action": "goto", "area": "bo", "path": "/x"},
                                        {"action": "expect_visible", "selector": "#panel"}],
                           _wired(FakePage()))
    ok &= check("BO expect_visible (butuh auth) TAK konklusif tanpa login",
                _by_action(bo_vis, "expect_visible")[0]["conclusive"] is False)
    # Keanggotaan SESSION_INDEPENDENT_ACTIONS dijaga per-elemen (verifier ronde-6: mutasi
    # membuang 'goto' dari tuple LOLOS senyap = regresi menelanjangi BO tanpa-auth bisa masuk).
    bo_goto = mod.run_steps(FakePage(status=500),
                            [{"action": "goto", "area": "bo", "path": "/x"}], _wired(FakePage(status=500)))
    ok &= check("BO goto KONKLUSIF tanpa login (menilai status server) — jaga keanggotaan tuple",
                _by_action(bo_goto, "goto")[0]["conclusive"] is True)
    # expect_no_console_error SENGAJA di LUAR set: tanpa login halaman termuat = login page,
    # bukan BO module -> memblok atas derau console login = misattribusi. Konklusif hanya
    # lewat bo_authed. (verifier: keanggotaannya di set dulu tak dijaga & memang tak diinginkan.)
    bo_ce = mod.run_steps(FakePage(), [{"action": "goto", "area": "bo", "path": "/x"},
                                       {"action": "expect_no_console_error"}],
                          {**_wired(FakePage()), "console_sink": [], "console_base": 0})
    ok &= check("BO expect_no_console_error TAK konklusif tanpa login (bukan session-independent)",
                _by_action(bo_ce, "expect_no_console_error")[0]["conclusive"] is False)
    # enh-2 inti — BO yang 500-fatal tanpa login: expect_no_fatal konklusif & GAGAL → temuan
    # MEMBLOK lewat assemble_findings (bukan inconclusive). Sebelum fix: conclusive False →
    # temuan jatuh ke inconclusive → pass=true atas BO mati. Diuji lewat assemble_findings,
    # bukan cuma run_steps, karena di situ kanal konklusif→memblok ditentukan.
    pg_bo500 = FakePage(status=500, raw_body="<html><body>Fatal error: Call to undefined Psm::x()</body></html>")
    bo500 = mod.run_steps(pg_bo500, [{"action": "goto", "area": "bo", "path": "/index.php?controller=AdminModules"},
                                     {"action": "expect_no_fatal"}], _wired(pg_bo500))
    bo500_nf = _by_action(bo500, "expect_no_fatal")[0]
    ok &= check("BO 500-fatal tanpa login: expect_no_fatal konklusif & gagal",
                bo500_nf["conclusive"] is True and bo500_nf["ok"] is False)
    f_bo, inc_bo = mod.assemble_findings("9.1", [{"browser": "chromium", "scenarios": [
        {"name": "psm-universal-smoke", "source": "builtin", "results": bo500}]}])
    ok &= check("BO 500-fatal -> temuan konklusif MEMBLOK (bukan inconclusive; anti false-pass)",
                len(f_bo) >= 1 and any(f["severity"] == "error" for f in f_bo))
    # Kontrol positif: BO SEHAT tanpa login (redirect AdminLogin 200, tak ada fatal) → tak ada
    # false-block walau expect_no_fatal kini konklusif.
    bo_ok = mod.run_steps(FakePage(), sm["steps"], _wired(FakePage()))
    f_ok, _ = mod.assemble_findings("9.1", [{"browser": "chromium", "scenarios": [
        {"name": "psm-universal-smoke", "source": "builtin", "results": bo_ok}]}])
    ok &= check("BO sehat tanpa login -> nol temuan memblok (konklusif tak berarti false-block)",
                f_ok == [])

    # --- run_steps: fatal terdeteksi (status 500 & tanda fatal) ---
    r500 = mod.run_steps(FakePage(status=500), [{"action": "goto", "area": "fo", "path": "/"},
                                                {"action": "expect_no_fatal"}], _ctx())
    ok &= check("status 500 -> goto ok False & expect_no_fatal gagal",
                _by_action(r500, "goto")[0]["ok"] is False and _by_action(r500, "expect_no_fatal")[0]["ok"] is False)
    pg_fatal = FakePage(raw_body="<html><body><b>Fatal error</b>: boom</body></html>")
    rfatal = mod.run_steps(pg_fatal, [{"action": "goto", "area": "fo", "path": "/"},
                                      {"action": "expect_no_fatal"}], _wired(pg_fatal))
    ok &= check("tanda 'Fatal error' di body mentah -> expect_no_fatal gagal (konklusif)",
                _by_action(rfatal, "expect_no_fatal")[0]["ok"] is False
                and _by_action(rfatal, "expect_no_fatal")[0]["conclusive"] is True)

    # REGRESI CRITICAL: fatal PHP memotong render DI TENGAH <script> (status tetap 200).
    # Body MENTAH tak punya </script>, jadi _SCRIPT_RE tak match & fatalnya tetap terlihat.
    # Cek lama membaca page.content() — DOM terserialisasi yang MENUTUP tag itu — sehingga
    # seluruh fatal tersapu strip dan smoke universal LOLOS KONKLUSIF atas toko rusak.
    pg_trunc = FakePage(
        html='<html><body><div>toko</div><script>var t={"a":1};\n<b>Fatal error</b>: boom</script></body></html>',
        raw_body='<html><body><div>toko</div><script>var t={"a":1};\n<b>Fatal error</b>: boom')
    rtrunc = mod.run_steps(pg_trunc, [{"action": "goto", "area": "fo", "path": "/"},
                                      {"action": "expect_no_fatal"}], _wired(pg_trunc))
    ok &= check("fatal memotong render di tengah <script> -> GAGAL konklusif (anti false-pass)",
                _by_action(rtrunc, "expect_no_fatal")[0]["ok"] is False
                and _by_action(rtrunc, "expect_no_fatal")[0]["conclusive"] is True)
    ok &= check("mock jujur: DOM terserialisasi MENUTUP script (kalau dibaca, fatal tersapu)",
                mod.fatal_sign_in(pg_trunc._html) is None and mod.fatal_sign_in(pg_trunc._raw_body) == "Fatal error")

    # Kamus terjemahan di script TERTUTUP pada body mentah -> bukan fatal (anti false-block)
    pg_dict = FakePage(raw_body='<html><head><script>var t={"e":"There was an error"};</script></head>'
                                '<body>ok</body></html>')
    rdict = mod.run_steps(pg_dict, [{"action": "goto", "area": "fo", "path": "/"},
                                    {"action": "expect_no_fatal"}], _wired(pg_dict))
    ok &= check("frasa generik di <script> TERTUTUP (kamus terjemahan) -> BUKAN fatal",
                _by_action(rdict, "expect_no_fatal")[0]["ok"] is True)

    # Body mentah tak tertangkap -> TAK menilai (tak konklusif), bukan menebak dari DOM
    pg_nobody = FakePage(raw_body=None, html="<b>Fatal error</b>: boom")
    rnobody = mod.run_steps(pg_nobody, [{"action": "goto", "area": "fo", "path": "/"},
                                        {"action": "expect_no_fatal"}], _wired(pg_nobody))
    nf = _by_action(rnobody, "expect_no_fatal")[0]
    ok &= check("tanpa body mentah -> tak konklusif & disurface (bukan tebakan dari DOM)",
                nf["ok"] is False and nf["conclusive"] is False and "mentah" in nf["message"])

    # --- _track_document: jalur listener (navigasi dipicu klik, bukan goto) ---
    sink = {}
    mod._track_document(sink, _FakeResp("http://x/a", "<b>Fatal error</b>: boom"))
    ok &= check("_track_document simpan body dokumen dikunci URL", sink.get("http://x/a") is not None)
    mod._track_document(sink, _FakeResp("http://x/img.png", "binari", kind="image"))
    ok &= check("_track_document abaikan non-dokumen (iframe/subresource tak mencemari)",
                "http://x/img.png" not in sink)

    class _RaisingResp(_FakeResp):
        def text(self):
            raise RuntimeError("body tak tersedia (redirect)")
    mod._track_document(sink, _RaisingResp("http://x/b", ""))
    ok &= check("_track_document: body tak terbaca -> sink tak terisi (tak crash, degrade jujur)",
                "http://x/b" not in sink)

    # body basi TAK dipakai: sink punya URL lain, halaman kini di URL berbeda
    pg_stale = FakePage(raw_body=None)
    stale_ctx = {**_ctx(), "doc": {"http://lama": "<b>Fatal error</b>: lama"}}
    pg_stale.url = "http://baru"
    rstale = mod.run_steps(pg_stale, [{"action": "expect_no_fatal"}], stale_ctx)
    ok &= check("body basi URL lain -> tak dipakai (tak konklusif), bukan divonis dari halaman lama",
                rstale[0]["conclusive"] is False and rstale[0]["ok"] is False)

    # --- run_steps: expect_visible / expect_text ---
    rvis = mod.run_steps(FakePage(visible=False), [{"action": "expect_visible", "selector": "#x"}], _ctx())
    ok &= check("expect_visible False -> gagal", rvis[0]["ok"] is False)
    pg_text = FakePage(visible_text="Update successful")
    rtext = mod.run_steps(pg_text,
                          [{"action": "expect_text", "text": "successful"},
                           {"action": "expect_text", "text": "tak-ada"}], _ctx())
    ok &= check("expect_text terlihat -> ok, tak ada -> gagal",
                rtext[0]["ok"] is True and rtext[1]["ok"] is False)
    ok &= check("expect_text settle 'load' dulu (anti false-fail timing pasca submit/redirect)",
                ("wait", "load") in pg_text.log)
    rsettle = mod.run_steps(FakePage(visible_text="x", raise_on={"load"}),
                            [{"action": "expect_text", "text": "x"}], _ctx())
    ok &= check("expect_text: settle raise -> best-effort, assertion tetap dievaluasi",
                rsettle[0]["ok"] is True)
    # REGRESI: teks HANYA di node tersembunyi (template growl/modal BO) -> HARUS gagal.
    # get_by_text tanpa filter menghitung node display:none -> simpan GAGAL terbaca lolos.
    pg_hidden = FakePage(visible_text="Invalid security token", hidden_text="Update successful")
    rhidden = mod.run_steps(pg_hidden, [{"action": "expect_text", "text": "successful"}],
                            _ctx(bo_authed=True))
    ok &= check("expect_text: teks hanya di node tersembunyi -> GAGAL (anti false-pass)",
                rhidden[0]["ok"] is False)
    ok &= check("mock jujur: tanpa filter(visible=True) node tersembunyi TERHITUNG",
                pg_hidden.get_by_text("successful").count() == 1
                and pg_hidden.get_by_text("successful").filter(visible=True).count() == 0)

    # --- run_steps: click/fill sukses & exception -> gagal ---
    rcf = mod.run_steps(FakePage(), [{"action": "fill", "selector": "#a", "value": "1"},
                                     {"action": "click", "selector": "#b"}], _ctx())
    ok &= check("fill+click sukses -> ok", all(r["ok"] for r in rcf))
    rexc = mod.run_steps(FakePage(raise_on={"goto"}), [{"action": "goto", "area": "fo", "path": "/"}], _ctx())
    ok &= check("goto exception -> ok False (assertion gagal)", rexc[0]["ok"] is False)

    # --- run_steps: click_optional — klik bila elemen ada, lewati tanpa gagal bila tidak ---
    ok &= check("click_optional terdaftar di SUPPORTED_ACTIONS (lolos validasi spec authored)",
                "click_optional" in mod.SUPPORTED_ACTIONS)
    pg_opt = FakePage()
    ropt = mod.run_steps(pg_opt, [{"action": "click_optional", "selector": "#tok-ok"}], _ctx())
    ok &= check("click_optional elemen ada -> diklik & ok",
                ropt[0]["ok"] is True and ("click", "#tok-ok") in pg_opt.log)
    pg_opt0 = FakePage(loc_count=0)
    ropt0 = mod.run_steps(pg_opt0, [{"action": "click_optional", "selector": "#tok-ok"}], _ctx())
    ok &= check("click_optional elemen tak ada -> dilewati tanpa gagal (tak ada klik)",
                ropt0[0]["ok"] is True and not any(e[0] == "click" for e in pg_opt0.log))
    ropt_exc = mod.run_steps(FakePage(raise_on={"click"}),
                             [{"action": "click_optional", "selector": "#x"}], _ctx())
    ok &= check("click_optional elemen ada tapi klik raise -> ok False", ropt_exc[0]["ok"] is False)
    # --- run_steps: select (penggerak) & wait_for_text (assertion yang sabar) ---
    pg_sel = FakePage()
    rsel = mod.run_steps(pg_sel, [{"action": "select", "selector": "select[name=id_country]",
                                   "value": "Indonesia"}], _ctx())
    ok &= check("select -> ok & memanggil select_option", rsel[0]["ok"] is True
                and ("select_option", "select[name=id_country]", "Indonesia", None) in pg_sel.log)
    ok &= check("select memilih lewat LABEL, bukan value (id numerik beda antar instalasi)",
                pg_sel.log[-1][2] == "Indonesia" and pg_sel.log[-1][3] is None)
    rsel_sub = mod.run_steps(FakePage(), [{"action": "select", "selector": "#s",
                                           "value": "{browser}"}],
                             {**_ctx(), "browser": "chromium"})
    ok &= check("select mensubstitusi placeholder di value", rsel_sub[0]["ok"] is True)
    rsel_err = mod.run_steps(FakePage(raise_on=["select"]),
                             [{"action": "select", "selector": "#s", "value": "X"}], _ctx())
    ok &= check("select gagal (opsi/elemen tak ada) -> ok False", rsel_err[0]["ok"] is False)

    # Halaman yang teksnya baru muncul: inilah yang membedakan wait_for_text dari expect_text.
    pg_late = LatePage(appear_after=2, text="Please send us your payment",
                       visible_text="")
    rwait = mod.run_steps(pg_late, [{"action": "wait_for_text",
                                     "text": "Please send us your payment",
                                     "timeout_ms": 5000}], _ctx())
    ok &= check("wait_for_text MENUNGGU teks yang menyusul -> ok",
                rwait[0]["ok"] is True and pg_late.checks > 2)
    pg_never = FakePage(visible_text="halaman lain")
    rwait_no = mod.run_steps(pg_never, [{"action": "wait_for_text", "text": "tak pernah ada",
                                         "timeout_ms": 50}], _ctx())
    ok &= check("wait_for_text teks tak pernah muncul -> ok False (bukan menggantung)",
                rwait_no[0]["ok"] is False)
    pg_hidden = FakePage(visible_text="", hidden_text="Please send us your payment")
    rwait_hid = mod.run_steps(pg_hidden, [{"action": "wait_for_text",
                                           "text": "Please send us your payment",
                                           "timeout_ms": 50}], _ctx())
    ok &= check("wait_for_text mengabaikan teks TERSEMBUNYI (template growl BO)",
                rwait_hid[0]["ok"] is False)
    rukn = mod.run_steps(FakePage(), [{"action": "teleport"}], _ctx())
    ok &= check("aksi tak dikenal -> ok False & tak konklusif (bukan silent pass)",
                rukn[0]["ok"] is False and rukn[0]["conclusive"] is False)
    ukn_f, ukn_inc = mod.assemble_findings("9.1", [{"browser": "chromium", "scenarios": [
        {"name": "typo", "source": "typo.json", "results": rukn}]}])
    ok &= check("aksi tak dikenal -> kanal inconclusive (tak memblok, tak hilang)",
                ukn_f == [] and len(ukn_inc) == 1 and ukn_inc[0]["action"] == "teleport")

    # --- run_steps: expect_no_console_error (baca console_sink sejak console_base) ---
    rce_clean = mod.run_steps(FakePage(), [{"action": "expect_no_console_error"}],
                              {**_ctx(), "console_sink": [], "console_base": 0})
    ok &= check("expect_no_console_error tanpa error -> ok", rce_clean[0]["ok"] is True)
    rce_err = mod.run_steps(FakePage(), [{"action": "expect_no_console_error"}],
                            {**_ctx(), "console_sink": [{"type": "error", "text": "Uncaught TypeError"}], "console_base": 0})
    ok &= check("expect_no_console_error dgn error JS -> gagal", rce_err[0]["ok"] is False)
    rce_off = mod.run_steps(FakePage(), [{"action": "expect_no_console_error"}],
                            {**_ctx(), "console_sink": [{"type": "error", "text": "lama"}], "console_base": 1})
    ok &= check("console_base offset: error sebelum base diabaikan", rce_off[0]["ok"] is True)

    # --- run_steps: screenshot + auto-snap (butuh screenshot_dir) ---
    with tempfile.TemporaryDirectory() as td:
        sctx = {**_ctx(), "engine": "chromium", "scenario": "s", "screenshot_dir": td, "_shots": []}
        mod.run_steps(FakePage(status=200), [{"action": "goto", "area": "fo", "path": "/"},
                                             {"action": "screenshot"}], sctx)
        ok &= check("screenshot: goto (auto-snap) + aksi screenshot -> 2 path di _shots", len(sctx["_shots"]) == 2)
        fctx = {**_ctx(), "engine": "chromium", "scenario": "s", "screenshot_dir": td, "_shots": []}
        mod.run_steps(FakePage(visible=False), [{"action": "expect_visible", "selector": "#x"}], fctx)
        ok &= check("auto-snap pada kegagalan assertion", len(fctx["_shots"]) == 1)
    nctx = {**_ctx(), "engine": "chromium", "scenario": "s"}
    mod.run_steps(FakePage(), [{"action": "screenshot"}], nctx)
    ok &= check("tanpa screenshot_dir -> tak ambil screenshot", nctx.get("_shots") is None)

    # --- _drive_page: setup+drive teruji dgn browser-tiruan; per-scenario console/screenshot ---
    dp_scn, dp_auth = mod._drive_page(_FakeBrowser(FakePage()), "chromium", [mod.universal_smoke()],
                                      {**_ctx(), "nav_timeout": 1000})
    ok &= check("_drive_page -> 1 skenario dgn hasil + field console_errors/screenshots",
                len(dp_scn) == 1 and "console_errors" in dp_scn[0] and "screenshots" in dp_scn[0])
    ok &= check("_drive_page -> bo_authed bool (login BO best-effort dijalankan utk smoke)",
                isinstance(dp_auth, bool))
    # gap honest-degrade yg ditutup: kegagalan SETELAH launch diangkat (drive_engine yg menangkap)
    raised = False
    try:
        mod._drive_page(_FakeBrowser(FakePage(), raise_on_context=True), "chromium",
                        [mod.universal_smoke()], {**_ctx(), "nav_timeout": 1000})
    except Exception:  # noqa: BLE001
        raised = True
    ok &= check("_drive_page mengangkat kegagalan setelah launch (ditangkap drive_engine -> degrade)", raised)

    # --- _bo_login: klik #submit_login (id stabil lintas 1.7/8/9; name tombol beda antar versi),
    #     networkidle dibatasi + fallback 'load', sukses = STRUKTURAL (passwd locator 0 + URL
    #     keluar AdminLogin), retry 1x utk cold-container 1.7/8 ---
    lctx = {**_ctx(), "admin_email": "a@b", "admin_password": "pw"}
    DASH = "http://bo/index.php?controller=AdminDashboard&token=x"
    pg_in = FakePage(loc_count=0, url_after_click=DASH)  # passwd hilang + redirect dashboard
    ok &= check("_bo_login sukses (passwd locator 0 + URL keluar AdminLogin) & klik #submit_login",
                mod._bo_login(pg_in, lctx) is True and ("click", "#submit_login") in pg_in.log)
    pg_form = FakePage(html='<form><input name="passwd"></form>', loc_count=1, url_after_click=DASH)
    ok &= check("_bo_login gagal bila field passwd masih ada (locator, bukan substring)",
                mod._bo_login(pg_form, lctx) is False)
    # REGRESI determinism-1 (anti false-auth): halaman error/interstitial TANPA field passwd
    # tapi URL masih AdminLogin -> False. Cek substring lama ('name="passwd"' not in html)
    # melaporkan sukses palsu di sini -> assertion BO memblok atas kegagalan infra.
    pg_500 = FakePage(html="<h1>500 Internal Server Error</h1>", loc_count=0)  # tanpa redirect
    ok &= check("_bo_login: halaman 500 tanpa field passwd + URL masih AdminLogin -> False (anti false-auth)",
                mod._bo_login(pg_500, lctx) is False)
    pg_ni = FakePage(raise_on={"networkidle"}, loc_count=0, url_after_click=DASH)
    ok &= check("_bo_login: networkidle timeout -> fallback 'load' (BO polling XHR), tetap sukses",
                mod._bo_login(pg_ni, lctx) is True and ("wait", "load") in pg_ni.log)

    # retry cold-container: attempt-1 POST tak redirect (URL tetap AdminLogin), attempt-2 sukses
    class _FlakyLogin(FakePage):
        def __init__(self):
            super().__init__(loc_count=0)
            self.clicks = 0

        def click(self, sel):
            super().click(sel)
            self.clicks += 1
            if self.clicks >= 2:
                self.url = DASH

    pg_flaky = _FlakyLogin()
    ok &= check("_bo_login retry: attempt-1 flaky (cold 1.7/8) -> attempt-2 sukses",
                mod._bo_login(pg_flaky, lctx) is True and pg_flaky.clicks == 2)

    # --- assemble_findings: konklusif gagal -> finding; tak konklusif -> inconclusive ---
    driven = [{"browser": "chromium", "scenarios": [
        {"name": "psm-universal-smoke", "source": "builtin", "results": [
            {"action": "expect_no_fatal", "ok": False, "conclusive": True, "message": "fatal FO", "location": "fo"},
            {"action": "expect_no_fatal", "ok": False, "conclusive": False, "message": "BO", "location": "bo"},
            {"action": "expect_visible", "ok": True, "conclusive": True, "message": "", "location": "body"},
        ]}]}]
    findings, inconclusive = mod.assemble_findings("8.1", driven)
    ok &= check("finding konklusif -> 1, severity error, versions [8.1]",
                len(findings) == 1 and findings[0]["severity"] == "error" and findings[0]["versions"] == ["8.1"])
    ok &= check("finding bawa browser & scenario", findings[0]["browser"] == "chromium")
    ok &= check("gagal tak-konklusif -> inconclusive (bukan finding)", len(inconclusive) == 1)

    # --- discover_scenarios: valid + invalid + tanpa folder ---
    with tempfile.TemporaryDirectory() as td:
        mdir = Path(td)
        found0, notes0 = mod.discover_scenarios(mdir)
        ok &= check("tanpa tests/e2e -> kosong", found0 == [] and notes0 == [])
        e2e = mdir / "tests" / "e2e"
        e2e.mkdir(parents=True)
        (e2e / "good.json").write_text(json.dumps(
            {"name": "cfg", "steps": [{"action": "goto", "area": "bo", "path": "/x"},
                                      {"action": "expect_visible", "selector": "#ok"}]}), encoding="utf-8")
        (e2e / "nosteps.json").write_text(json.dumps({"name": "x"}), encoding="utf-8")
        (e2e / "broken.json").write_text("{bukan json", encoding="utf-8")
        (e2e / "typo.json").write_text(json.dumps(
            {"name": "t", "steps": [{"action": "goto", "area": "fo", "path": "/"},
                                    {"action": "expect_visable", "selector": "#x"}]}), encoding="utf-8")
        (e2e / "zz-optional.json").write_text(json.dumps(
            {"name": "opt", "steps": [{"action": "goto", "area": "bo", "path": "/x"},
                                      {"action": "click_optional", "selector": "#token-ok"}]}), encoding="utf-8")
        found, notes = mod.discover_scenarios(mdir)
        ok &= check("spec valid ditemukan (2: cfg + spec ber-click_optional) dgn name",
                    len(found) == 2 and found[0]["name"] == "cfg" and found[1]["name"] == "opt")
        ok &= check("spec tanpa steps & JSON rusak & aksi typo dicatat (3 notes)",
                    len([n for n in notes if "expect_*" not in n]) == 3)
        ok &= check("note aksi tak dikenal menyebut aksinya",
                    any("expect_visable" in n for n in notes))
        # Spec tanpa satu pun expect_* dicatat SEBELUM container boot — tapi TETAP dijalankan,
        # sebab `goto` yang kena HTTP 500 masih temuan yang memblok. Catatannya lahir di
        # pemilik tunggal aturan spec, jadi pra-pass ps-plan-layers ikut memancarkannya.
        ok &= check("spec tanpa aksi expect_* dicatat (tak menegakkan apa pun)",
                    any("zz-optional.json" in n and "tak menegakkan apa pun" in n for n in notes))
        ok &= check("spec tanpa expect_* TETAP dijalankan (goto 500 tetap memblok)",
                    any(s["source"] == "zz-optional.json" for s in found))
        ok &= check("spec ber-expect_* TIDAK dicatat sebagai kosong (kontrol positif)",
                    not any("good.json" in n for n in notes))

    # --- count_authored_assertions: cakupan = assertion yang DINILAI, bukan file yang ADA ---
    def _sc(source, results):
        return {"browser": "chromium", "scenarios": [{"name": "s", "source": source,
                                                      "results": results}]}
    def _r(action, conclusive=True):
        return {"action": action, "ok": True, "conclusive": conclusive, "message": "", "location": ""}

    ok &= check("smoke builtin tak dihitung sbg cakupan authored",
                mod.count_authored_assertions([_sc("builtin", [_r("expect_visible")])]) == 0)
    ok &= check("spec authored cuma screenshot/goto/click -> 0 (dulu: dianggap 'punya uji')",
                mod.count_authored_assertions([_sc("trivial.json", [
                    _r("screenshot"), _r("goto"), _r("click"), _r("fill"),
                    _r("click_optional")])]) == 0)
    ok &= check("wait_for_text terhitung authored assertion (aksi penggerak tidak)",
                mod.count_authored_assertions([_sc("cfg.json", [
                    _r("wait_for_text"), _r("goto"), _r("select")])]) == 1)
    ok &= check("aksi expect_* authored dihitung",
                mod.count_authored_assertions([_sc("cfg.json", [
                    _r("expect_visible"), _r("expect_text"), _r("goto")])]) == 2)
    ok &= check("assertion TAK konklusif tak dihitung (jangan percaya sesi rusak)",
                mod.count_authored_assertions([_sc("cfg.json", [
                    _r("expect_visible", conclusive=False), _r("expect_text")])]) == 1)
    # Kontrak: ASSERT_ACTIONS boleh memuat aksi non-expect_ (wait_for_text menegakkan
    # sesuatu juga), TAPI tiap anggotanya WAJIB ada di SUPPORTED_ACTIONS. Itu yang menutup
    # kelas "daftar kedua yang mendrift": aksi yang dibuang dari SUPPORTED_ACTIONS tak bisa
    # tertinggal hidup di sini, dan entri eksplisit yang salah ketik langsung merah.
    ok &= check("tiap ASSERT_ACTION ada di SUPPORTED_ACTIONS (nol yatim)",
                set(mod.ASSERT_ACTIONS) <= set(mod.SUPPORTED_ACTIONS))
    ok &= check("semua expect_* ikut terhitung otomatis (derivasi tak dilewati)",
                {a for a in mod.SUPPORTED_ACTIONS if a.startswith("expect_")}
                <= set(mod.ASSERT_ACTIONS))
    ok &= check("wait_for_text dihitung sbg assertion (gagal bila teks tak pernah muncul)",
                "wait_for_text" in mod.ASSERT_ACTIONS)
    ok &= check("aksi penggerak TIDAK terhitung assertion",
                not ({"goto", "click", "fill", "select", "screenshot", "click_optional"}
                     & set(mod.ASSERT_ACTIONS)))

    # --- playwright_available -> bool (env apa pun) ---
    ok &= check("playwright_available -> bool", isinstance(mod.playwright_available(), bool))

    # --- run_one_version: gerbang browser DULU — daftar browser kosong -> skipped_browser tanpa Docker ---
    r0 = mod.run_one_version(Path("/tmp"), "testmod", "9.1", "9.1.4-nginx", [], [mod.universal_smoke()],
                             orchestrator="auto", db_image="mariadb:lts", ps_domain="localhost:8000",
                             admin_path="admin-dev", admin_email="a", admin_password="b",
                             startup_timeout=1, op_timeout=1, nav_timeout=1000, allow_pull=False)
    ok &= check("browsers kosong -> skipped_browser, orchestrator None (tak sentuh Docker)",
                r0.get("skipped_browser") is True and r0["orchestrator"] is None and r0["pass"] is False)

    # Sentinel infra Lapis 4: INSTALL_SH punya gerbang console sendiri (dulu hanya
    # INNER_SH flashlight yang diperbaiki -> sentinel di sini dibaca tapi tak diemit).
    ok &= check("INSTALL_SH mengemit PSM_NO_CONSOLE (produsen == konsumen, seperti INNER_SH)",
                "echo PSM_NO_CONSOLE" in mod.INSTALL_SH and "[ ! -f bin/console ]" in mod.INSTALL_SH)

    # --- run_one_version: orchestrator=compose diminta tapi compose absen -> error, tak crash ---
    orig_present, orig_compose = mod.fl.image_present, mod.fl.compose_available
    try:
        mod.fl.compose_available = lambda: False
        r = mod.run_one_version(Path("/tmp"), "testmod", "9.1", "9.1.4-nginx", ["chromium"], [mod.universal_smoke()],
                                orchestrator="compose", db_image="mariadb:lts", ps_domain="localhost:8000",
                                admin_path="admin-dev", admin_email="a", admin_password="b",
                                startup_timeout=1, op_timeout=1, nav_timeout=1000, allow_pull=False)
        ok &= check("compose diminta tapi absen -> error & pass False",
                    r["pass"] is False and any("docker compose" in e for e in r["errors"]))

        # image absen + pull tak diizinkan -> skipped_image (degrade jujur, mirror flashlight)
        mod.fl.image_present = lambda ref: False
        mod.fl.compose_available = lambda: True
        r2 = mod.run_one_version(Path("/tmp"), "testmod", "9.1", "9.1.4-nginx", ["chromium"], [mod.universal_smoke()],
                                 orchestrator="auto", db_image="mariadb:lts", ps_domain="localhost:8000",
                                 admin_path="admin-dev", admin_email="a", admin_password="b",
                                 startup_timeout=1, op_timeout=1, nav_timeout=1000, allow_pull=False)
        ok &= check("image absen + allow_pull False -> skipped_image", r2.get("skipped_image") is True)
        ok &= check("skipped_image -> orchestrator compose, pass False, install None",
                    r2["orchestrator"] == "compose" and r2["pass"] is False and r2["install"] is None)
    finally:
        mod.fl.image_present, mod.fl.compose_available = orig_present, orig_compose

    # --- REGRESI false-pass: drive loop me-rute launch-fail per-browser ke browser_notes,
    #     BUKAN errors; temuan konklusif dari engine yang jalan tetap ada (fix determinism-1) ---
    saved = {n: getattr(mod, n, None) for n in ("drive_engine", "install_module", "wait_http")}
    saved_fl = {n: getattr(mod.fl, n) for n in ("compose_available", "image_present",
                "_bring_up_compose", "wait_healthy", "_teardown", "_logs")}
    try:
        mod.fl.compose_available = lambda: True
        mod.fl.image_present = lambda ref: True
        mod.fl._bring_up_compose = lambda *a, **k: ({"ps_container": "x", "mode": "compose"}, None)
        mod.fl.wait_healthy = lambda c, t: (True, "healthy")
        mod.fl._teardown = lambda s: None
        mod.fl._logs = lambda c: ""
        mod.install_module = lambda s, m, t: ({"ok": True, "no_console": False}, None)
        warm_urls = []
        mod.wait_http = lambda u, t: (warm_urls.append(u) or True, 200, True)

        captured = {}

        def fake_drive(engine, scenarios, ctx, headed=False):
            captured["headed"] = headed
            captured["sdir"] = ctx.get("screenshot_dir")
            if engine == "firefox":
                return {"browser": "firefox", "scenarios": [], "launch_error": "boom", "bo_authed": False}
            return {"browser": "chromium", "bo_authed": True, "launch_error": None, "scenarios": [
                {"name": "psm-universal-smoke", "source": "builtin",
                 "results": [{"action": "expect_no_fatal", "ok": False, "conclusive": True,
                              "message": "fatal FO", "location": "fo"}],
                 "console_errors": [{"type": "error", "text": "Uncaught X"}],
                 "screenshots": ["/tmp/shot/chromium-smoke-00-goto.png"]}]}
        mod.drive_engine = fake_drive

        r = mod.run_one_version(Path("/tmp"), "m", "9.1", "9.1.4-nginx", ["chromium", "firefox"],
                                [mod.universal_smoke()], requested_browsers=["chromium", "firefox"],
                                orchestrator="auto", db_image="mariadb:lts", ps_domain="localhost:8000",
                                admin_path="admin-dev", admin_email="a", admin_password="b",
                                startup_timeout=1, op_timeout=1, nav_timeout=1000, allow_pull=False)
        ok &= check("firefox launch-fail -> browser_notes (BUKAN errors)",
                    r["errors"] == [] and any("firefox" in n for n in r["browser_notes"]))
        ok &= check("chromium yang jalan tetap menghasilkan temuan konklusif memblok (fix false-pass)",
                    r["browsers"] == ["chromium"] and len(r["findings"]) == 1 and r["pass"] is False)
        ok &= check("warm-up BO: wait_http menyentuh AdminLogin sebelum drive (cold-container 1.7/8)",
                    any("controller=AdminLogin" in u for u in warm_urls))
        # rollup artefak visual: console_errors dihitung + screenshot terkumpul
        ok &= check("rollup: console_errors=1 & screenshot terkumpul",
                    r["console_errors"] == 1 and r["screenshots"] == ["/tmp/shot/chromium-smoke-00-goto.png"])
        # Error console TAK boleh masuk browser_notes. Field itu memikul celah CAKUPAN yang
        # menjatuhkan `ready`; error console adalah observasi yang tak memblok. Menyatukannya
        # bikin `ready` tak deterministik — direproduksi di container nyata: module & spec
        # identik, ready=true saat console_errors=0 lalu ready=false saat =3. Assert lama
        # ("advisory di browser_notes") mensertifikasi cacat itu.
        ok &= check("console error TIDAK dituang ke browser_notes (kanal cakupan bersih)",
                    not any("console" in n.lower() for n in r["browser_notes"]))
        ok &= check("default headed False diteruskan ke drive_engine", captured["headed"] is False)

        # WIRING host-preservasi: fungsi host_from_domain teruji sendiri, tapi run-path harus
        # BENAR-BENAR memakainya. Mutasi run-path ke "localhost:{port}" lolos senyap tanpa ini
        # (kelas "jalur tanpa cakupan"). Tangkap ps_domain yang diteruskan ke bring-up (host
        # dari config, port dinamis) — dan res["ps_domain"] yang dilihat base_urls Playwright.
        seen_domain = {}
        mod.fl._bring_up_compose = lambda md, fv, ir, db, dom, ot, pub=None, **_k: (
            seen_domain.update(dom=dom) or ({"ps_container": "x", "mode": "compose"}, None))
        rh = mod.run_one_version(Path("/tmp"), "m", "9.1", "9.1.4-nginx", ["chromium"],
                                 [mod.universal_smoke()], requested_browsers=["chromium"],
                                 orchestrator="auto", db_image="mariadb:lts",
                                 ps_domain="shop.mycorp.local:8000", admin_path="admin-dev",
                                 admin_email="a", admin_password="b", startup_timeout=1,
                                 op_timeout=1, nav_timeout=1000, allow_pull=False)
        ok &= check("host config dipertahankan di PS_DOMAIN yang di-boot (bukan dipaksa localhost)",
                    seen_domain.get("dom", "").startswith("shop.mycorp.local:"))
        ok &= check("host config sampai ke res['ps_domain'] (yang jadi base URL Playwright)",
                    rh["ps_domain"].startswith("shop.mycorp.local:"))
        ok &= check("port tetap mengambang (bukan port config 8000 yang dipublish mentah)",
                    rh["ps_domain"] != "shop.mycorp.local:8000" or ":" in rh["ps_domain"])
        # WIRING produsen->agregat. Mutasi "res['authored_assertions'] -> res['_unused']" SEMULA
        # LOLOS SENYAP: count_authored_assertions punya test, e2e_layer punya test, tapi tak ada
        # yang menguji run_one_version benar-benar MENGEMIT angkanya — persis mode "jalur tanpa
        # coverage" yang bikin test hijau di atas kode salah.
        ok &= check("run_one_version mengemit authored_assertions (smoke saja -> 0)",
                    r["authored_assertions"] == 0)

        def fake_drive_authored(engine, scenarios, ctx, headed=False):
            return {"browser": engine, "bo_authed": True, "launch_error": None, "scenarios": [
                {"name": "psm-universal-smoke", "source": "builtin",
                 "results": [{"action": "expect_no_fatal", "ok": True, "conclusive": True,
                              "message": "", "location": ""}]},
                {"name": "cfg", "source": "cfg.json",
                 "results": [{"action": "expect_visible", "ok": True, "conclusive": True,
                              "message": "", "location": ""},
                             {"action": "screenshot", "ok": True, "conclusive": True,
                              "message": "", "location": ""}]}]}
        mod.drive_engine = fake_drive_authored
        r_auth = mod.run_one_version(Path("/tmp"), "m", "9.1", "9.1.4-nginx", ["chromium"],
                                     [mod.universal_smoke()], requested_browsers=["chromium"],
                                     orchestrator="auto", db_image="mariadb:lts",
                                     ps_domain="localhost:8000", admin_path="admin-dev",
                                     admin_email="a", admin_password="b", startup_timeout=1,
                                     op_timeout=1, nav_timeout=1000, allow_pull=False)
        ok &= check("run_one_version mengemit authored_assertions (1 expect_* authored, "
                    "screenshot & smoke tak dihitung)",
                    r_auth["authored_assertions"] == 1)
        mod.drive_engine = fake_drive

        # probe-miss: firefox tak lolos probe di main -> browser_notes coverage, chromium tetap jalan
        r2 = mod.run_one_version(Path("/tmp"), "m", "9.1", "9.1.4-nginx", ["chromium"],
                                 [mod.universal_smoke()], requested_browsers=["chromium", "firefox"],
                                 orchestrator="auto", db_image="mariadb:lts", ps_domain="localhost:8000",
                                 admin_path="admin-dev", admin_email="a", admin_password="b",
                                 startup_timeout=1, op_timeout=1, nav_timeout=1000, allow_pull=False)
        ok &= check("engine probe-miss (firefox) -> browser_notes coverage, tak di errors",
                    r2["errors"] == [] and any("firefox" in n for n in r2["browser_notes"]))

        # --headed & --screenshot-dir diteruskan; per-versi subdir screenshot dibuat
        with tempfile.TemporaryDirectory() as td:
            r3 = mod.run_one_version(Path("/tmp"), "m", "9.1", "9.1.4-nginx", ["chromium"],
                                     [mod.universal_smoke()], requested_browsers=["chromium"],
                                     orchestrator="auto", db_image="mariadb:lts", ps_domain="localhost:8000",
                                     admin_path="admin-dev", admin_email="a", admin_password="b",
                                     startup_timeout=1, op_timeout=1, nav_timeout=1000, allow_pull=False,
                                     headed=True, screenshot_dir=td)
            ok &= check("headed=True diteruskan ke drive_engine", captured["headed"] is True)
            ok &= check("screenshot_dir -> per-versi subdir '9.1' diteruskan ke ctx",
                        bool(captured["sdir"]) and captured["sdir"].endswith("9.1") and Path(captured["sdir"]).is_dir())

        # det-1/enh-1 (ronde-6, CRITICAL): FO 5xx yang BERTAHAN = server menjawab (port jelas
        # terpublish) → module merusak toko, BUKAN infra. run_one_version harus LANJUT drive
        # browser supaya expect_no_fatal memvonis, bukan menyapu ke errors sbg "port gagal".
        # Jalur ini dulu NOL coverage: mutasi copot gerbang reachability = suite tetap hijau.
        mod.wait_http = lambda u, t: (False, "HTTP 500", True)
        r5 = mod.run_one_version(Path("/tmp"), "m", "9.1", "9.1.4-nginx", ["chromium"],
                                 [mod.universal_smoke()], requested_browsers=["chromium"],
                                 orchestrator="auto", db_image="mariadb:lts", ps_domain="localhost:8000",
                                 admin_path="admin-dev", admin_email="a", admin_password="b",
                                 startup_timeout=1, op_timeout=1, nav_timeout=1000, allow_pull=False)
        ok &= check("FO 5xx bertahan (responded) -> browser di-drive, temuan konklusif memblok (BUKAN infra)",
                    not any("port publish" in e for e in r5["errors"])
                    and len(r5["findings"]) == 1 and r5["pass"] is False)

        # Sebaliknya: TAK ada respons TCP sama sekali -> infra jujur (port/boot gagal), browser
        # TAK di-drive. Ini kondisi SEBELUM prasyarat vonis lengkap → kanal infra memang sah.
        drove = []
        _fd = mod.drive_engine
        mod.drive_engine = lambda *a, **k: (drove.append(1) or _fd(*a, **k))
        mod.wait_http = lambda u, t: (False, "connection refused", False)
        rnr = mod.run_one_version(Path("/tmp"), "m", "9.1", "9.1.4-nginx", ["chromium"],
                                  [mod.universal_smoke()], requested_browsers=["chromium"],
                                  orchestrator="auto", db_image="mariadb:lts", ps_domain="localhost:8000",
                                  admin_path="admin-dev", admin_email="a", admin_password="b",
                                  startup_timeout=1, op_timeout=1, nav_timeout=1000, allow_pull=False)
        ok &= check("FO tanpa respons TCP -> errors 'port publish/boot gagal' & browser TAK di-drive",
                    any("port publish" in e for e in rnr["errors"]) and drove == [])
        mod.drive_engine = _fd
    finally:
        for n, v in saved.items():
            setattr(mod, n, v)
        for n, v in saved_fl.items():
            setattr(mod.fl, n, v)

    # det-1/enh-1: wait_http langsung — membedakan "server menjawab 5xx" (responded True →
    # module rusak, browser yang memvonis) dari "tak ada respons TCP" (responded False → infra).
    import urllib.error as _uerr
    _saved_urlopen = mod.urllib.request.urlopen
    try:
        def _raise_500(url, timeout=10):
            raise _uerr.HTTPError(url, 500, "Server Error", {}, None)
        mod.urllib.request.urlopen = _raise_500
        w500 = mod.wait_http("http://x/", 0.05, poll=0.01)
        ok &= check("wait_http 5xx bertahan -> (False, ~'HTTP 500', responded=True)",
                    w500[0] is False and w500[2] is True and "500" in str(w500[1]))

        def _raise_conn(url, timeout=10):
            raise _uerr.URLError("connection refused")
        mod.urllib.request.urlopen = _raise_conn
        wcr = mod.wait_http("http://x/", 0.05, poll=0.01)
        ok &= check("wait_http tanpa respons TCP -> responded=False (infra sejati)",
                    wcr[0] is False and wcr[2] is False)
    finally:
        mod.urllib.request.urlopen = _saved_urlopen

    # --- det-4 residual (keputusan user 2026-07-17): menghapus spec yang MERAH dulu
    # menaikkan `ready` — catatan "spec dilewati" mati bersama filenya, jadi vonis membaik
    # justru karena coverage berkurang. Yang masih mengingat spec itu ada: git.
    def _git(cwd, *args):
        return subprocess.run(["git", "-C", str(cwd), *args], capture_output=True, text=True)

    with tempfile.TemporaryDirectory() as td:
        repo = Path(td)
        if _git(repo, "init", "-q").returncode != 0:
            ok &= check("git tersedia untuk menguji deteksi spec terhapus", False)
        else:
            _git(repo, "config", "user.email", "t@t")
            _git(repo, "config", "user.name", "t")
            mdir = repo / "mymod"
            (mdir / "tests" / "e2e").mkdir(parents=True)
            (mdir / "mymod.php").write_text("<?php class MyMod extends Module {}")
            spec_ok = mdir / "tests" / "e2e" / "checkout.json"
            spec_bad = mdir / "tests" / "e2e" / "broken.json"
            spec_ok.write_text(json.dumps(
                {"name": "checkout", "steps": [{"action": "goto", "area": "fo", "path": "/"}]}))
            spec_bad.write_text("{bukan json")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-qm", "init")

            ok &= check("spec lengkap -> tak ada catatan penghapusan", mod.deleted_specs(mdir) == [])
            _, notes_present = mod.discover_scenarios(mdir)
            ok &= check("spec rusak yang ADA -> dicatat sbg dilewati (ready jatuh)",
                        any("gagal parse" in n for n in notes_present))

            spec_bad.unlink()  # hapus spec yang merah, belum di-commit
            ok &= check("spec dihapus (belum commit) -> git masih mengingatnya",
                        mod.deleted_specs(mdir) == ["broken.json"])
            _, notes_gone = mod.discover_scenarios(mdir)
            ok &= check("penghapusan sampai ke scenario_notes -> `ready` tetap jatuh, "
                        "bukan membaik karena uji dibuang",
                        any("dihapus" in n and "broken.json" in n for n in notes_gone))

            _git(repo, "rm", "-q", "--cached", "mymod/tests/e2e/broken.json")
            ok &= check("penghapusan yang di-stage tetap terdeteksi (belum jadi keputusan terekam)",
                        mod.deleted_specs(mdir) == ["broken.json"])

            _git(repo, "commit", "-qam", "hapus spec broken (sadar)")
            ok &= check("penghapusan yang DI-COMMIT -> berhenti dicatat (keputusan terekam, "
                        "ditinjau lewat diff)", mod.deleted_specs(mdir) == [])

            # JSON lain yang dihapus di luar tests/e2e BUKAN spec — pathspec-nya harus
            # menyaring, kalau tidak setiap composer.json terhapus jadi "spec dihapus" palsu.
            other = mdir / "composer.json"
            other.write_text("{}")
            _git(repo, "add", "-A")
            _git(repo, "commit", "-qm", "tambah composer")
            other.unlink()
            ok &= check("JSON terhapus di luar tests/e2e -> BUKAN spec (pathspec menyaring)",
                        mod.deleted_specs(mdir) == [])

            # Spec sehat yang dihapus juga terdeteksi — bukan cuma yang rusak.
            spec_ok.unlink()
            ok &= check("spec sehat yang dihapus juga terdeteksi", mod.deleted_specs(mdir) == ["checkout.json"])
            # SELURUH folder tests/e2e lenyap: cek git harus mendahului early-return
            # `not e2e_dir.is_dir()`, kalau tidak menghapus seluruh folder uji = senyap total.
            (mdir / "tests" / "e2e").rmdir()
            ok &= check("folder tests/e2e lenyap seluruhnya -> git ditanya sebelum early-return",
                        not (mdir / "tests" / "e2e").is_dir()
                        and any("checkout.json" in n and "dihapus" in n
                                for n in mod.discover_scenarios(mdir)[1]))

    with tempfile.TemporaryDirectory() as td:
        plain = Path(td) / "mymod"
        (plain / "tests" / "e2e").mkdir(parents=True)
        ok &= check("bukan repo git -> [] (tak bisa tahu; jangan menebak)",
                    mod.deleted_specs(plain) == [])

    # --- architecture-1 (analyze 2026-07-17-1024): nama screenshot deterministik + tanpa
    # cleanup = folder datar yang menumpuk PNG run-run lama, termasuk versi yang tak lagi
    # dalam cakupan. Verifikasi visual Lapis 4 memvonis DARI gambar itu, jadi PNG basi bisa
    # jadi `error` yang memblok atas bukti dari run yang sudah tak ada.
    ok &= check("screenshot_dir None -> tetap None (fitur tetap opt-in)",
                mod.run_shot_dir(None) is None)
    d1 = mod.run_shot_dir("/tmp/shots")
    ok &= check("screenshot ditulis ke subfolder per-run di bawah folder yang diminta",
                d1.startswith("/tmp/shots/run-") and re.fullmatch(r"run-\d{8}-\d{6}", Path(d1).name) is not None)
    # Dua run yang cakupannya beda tak boleh saling menimpa/menumpuk artefak.
    with mock.patch.object(mod, "datetime") as fake_dt:
        fake_dt.now.return_value = datetime(2026, 7, 17, 10, 0, 0)
        a = mod.run_shot_dir("/tmp/shots")
        fake_dt.now.return_value = datetime(2026, 7, 24, 11, 30, 0)
        b = mod.run_shot_dir("/tmp/shots")
    ok &= check("run berbeda -> folder berbeda (PNG minggu lalu tak bisa dibaca sbg bukti run ini)",
                a != b and a.endswith("run-20260717-100000") and b.endswith("run-20260724-113000"))

    # Idempoten: orkestrator multi-versi (ps-run-layer.py) menstempel SEKALI lalu memberi
    # folder yang sama ke tiap anak. Tanpa ini tiap anak menstempel ulang, bukti visual N
    # versi pecah jadi N folder, dan hanya satu yang sampai ke vonis.
    already = "/tmp/shots/run-20260724-113000"
    ok &= check("folder yang SUDAH berstempel dikembalikan apa adanya (tak distempel ulang)",
                mod.run_shot_dir(already) == already)
    ok &= check("nama yang cuma mirip stempel tetap distempel (bukan pencocokan longgar)",
                mod.run_shot_dir("/tmp/run-lama").startswith("/tmp/run-lama/run-"))

    ok &= test_cells_and_timing()
    ok &= test_main_engines_and_exit()
    ok &= test_sequential_browsers()
    ok &= test_child_flags()
    ok &= test_slot_labels()

    print("\n" + ("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
