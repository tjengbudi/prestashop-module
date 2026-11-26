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


SESSION = "abcdefghij012345"


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


def _run_full(argv, fake, docker=True):
    """Jalankan main() dengan anak palsu & Docker di-stub. Return (exit_code, stderr, stdout).

    stderr ikut dikembalikan karena beberapa gerbang menghasilkan exit code yang SAMA lewat
    jalur berbeda (lapis serial vs lapis tak dikenal; gerbang bentuk vs raise merge), jadi
    exit code saja tak membuktikan gerbang yang dimaksud yang menyala. stdout memikul baris
    output JSON Lapis 4.
    """
    fl = mod.flashlight()
    real, real_docker = mod._spawn, fl.docker_available
    mod._spawn = fake
    fl.docker_available = lambda: docker
    buf, out = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stderr(buf), contextlib.redirect_stdout(out):
            rc = mod.main(argv)
    finally:
        mod._spawn = real
        fl.docker_available = real_docker
    kept = re.search(r"DIPERTAHANKAN untuk diagnosis: (\S+)", buf.getvalue())
    if kept and "/psm-layer-" in kept.group(1) and Path(kept.group(1)).is_dir() \
            and any(a == "e2e" for a in argv):
        import shutil as _sh
        _sh.rmtree(kept.group(1), ignore_errors=True)  # test e2e: tak meninggalkan sampah /tmp
    return rc, buf.getvalue(), out.getvalue()


