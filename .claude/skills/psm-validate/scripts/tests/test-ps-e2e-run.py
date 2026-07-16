#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Unit test untuk ps-e2e-run.py — fungsi murni, eksekusi langkah (page tiruan),
perakitan temuan, & degrade orkestrasi — semua tanpa Playwright/Docker nyata.

Playwright & Docker di-monkeypatch / tak dipanggil; logika langkah diuji dengan
page-tiruan (duck-typed). Jalankan: uv run scripts/tests/test-ps-e2e-run.py
"""
import importlib.util
import json
import sys
import tempfile
from pathlib import Path

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
    def __init__(self, visible):
        self.first = _LocFirst(visible)


class FakePage:
    def __init__(self, *, status=200, html="<html><body>halaman ok</body></html>",
                 visible=True, raise_on=None):
        self._status = status
        self._html = html
        self._visible = visible
        self._raise_on = set(raise_on or ())
        self.log = []

    def set_default_timeout(self, t):
        pass

    def wait_for_load_state(self, *a, **k):
        pass

    def goto(self, url):
        self.log.append(("goto", url))
        if "goto" in self._raise_on:
            raise RuntimeError("nav gagal")
        return _Resp(self._status)

    def content(self):
        return self._html

    def locator(self, sel):
        if "visible" in self._raise_on:
            raise RuntimeError("locator gagal")
        return _Loc(self._visible)

    def click(self, sel):
        self.log.append(("click", sel))
        if "click" in self._raise_on:
            raise RuntimeError("click gagal")

    def fill(self, sel, val):
        self.log.append(("fill", sel, val))
        if "fill" in self._raise_on:
            raise RuntimeError("fill gagal")

    def on(self, event, handler):
        self.log.append(("on", event))

    def screenshot(self, path=None, full_page=False):
        self.log.append(("screenshot", path))
        if "screenshot" in self._raise_on:
            raise RuntimeError("screenshot gagal")


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


def _by_action(results, action):
    return [r for r in results if r["action"] == action]


def main():
    ok = True

    # --- parse_browsers ---
    ok &= check("browsers 'chromium,firefox'", mod.parse_browsers("chromium,firefox") == ["chromium", "firefox"])
    ok &= check("browsers kosong -> default", mod.parse_browsers("") == ["chromium", "firefox"])
    ok &= check("browsers case-insensitif + dedup + filter",
                mod.parse_browsers("Chromium, FIREFOX, safari, chromium") == ["chromium", "firefox"])
    ok &= check("browsers semua invalid -> default", mod.parse_browsers("safari,ie") == ["chromium", "firefox"])

    # --- host_port_from_domain / publish_spec ---
    ok &= check("port 'localhost:8000' -> 8000", mod.host_port_from_domain("localhost:8000") == 8000)
    ok &= check("port tanpa ':' -> default 8000", mod.host_port_from_domain("localhost") == 8000)
    ok &= check("port host lain -> 9999", mod.host_port_from_domain("example.com:9999") == 9999)
    ok &= check("publish_spec -> '8000:80'", mod.publish_spec("localhost:8000") == "8000:80")

    # --- base_urls ---
    fo, bo = mod.base_urls("localhost:8000", "admin-dev")
    ok &= check("base fo", fo == "http://localhost:8000")
    ok &= check("base bo (folder admin)", bo == "http://localhost:8000/admin-dev")
    _, bo2 = mod.base_urls("localhost:8000", "/admin-dev/")
    ok &= check("admin_path slash dinormalkan", bo2 == "http://localhost:8000/admin-dev")

    # --- substitute ---
    s = mod.substitute("{fo}/a {bo}/b mod={mod}", _ctx())
    ok &= check("substitute {fo}/{bo}/{mod}", s == "http://fo/a http://bo/b mod=m")

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
    res = mod.run_steps(FakePage(), sm["steps"], _ctx(bo_authed=False))
    ok &= check("smoke bersih -> semua langkah ok", all(r["ok"] for r in res))
    fo_nofatal = _by_action(res, "expect_no_fatal")
    ok &= check("FO expect_no_fatal konklusif", fo_nofatal[0]["conclusive"] is True)
    ok &= check("BO expect_no_fatal TAK konklusif tanpa login", fo_nofatal[-1]["conclusive"] is False)
    # dengan login BO -> BO jadi konklusif
    res_auth = mod.run_steps(FakePage(), sm["steps"], _ctx(bo_authed=True))
    ok &= check("BO konklusif bila bo_authed True", _by_action(res_auth, "expect_no_fatal")[-1]["conclusive"] is True)

    # --- run_steps: fatal terdeteksi (status 500 & tanda fatal) ---
    r500 = mod.run_steps(FakePage(status=500), [{"action": "goto", "area": "fo", "path": "/"},
                                                {"action": "expect_no_fatal"}], _ctx())
    ok &= check("status 500 -> goto ok False & expect_no_fatal gagal",
                _by_action(r500, "goto")[0]["ok"] is False and _by_action(r500, "expect_no_fatal")[0]["ok"] is False)
    rfatal = mod.run_steps(FakePage(html="<b>Fatal error</b>: boom"),
                           [{"action": "goto", "area": "fo", "path": "/"}, {"action": "expect_no_fatal"}], _ctx())
    ok &= check("tanda 'Fatal error' -> expect_no_fatal gagal (konklusif)",
                _by_action(rfatal, "expect_no_fatal")[0] == _by_action(rfatal, "expect_no_fatal")[0] and
                _by_action(rfatal, "expect_no_fatal")[0]["ok"] is False)

    # --- run_steps: expect_visible / expect_text ---
    rvis = mod.run_steps(FakePage(visible=False), [{"action": "expect_visible", "selector": "#x"}], _ctx())
    ok &= check("expect_visible False -> gagal", rvis[0]["ok"] is False)
    rtext = mod.run_steps(FakePage(html="Update successful"),
                          [{"action": "expect_text", "text": "successful"},
                           {"action": "expect_text", "text": "tak-ada"}], _ctx())
    ok &= check("expect_text ada -> ok, tak ada -> gagal",
                rtext[0]["ok"] is True and rtext[1]["ok"] is False)

    # --- run_steps: click/fill sukses & exception -> gagal ---
    rcf = mod.run_steps(FakePage(), [{"action": "fill", "selector": "#a", "value": "1"},
                                     {"action": "click", "selector": "#b"}], _ctx())
    ok &= check("fill+click sukses -> ok", all(r["ok"] for r in rcf))
    rexc = mod.run_steps(FakePage(raise_on={"goto"}), [{"action": "goto", "area": "fo", "path": "/"}], _ctx())
    ok &= check("goto exception -> ok False (assertion gagal)", rexc[0]["ok"] is False)
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
            {"name": "cfg", "steps": [{"action": "goto", "area": "bo", "path": "/x"}]}), encoding="utf-8")
        (e2e / "nosteps.json").write_text(json.dumps({"name": "x"}), encoding="utf-8")
        (e2e / "broken.json").write_text("{bukan json", encoding="utf-8")
        (e2e / "typo.json").write_text(json.dumps(
            {"name": "t", "steps": [{"action": "goto", "area": "fo", "path": "/"},
                                    {"action": "expect_visable", "selector": "#x"}]}), encoding="utf-8")
        found, notes = mod.discover_scenarios(mdir)
        ok &= check("spec valid ditemukan (1) dgn name", len(found) == 1 and found[0]["name"] == "cfg")
        ok &= check("spec tanpa steps & JSON rusak & aksi typo dicatat (3 notes)", len(notes) == 3)
        ok &= check("note aksi tak dikenal menyebut aksinya",
                    any("expect_visable" in n for n in notes))

    # --- playwright_available -> bool (env apa pun) ---
    ok &= check("playwright_available -> bool", isinstance(mod.playwright_available(), bool))

    # --- run_one_version: gerbang browser DULU — daftar browser kosong -> skipped_browser tanpa Docker ---
    r0 = mod.run_one_version(Path("/tmp"), "testmod", "9.1", "9.1.4-nginx", [], [mod.universal_smoke()],
                             orchestrator="auto", db_image="mariadb:lts", ps_domain="localhost:8000",
                             admin_path="admin-dev", admin_email="a", admin_password="b",
                             startup_timeout=1, op_timeout=1, nav_timeout=1000, allow_pull=False)
    ok &= check("browsers kosong -> skipped_browser, orchestrator None (tak sentuh Docker)",
                r0.get("skipped_browser") is True and r0["orchestrator"] is None and r0["pass"] is False)

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
        mod.wait_http = lambda u, t: (True, 200)

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
        # rollup artefak visual: console_errors dihitung + screenshot terkumpul + advisory di browser_notes
        ok &= check("rollup: console_errors=1 & screenshot terkumpul",
                    r["console_errors"] == 1 and r["screenshots"] == ["/tmp/shot/chromium-smoke-00-goto.png"])
        ok &= check("console error disurface advisory di browser_notes (tak memblok)",
                    any("console/JS" in n for n in r["browser_notes"]))
        ok &= check("default headed False diteruskan ke drive_engine", captured["headed"] is False)

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
    finally:
        for n, v in saved.items():
            setattr(mod, n, v)
        for n, v in saved_fl.items():
            setattr(mod.fl, n, v)

    print("\n" + ("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
