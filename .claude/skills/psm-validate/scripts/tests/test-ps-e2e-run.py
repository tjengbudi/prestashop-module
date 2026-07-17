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

    def on(self, event, handler):
        self.log.append(("on", event))
        self._handlers[event] = handler

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


def main():
    ok = True

    # --- parse_browsers ---
    ok &= check("browsers 'chromium,firefox'", mod.parse_browsers("chromium,firefox") == ["chromium", "firefox"])
    ok &= check("browsers kosong -> default", mod.parse_browsers("") == ["chromium", "firefox"])
    ok &= check("browsers case-insensitif + dedup + filter",
                mod.parse_browsers("Chromium, FIREFOX, safari, chromium") == ["chromium", "firefox"])
    ok &= check("browsers semua invalid -> default", mod.parse_browsers("safari,ie") == ["chromium", "firefox"])

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
    ok &= check("BO expect_no_fatal TAK konklusif tanpa login", fo_nofatal[-1]["conclusive"] is False)
    # dengan login BO -> BO jadi konklusif
    pg_auth = FakePage()
    res_auth = mod.run_steps(pg_auth, sm["steps"], _wired(pg_auth, bo_authed=True))
    ok &= check("BO konklusif bila bo_authed True", _by_action(res_auth, "expect_no_fatal")[-1]["conclusive"] is True)

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
            {"name": "cfg", "steps": [{"action": "goto", "area": "bo", "path": "/x"}]}), encoding="utf-8")
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
        mod.wait_http = lambda u, t: (warm_urls.append(u) or True, 200)

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