def _run_main(argv, fake):
    rc, err, _out = _run_full(argv, fake)
    return rc, err


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
                    ["--tag-map", "9.1=9.1.4-nginx", "--extra-tag-map", "8.1=8.1.7",
                     "--orchestrator", "compose", "--headed", "--startup-timeout", "60",
                     "--allow-image-pull", "--screenshot-dir", "/s", "--verbose"]) == [])
    # Slice CAP-2: --config diteruskan skrip ini sendiri, engine tiap versi dipilih di sini.
    ok &= check("reserved: --config/--browsers/--engines (juga bentuk =) tak boleh di passthrough",
                mod.reserved_in_passthrough(["--config", "c.json"]) == ["--config"]
                and mod.reserved_in_passthrough(["--browsers=chromium"]) == ["--browsers"]
                and mod.reserved_in_passthrough(["--engines", "firefox"]) == ["--engines"])
    ok &= check("reserved: singkatan awalan >= 4 karakter atas SELURUH tuple",
                mod.reserved_in_passthrough(["--conf", "c"]) == ["--config"]
                and mod.reserved_in_passthrough(["--brow=x"]) == ["--browsers"]
                and mod.reserved_in_passthrough(["--eng", "x"]) == ["--engines"]
                and mod.reserved_in_passthrough(["--clean"]) == ["--cleanup-orphans"]
                and mod.reserved_in_passthrough(["--stop", "j"]) == ["--stop-job"]
                and mod.reserved_in_passthrough(["--list"]) == ["--list-jobs"])

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
    ok &= check("plan: tanpa progress -> tak ada --progress-file", "--progress-file" not in c0)

    # Log kemajuan anak: nama DITURUNKAN di reports dir (bukan folder temp bukti) supaya
    # pemanggil bisa memantau macet selagi run berjalan.
    planp = mod.plan_children("/s/ps-e2e-run.py", "/x/mymod", ["9.1", "8.1"], "/tmp/x",
                              ["--browsers", "chromium"], progress=("/rep", "e2e"))
    cp0, cp1 = planp[0][1], planp[1][1]
    ok &= check("plan: --progress-file per versi diturunkan di reports dir",
                cp0[cp0.index("--progress-file") + 1] == "/rep/mymod-e2e-9.1.progress.log"
                and cp1[cp1.index("--progress-file") + 1] == "/rep/mymod-e2e-8.1.progress.log")
    ok &= check("progress_file: bentuk <module>-<lapis>-<versi>.progress.log",
                mod.progress_file("/rep", "/x/mymod", "flashlight", "1.7.8")
                == "/rep/mymod-flashlight-1.7.8.progress.log")
    planj = mod.plan_children("/s/ps-e2e-run.py", "/x/mymod", ["9.1", "8.1"], "/tmp/x", [],
                              job_id="mymod-e2e-1204-abcd")
    ok &= check("plan: SEMUA anak berbagi satu --job-id (stop-job menghentikan pemanggilan ini)",
                all(c[c.index("--job-id") + 1] == "mymod-e2e-1204-abcd" for _v, c, _o in planj))
    ok &= check("reserved: --job-id/--stop-job/--list-jobs tak boleh di passthrough",
                set(mod.reserved_in_passthrough(["--job-id", "x", "--stop-job", "y", "--list-jobs"]))
                == {"--job-id", "--stop-job", "--list-jobs"}
                and mod.reserved_in_passthrough(["--job=x"]) == ["--job-id"])
    ok &= check("reserved: --progress-file (dan singkatannya) tak boleh di passthrough",
                mod.reserved_in_passthrough(["--progress-file", "/a"]) == ["--progress-file"]
                and mod.reserved_in_passthrough(["--progress=/a"]) == ["--progress-file"])
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

        rc_v, err_v = _run_main(["--layer", "flashlight", "--module", m, "--versions", " , ",
                                 "--reports-dir", rep], fake)
        ok &= check("--versions kosong -> exit 2", rc_v == 2 and "kosong" in err_v)
        rc_n, err_n = _run_main(["--layer", "flashlight", "--module", m, "--reports-dir", rep],
                                fake)
        ok &= check("--versions absen (lapis selain e2e) -> exit 2", rc_n == 2 and "kosong" in err_n)
        rc_j, _ = _run_main(["--layer", "e2e", "--module", m, "--versions", "9.1",
                             "--reports-dir", rep, "--jobs", "0"], fake)
        ok &= check("--jobs 0 -> exit 2", rc_j == 2)

        rc_r, err_r = _run_main(["--layer", "flashlight", "--module", m, "--versions", "9.1",
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

        for layer, sess in (("flashlight", []), ("e2e", ["--session", SESSION])):
            rc_t, err_t = _run_main(["--layer", layer, "--module", m, "--versions", "9.1",
                                     "--reports-dir", "{project-root}/rep", *sess], fake)
            ok &= check(f"{layer}: token {{project-root}} di --reports-dir -> exit 2",
                        rc_t == 2 and "belum diresolve" in err_t)
            rc_t2, err_t2 = _run_main(["--layer", layer, "--module", m, "--versions", "9.1",
                                       "--reports-dir", rep, *sess, "--", "--screenshot-dir",
                                       "{project-root}/shots"], fake)
            ok &= check(f"{layer}: token {{project-root}} di --screenshot-dir -> exit 2",
                        rc_t2 == 2 and "belum diresolve" in err_t2)
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
        rc, _ = _run_main(["--layer", "scenario", "--module", modA, "--versions", "9.1",
                           "--reports-dir", rep], fake)
        ok &= check("run modA -> exit 0", rc == 0)
        ok &= check("bukti modA mendarat di modA-scenario.json",
                    (Path(rep) / "modA-scenario.json").is_file())
        ok &= check("tak ada file lapis modB yang tersentuh",
                    not (Path(rep) / "modB-scenario.json").exists())
        ok &= check("tak ada file lapis flashlight yang tersentuh",
                    not (Path(rep) / "modA-flashlight.json").exists())

        rc2, _ = _run_main(["--layer", "flashlight", "--module", modB, "--versions", "9.1",
                            "--reports-dir", rep], FakeChildren())
        ok &= check("run modB flashlight menulis file-nya sendiri",
                    rc2 == 0 and (Path(rep) / "modB-flashlight.json").is_file())
        ok &= check("file modA tetap utuh sesudahnya",
                    json.loads((Path(rep) / "modA-scenario.json").read_text())["module"] == "m")
    return ok


def test_cli_happy_and_degrade():
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        shots = str(Path(tmp) / "shots")
        fake = FakeChildren()
        started = time.time()
        rc, _ = _run_main(["--layer", "scenario", "--module", m, "--versions", "9.1,8.1",
                           "--reports-dir", rep, "--jobs", "2",
                           "--", "--screenshot-dir", shots], fake)
        out = Path(rep) / "mymod-scenario.json"
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
         "scenario_notes": ["a"], "screenshot_dir": None, "reason": None,
         "versions": {"9.1": {"pass": True, "findings": []}}}
    b = {"e2e_available": True, "status": "ran", "pass": False, "browsers": ["firefox"],
         "scenario_notes": ["b"], "screenshot_dir": "/shots/run-x",
         "reason": "Docker tidak tersedia",
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
                top["reason"] == "Docker tidak tersedia")
    ok &= check("kunci union: null dilewati, hasilnya tetap daftar",
                top.get("screenshot_dir") == ["/shots/run-x"])

    ok &= check("duplikat versi identik -> sah, satu entri",
                list(mod.merge_versions_field([a, a]).keys()) == ["9.1"])
    ok &= check("versi bertumpuk isi beda -> raise ValueError",
                _raises(mod.merge_versions_field,
                        [a, {"versions": {"9.1": {"pass": False, "findings": []}}}]))
    return ok


def _merged_or_none(payloads):
    """merge_toplevel yang meledak -> None, supaya assertion bisa melaporkannya sbg FAIL.

    Tanpa ini regresi di kunci union menghentikan seluruh suite dengan traceback dan
    setiap test sesudahnya diam — kegagalan yang menyamar jadi 'cuma satu yang merah'.
    """
    try:
        return mod.merge_toplevel(payloads, mod.merge_versions_field(payloads))
    except ValueError:
        return None


def test_scalar_conflict():
    """Skalar berbeda antar bukti = konflik, BUKAN 'ambil yang pertama'.

    KECUALI kunci _UNION_KEYS: `screenshot_dir` distempel run-<ts> BARU tiap invokasi
    orkestrator, dan alur terdokumentasi mengonvergensikan versi satu per satu — jadi
    stempel berbeda adalah bukti SEHAT dari dua invokasi, bukan dua klaim bertentangan.
    Dulu ia raise di sini dan menjatuhkan gerbang rilis tanpa input yang bisa diperbaiki.
    """
    ok = True
    s1 = {"screenshot_dir": "/shots/run-A", "versions": {"9.1": {"pass": True}}}
    s2 = {"screenshot_dir": "/shots/run-B", "versions": {"8.1": {"pass": True}}}
    merged = _merged_or_none([s1, s2])
    ok &= check("dua screenshot_dir BERBEDA -> dikumpulkan, nol folder dibuang",
                merged is not None
                and merged["screenshot_dir"] == ["/shots/run-A", "/shots/run-B"])
    same = {"screenshot_dir": "/shots/run-A", "versions": {"8.1": {"pass": True}}}
    ok &= check("screenshot_dir sama -> satu entri, tak diduplikasi",
                mod.merge_toplevel([s1, same], mod.merge_versions_field([s1, same]))
                ["screenshot_dir"] == ["/shots/run-A"])
    ok &= check("screenshot_dir null tak jadi entri hampa",
                mod.merge_toplevel(
                    [{"screenshot_dir": None, "versions": {"9.1": {}}},
                     {"screenshot_dir": "/shots/run-A", "versions": {"8.1": {}}}],
                    {})["screenshot_dir"] == ["/shots/run-A"])
    ok &= check("kunci skalar LAIN tetap raise (union tak bocor ke semua kunci)",
                _raises(mod.merge_toplevel,
                        [{"ps_domain": "a:1", "versions": {"9.1": {}}},
                         {"ps_domain": "b:2", "versions": {"8.1": {}}}], {}))
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


def test_shot_dirs_survive_separate_invocations():
    """REPRODUKSI: konvergensi per-versi = N invokasi = N stempel, lalu --merge-only.

    Dulu jalur ini exit 2 'bukti tak konsisten' atas bukti yang sehat, dan tak ada input
    yang bisa diperbaiki — satu-satunya pemulihan adalah mem-boot ulang Docker+browser
    semua versi dalam satu invokasi. Diuji lewat merge nyata, bukan fungsi murni saja.
    """
    ok = True
    payloads = []
    for ver, stamp in (("9.1", "run-20260908-100000"), ("8.1", "run-20260908-101500")):
        payloads.append({
            "module": "mymod", "layer": "e2e", "status": "ran", "pass": True,
            "screenshot_dir": f"/reports/e2e-shots/{stamp}",
            "versions": {ver: {"pass": True, "conclusive": True,
                               "screenshot_dir": f"/reports/e2e-shots/{stamp}/{ver}"}},
        })
    merged = _merged_or_none(payloads)
    ok &= check("dua invokasi terpisah -> merge TIDAK meledak",
                merged is not None and isinstance(merged.get("screenshot_dir"), list))
    ok &= check("kedua folder run terjangkau peninjau visual",
                merged is not None
                and merged["screenshot_dir"] == ["/reports/e2e-shots/run-20260908-100000",
                                                 "/reports/e2e-shots/run-20260908-101500"])
    ok &= check("path per-versi berstempel tetap utuh di entri versinya",
                merged is not None
                and merged["versions"]["9.1"]["screenshot_dir"].endswith("run-20260908-100000/9.1")
                and merged["versions"]["8.1"]["screenshot_dir"].endswith("run-20260908-101500/8.1"))
    return ok


def test_consumed_by_aggregate():
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        rc, _ = _run_main(["--layer", "flashlight", "--module", m, "--versions", "9.1,8.1",
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
             "--flashlight", str(Path(rep) / "mymod-flashlight.json")],
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
        rc, _ = _run_main(["--layer", "scenario", "--module", m, "--versions", "9.1,8.1",
                           "--reports-dir", rep, "--per-version"], fake)
        pv91 = Path(rep) / "mymod-scenario-9.1.json"
        pv81 = Path(rep) / "mymod-scenario-8.1.json"
        ok &= check("per-version: semua versi berbukti -> exit 0", rc == 0)
        ok &= check("per-version: file per-versi DITULIS (nama diturunkan, segmen versi)",
                    pv91.is_file() and pv81.is_file())
        ok &= check("per-version: file KANONIK TAK ditulis (tak menimpa bukti versi lain)",
                    not (Path(rep) / "mymod-scenario.json").exists())
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
    # Dipakai ps_domain, BUKAN screenshot_dir: yang terakhir kini kunci union (stempel run
    # berbeda antar invokasi adalah bukti sehat), jadi memakainya di sini akan menguji
    # kebalikan dari kontrak yang berlaku.
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        _write_pv(rep, "scenario", "8.1", 100, top={"ps_domain": "localhost:8000"})
        _write_pv(rep, "scenario", "9.1", 200, top={"ps_domain": "shop.test:9000"})
        rc, err = _run_main(["--layer", "scenario", "--module", m, "--versions", "8.1,9.1",
                             "--reports-dir", rep, "--merge-only"], FakeChildren())
        ok &= check("merge-only: skalar top-level bertentangan -> exit 2",
                    rc == 2 and "berbeda antar bukti" in err
                    and not (Path(rep) / "mymod-scenario.json").exists())

    # Kontrol positif untuk kelas yang baru dibuka: stempel run berbeda LOLOS dan terkumpul.
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        _write_pv(rep, "scenario", "8.1", 100, top={"screenshot_dir": "/shots/run-A"})
        _write_pv(rep, "scenario", "9.1", 200, top={"screenshot_dir": "/shots/run-B"})
        rc, err = _run_main(["--layer", "scenario", "--module", m, "--versions", "8.1,9.1",
                             "--reports-dir", rep, "--merge-only"], FakeChildren())
        canon = Path(rep) / "mymod-scenario.json"
        ok &= check("merge-only: stempel run berbeda -> exit 0 & kedua folder terkumpul",
                    rc == 0 and canon.exists()
                    and json.loads(canon.read_text())["screenshot_dir"]
                        == ["/shots/run-A", "/shots/run-B"])

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
        _write_pv(rep, "scenario", "8.1", 100)
        mis = Path(rep) / "mymod-scenario-9.1.json"
        mis.write_text(json.dumps({"module": "m", "status": "ran", "pass": True,
                                   "versions": {"8.1": {"pass": True}}}), encoding="utf-8")
        os.utime(mis, (200, 200))
        rc, err = _run_main(["--layer", "scenario", "--module", m, "--versions", "8.1,9.1",
                             "--reports-dir", rep, "--merge-only"], FakeChildren())
        ok &= check("merge-only: file salah-label (isi versi lain) -> exit 2 (identitas ditegakkan)",
                    rc == 2 and "salah-label" in err
                    and not (Path(rep) / "mymod-scenario.json").exists())

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


# --- Lapis 4: histori per sel (spec-psm-e2e-cap2-cap6-cell-evidence) ---------------------
# Kunci Fields kontrak (cell-contract.md > Evidence record > Fields) + boot_wall_clock & boot_log.
CONTRACT_FIELDS = (
    "version", "browser", "started_at", "finished_at", "boot", "boot_id", "session",
    "browser_mode", "scenario_set", "scenarios_run", "source_fingerprint", "image_tag", "run_id",
    "job_id", "tier", "state", "conclusive", "reason", "errors", "install", "launch_error",
    "bo_authed", "findings", "inconclusive", "authored_assertions", "scenario_notes",
    "browser_notes", "parallel_only", "console_errors", "screenshots", "scenario_spans",
    "phase_durations", "boot_phases", "keeper_boot", "wall_clock")
RECORD_FIELDS = set(CONTRACT_FIELDS) | {"boot_wall_clock", "boot_log"}
PL = mod.plan_layers()


def _iso(offset=0.0):
    from datetime import datetime, timedelta, timezone
    return (datetime(2026, 11, 26, 10, 0, 0, tzinfo=timezone.utc)
            + timedelta(seconds=offset)).isoformat(timespec="microseconds")


def _child_payload(ver, engines, *, kind="pass", available=None, tag=None):
    """Output anak berbentuk ps-e2e-run (sel dari _new_cell milik anak asli)."""
    e2e = mod.e2e_module()
    vres = {"run_id": "c0ffee000001", "boot": "cold", "boot_id": "c0ffee000001",
            "image_tag": tag or f"{ver}-img", "browser_mode": "sequential",
            "boot_phases": {"pull": {"seconds": 1.0, "outcome": "ok"}},
            "boot_wall_clock": 42.5, "boot_log": None, "errors": [],
            "install": {"ok": True}, "scenario_notes": [], "cells": {}}
    for i, e in enumerate(engines):
        cell = e2e._new_cell()
        if kind in ("install", "boot"):
            pass  # engine tak pernah jalan: started_at/finished_at None, tanpa browser:<engine>
        else:
            cell.update({"started_at": _iso(10 * i), "finished_at": _iso(10 * i + 7.25),
                         "scenarios_run": ["psm-universal-smoke", "a"],
                         "findings": ([{"scenario": "a", "action": "expect_text", "step": 3}]
                                      if kind == "fail" else []),
                         "inconclusive": [], "authored_assertions": 2, "bo_authed": True,
                         "console_errors": 0, "screenshots": [],
                         "phase_durations": {f"browser:{e}": {"seconds": 7.2,
                                                                "outcome": "ok"}}})
        vres["cells"][e] = cell
    if kind == "install":
        vres["install"] = {"ok": False, "output": "boom"}
        vres["errors"] = ["install gagal"]
    if kind == "boot":
        vres["install"] = None
        vres["errors"] = ["wait-healthy: timeout"]
        vres["boot_log"] = "db: crash"
    return {"module": "mymod", "status": "ran", "e2e_available": True,
            "browsers": list(engines),
            "browsers_available": list(engines) if available is None else available,
            "versions": {ver: vres}}


class E2EChild:
    """Anak ps-e2e-run palsu. `behave(ver, engines) -> (payload|None|str, rc)`; str = teks mentah.

    Merekam perintah & urutan selesai; `delay` per versi mengatur urutan selesai.
    """

    def __init__(self, behave=None, delay=None, hook=None):
        self.cmds, self.done = [], []
        self.behave = behave or (lambda ver, engines: (_child_payload(ver, engines), 0))
        self.delay = delay or {}
        self.hook = hook

    def __call__(self, cmd):
        self.cmds.append(list(cmd))
        ver = _ver_of(cmd)
        engines = cmd[cmd.index("--engines") + 1].split(",")
        time.sleep(self.delay.get(ver, 0))
        if self.hook:
            self.hook(ver)
        payload, rc = self.behave(ver, engines)
        if isinstance(payload, str):
            Path(_out_of(cmd)).write_text(payload, encoding="utf-8")
        elif payload is not None:
            Path(_out_of(cmd)).write_text(json.dumps(payload), encoding="utf-8")
        self.done.append(ver)
        if isinstance(rc, BaseException):
            raise rc
        return rc

    def arg(self, flag):
        return [c[c.index(flag) + 1] if flag in c else None for c in self.cmds]


def _cfg(tmp, versions="1.7.8,8.1,9.1", browsers="chromium,firefox", name="psm-config.json",
         **more):
    p = Path(tmp) / name
    data = {"psm_target_versions": versions, "psm_e2e_browsers": browsers}
    data.update(more)
    p.write_text(json.dumps(data), encoding="utf-8")
    return str(p)


def _e2e_env(tmp):
    rep = str(Path(tmp) / "reports")
    Path(rep).mkdir(exist_ok=True)
    m = _mod_dir(tmp)
    Path(m, "mymod.php").write_text("<?php\n", encoding="utf-8")
    return rep, m


def _e2e(rep, m, cfg, *scope, extra=(), session=SESSION, more=()):
    argv = ["--layer", "e2e", "--module", m, "--reports-dir", rep, *scope]
    if cfg:
        argv += ["--config", cfg]
    if session:
        argv += ["--session", session]
    argv += list(more)
    if extra:
        argv += ["--", *extra]
    return argv


def _hist(rep, ver, browser):
    return PL.read_history(PL.history_path(rep, "mymod", ver, browser), ver, browser)[0]


def _line(out):
    lines = [ln for ln in out.splitlines() if ln.strip()]
    return json.loads(lines[-1]) if lines else None


def _no_layer_files(rep):
    return not list(Path(rep).glob("mymod-e2e*.json"))


def test_e2e_input_errors():
    """Tiap error input Lapis 4 -> exit 2 SEBELUM spawn, tanpa baris output."""
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        inside_shots = str(Path(m) / "shots")
        cases = [
            ("tanpa --cells/--versions", _e2e(rep, m, cfg)),
            ("--cells DAN --versions", _e2e(rep, m, cfg, "--cells", "9.1:chromium",
                                            "--versions", "9.1")),
            ("--session absen", _e2e(rep, m, cfg, "--versions", "9.1", session=None)),
            ("--session salah bentuk", _e2e(rep, m, cfg, "--versions", "9.1", session="ABC")),
            ("--session 15 karakter", _e2e(rep, m, cfg, "--versions", "9.1",
                                           session="abcdefghij01234")),
            ("token --cells tanpa ':'", _e2e(rep, m, cfg, "--cells", "9.1")),
            ("token --cells kosong", _e2e(rep, m, cfg, "--cells", "9.1:chromium,,8.1:firefox")),
            ("token --cells koma di ujung", _e2e(rep, m, cfg, "--cells", "9.1:chromium,")),
            ("browser kosong di sel", _e2e(rep, m, cfg, "--cells", "9.1:chromium+")),
            ("browser berulang di satu sel", _e2e(rep, m, cfg, "--cells",
                                                  "9.1:chromium+chromium")),
            ("versi berulang di --cells", _e2e(rep, m, cfg, "--cells",
                                               "9.1:chromium,9.1:firefox")),
            ("versi --cells bukan string terkonfigurasi", _e2e(rep, m, cfg, "--cells",
                                                               "9.1.0:chromium")),
            ("browser di luar himpunan", _e2e(rep, m, cfg, "--cells", "9.1:webkit")),
            ("versi di luar himpunan", _e2e(rep, m, cfg, "--cells", "7.0:chromium")),
            ("--versions bukan string terkonfigurasi", _e2e(rep, m, cfg, "--versions", "9.1.0")),
            ("--versions kosong", _e2e(rep, m, cfg, "--versions", " , ")),
            ("--per-version", _e2e(rep, m, cfg, "--versions", "9.1", more=["--per-version"])),
            ("reports dir = akar module", _e2e(m, m, cfg, "--versions", "9.1")),
            ("--screenshot-dir di module, di luar reports", _e2e(
                rep, m, cfg, "--versions", "9.1", extra=["--screenshot-dir", inside_shots])),
            ("--browsers di passthrough", _e2e(rep, m, cfg, "--versions", "9.1",
                                               extra=["--browsers", "chromium"])),
            ("--engines di passthrough", _e2e(rep, m, cfg, "--versions", "9.1",
                                              extra=["--engines=chromium"])),
            ("--config di passthrough", _e2e(rep, m, cfg, "--versions", "9.1",
                                             extra=["--config", cfg])),
            ("singkatan --brow di passthrough", _e2e(rep, m, cfg, "--versions", "9.1",
                                                     extra=["--brow", "chromium"])),
            ("config tak terbaca", _e2e(rep, m, str(Path(tmp) / "absen.json"),
                                        "--versions", "9.1")),
            ("config engine webkitx", _e2e(rep, m, _cfg(tmp, browsers="chromium,webkitx",
                                                     name="webkitx.json"),
                                           "--versions", "9.1")),
        ]
        cfg_bad = {
            "config 9.1 + 9.1.0": {"psm_target_versions": "9.1,9.1.0"},
            "config list kosong": {"psm_target_versions": []},
            "config versi tak bertitik": {"psm_target_versions": "9.x"},
            "config bukan objek": [1, 2],
            "config tag map bukan string": {"psm_flashlight_tag_map": {"9.1": "x"}},
            "config startup timeout bukan bilangan": {"psm_flashlight_startup_timeout": "abc"},
        }
        for i, (name, data) in enumerate(cfg_bad.items()):
            p = Path(tmp) / f"bad{i}.json"
            p.write_text(json.dumps(data), encoding="utf-8")
            cases.append((name, _e2e(rep, m, str(p), "--versions", "9.1")))
        cases += [
            ("--cells dgn lapis flashlight", ["--layer", "flashlight", "--module", m,
                                               "--reports-dir", rep, "--versions", "9.1",
                                               "--cells", "9.1:chromium"]),
            ("--session dgn lapis scenario", ["--layer", "scenario", "--module", m,
                                               "--reports-dir", rep, "--versions", "9.1",
                                               "--session", SESSION]),
        ]
        for name, argv in cases:
            fake = E2EChild()
            rc, err, out = _run_full(argv, fake)
            ok &= check(f"input error: {name} -> exit 2, tak spawn, tanpa baris output",
                        rc == 2 and fake.cmds == [] and out.strip() == "" and "error" in err)
        ok &= check("tak ada histori tertulis oleh error input",
                    not list(Path(rep).glob("*.jsonl")))
        # Kontrol positif: --screenshot-dir di dalam reports dir yang ada DI DALAM module sah.
        rep_in = str(Path(m) / "reports")
        Path(rep_in).mkdir()
        fake = E2EChild()
        rc, err, _out = _run_full(_e2e(rep_in, m, cfg, "--versions", "9.1",
                                       extra=["--screenshot-dir", str(Path(rep_in) / "shots")]),
                                  fake)
        ok &= check("kontrol: reports & screenshot dir di dalam module (screenshot di reports) sah",
                    rc == 0 and len(fake.cmds) == 1)
        ok &= check("kontrol: --config 'startup timeout' bilangan string diterima",
                    _run_full(_e2e(rep, m, _cfg(tmp, name="t60.json",
                                        psm_flashlight_startup_timeout="60"),
                                   "--versions", "9.1"), E2EChild())[0] == 0)
    return ok


def test_reserved_on_other_layers():
    """Cek reserved (termasuk --config/--browsers/--engines & singkatannya) berlaku SEMUA lapis."""
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = tmp, _mod_dir(tmp)
        for extra in (["--browsers", "chromium"], ["--config=x.json"], ["--engines", "firefox"],
                      ["--conf", "x"], ["--engi", "x"]):
            for layer in ("flashlight", "scenario"):
                fake = FakeChildren()
                rc, err = _run_main(["--layer", layer, "--module", m, "--versions", "9.1",
                                     "--reports-dir", rep, "--", *extra], fake)
                ok &= check(f"{layer}: passthrough {extra[0]} -> exit 2, tak spawn",
                            rc == 2 and fake.cmds == [] and "passthrough" in err)
        # --config diteruskan APA ADANYA ke tiap anak lapis lain, tak divalidasi (isi apa pun).
        bogus = Path(tmp) / "cfg.json"
        bogus.write_text('{"psm_e2e_browsers": "webkitx"}', encoding="utf-8")
        fake = FakeChildren()
        rc, _ = _run_main(["--layer", "flashlight", "--module", m, "--versions", "9.1,8.1",
                           "--reports-dir", rep, "--config", str(bogus)], fake)
        ok &= check("flashlight: --config diteruskan ke SETIAP anak, tanpa validasi",
                    rc == 0 and fake.extra_of("--config") == [str(bogus)] * 2)
    return ok


def test_e2e_ac3():
    """AC3: --versions 9.1 + anak sukses -> tepat satu rekaman per browser terkonfigurasi 9.1."""
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        fake = E2EChild()
        rc, err, out = _run_full(_e2e(rep, m, cfg, "--versions", "9.1"), fake)
        line = _line(out)
        ok &= check("AC3: exit 0", rc == 0)
        ok &= check("AC3: satu anak, --versions 9.1, --engines = browser terkonfigurasi",
                    len(fake.cmds) == 1 and _ver_of(fake.cmds[0]) == "9.1"
                    and fake.arg("--engines") == ["chromium,firefox"])
        ok &= check("AC3: anak menerima --config, tanpa --browsers",
                    fake.arg("--config") == [cfg] and "--browsers" not in fake.cmds[0])
        ok &= check("AC3: tepat satu rekaman per browser 9.1",
                    len(_hist(rep, "9.1", "chromium")) == 1
                    and len(_hist(rep, "9.1", "firefox")) == 1)
        ok &= check("AC3: versi lain tak tersentuh",
                    sorted(p.name for p in Path(rep).glob("*.jsonl"))
                    == ["mymod-e2e-9.1-chromium.jsonl", "mymod-e2e-9.1-firefox.jsonl"])
        ok &= check("AC3: tak ada <module>-e2e*.json", _no_layer_files(rep))
        ok &= check("baris output: ran, appended, fingerprint = source_fingerprint sekarang",
                    line == {"e2e_status": "ran", "reason": None,
                             "appended": ["9.1:chromium", "9.1:firefox"],
                             "source_fingerprint": PL.source_fingerprint(m, rep)})
        ok &= check("baris output adalah satu-satunya isi stdout", len(out.strip().splitlines()) == 1)
    return ok


def test_e2e_record_fields():
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp, browsers="chromium,firefox",
                   psm_flashlight_tag_map="1.7.8=1.7.8.11,8.1=8.1.6-nginx,9.1=9.1.4-nginx")
        job = "mymod-e2e-1200-abcd"

        def behave(ver, engines):
            return _child_payload(ver, engines, tag="9.1.4-nginx"), 0
        rc, _err, out = _run_full(_e2e(rep, m, cfg, "--cells", "9.1:firefox",
                                       more=["--job-id", job]), E2EChild(behave))
        recs = _hist(rep, "9.1", "firefox")
        r = recs[0] if recs else {}
        ok &= check("rekaman: kunci PERSIS Fields + boot_wall_clock + boot_log",
                    set(r) == RECORD_FIELDS and set(mod.RECORD_KEYS) == RECORD_FIELDS)
        ok &= check("rekaman: field runner (session, fingerprint, job_id, tier/keeper_boot null)",
                    r.get("session") == SESSION and r.get("job_id") == job
                    and r.get("source_fingerprint") == _line(out)["source_fingerprint"]
                    and r.get("tier") is None and r.get("keeper_boot") is None)
        ok &= check("rekaman: state/conclusive/reason dari derive_state",
                    (r.get("state"), r.get("conclusive"), r.get("reason")) == ("pass", True, None))
        ok &= check("rekaman: field level-versi anak disalin apa adanya",
                    r.get("boot") == "cold" and r.get("boot_id") == "c0ffee000001"
                    and r.get("run_id") == "c0ffee000001" and r.get("image_tag") == "9.1.4-nginx"
                    and r.get("browser_mode") == "sequential" and r.get("boot_wall_clock") == 42.5
                    and r.get("boot_phases") == {"pull": {"seconds": 1.0, "outcome": "ok"}}
                    and r.get("boot_log") is None and r.get("install") == {"ok": True}
                    and r.get("errors") == [] and r.get("scenario_notes") == [])
        ok &= check("rekaman: field sel anak (timestamp, phase_durations, scenario_set)",
                    r.get("started_at") == _iso(0) and r.get("finished_at") == _iso(7.25)
                    and r.get("phase_durations") == {"browser:firefox": {"seconds": 7.2,
                                                                         "outcome": "ok"}}
                    and r.get("scenario_set") == "full" and r.get("authored_assertions") == 2)
        ok &= check("rekaman: wall_clock = finished_at - started_at", r.get("wall_clock") == 7.25)
        ok &= check("rekaman: pembaca plan menilainya passing gate-grade",
                    bool(recs) and PL.is_passing_gate_grade(
                        r, PL.source_fingerprint(m, rep), "9.1.4-nginx"))
        ok &= check("hanya sel yang diminta (9.1:firefox) yang di-append",
                    rc == 0 and _hist(rep, "9.1", "chromium") == [])

        # Rekaman crash punya kunci yang sama persis.
        rc2, _e, _o = _run_full(_e2e(rep, m, cfg, "--cells", "8.1:chromium"),
                                E2EChild(lambda v, e: (None, 1)))
        c = (_hist(rep, "8.1", "chromium") or [{}])[0]
        ok &= check("rekaman crash: kunci PERSIS sama", set(c) == RECORD_FIELDS and rc2 == 1)
    return ok


def test_e2e_crash_and_shape():
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        fl = mod.flashlight()
        rc, _err, out = _run_full(_e2e(rep, m, cfg, "--versions", "9.1"),
                                  E2EChild(lambda v, e: (None, 1)))
        recs = _hist(rep, "9.1", "chromium") + _hist(rep, "9.1", "firefox")
        ok &= check("crash: anak exit 1 tanpa output -> exit 1", rc == 1)
        ok &= check("crash: satu rekaman inconclusive/crash per sel diadmisi",
                    len(recs) == 2 and all((r["state"], r["conclusive"], r["reason"])
                                           == ("inconclusive", False, "crash") for r in recs))
        ok &= check("crash: run_id = RUN_ID ps-run-layer, image_tag = tag ter-resolve",
                    all(r["run_id"] == fl.RUN_ID and r["image_tag"] == "9.1.4-nginx"
                        for r in recs))
        ok &= check("crash: field level-versi lain null, timestamp diisi (UTC valid)",
                    all(r["boot"] is None and r["install"] is None and r["boot_log"] is None
                        and PL.parse_utc(r["started_at"]) and PL.parse_utc(r["finished_at"])
                        and r["wall_clock"] >= 0 for r in recs))
        ok &= check("crash: baris output ran", _line(out)["e2e_status"] == "ran")

        shapes = {
            "JSON rusak": ("{bukan json", 1),
            "versi nyasar": (lambda v, e: {**_child_payload(v, e),
                                           "versions": {**_child_payload(v, e)["versions"],
                                                        "7.0": {"cells": {}}}}, 3),
            "cells bukan objek": (lambda v, e: {**_child_payload(v, e),
                                                "versions": {v: {"cells": ["x"]}}}, 1),
            "bukan objek": ("[1, 2]", 0),
        }
        for name, (payload, code) in shapes.items():
            ver = "8.1"
            before = len(_hist(rep, ver, "chromium"))

            def behave(v, e, payload=payload, code=code):
                return (payload(v, e) if callable(payload) else payload), code
            rc_s, _e2, out_s = _run_full(_e2e(rep, m, cfg, "--cells", "8.1:chromium"),
                                         E2EChild(behave))
            new = _hist(rep, ver, "chromium")[before:]
            ok &= check(f"bentuk salah ({name}) -> crash, bukan exit 2",
                        rc_s == 1 and len(new) == 1 and new[0]["reason"] == "crash"
                        and _line(out_s)["appended"] == ["8.1:chromium"])

        # Sel di luar yang diadmisi tak di-append; engine diadmisi tanpa sel padahal tersedia -> crash.
        def extra_cell(v, e):
            p = _child_payload(v, ["chromium", "firefox"])
            del p["versions"][v]["cells"]["chromium"]
            p["browsers_available"] = ["chromium", "firefox"]
            return p, 0
        rc_x, err_x, _o = _run_full(_e2e(rep, m, cfg, "--cells", "1.7.8:chromium"),
                                    E2EChild(extra_cell))
        ok &= check("sel tak diadmisi (firefox) tak di-append & dicatat di stderr",
                    _hist(rep, "1.7.8", "firefox") == [] and "firefox" in err_x)
        ok &= check("engine diadmisi tersedia tapi tanpa sel -> crash",
                    rc_x == 1 and [r["reason"] for r in _hist(rep, "1.7.8", "chromium")] == ["crash"])
    return ok


def test_e2e_install_boot_failure():
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        for kind, reason, ver in (("install", "install", "9.1"), ("boot", "errors", "8.1")):
            rc, _err, _out = _run_full(_e2e(rep, m, cfg, "--versions", ver),
                                       E2EChild(lambda v, e, k=kind: (_child_payload(v, e, kind=k), 1)))
            recs = _hist(rep, ver, "chromium") + _hist(rep, ver, "firefox")
            ok &= check(f"{kind} gagal -> satu rekaman per engine, reason {reason} (bukan crash)",
                        rc == 1 and len(recs) == 2
                        and all((r["state"], r["reason"]) == ("inconclusive", reason) for r in recs))
            ok &= check(f"{kind} gagal: started_at/finished_at diisi ps-run-layer",
                        all(PL.parse_utc(r["started_at"]) and PL.parse_utc(r["finished_at"])
                            for r in recs))
        boot = _hist(rep, "8.1", "chromium")[0]
        ok &= check("boot gagal: install null, errors & boot_log dari anak",
                    boot["install"] is None and boot["errors"] == ["wait-healthy: timeout"]
                    and boot["boot_log"] == "db: crash")
    return ok


def test_e2e_probe_drop_and_fail():
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)

        def drop(v, e):
            p = _child_payload(v, ["chromium"], available=["chromium"])
            return p, 0
        rc, _err, out = _run_full(_e2e(rep, m, cfg, "--versions", "9.1"), E2EChild(drop))
        ff = (_hist(rep, "9.1", "firefox") or [{}])[0]
        ok &= check("probe drop: firefox -> browser-unavailable",
                    (ff.get("state"), ff.get("reason")) == ("inconclusive", "browser-unavailable"))
        ok &= check("probe drop: field level-versi anak ikut di rekaman browser-unavailable",
                    ff.get("boot") == "cold" and ff.get("run_id") == "c0ffee000001"
                    and ff.get("scenario_set") is None)
        ok &= check("probe drop: chromium tetap pass; exit 1 (ada inconclusive)",
                    _hist(rep, "9.1", "chromium")[0]["state"] == "pass" and rc == 1
                    and _line(out)["appended"] == ["9.1:chromium", "9.1:firefox"])

        rc3, _e, out3 = _run_full(_e2e(rep, m, cfg, "--cells", "8.1:chromium+firefox"),
                                  E2EChild(lambda v, e: (_child_payload(v, e, kind="fail"), 3)))
        ok &= check("sel fail -> rekaman fail, exit 3, baris output ran",
                    rc3 == 3 and _hist(rep, "8.1", "firefox")[0]["state"] == "fail"
                    and _line(out3)["e2e_status"] == "ran")
    return ok


