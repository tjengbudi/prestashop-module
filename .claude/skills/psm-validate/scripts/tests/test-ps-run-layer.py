#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Unit test untuk ps-run-layer.py — orkestrator lapis mahal multi-versi.

Fokus kontrak: (1) hanya lapis yang memang per-versi diterima, static/adversarial ditolak
dengan sebabnya; (2) flag milik skrip ini tak boleh datang dari passthrough — TERMASUK bentuk
menempel `-o/path` dan singkatan awalan, yang pernah lolos lalu MENIMPA file lapis lain;
(3) nama file lapis DITURUNKAN dari (folder laporan, module, lapis), tak bisa diketik;
(4) folder screenshot distempel SEKALI dan semua anak menerima yang sama; (5) versi tanpa
bukti per-versi DIHILANGKAN dan disebut, tak pernah dikarang jadi vonis; (6) exit code
mengikuti kontrak keluarga — lapis yang memang tak tersedia = exit 0 seperti run serial,
bukan vonis gagal; (7) kegagalan pasca-spawn MEMPERTAHANKAN bukti per-versi untuk diagnosis.

Jalur CLI diuji penuh dengan ANAK PALSU (injeksi `_spawn`) — bukan cuma fungsi murninya,
karena jalur CLI tanpa cakupan sudah tiga kali meloloskan kode yang salah di skill ini.
Jalankan: uv run scripts/tests/test-ps-run-layer.py
"""
import contextlib
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent.parent
MOD_PATH = SCRIPTS / "ps-run-layer.py"
spec = importlib.util.spec_from_file_location("ps_run_layer", MOD_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}: {name}")
    return cond


def _raises(fn, *a):
    try:
        fn(*a)
        return False
    except ValueError:
        return True


def _out_of(cmd):
    return cmd[cmd.index("-o") + 1]


def _ver_of(cmd):
    return cmd[cmd.index("--versions") + 1]


class FakeChildren:
    """Anak palsu: menulis payload lapis ke -o dan mengembalikan exit code yang diminta.

    Merekam tiap perintah supaya test bisa memeriksa apa yang SEBENARNYA diterima anak —
    itu satu-satunya cara membuktikan folder screenshot dibagi, bukan cuma dihitung benar.
    """

    def __init__(self, payload_for=None, code_for=None):
        self.cmds = []
        self.payload_for = payload_for or (lambda ver: {
            "module": "m", "e2e_available": True, "status": "ran", "pass": True,
            "versions": {ver: {"pass": True, "findings": [], "authored_assertions": 1}}})
        self.code_for = code_for or (lambda ver: 0)

    def __call__(self, cmd):
        self.cmds.append(list(cmd))
        ver = _ver_of(cmd)
        payload = self.payload_for(ver)
        if payload is not None:
            Path(_out_of(cmd)).write_text(json.dumps(payload), encoding="utf-8")
        return self.code_for(ver)

    def extra_of(self, flag):
        return [c[c.index(flag) + 1] if flag in c else None for c in self.cmds]


def _run_main(argv, fake):
    """Jalankan main() dengan anak palsu. Return (exit_code, stderr).

    stderr ikut dikembalikan karena beberapa gerbang menghasilkan exit code yang SAMA lewat
    jalur berbeda (lapis serial vs lapis tak dikenal; gerbang bentuk vs raise merge), jadi
    exit code saja tak membuktikan gerbang yang dimaksud yang menyala.
    """
    real = mod._spawn
    mod._spawn = fake
    buf = io.StringIO()
    try:
        with contextlib.redirect_stderr(buf):
            rc = mod.main(argv)
    finally:
        mod._spawn = real
    return rc, buf.getvalue()


def _mod_dir(tmp, name="mymod"):
    d = Path(tmp) / name
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


def test_pure():
    ok = True
    ok &= check("parse_versions memangkas spasi & membuang kosong",
                mod.parse_versions(" 1.7.8 , 8.1 ,, ") == ["1.7.8", "8.1"])
    ok &= check("parse_versions atas string kosong -> []", mod.parse_versions("") == [])
    # Duplikat = dua anak menulis file bukti yang sama & mem-boot container ber-nama sama.
    ok &= check("parse_versions membuang duplikat (bukan cuma kata di docstring)",
                mod.parse_versions("9.1,9.1,8.1,9.1") == ["9.1", "8.1"])

    ok &= check("reserved: --versions di passthrough terdeteksi",
                mod.reserved_in_passthrough(["--tag-map", "x", "--versions", "9.1"]) == ["--versions"])
    ok &= check("reserved: bentuk --output=… terdeteksi",
                mod.reserved_in_passthrough(["--output=/tmp/x.json"]) == ["--output"])
    # Bentuk MENEMPEL: argparse anak menerimanya, dan ia pernah lolos gerbang lalu menimpa
    # file lapis lain di folder laporan.
    ok &= check("reserved: bentuk menempel -o/path terdeteksi",
                mod.reserved_in_passthrough(["-o/tmp/lain.json"]) == ["-o"])
    ok &= check("reserved: singkatan awalan --version terdeteksi",
                mod.reserved_in_passthrough(["--version", "8.1"]) == ["--versions"])
    ok &= check("reserved: singkatan awalan --outp= terdeteksi",
                mod.reserved_in_passthrough(["--outp=/tmp/x.json"]) == ["--output"])
    ok &= check("reserved: flag lapis biasa lolos",
                mod.reserved_in_passthrough(
                    ["--tag-map", "9.1=9.1.4-nginx", "--browsers", "chromium",
                     "--orchestrator", "compose", "--headed"]) == [])

    rest, base = mod.split_screenshot_dir(["--a", "1", "--screenshot-dir", "/s", "--b", "2"])
    ok &= check("split_screenshot_dir bentuk terpisah", (rest, base) == (["--a", "1", "--b", "2"], "/s"))
    rest2, base2 = mod.split_screenshot_dir(["--screenshot-dir=/s2", "--c"])
    ok &= check("split_screenshot_dir bentuk =", (rest2, base2) == (["--c"], "/s2"))
    rest3, base3 = mod.split_screenshot_dir(["--c"])
    ok &= check("split_screenshot_dir tanpa flag -> base None", (rest3, base3) == (["--c"], None))

    ok &= check("layer_file diturunkan dari (folder, module, lapis)",
                mod.layer_file("/rep", "/x/mymod", "e2e") == "/rep/mymod-e2e.json")
    ok &= check("layer_file: lapis beda -> file beda",
                mod.layer_file("/rep", "/x/mymod", "flashlight") == "/rep/mymod-flashlight.json")

    plan = mod.plan_children("/s/ps-e2e-run.py", "/m", ["9.1", "8.1"], "/tmp/x", ["--browsers", "chromium"])
    ok &= check("plan: satu anak per versi", [v for v, _c, _o in plan] == ["9.1", "8.1"])
    c0 = plan[0][1]
    ok &= check("plan: anak menerima SATU versi", _ver_of(c0) == "9.1")
    ok &= check("plan: -o per versi di direktori temp", _out_of(c0) == str(Path("/tmp/x") / "9.1.json"))
    ok &= check("plan: passthrough diteruskan apa adanya", c0[-2:] == ["--browsers", "chromium"])
    ok &= check("plan: module diteruskan sebagai argumen posisional", "/m" in c0)
    return ok


def test_execute_and_collect():
    ok = True
    plan = [("9.1", ["uv", "--versions", "9.1", "-o", "/x/9.1.json"], "/x/9.1.json"),
            ("8.1", ["uv", "--versions", "8.1", "-o", "/x/8.1.json"], "/x/8.1.json")]
    ok &= check("execute mengembalikan exit code tiap versi",
                mod.execute(plan, jobs=2, runner=lambda cmd: 0) == {"9.1": 0, "8.1": 0})

    def boom(cmd):
        raise RuntimeError("runner meledak")
    ok &= check("runner meledak -> versi itu None, bukan crash orkestrator",
                mod.execute(plan, jobs=2, runner=boom) == {"9.1": None, "8.1": None})

    with tempfile.TemporaryDirectory() as tmp:
        p1 = Path(tmp) / "9.1.json"
        p1.write_text(json.dumps({"versions": {"9.1": {"pass": True}}}), encoding="utf-8")
        p2 = Path(tmp) / "8.1.json"
        pl = [("9.1", [], str(p1)), ("8.1", [], str(p2))]
        pairs, missing, rejected = mod.collect(pl, {"9.1": 0, "8.1": 0})
        ok &= check("collect: file ada -> pasangan (versi, payload)", [v for v, _p in pairs] == ["9.1"])
        ok &= check("collect: file tak ada -> missing", missing == ["8.1"])
        ok &= check("collect: tak ada yang ditolak", rejected == [])

        p2.write_text("{bukan json", encoding="utf-8")
        _p, missing_b, _r = mod.collect(pl, {"9.1": 0, "8.1": 0})
        ok &= check("collect: JSON rusak -> missing (bukti tak bisa dipercaya)", missing_b == ["8.1"])

        p2.write_text(json.dumps({"versions": {"7.0": {"pass": True}}}), encoding="utf-8")
        _p, _m, rej_stray = mod.collect(pl, {"9.1": 0, "8.1": 0})
        ok &= check("collect: anak melaporkan versi lain -> rejected",
                    len(rej_stray) == 1 and rej_stray[0][0] == "8.1")

        # Anak yang melewatkan lapis (Docker/Playwright absen) mengemit versions:{} lalu exit 0.
        # Kalau itu dihitung sukses, versinya lenyap dari file kanonik tanpa sepatah kata.
        p2.write_text(json.dumps({"status": "skipped", "reason": "Docker tidak tersedia",
                                  "versions": {}}), encoding="utf-8")
        pairs_e, missing_e, rej_e = mod.collect(pl, {"9.1": 0, "8.1": 0})
        ok &= check("collect: versions kosong -> MISSING (tak diam-diam dianggap sukses)",
                    missing_e == ["8.1"] and rej_e == [])
        ok &= check("collect: payload skip tetap dipakai (ia membawa alasannya)",
                    len(pairs_e) == 2)

        _p, _m, rej_2 = mod.collect(pl, {"9.1": 0, "8.1": 2})
        ok &= check("collect: anak exit 2 -> rejected (error input, bukan vonis)",
                    len(rej_2) == 1 and rej_2[0][0] == "8.1")
    return ok


def test_cli_gates():
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        fake = FakeChildren()

        for layer, why in (("static", "sekali di orkestrator"), ("adversarial", "satu reviewer")):
            rc, err = _run_main(["--layer", layer, "--module", m, "--versions", "9.1",
                                 "--reports-dir", rep], fake)
            ok &= check(f"lapis '{layer}' ditolak exit 2 dengan sebabnya", rc == 2 and why in err)
        rc_u, err_u = _run_main(["--layer", "ngawur", "--module", m, "--versions", "9.1",
                                 "--reports-dir", rep], fake)
        ok &= check("lapis tak dikenal -> exit 2 & pesannya beda dari lapis serial",
                    rc_u == 2 and "tak dikenal" in err_u)

        rc_v, _ = _run_main(["--layer", "e2e", "--module", m, "--versions", " , ",
                             "--reports-dir", rep], fake)
        ok &= check("--versions kosong -> exit 2", rc_v == 2)
        rc_j, _ = _run_main(["--layer", "e2e", "--module", m, "--versions", "9.1",
                             "--reports-dir", rep, "--jobs", "0"], fake)
        ok &= check("--jobs 0 -> exit 2", rc_j == 2)

        rc_r, err_r = _run_main(["--layer", "e2e", "--module", m, "--versions", "9.1",
                                 "--reports-dir", rep, "--", "--versions", "8.1"], fake)
        ok &= check("--versions di passthrough -> exit 2", rc_r == 2 and "--versions" in err_r)

        # Bentuk MENEMPEL pernah lolos gerbang, mengalihkan bukti anak keluar dari temp, dan
        # menimpa file lapis lain di folder laporan.
        korban = Path(rep) / "mymod-static.json"
        korban.write_text('{"module":"mymod","pass":true}', encoding="utf-8")
        rc_a, err_a = _run_main(["--layer", "flashlight", "--module", m, "--versions", "9.1",
                                 "--reports-dir", rep, "--", f"-o{korban}"], fake)
        ok &= check("bentuk menempel -o<path> di passthrough -> exit 2", rc_a == 2 and "-o" in err_a)
        ok &= check("file lapis lain TIDAK tertimpa",
                    json.loads(korban.read_text())["pass"] is True)
        ok &= check("gerbang menyala SEBELUM anak di-spawn", fake.cmds == [])

        rc_t, err_t = _run_main(["--layer", "e2e", "--module", m, "--versions", "9.1",
                                 "--reports-dir", "{project-root}/rep"], fake)
        ok &= check("token {project-root} di --reports-dir -> exit 2",
                    rc_t == 2 and "belum diresolve" in err_t)
        rc_t2, _ = _run_main(["--layer", "e2e", "--module", m, "--versions", "9.1",
                              "--reports-dir", rep, "--", "--screenshot-dir",
                              "{project-root}/shots"], fake)
        ok &= check("token {project-root} di --screenshot-dir -> exit 2", rc_t2 == 2)
        ok &= check("tak satu pun gerbang di atas men-spawn anak", fake.cmds == [])
    return ok


def test_output_is_derived():
    """Nama file lapis diturunkan, jadi bukti tak bisa mendarat di module/lapis lain."""
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep = str(Path(tmp) / "reports")
        Path(rep).mkdir()
        modA, modB = _mod_dir(tmp, "modA"), _mod_dir(tmp, "modB")
        fake = FakeChildren()
        rc, _ = _run_main(["--layer", "e2e", "--module", modA, "--versions", "9.1",
                           "--reports-dir", rep], fake)
        ok &= check("run modA -> exit 0", rc == 0)
        ok &= check("bukti modA mendarat di modA-e2e.json",
                    (Path(rep) / "modA-e2e.json").is_file())
        ok &= check("tak ada file lapis modB yang tersentuh",
                    not (Path(rep) / "modB-e2e.json").exists())
        ok &= check("tak ada file lapis flashlight yang tersentuh",
                    not (Path(rep) / "modA-flashlight.json").exists())

        rc2, _ = _run_main(["--layer", "flashlight", "--module", modB, "--versions", "9.1",
                            "--reports-dir", rep], FakeChildren())
        ok &= check("run modB flashlight menulis file-nya sendiri",
                    rc2 == 0 and (Path(rep) / "modB-flashlight.json").is_file())
        ok &= check("file modA tetap utuh sesudahnya",
                    json.loads((Path(rep) / "modA-e2e.json").read_text())["module"] == "m")
    return ok


def test_cli_happy_and_degrade():
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        shots = str(Path(tmp) / "shots")
        fake = FakeChildren()
        started = time.time()
        rc, _ = _run_main(["--layer", "e2e", "--module", m, "--versions", "9.1,8.1",
                           "--reports-dir", rep, "--jobs", "2",
                           "--", "--screenshot-dir", shots], fake)
        out = Path(rep) / "mymod-e2e.json"
        ok &= check("dua versi berbukti & lolos -> exit 0", rc == 0)
        ok &= check("file kanonik memuat kedua versi",
                    set(json.loads(out.read_text())["versions"]) == {"9.1", "8.1"})

        got = fake.extra_of("--screenshot-dir")
        ok &= check("kedua anak menerima folder screenshot yang SAMA",
                    len(set(got)) == 1 and got[0] is not None)
        ok &= check("folder itu sudah berstempel run-<ts>",
                    bool(re.match(r"^run-\d{8}-\d{6}$", Path(got[0]).name)))
        ok &= check("folder berstempel berada di bawah base yang diminta",
                    str(Path(got[0]).parent) == shots)
        # Komposisi nyata: nilai yang diterima anak dilewatkan ke run_shot_dir milik
        # ps-e2e-run — anak asli memanggilnya, jadi idempotensinya harus tahan di sini.
        ok &= check("anak asli tak akan menstempel ulang folder itu",
                    mod.e2e_module().run_shot_dir(got[0]) == got[0])

        stray = sorted(p.name for p in Path(rep).glob("*.json") if p.name != out.name)
        ok &= check("bukti per-versi tak menetap di folder laporan", stray == [])

    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        fake = FakeChildren(payload_for=lambda ver: None if ver == "8.1" else {
            "module": "m", "docker_available": True, "status": "ran", "pass": True,
            "versions": {ver: {"pass": True}}})
        rc, err = _run_main(["--layer", "flashlight", "--module", m, "--versions", "9.1,8.1",
                             "--reports-dir", rep], fake)
        ok &= check("versi tanpa bukti -> exit 1 dan DISEBUT", rc == 1 and "8.1" in err)
        merged = json.loads((Path(rep) / "mymod-flashlight.json").read_text())
        ok &= check("versi tanpa bukti dihilangkan, tak dikarang jadi vonis",
                    set(merged["versions"]) == {"9.1"})

    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        # SEMUA anak melewatkan lapis (Docker absen) — bentuk & exit code harus mengikuti
        # run serial: degrade jujur, bukan vonis gagal di runner tanpa Docker.
        fake = FakeChildren(payload_for=lambda ver: {
            "module": "m", "docker_available": False, "status": "skipped",
            "reason": "Docker tidak tersedia — lewati uji flashlight.", "versions": {}})
        rc, err = _run_main(["--layer", "flashlight", "--module", m, "--versions", "9.1,8.1",
                             "--reports-dir", rep], fake)
        ok &= check("lapis tak tersedia sama sekali -> exit 0 (seperti run serial)", rc == 0)
        ok &= check("alasannya disebut, bukan exit senyap", "Docker tidak tersedia" in err)
        merged = json.loads((Path(rep) / "mymod-flashlight.json").read_text())
        ok &= check("file kanonik memakai bentuk skip, tak mengklaim pass",
                    merged.get("status") == "skipped" and "pass" not in merged)

    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        fake = FakeChildren(code_for=lambda ver: 2 if ver == "8.1" else 0)
        rc, err = _run_main(["--layer", "flashlight", "--module", m, "--versions", "9.1,8.1",
                             "--reports-dir", rep], fake)
        ok &= check("anak menolak input -> exit 2, file kanonik tak ditulis",
                    rc == 2 and not (Path(rep) / "mymod-flashlight.json").exists())
        # Kegagalan pasca-spawn tak boleh membuang puluhan menit boot Docker.
        keep = re.search(r"DIPERTAHANKAN untuk diagnosis: (\S+)", err)
        ok &= check("bukti per-versi dipertahankan & pathnya disebut",
                    bool(keep) and Path(keep.group(1)).is_dir())
        if keep:
            ok &= check("bukti versi yang berhasil masih ada di sana",
                        (Path(keep.group(1)) / "9.1.json").is_file())
            import shutil as _sh
            _sh.rmtree(keep.group(1), ignore_errors=True)

    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        fake = FakeChildren(payload_for=lambda ver: {
            "module": "m", "docker_available": True, "status": "ran", "pass": True,
            "versions": {ver: {"pass": True, "findings": "bukan-list"}}})
        rc, err = _run_main(["--layer", "flashlight", "--module", m, "--versions", "9.1",
                             "--reports-dir", rep], fake)
        ok &= check("bukti salah-bentuk -> exit 2 lewat gerbang bentuk (bukan lewat merge)",
                    rc == 2 and "gerbang bentuk" in err)
        ok &= check("bukti salah-bentuk tak jadi file kanonik",
                    not (Path(rep) / "mymod-flashlight.json").exists())
        k = re.search(r"DIPERTAHANKAN untuk diagnosis: (\S+)", err)
        if k:
            import shutil as _sh
            _sh.rmtree(k.group(1), ignore_errors=True)

    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        fake = FakeChildren(payload_for=lambda ver: {
            "module": "m", "docker_available": True, "status": "ran",
            "pass": ver == "9.1", "versions": {ver: {"pass": ver == "9.1"}}})
        rc, _ = _run_main(["--layer", "flashlight", "--module", m, "--versions", "9.1,8.1",
                           "--reports-dir", rep], fake)
        ok &= check("satu versi gagal -> exit 1 (pass=AND)", rc == 1)
        merged = json.loads((Path(rep) / "mymod-flashlight.json").read_text())
        ok &= check("kedua versi tetap dilaporkan", set(merged["versions"]) == {"9.1", "8.1"})
    return ok


def test_freshness_stamp():
    """mtime file lapis = saat run MULAI, bukan saat tulis.

    Gerbang kesegaran ps-plan-layers memakai mtime file lapis sebagai proksi "kapan bukti ini
    diproduksi". Run multi-versi bisa berjalan puluhan menit, jadi stempel waktu-tulis membuat
    source yang diedit DI TENGAH run terbaca lebih tua dari buktinya lalu dipakai ulang.
    Anak sengaja dibuat lambat supaya selisih tulis-vs-mulai lebih besar dari toleransi —
    tanpa itu test lolos walau stempelnya dicopot.
    """
    ok = True
    lag = 2.0
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)

        class SlowChild(FakeChildren):
            def __call__(self, cmd):
                time.sleep(lag)
                return super().__call__(cmd)

        started = time.time()
        rc, _ = _run_main(["--layer", "flashlight", "--module", m, "--versions", "9.1",
                           "--reports-dir", rep], SlowChild())
        out = Path(rep) / "mymod-flashlight.json"
        elapsed = time.time() - started
        ok &= check("run selesai (kontrol)", rc == 0 and out.is_file())
        ok &= check(f"run benar-benar makan waktu >= {lag}s (kalau tidak, test ini hampa)",
                    elapsed >= lag)
        ok &= check("mtime file lapis dekat ke waktu MULAI, bukan waktu tulis",
                    out.stat().st_mtime < started + (lag / 2))
    return ok


def test_merge_rules():
    """Aturan penggabungan bukti per-versi (dulu skrip terpisah, kini milik konsumennya)."""
    ok = True
    a = {"e2e_available": True, "status": "ran", "pass": True, "browsers": ["chromium"],
         "scenario_notes": ["a"], "screenshot_dir": None,
         "versions": {"9.1": {"pass": True, "findings": []}}}
    b = {"e2e_available": True, "status": "ran", "pass": False, "browsers": ["firefox"],
         "scenario_notes": ["b"], "screenshot_dir": "/shots/run-x",
         "versions": {"8.1": {"pass": False, "findings": []}}}
    c = {"e2e_available": False, "status": "skipped", "pass": True, "browsers": ["chromium"],
         "scenario_notes": [], "versions": {}}

    mv = mod.merge_versions_field([a, b, c])
    ok &= check("union 3 payload -> 9.1 & 8.1 (skipped tak menyumbang)",
                set(mv.keys()) == {"9.1", "8.1"})
    ok &= check("urutan versi mengikuti kemunculan payload", list(mv.keys()) == ["9.1", "8.1"])

    top = mod.merge_toplevel([a, b, c], mv)
    ok &= check("pass = AND semua", top["pass"] is False)
    ok &= check("status 'ran' bila ada yang jalan", top["status"] == "ran")
    ok &= check("e2e_available OR", top["e2e_available"] is True)
    ok &= check("browsers di-union urut-stabil", top["browsers"] == ["chromium", "firefox"])
    ok &= check("scenario_notes di-union", top["scenario_notes"] == ["a", "b"])
    ok &= check("skalar null dilewati, nilai yang dilaporkan menang",
                top["screenshot_dir"] == "/shots/run-x")

    ok &= check("duplikat versi identik -> sah, satu entri",
                list(mod.merge_versions_field([a, a]).keys()) == ["9.1"])
    ok &= check("versi bertumpuk isi beda -> raise ValueError",
                _raises(mod.merge_versions_field,
                        [a, {"versions": {"9.1": {"pass": False, "findings": []}}}]))
    return ok


def test_scalar_conflict():
    """Skalar berbeda antar bukti = konflik, BUKAN 'ambil yang pertama'."""
    ok = True
    s1 = {"screenshot_dir": "/shots/run-A", "versions": {"9.1": {"pass": True}}}
    s2 = {"screenshot_dir": "/shots/run-B", "versions": {"8.1": {"pass": True}}}
    ok &= check("dua screenshot_dir BERBEDA -> raise (bukan diam-diam pilih satu)",
                _raises(mod.merge_toplevel, [s1, s2], mod.merge_versions_field([s1, s2])))
    same = {"screenshot_dir": "/shots/run-A", "versions": {"8.1": {"pass": True}}}
    ok &= check("screenshot_dir sama -> lolos (kontrol positif)",
                mod.merge_toplevel([s1, same], mod.merge_versions_field([s1, same]))
                ["screenshot_dir"] == "/shots/run-A")
    m1 = {"module": "mymod", "versions": {"9.1": {"pass": True}}}
    m2 = {"module": "modul-lain", "versions": {"8.1": {"pass": True}}}
    ok &= check("module berbeda antar bukti -> raise",
                _raises(mod.merge_toplevel, [m1, m2], mod.merge_versions_field([m1, m2])))
    n1 = {"reason": None, "versions": {"9.1": {"pass": True}}}
    n2 = {"reason": "Docker tidak tersedia", "versions": {"8.1": {"pass": True}}}
    ok &= check("null bukan klaim tandingan",
                mod.merge_toplevel([n1, n2], mod.merge_versions_field([n1, n2]))
                ["reason"] == "Docker tidak tersedia")
    return ok


def test_consumed_by_aggregate():
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        rc, _ = _run_main(["--layer", "e2e", "--module", m, "--versions", "9.1,8.1",
                           "--reports-dir", rep], FakeChildren())
        ok &= check("orkestrator menulis file kanonik (exit 0)", rc == 0)
        static = Path(rep) / "static.json"
        static.write_text(json.dumps(
            {"module": "m", "main_file_found": True, "pass": True,
             "versions": {"9.1": {"errors": 0, "warnings": 0, "findings": [], "rules_evaluated": 5},
                          "8.1": {"errors": 0, "warnings": 0, "findings": [], "rules_evaluated": 5}}}),
            encoding="utf-8")
        agg = subprocess.run(
            ["uv", "run", str(SCRIPTS / "ps-aggregate.py"), "--static", str(static),
             "--e2e", str(Path(rep) / "mymod-e2e.json"), "--versions", "9.1,8.1"],
            capture_output=True, text=True)
        ok &= check("ps-aggregate menerima file kanonik (exit 0/1, bukan 2 salah-bentuk)",
                    agg.returncode in (0, 1))
    return ok


def test_help_prints_docstring():
    r = subprocess.run(["uv", "run", str(MOD_PATH), "--help"], capture_output=True, text=True)
    return check("--help mencetak docstring (epilog=__doc__)",
                 "KESEGARAN" in r.stdout and r.returncode == 0)


def test_per_version_persist():
    """Mode --per-version: bukti tiap versi menetap di file per-versi sendiri, kanonik tak ditulis.

    Ini yang memungkinkan konvergensi version-first — menjalankan versi lain tak menimpa bukti
    versi yang sudah bersih, beda dengan file kanonik satu-untuk-semua yang selalu ditimpa.
    """
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        fake = FakeChildren()
        started = time.time()
        rc, _ = _run_main(["--layer", "e2e", "--module", m, "--versions", "9.1,8.1",
                           "--reports-dir", rep, "--per-version"], fake)
        pv91 = Path(rep) / "mymod-e2e-9.1.json"
        pv81 = Path(rep) / "mymod-e2e-8.1.json"
        ok &= check("per-version: semua versi berbukti -> exit 0", rc == 0)
        ok &= check("per-version: file per-versi DITULIS (nama diturunkan, segmen versi)",
                    pv91.is_file() and pv81.is_file())
        ok &= check("per-version: file KANONIK TAK ditulis (tak menimpa bukti versi lain)",
                    not (Path(rep) / "mymod-e2e.json").exists())
        ok &= check("per-version: tiap file memuat PERSIS versinya",
                    set(json.loads(pv91.read_text())["versions"]) == {"9.1"}
                    and set(json.loads(pv81.read_text())["versions"]) == {"8.1"})
        # mtime = saat run mulai (proksi "kapan bukti diproduksi"), bukan waktu tulis — supaya
        # gerbang kesegaran ps-plan-layers per-versi menyala benar.
        ok &= check("per-version: mtime file = saat run mulai (untuk gerbang kesegaran)",
                    abs(pv91.stat().st_mtime - started) < 5)

    # Satu versi tanpa bukti: file itu TAK ditulis (tak dikarang), exit 1, disebut.
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        fake = FakeChildren(payload_for=lambda ver: None if ver == "8.1" else {
            "module": "m", "docker_available": True, "status": "ran", "pass": True,
            "versions": {ver: {"pass": True}}})
        rc, err = _run_main(["--layer", "flashlight", "--module", m, "--versions", "9.1,8.1",
                             "--reports-dir", rep, "--per-version"], fake)
        ok &= check("per-version: versi tanpa bukti -> exit 1 & DISEBUT", rc == 1 and "8.1" in err)
        ok &= check("per-version: file 9.1 ditulis, file 8.1 TIDAK (tak dikarang jadi vonis)",
                    (Path(rep) / "mymod-flashlight-9.1.json").is_file()
                    and not (Path(rep) / "mymod-flashlight-8.1.json").exists())

    # Payload skip (versions {}, Docker absen utk versi itu) TAK dipersist jadi file per-versi
    # kosong — versi masuk missing (exit 1). Kalau ditulis, merge-only kelak membacanya sebagai
    # "ada tapi hampa"; jangan produksi sumbernya.
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        fake = FakeChildren(payload_for=lambda ver: {
            "module": "m", "docker_available": True, "status": "ran", "pass": True,
            "versions": {ver: {"pass": True}}} if ver == "9.1" else {
            "module": "m", "docker_available": False, "status": "skipped", "versions": {}})
        rc, _ = _run_main(["--layer", "flashlight", "--module", m, "--versions", "9.1,8.1",
                           "--reports-dir", rep, "--per-version"], fake)
        ok &= check("per-version: versi skip (versions {}) -> file per-versi TAK ditulis, exit 1",
                    rc == 1 and (Path(rep) / "mymod-flashlight-9.1.json").is_file()
                    and not (Path(rep) / "mymod-flashlight-8.1.json").exists())

    # Semua versi skip (Docker absen): tak ada file per-versi ditulis, exit 0 (lapis tak tersedia,
    # seperti run serial) — bukan exit 1 yang menuduh runner tanpa Docker gagal.
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        fake = FakeChildren(payload_for=lambda ver: {
            "module": "m", "docker_available": False, "status": "skipped", "versions": {}})
        rc, _ = _run_main(["--layer", "flashlight", "--module", m, "--versions", "9.1,8.1",
                           "--reports-dir", rep, "--per-version"], fake)
        ok &= check("per-version: SEMUA skip -> tak ada file per-versi, exit 0 (lapis tak tersedia)",
                    rc == 0 and not list(Path(rep).glob("mymod-flashlight-*.json")))
    return ok


def _write_pv(rep, layer, ver, mtime, top=None):
    """Tulis satu file lapis per-versi persisten (bentuk seperti keluaran --per-version)."""
    p = Path(rep) / f"mymod-{layer}-{ver}.json"
    payload = {"module": "m", "docker_available": True, "status": "ran", "pass": True,
               "versions": {ver: {"pass": True}}}
    if top:
        payload.update(top)
    p.write_text(json.dumps(payload), encoding="utf-8")
    os.utime(p, (mtime, mtime))
    return p


def test_merge_only():
    """--merge-only: satukan file per-versi persisten jadi kanonik, tanpa men-spawn apa pun."""
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        _write_pv(rep, "flashlight", "1.7.8", 100)  # tertua
        _write_pv(rep, "flashlight", "8.1", 300)
        _write_pv(rep, "flashlight", "9.1", 200)
        fake = FakeChildren()
        rc, _ = _run_main(["--layer", "flashlight", "--module", m, "--versions", "1.7.8,8.1,9.1",
                           "--reports-dir", rep, "--merge-only"], fake)
        out = Path(rep) / "mymod-flashlight.json"
        ok &= check("merge-only: exit 0 & kanonik ditulis", rc == 0 and out.is_file())
        ok &= check("merge-only TAK men-spawn anak sama sekali (hanya menyatukan)", fake.cmds == [])
        merged = json.loads(out.read_text())
        ok &= check("merge-only: kanonik = union ketiga versi",
                    set(merged["versions"]) == {"1.7.8", "8.1", "9.1"})
        # mtime = bukti TERTUA: kanonik tak boleh tampak lebih segar dari bukti terbasinya, jadi
        # source yang diedit sesudah salah satu versi dikonvergensi tetap membasikan kanonik.
        ok &= check("merge-only: mtime kanonik = min(bukti), bukan sekarang",
                    abs(out.stat().st_mtime - 100) < 1)

    # Versi tanpa file per-versi -> dihilangkan (bukan dikarang), exit 1, disebut.
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        _write_pv(rep, "flashlight", "8.1", 300)
        _write_pv(rep, "flashlight", "9.1", 200)
        rc, err = _run_main(["--layer", "flashlight", "--module", m, "--versions", "1.7.8,8.1,9.1",
                             "--reports-dir", rep, "--merge-only"], FakeChildren())
        ok &= check("merge-only: versi hilang -> exit 1 & DISEBUT", rc == 1 and "1.7.8" in err)
        merged = json.loads((Path(rep) / "mymod-flashlight.json").read_text())
        ok &= check("merge-only: versi hilang dihilangkan dari kanonik (ready jatuh di agregat)",
                    set(merged["versions"]) == {"8.1", "9.1"})

    # Nol file per-versi -> kanonik TAK ditulis (tak ada bukti untuk disatukan), exit 1.
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        rc, err = _run_main(["--layer", "flashlight", "--module", m, "--versions", "9.1",
                             "--reports-dir", rep, "--merge-only"], FakeChildren())
        ok &= check("merge-only: nol bukti -> exit 1, kanonik TAK ditulis",
                    rc == 1 and not (Path(rep) / "mymod-flashlight.json").exists())

    # Skalar top-level bertentangan -> bukti tak konsisten -> exit 2 (bukan pilih senyap).
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        _write_pv(rep, "e2e", "8.1", 100, top={"screenshot_dir": "/a"})
        _write_pv(rep, "e2e", "9.1", 200, top={"screenshot_dir": "/b"})
        rc, err = _run_main(["--layer", "e2e", "--module", m, "--versions", "8.1,9.1",
                             "--reports-dir", rep, "--merge-only"], FakeChildren())
        ok &= check("merge-only: skalar top-level bertentangan -> exit 2",
                    rc == 2 and "berbeda antar bukti" in err
                    and not (Path(rep) / "mymod-e2e.json").exists())

    # File per-versi terpotong (versions bukan object) -> gerbang bentuk -> exit 2 (tak menyelinap).
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        _write_pv(rep, "flashlight", "8.1", 100)
        bad = Path(rep) / "mymod-flashlight-9.1.json"
        bad.write_text(json.dumps({"module": "m", "versions": {"9.1": "bukan-object"}}), encoding="utf-8")
        os.utime(bad, (200, 200))
        rc, err = _run_main(["--layer", "flashlight", "--module", m, "--versions", "8.1,9.1",
                             "--reports-dir", rep, "--merge-only"], FakeChildren())
        ok &= check("merge-only: file per-versi cacat -> gerbang bentuk -> exit 2",
                    rc == 2 and "gerbang bentuk" in err
                    and not (Path(rep) / "mymod-flashlight.json").exists())

    # Review-A: file per-versi KOSONG (versions {}) = tak berbukti -> versi masuk missing (exit 1
    # & disebut), BUKAN menyelinap hilang dengan exit 0 (present-kosong dulu lebih longgar dari
    # absen — kebalikan arah degrade jujur). Cermin guard collect() di jalur run nyata.
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        _write_pv(rep, "flashlight", "8.1", 100)
        empty = Path(rep) / "mymod-flashlight-9.1.json"
        empty.write_text(json.dumps({"module": "m", "status": "skipped", "versions": {}}),
                         encoding="utf-8")
        os.utime(empty, (200, 200))
        rc, err = _run_main(["--layer", "flashlight", "--module", m, "--versions", "8.1,9.1",
                             "--reports-dir", rep, "--merge-only"], FakeChildren())
        merged = json.loads((Path(rep) / "mymod-flashlight.json").read_text())
        ok &= check("merge-only: file KOSONG -> versi itu missing (exit 1 & disebut), bukan exit 0",
                    rc == 1 and "9.1" in err and set(merged["versions"]) == {"8.1"})

    # Review-B: file salah-label (nama -9.1 tapi isi versi 8.1) -> exit 2, bukan diam-diam merge
    # 8.1 & biarkan 9.1 tak berbukti. Identitas by-construction DITEGAKKAN pada baca (merge-only
    # memakan file yang tak ditulisnya sendiri). Cermin guard stray di collect().
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        _write_pv(rep, "e2e", "8.1", 100)
        mis = Path(rep) / "mymod-e2e-9.1.json"
        mis.write_text(json.dumps({"module": "m", "status": "ran", "pass": True,
                                   "versions": {"8.1": {"pass": True}}}), encoding="utf-8")
        os.utime(mis, (200, 200))
        rc, err = _run_main(["--layer", "e2e", "--module", m, "--versions", "8.1,9.1",
                             "--reports-dir", rep, "--merge-only"], FakeChildren())
        ok &= check("merge-only: file salah-label (isi versi lain) -> exit 2 (identitas ditegakkan)",
                    rc == 2 and "salah-label" in err
                    and not (Path(rep) / "mymod-e2e.json").exists())

    # Review-C: kanonik ber-pass:false tanpa versi hilang -> exit 1 (dulu `1 if missing else 0`
    # MENGABAIKAN pass -> exit 0, gerbang CI terbaca hijau atas lapis yang gagal).
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        _write_pv(rep, "flashlight", "8.1", 100)
        fail = Path(rep) / "mymod-flashlight-9.1.json"
        fail.write_text(json.dumps({"module": "m", "status": "ran", "pass": False,
                                    "versions": {"9.1": {"pass": False}}}), encoding="utf-8")
        os.utime(fail, (200, 200))
        rc, _ = _run_main(["--layer", "flashlight", "--module", m, "--versions", "8.1,9.1",
                           "--reports-dir", rep, "--merge-only"], FakeChildren())
        merged = json.loads((Path(rep) / "mymod-flashlight.json").read_text())
        ok &= check("merge-only: ada versi gagal (pass:false) -> exit 1 (exit code tak berbohong)",
                    rc == 1 and merged.get("pass") is False)

    # Seluruh lapis tak tersedia (semua file skip) -> exit 0 degrade jujur + kanonik skip-shape,
    # MENGIKUTI run serial. Bukan exit 1 (itu akan menjatuhkan runner tanpa Docker jadi "gagal").
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        for v in ("8.1", "9.1"):
            p = Path(rep) / f"mymod-flashlight-{v}.json"
            p.write_text(json.dumps({"module": "m", "status": "skipped",
                                     "reason": "Docker tidak tersedia", "versions": {}}),
                         encoding="utf-8")
            os.utime(p, (100, 100))
        rc, _ = _run_main(["--layer", "flashlight", "--module", m, "--versions", "8.1,9.1",
                           "--reports-dir", rep, "--merge-only"], FakeChildren())
        merged = json.loads((Path(rep) / "mymod-flashlight.json").read_text())
        ok &= check("merge-only: SEMUA skip -> exit 0 (degrade jujur, seperti run serial)",
                    rc == 0 and merged.get("status") == "skipped" and "pass" not in merged)
    return ok


def test_modes_exclusive_and_passthrough():
    """Guard: dua mode saling eksklusif; merge-only menolak passthrough (tak ada yang dijalankan)."""
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        rc, err = _run_main(["--layer", "flashlight", "--module", m, "--versions", "9.1",
                             "--reports-dir", rep, "--per-version", "--merge-only"], FakeChildren())
        ok &= check("--per-version + --merge-only -> exit 2 (saling eksklusif)",
                    rc == 2 and "saling eksklusif" in err)
        rc2, err2 = _run_main(["--layer", "flashlight", "--module", m, "--versions", "9.1",
                               "--reports-dir", rep, "--merge-only", "--", "--tag-map", "x"],
                              FakeChildren())
        ok &= check("--merge-only + passthrough -> exit 2 (tak ada yang dijalankan)",
                    rc2 == 2 and "passthrough" in err2)
    return ok


def main():
    ok = True
    for name, fn in (("test_pure", test_pure),
                     ("test_execute_and_collect", test_execute_and_collect),
                     ("test_cli_gates", test_cli_gates),
                     ("test_output_is_derived", test_output_is_derived),
                     ("test_cli_happy_and_degrade", test_cli_happy_and_degrade),
                     ("test_freshness_stamp", test_freshness_stamp),
                     ("test_merge_rules", test_merge_rules),
                     ("test_scalar_conflict", test_scalar_conflict),
                     ("test_per_version_persist", test_per_version_persist),
                     ("test_merge_only", test_merge_only),
                     ("test_modes_exclusive_and_passthrough", test_modes_exclusive_and_passthrough),
                     ("test_consumed_by_aggregate", test_consumed_by_aggregate),
                     ("test_help_prints_docstring", test_help_prints_docstring)):
        print(f"{name}:")
        ok &= fn()
    print()
    print("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