def test_e2e_child_exit2():
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        fake = E2EChild(lambda v, e: (None, 2) if v == "1.7.8" else (_child_payload(v, e), 0))
        rc, err, out = _run_full(_e2e(rep, m, cfg, "--cells",
                                      "1.7.8:chromium,8.1:chromium,9.1:firefox",
                                      more=["--jobs", "1"]), fake)
        ok &= check("anak pertama exit 2 (--jobs 1) -> tak ada anak lain dimulai",
                    [_ver_of(c) for c in fake.cmds] == ["1.7.8"])
        ok &= check("anak exit 2 -> nihil di-append, exit 2",
                    rc == 2 and not list(Path(rep).glob("*.jsonl")))
        ok &= check("anak exit 2 -> baris output ran (pasca-spawn), appended kosong",
                    _line(out) == {"e2e_status": "ran", "reason": None, "appended": [],
                                   "source_fingerprint": PL.source_fingerprint(m, rep)})

    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        # 8.1 cepat & exit 2; 9.1 sedang jalan (lambat) tetap selesai & di-append; 1.7.8 antre.
        fake = E2EChild(lambda v, e: (None, 2) if v == "8.1" else (_child_payload(v, e), 0),
                        delay={"9.1": 0.4})
        rc, _err, out = _run_full(_e2e(rep, m, cfg, "--cells",
                                       "9.1:chromium,8.1:chromium,1.7.8:chromium",
                                       more=["--jobs", "2"]), fake)
        ok &= check("exit 2: anak yang sedang jalan selesai & rekamannya di-append",
                    rc == 2 and len(_hist(rep, "9.1", "chromium")) == 1
                    and _line(out)["appended"] == ["9.1:chromium"])
        ok &= check("exit 2: versi antre tak dimulai, versi exit 2 tanpa rekaman",
                    "1.7.8" not in [_ver_of(c) for c in fake.cmds]
                    and _hist(rep, "8.1", "chromium") == [])

    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        # Exit 2 menang atas fail dan skipped.
        def behave(v, e):
            return {"9.1": (_child_payload(v, e, kind="fail"), 3),
                    "8.1": ({"status": "skipped", "reason": "Playwright absen",
                             "versions": {}}, 0),
                    "1.7.8": (None, 2)}[v]
        rc, _err, out = _run_full(_e2e(rep, m, cfg, "--cells",
                                       "9.1:chromium,8.1:chromium,1.7.8:chromium",
                                       more=["--jobs", "3"]), E2EChild(behave))
        ok &= check("exit 2 mengalahkan fail & skipped (ran, exit 2)",
                    rc == 2 and _line(out)["e2e_status"] == "ran"
                    and _line(out)["reason"] is None)
    return ok


def test_review_patches():
    """Patch review: singkatan --screenshot-dir tertangkap; browser --cells case-insensitive."""
    ok = True
    ok &= check("singkatan --screen <dir> diangkat dari passthrough",
                mod.split_screenshot_dir(["--screen", "/x", "--headed"]) == (["--headed"], "/x"))
    ok &= check("singkatan --screenshot-d=<dir> diangkat dari passthrough",
                mod.split_screenshot_dir(["--screenshot-d=/y"]) == ([], "/y"))
    ok &= check("prefix < 4 karakter tak dianggap --screenshot-dir",
                mod.split_screenshot_dir(["--s", "z"]) == (["--s", "z"], None))
    ok &= check("--cells 9.1:Chromium+FIREFOX dinormalkan huruf kecil",
                mod.parse_cells("9.1:Chromium+FIREFOX", ["9.1"], ["chromium", "firefox"])
                == [("9.1", ["chromium", "firefox"])])
    return ok


def test_require_config():
    """psm-config.json ada di reports tapi --config absen -> exit 2 sebelum spawn (run & view)."""
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        Path(rep, "psm-config.json").write_text('{"psm_target_versions": "1.7.6,9.1"}',
                                                encoding="utf-8")
        fake = E2EChild()
        rc, err, out = _run_full(_e2e(rep, m, None, "--versions", "9.1"), fake)
        ok &= check("run e2e tanpa --config padahal psm-config.json ada -> exit 2, tak spawn",
                    rc == 2 and fake.cmds == [] and out.strip() == "" and "--config" in err)
        fake = E2EChild()
        rc, err, _out = _run_full(["--layer", "e2e", "--module", m, "--reports-dir", rep,
                                   "--merge-only"], fake)
        ok &= check("merge-only e2e tanpa --config padahal psm-config.json ada -> exit 2",
                    rc == 2 and "--config" in err)
    return ok


def test_e2e_stopped():
    ok = True
    fl = mod.flashlight()
    # SIGTERM ke SATU anak (bukan --stop-job pemanggil) = versi itu tak berbukti, saudaranya lanjut.
    for label, code in (("rc 143", 143), ("rc -15", -15)):
        with tempfile.TemporaryDirectory() as tmp:
            rep, m = _e2e_env(tmp)
            cfg = _cfg(tmp)
            fake = E2EChild(lambda v, e, s=code: (None, s) if v == "9.1"
                            else (_child_payload(v, e), 0))
            rc, _err, out = _run_full(_e2e(rep, m, cfg, "--cells",
                                           "8.1:chromium,9.1:chromium,1.7.8:chromium",
                                           more=["--jobs", "1"]), fake)
            ok &= check(f"anak di-SIGTERM ({label}): run lanjut, baris output ada, exit 1",
                        rc == 1 and _line(out)["e2e_status"] == "ran"
                        and sorted(_line(out)["appended"]) == ["1.7.8:chromium", "8.1:chromium"])
            ok &= check(f"anak di-SIGTERM ({label}): tak ada crash utk versi itu, saudara di-append",
                        _hist(rep, "9.1", "chromium") == []
                        and len(_hist(rep, "1.7.8", "chromium")) == 1
                        and [_ver_of(c) for c in fake.cmds] == ["8.1", "9.1", "1.7.8"])
    for label, stop in (("JobStopped", fl.JobStopped()),):
        with tempfile.TemporaryDirectory() as tmp:
            rep, m = _e2e_env(tmp)
            cfg = _cfg(tmp)
            fake = E2EChild(lambda v, e, s=stop: (None, s) if v == "9.1"
                            else (_child_payload(v, e), 0))
            rc, _err, out = _run_full(_e2e(rep, m, cfg, "--cells",
                                           "8.1:chromium,9.1:chromium,1.7.8:chromium",
                                           more=["--jobs", "1"]), fake)
            ok &= check(f"stop ({label}): exit 143, tanpa baris output",
                        rc == 143 and out.strip() == "")
            ok &= check(f"stop ({label}): rekaman anak yang sudah selesai tetap",
                        len(_hist(rep, "8.1", "chromium")) == 1)
            ok &= check(f"stop ({label}): tak ada crash utk yang dihentikan / belum mulai",
                        _hist(rep, "9.1", "chromium") == [] and _hist(rep, "1.7.8", "chromium") == []
                        and [_ver_of(c) for c in fake.cmds] == ["8.1", "9.1"])
    return ok


def test_e2e_skipped():
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        fake = E2EChild()
        rc, _err, out = _run_full(_e2e(rep, m, cfg, "--versions", "9.1,8.1"), fake, docker=False)
        line = _line(out)
        ok &= check("Docker absen sebelum spawn -> skipped, exit 0, tak spawn",
                    rc == 0 and fake.cmds == [] and line["e2e_status"] == "skipped"
                    and line["appended"] == [] and "Docker" in (line["reason"] or ""))
        ok &= check("Docker absen -> nihil di-append", not list(Path(rep).glob("*.jsonl")))

        skip = {"module": "mymod", "e2e_available": False, "status": "skipped",
                "reason": "Playwright tak terpasang", "versions": {}}
        rc, _err, out = _run_full(_e2e(rep, m, cfg, "--versions", "9.1,8.1"),
                                  E2EChild(lambda v, e: (skip, 0) if v == "9.1"
                                           else (_child_payload(v, e, kind="boot"), 1)))
        line = _line(out)
        ok &= check("anak skipped (+ anak lain inconclusive) -> skipped, exit 0, alasan anak",
                    rc == 0 and line["e2e_status"] == "skipped"
                    and line["reason"] == "Playwright tak terpasang")
        ok &= check("anak skipped: sel-nya tak di-append; rekaman anak lain tetap di-append",
                    _hist(rep, "9.1", "chromium") == [] and len(_hist(rep, "8.1", "firefox")) == 1
                    and line["appended"] == ["8.1:chromium", "8.1:firefox"])

        rc, _err, out = _run_full(_e2e(rep, m, cfg, "--versions", "9.1,8.1"),
                                  E2EChild(lambda v, e: (skip, 0) if v == "9.1"
                                           else (_child_payload(v, e, kind="fail"), 3)))
        ok &= check("anak skipped + rekaman fail -> ran, exit 3",
                    rc == 3 and _line(out)["e2e_status"] == "ran" and _line(out)["reason"] is None)
    return ok


def test_e2e_completion_order():
    """Rekaman di-append begitu anak di-reap, dalam URUTAN SELESAI (bukan urutan --cells)."""
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        seen = {}

        def hook(ver):
            if ver == "8.1":  # anak lambat: saat ia selesai, 9.1 (cepat) sudah harus ter-append
                seen["9.1"] = len(_hist(rep, "9.1", "chromium"))
        fake = E2EChild(delay={"8.1": 0.6}, hook=hook)
        rc, _err, out = _run_full(_e2e(rep, m, cfg, "--cells", "8.1:chromium,9.1:chromium",
                                       more=["--jobs", "2"]), fake)
        ok &= check("anak cepat di-append SEBELUM anak lambat selesai", seen.get("9.1") == 1)
        ok &= check("appended mengikuti urutan selesai",
                    rc == 0 and _line(out)["appended"] == ["9.1:chromium", "8.1:chromium"])
    return ok


def test_e2e_tag_resolution():
    """image_tag rekaman tanpa output anak: --tag-map passthrough > psm_flashlight_tag_map >
    default; --extra-tag-map menambah di atas keduanya."""
    ok = True
    cases = (
        ("default skrip", {}, [], "9.1.4-nginx"),
        ("config psm_flashlight_tag_map", {"psm_flashlight_tag_map": "9.1=9.1.9"}, [], "9.1.9"),
        ("--tag-map passthrough mengalahkan config", {"psm_flashlight_tag_map": "9.1=9.1.9"},
         ["--tag-map", "9.1=9.1.7"], "9.1.7"),
        ("--tag-map= bentuk sama", {}, ["--tag-map=9.1=9.1.6"], "9.1.6"),
        ("--extra-tag-map di atas config", {"psm_flashlight_tag_map": "9.1=9.1.9,8.1=8.1.1"},
         ["--extra-tag-map", "9.1=9.1.8"], "9.1.8"),
        ("--extra-tag-map tak menyentuh versi lain", {"psm_flashlight_tag_map": "9.1=9.1.9"},
         ["--extra-tag-map", "8.1=8.1.8"], "9.1.9"),
    )
    for name, more_cfg, extra, want in cases:
        with tempfile.TemporaryDirectory() as tmp:
            rep, m = _e2e_env(tmp)
            cfg = _cfg(tmp, **more_cfg)
            fake = E2EChild(lambda v, e: (None, 1))
            _run_full(_e2e(rep, m, cfg, "--cells", "9.1:chromium", extra=extra), fake)
            got = [r["image_tag"] for r in _hist(rep, "9.1", "chromium")]
            ok &= check(f"tag: {name} -> {want}", got == [want])
            ok &= check(f"tag: {name}: passthrough tag diteruskan ke anak apa adanya",
                        all(x in fake.cmds[0] for x in extra))
    return ok


def test_e2e_screenshots_line():
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        shots = str(Path(rep) / "e2e-shots")
        fake = E2EChild()
        rc, err, out = _run_full(_e2e(rep, m, cfg, "--versions", "9.1,8.1",
                                      extra=["--screenshot-dir", shots]), fake)
        got = fake.arg("--screenshot-dir")
        stamped = re.search(r"^screenshots: (\S+)$", err, re.M)
        ok &= check("stderr: 'screenshots: <folder run berstempel>'",
                    rc == 0 and bool(stamped) and stamped.group(1) == got[0]
                    and Path(got[0]).parent == Path(shots))
        ok &= check("semua anak menerima folder berstempel yang SAMA", len(set(got)) == 1)
        ok &= check("baris output tetap berbentuk kontrak",
                    set(_line(out)) == {"e2e_status", "reason", "appended", "source_fingerprint"})
    return ok


def test_e2e_append_error():
    """Error OS saat append -> exit 2 menyebut path, SESUDAH anak yang sedang jalan selesai."""
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        blocker = PL.history_path(rep, "mymod", "9.1", "chromium")
        Path(blocker).mkdir()  # path histori berupa folder -> open() gagal
        fake = E2EChild(delay={"8.1": 0.3})
        rc, err, out = _run_full(_e2e(rep, m, cfg, "--versions", "9.1,8.1",
                                      more=["--jobs", "2"]), fake)
        ok &= check("append gagal -> exit 2 menyebut path", rc == 2 and str(blocker) in err)
        ok &= check("append gagal: sel lain & anak yang sedang jalan tetap di-append",
                    len(_hist(rep, "9.1", "firefox")) == 1 and len(_hist(rep, "8.1", "chromium")) == 1
                    and len(_hist(rep, "8.1", "firefox")) == 1)
        ok &= check("append gagal: TANPA baris output (galat lingkungan, bukan exit 2 anak "
                    "yang mengakhiri loop E2E)", out.strip() == "")
    return ok


def test_e2e_merge_only_view():
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp, versions="8.1,9.1", browsers="chromium,firefox")
        hp = PL.history_path(rep, "mymod", "9.1", "chromium")
        old = {"version": "9.1", "browser": "chromium", "started_at": _iso(0), "state": "fail"}
        new = {"version": "9.1", "browser": "chromium", "started_at": _iso(-60), "state": "pass"}
        PL.append_record(hp, old)
        PL.append_record(hp, new)
        with open(hp, "a", encoding="utf-8") as f:
            f.write("{rusak\n")
        legacy = Path(rep) / "mymod-e2e.json"
        legacy.write_text('{"module": "mymod", "pass": true, "versions": {}}', encoding="utf-8")
        fake = E2EChild()
        rc, err, out = _run_full(["--layer", "e2e", "--module", m, "--reports-dir", rep,
                                  "--config", cfg, "--merge-only", "--jobs", "7"], fake)
        view = json.loads(legacy.read_text()) if legacy.is_file() else {}
        ok &= check("merge-only e2e: exit 0, tak spawn, --jobs diabaikan",
                    rc == 0 and fake.cmds == [] and out.strip() == "")
        ok &= check("merge-only e2e: tampilan menimpa file legacy dgn {module, view, cells}",
                    set(view) == {"module", "view", "cells"} and view["view"] is True
                    and view["module"] == "mymod")
        ok &= check("merge-only e2e: tiap sel terkonfigurasi ada; tanpa rekaman valid = null",
                    set(view.get("cells", {})) == {"8.1", "9.1"}
                    and view["cells"]["8.1"] == {"chromium": None, "firefox": None}
                    and view["cells"]["9.1"]["firefox"] is None)
        ok &= check("merge-only e2e: sel = rekaman valid TERBARU (urutan append, bukan started_at)",
                    view.get("cells", {}).get("9.1", {}).get("chromium") == new)
        ok &= check("merge-only e2e: tak menulis histori", len(list(Path(rep).glob("*.jsonl"))) == 1)
        for name, more in (("--versions", ["--versions", "9.1"]),
                           ("--cells", ["--cells", "9.1:chromium"]),
                           ("--session", ["--session", SESSION]),
                           ("passthrough", ["--", "--tag-map", "x"])):
            rc2, err2, _o = _run_full(["--layer", "e2e", "--module", m, "--reports-dir", rep,
                                       "--config", cfg, "--merge-only", *more], E2EChild())
            ok &= check(f"merge-only e2e + {name} -> exit 2", rc2 == 2 and "merge-only" in err2)
        rc3, _e, _o = _run_full(["--layer", "e2e", "--module", m, "--reports-dir", rep,
                                 "--config", cfg, "--merge-only", "--per-version"], E2EChild())
        ok &= check("merge-only e2e + --per-version -> exit 2", rc3 == 2)
        bad = _cfg(tmp, browsers="webkitx", name="bad.json")
        rc4, _e, _o = _run_full(["--layer", "e2e", "--module", m, "--reports-dir", rep,
                                 "--config", bad, "--merge-only"], E2EChild())
        ok &= check("merge-only e2e: config tak sah -> exit 2", rc4 == 2)
        rc5, _e, _o = _run_full(["--layer", "e2e", "--module", m, "--reports-dir",
                                 str(Path(tmp) / "tak-ada"), "--config", cfg, "--merge-only"],
                                E2EChild())
        ok &= check("merge-only e2e: tulis gagal -> exit 2", rc5 == 2)
    return ok


def main():
    ok = True
    for name, fn in (("test_pure", test_pure),
                     ("test_review_patches", test_review_patches),
                     ("test_require_config", test_require_config),
                     ("test_execute_and_collect", test_execute_and_collect),
                     ("test_cli_gates", test_cli_gates),
                     ("test_output_is_derived", test_output_is_derived),
                     ("test_cli_happy_and_degrade", test_cli_happy_and_degrade),
                     ("test_freshness_stamp", test_freshness_stamp),
                     ("test_merge_rules", test_merge_rules),
                     ("test_scalar_conflict", test_scalar_conflict),
                     ("test_shot_dirs_survive_separate_invocations",
                      test_shot_dirs_survive_separate_invocations),
                     ("test_per_version_persist", test_per_version_persist),
                     ("test_merge_only", test_merge_only),
                     ("test_modes_exclusive_and_passthrough", test_modes_exclusive_and_passthrough),
                     ("test_consumed_by_aggregate", test_consumed_by_aggregate),
                     ("test_e2e_input_errors", test_e2e_input_errors),
                     ("test_reserved_on_other_layers", test_reserved_on_other_layers),
                     ("test_e2e_ac3", test_e2e_ac3),
                     ("test_e2e_record_fields", test_e2e_record_fields),
                     ("test_e2e_crash_and_shape", test_e2e_crash_and_shape),
                     ("test_e2e_install_boot_failure", test_e2e_install_boot_failure),
                     ("test_e2e_probe_drop_and_fail", test_e2e_probe_drop_and_fail),
                     ("test_e2e_child_exit2", test_e2e_child_exit2),
                     ("test_e2e_stopped", test_e2e_stopped),
                     ("test_e2e_skipped", test_e2e_skipped),
                     ("test_e2e_completion_order", test_e2e_completion_order),
                     ("test_e2e_tag_resolution", test_e2e_tag_resolution),
                     ("test_e2e_screenshots_line", test_e2e_screenshots_line),
                     ("test_e2e_append_error", test_e2e_append_error),
                     ("test_e2e_merge_only_view", test_e2e_merge_only_view),
                     ("test_help_prints_docstring", test_help_prints_docstring)):
        print(f"{name}:")
        ok &= fn()
    print()
    print("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
