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


def _no_cleanup():
    return {"mode": "cleanup-orphans", "status": "ran", "removed": [], "skipped": [], "errors": []}


def _run_full(argv, fake, docker=True, *, usage=None, cleanup=None, seed=None):
    """Jalankan main() dengan anak palsu & Docker di-stub. Return (exit_code, stderr, stdout).

    stderr ikut dikembalikan karena beberapa gerbang menghasilkan exit code yang SAMA lewat
    jalur berbeda (lapis serial vs lapis tak dikenal; gerbang bentuk vs raise merge), jadi
    exit code saja tak membuktikan gerbang yang dimaksud yang menyala. stdout memikul baris
    output JSON Lapis 4.

    Tak pernah menyentuh daemon Docker maupun registry `/tmp/psm-jobs` asli: hitungan slot
    (`usage`, default daemon kosong) dan `--cleanup-orphans` (`cleanup`) di-stub; JOB_REGISTRY
    dan LOCK_DIR menunjuk folder temp BARU per panggilan (`seed(registry_dir)` boleh mengisinya
    dulu); SLOT_POLL & PROGRESS_HEARTBEAT dikecilkan.
    """
    fl = mod.flashlight()
    saved = (mod._spawn, fl.docker_available, fl.daemon_slot_usage, fl.cleanup_orphans,
             fl.JOB_REGISTRY, fl.LOCK_DIR, mod.SLOT_POLL, fl.PROGRESS_HEARTBEAT)
    reg_tmp = tempfile.mkdtemp(prefix="psm-test-reg-")
    mod._spawn = fake
    fl.docker_available = lambda: docker
    fl.daemon_slot_usage = usage or (lambda: (0, [], None))
    fl.cleanup_orphans = cleanup or _no_cleanup
    fl.JOB_REGISTRY = Path(reg_tmp) / "psm-jobs"
    fl.LOCK_DIR = Path(reg_tmp) / "psm-locks"
    mod.SLOT_POLL = 0.02
    fl.PROGRESS_HEARTBEAT = 0.02
    if seed:
        seed(fl.JOB_REGISTRY)
    buf, out = io.StringIO(), io.StringIO()
    try:
        with contextlib.redirect_stderr(buf), contextlib.redirect_stdout(out):
            rc = mod.main(argv)
    finally:
        (mod._spawn, fl.docker_available, fl.daemon_slot_usage, fl.cleanup_orphans,
         fl.JOB_REGISTRY, fl.LOCK_DIR, mod.SLOT_POLL, fl.PROGRESS_HEARTBEAT) = saved
        import shutil as _sh0
        _sh0.rmtree(reg_tmp, ignore_errors=True)
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
        rc_j, _ = _run_main(["--layer", "flashlight", "--module", m, "--versions", "9.1",
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

        for layer, sess in (("flashlight", []), ("e2e", ["--session", SESSION, "--tier", "0"])):
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


def _e2e(rep, m, cfg, *scope, extra=(), session=SESSION, more=(), tier="0"):
    """argv run Lapis 4; `--tier` (wajib) default `0`, `tier=None` = tanpa `--tier`."""
    argv = ["--layer", "e2e", "--module", m, "--reports-dir", rep, *scope]
    if cfg:
        argv += ["--config", cfg]
    if session:
        argv += ["--session", session]
    if tier is not None:
        argv += ["--tier", tier]
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
        child = E2EChild(behave)
        rc, _err, out = _run_full(_e2e(rep, m, cfg, "--cells", "9.1:firefox",
                                       more=["--job-id", job]), child)
        recs = _hist(rep, "9.1", "firefox")
        r = recs[0] if recs else {}
        ok &= check("rekaman: kunci PERSIS Fields + boot_wall_clock + boot_log",
                    set(r) == RECORD_FIELDS and set(mod.RECORD_KEYS) == RECORD_FIELDS)
        ok &= check("rekaman: field runner (session, fingerprint, job_id, tier 0, keeper_boot null)",
                    r.get("session") == SESSION and r.get("job_id") == job
                    and r.get("source_fingerprint") == _line(out)["source_fingerprint"]
                    and type(r.get("tier")) is int and r.get("tier") == 0
                    and r.get("keeper_boot") is None)
        ok &= check("rekaman: state/conclusive/reason dari derive_state",
                    (r.get("state"), r.get("conclusive"), r.get("reason")) == ("pass", True, None))
        ok &= check("rekaman: field level-versi anak disalin apa adanya",
                    r.get("boot") == "cold" and r.get("boot_id") == "c0ffee000001"
                    and r.get("run_id") == child.arg("--run-id")[0]
                    and r.get("image_tag") == "9.1.4-nginx"
                    and r.get("browser_mode") == "sequential" and r.get("boot_wall_clock") == 42.5
                    and r.get("boot_phases") == {"pull": {"seconds": 1.0, "outcome": "ok"}}
                    and r.get("boot_log") is None and r.get("install") == {"ok": True}
                    and r.get("errors") == [] and r.get("scenario_notes") == [])
        ok &= check("rekaman: field sel anak (timestamp, phase_durations, scenario_set)",
                    r.get("started_at") == _iso(0) and r.get("finished_at") == _iso(7.25)
                    and (r.get("phase_durations") or {}).get("browser:firefox")
                    == {"seconds": 7.2, "outcome": "ok"}
                    and set(r["phase_durations"]) == {"browser:firefox", "wait-slots"}
                    and r["phase_durations"]["wait-slots"]["outcome"] == "ok"
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
        crash_child = E2EChild(lambda v, e: (None, 1))
        rc, _err, out = _run_full(_e2e(rep, m, cfg, "--versions", "9.1"), crash_child)
        recs = _hist(rep, "9.1", "chromium") + _hist(rep, "9.1", "firefox")
        ok &= check("crash: anak exit 1 tanpa output -> exit 1", rc == 1)
        ok &= check("crash: satu rekaman inconclusive/crash per sel diadmisi",
                    len(recs) == 2 and all((r["state"], r["conclusive"], r["reason"])
                                           == ("inconclusive", False, "crash") for r in recs))
        ok &= check("crash: run_id = RUN_ID klaim versi (--run-id anak), image_tag = tag ter-resolve",
                    all(r["run_id"] == crash_child.arg("--run-id")[0] != fl.RUN_ID
                        and r["image_tag"] == "9.1.4-nginx" for r in recs))
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
        drop_child = E2EChild(drop)
        rc, _err, out = _run_full(_e2e(rep, m, cfg, "--versions", "9.1"), drop_child)
        ff = (_hist(rep, "9.1", "firefox") or [{}])[0]
        ok &= check("probe drop: firefox -> browser-unavailable",
                    (ff.get("state"), ff.get("reason")) == ("inconclusive", "browser-unavailable"))
        ok &= check("probe drop: field level-versi anak ikut di rekaman browser-unavailable",
                    ff.get("boot") == "cold" and ff.get("run_id") == drop_child.arg("--run-id")[0]
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


def _log_lines(rep, ver):
    p = Path(rep) / f"mymod-e2e-{ver}.progress.log"
    return p.read_text(encoding="utf-8").splitlines() if p.is_file() else []


def _tok(line):
    """(TOKEN, sisa) satu baris log kemajuan: <iso> job= pid= run= v= TOKEN ..."""
    parts = line.split()
    return (parts[5] if len(parts) > 5 else None), " ".join(parts[6:])


def test_e2e_child_exit2():
    """I/O 'Child exit 2': sel antre -> not-run `input-error after <ver>`, versi itu nihil, exit 2."""
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        fake = E2EChild(lambda v, e: (None, 2) if v == "1.7.8" else (_child_payload(v, e), 0))
        rc, err, out = _run_full(_e2e(rep, m, cfg, "--cells",
                                      "1.7.8:chromium,8.1:chromium,9.1:firefox",
                                      more=["--slots", "1"]), fake)
        ok &= check("anak pertama exit 2 (--slots 1) -> tak ada anak lain dimulai",
                    [_ver_of(c) for c in fake.cmds] == ["1.7.8"])
        ok &= check("anak exit 2 -> versi itu sendiri tanpa rekaman, exit 2",
                    rc == 2 and _hist(rep, "1.7.8", "chromium") == [])
        nr = _hist(rep, "8.1", "chromium") + _hist(rep, "9.1", "firefox")
        ok &= check("anak exit 2 -> sel antre not-run `input-error after 1.7.8`",
                    len(nr) == 2 and all((r["state"], r["conclusive"], r["reason"])
                                         == ("not-run", False, "input-error after 1.7.8")
                                         for r in nr))
        ok &= check("anak exit 2 -> baris output ran, appended = sel not-run",
                    _line(out) == {"e2e_status": "ran", "reason": None,
                                   "appended": ["8.1:chromium", "9.1:firefox"],
                                   "source_fingerprint": PL.source_fingerprint(m, rep)})
        ok &= check("anak exit 2 -> log versi antre = satu baris DONE rc=not-run <reason>",
                    all([_tok(ln) for ln in _log_lines(rep, v)]
                        == [("DONE", "rc=not-run input-error after 1.7.8")]
                        for v in ("8.1", "9.1")))

    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        # 8.1 cepat & exit 2; 9.1 sedang jalan (lambat) tetap selesai & di-append; 1.7.8 antre.
        fake = E2EChild(lambda v, e: (None, 2) if v == "8.1" else (_child_payload(v, e), 0),
                        delay={"9.1": 0.4})
        rc, _err, out = _run_full(_e2e(rep, m, cfg, "--cells",
                                       "9.1:chromium,8.1:chromium,1.7.8:chromium",
                                       more=["--slots", "2"]), fake)
        ok &= check("exit 2: anak yang sedang jalan selesai & rekamannya di-append",
                    rc == 2 and len(_hist(rep, "9.1", "chromium")) == 1
                    and _line(out)["appended"] == ["1.7.8:chromium", "9.1:chromium"])
        ok &= check("exit 2: versi antre tak dimulai (not-run), versi exit 2 tanpa rekaman",
                    "1.7.8" not in [_ver_of(c) for c in fake.cmds]
                    and [r["reason"] for r in _hist(rep, "1.7.8", "chromium")]
                    == ["input-error after 8.1"]
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
                                       more=["--slots", "3"]), E2EChild(behave))
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
                                           more=["--slots", "1"]), fake)
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
                                           more=["--slots", "1"]), fake)
            ok &= check(f"stop ({label}): exit 143, tanpa baris output",
                        rc == 143 and out.strip() == "")
            ok &= check(f"stop ({label}): rekaman anak yang sudah selesai tetap",
                        len(_hist(rep, "8.1", "chromium")) == 1)
            ok &= check(f"stop ({label}): tak ada crash utk yang dihentikan / belum mulai",
                        _hist(rep, "9.1", "chromium") == [] and _hist(rep, "1.7.8", "chromium") == []
                        and [_ver_of(c) for c in fake.cmds] == ["8.1", "9.1"])
            t178 = [_tok(ln) for ln in _log_lines(rep, "1.7.8")]
            ok &= check(f"stop ({label}): versi antre: END wait-slots stopped lalu DONE rc=stopped",
                        any(t == "END" and d.startswith("wait-slots stopped") for t, d in t178)
                        and t178[-1] == ("DONE", "rc=stopped")
                        and [_tok(ln) for ln in _log_lines(rep, "9.1")][-1]
                        == ("DONE", "rc=stopped"))
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
                                       more=["--slots", "2"]), fake)
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
                                      more=["--slots", "2"]), fake)
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
                                  "--config", cfg, "--merge-only"], fake)
        view = json.loads(legacy.read_text()) if legacy.is_file() else {}
        ok &= check("merge-only e2e: exit 0, tak spawn",
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
        for name, more, needle in (("--jobs", ["--jobs", "7"], "--slots"),
                                   ("--slots", ["--slots", "2"], "--merge-only")):
            rc2, err2, _o = _run_full(["--layer", "e2e", "--module", m, "--reports-dir", rep,
                                       "--config", cfg, "--merge-only", *more], E2EChild())
            ok &= check(f"merge-only e2e + {name} -> exit 2 (menyebut {needle})",
                        rc2 == 2 and needle in err2)
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


# --- CAP-3: fail-fast, not-run, slot sedaemon (spec-psm-e2e-cap3-failfast-slots) -----------
FL = mod.flashlight()
THREE = "9.1:chromium,8.1:chromium,1.7.8:chromium"


def _spawned(fake):
    return [_ver_of(c) for c in fake.cmds]


def _seed_entry(reg, job, pid, claims, **over):
    """Entri registry run LAIN di folder registry temp (bukan /tmp/psm-jobs asli)."""
    d = Path(reg) / job
    d.mkdir(parents=True, exist_ok=True)
    entry = {"job": job, "pid": pid, "host": FL.OWNER_HOST, "boot": FL.OWNER_BOOT,
             "ns": FL.OWNER_NS, "slot_claims": claims}
    entry.update(over)
    path = d / f"{pid}.json"
    path.write_text(json.dumps(entry), encoding="utf-8")
    return path


def _usage(used=0, counted=(), err=None):
    return lambda: (used if err is None else None, list(counted) if err is None else [], err)


def test_e2e_failfast_ac():
    """I/O 'AC fail-fast' + AC 1: --slots 1, daemon kosong, 9.1 gagal -> 8.1 & 1.7.8 tak
    pernah di-spawn, not-run `fail-fast after 9.1:chromium`, log = satu DONE, exit 3."""
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        fake = E2EChild(lambda v, e: (_child_payload(v, e, kind="fail"), 3) if v == "9.1"
                        else (_child_payload(v, e), 0))
        rc, _err, out = _run_full(_e2e(rep, m, cfg, "--cells", THREE, more=["--slots", "1"]),
                                  fake, usage=_usage(0))
        ok &= check("AC fail-fast: exit 3, hanya 9.1 di-spawn", rc == 3 and _spawned(fake) == ["9.1"])
        ok &= check("AC 1: baris output `appended` memuat KETIGA sel",
                    _line(out)["e2e_status"] == "ran"
                    and sorted(_line(out)["appended"]) == sorted(THREE.split(",")))
        ok &= check("AC 1: tiap histori tepat satu rekaman",
                    all(len(_hist(rep, v, "chromium")) == 1 for v in ("9.1", "8.1", "1.7.8")))
        nr = [_hist(rep, v, "chromium")[0] for v in ("8.1", "1.7.8")]
        ok &= check("AC fail-fast: not-run, conclusive false, reason `fail-fast after 9.1:chromium`",
                    all((r["state"], r["conclusive"], r["reason"])
                        == ("not-run", False, "fail-fast after 9.1:chromium") for r in nr))
        ok &= check("not-run: wait-slots yang dibatalkan tercatat `cancelled` di phase_durations",
                    all(set(r["phase_durations"]) == {"wait-slots"}
                        and r["phase_durations"]["wait-slots"]["outcome"] == "cancelled"
                        for r in nr))
        ok &= check("not-run: run_id ps-run-layer, timestamp UTC valid, kunci rekaman persis",
                    all(r["run_id"] == FL.RUN_ID and PL.parse_utc(r["started_at"])
                        and PL.parse_utc(r["finished_at"]) and set(r) == RECORD_FIELDS
                        for r in nr))
        ok &= check("not-run tak pernah gate-grade",
                    not any(PL.is_gate_grade(r, PL.source_fingerprint(m, rep), r["image_tag"])
                            for r in nr))
        ok &= check("AC fail-fast: log 8.1 & 1.7.8 = satu baris DONE rc=not-run, tanpa bring-up",
                    all([_tok(ln) for ln in _log_lines(rep, v)]
                        == [("DONE", "rc=not-run fail-fast after 9.1:chromium")]
                        and "bring-up" not in "".join(_log_lines(rep, v))
                        for v in ("8.1", "1.7.8")))
        f91 = _hist(rep, "9.1", "chromium")[0]
        ok &= check("9.1: rekaman fail, wait-slots ok (diadmisi pass pertama) + browser:chromium",
                    f91["state"] == "fail"
                    and f91["phase_durations"]["wait-slots"]["outcome"] == "ok"
                    and "browser:chromium" in f91["phase_durations"])
    # Engine gagal PERTAMA menurut urutan psm_e2e_browsers yang menamai sel pemicu.
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp, browsers="firefox,chromium")
        fake = E2EChild(lambda v, e: (_child_payload(v, e, kind="fail"), 3) if v == "9.1"
                        else (_child_payload(v, e), 0))
        rc, _err, _out = _run_full(_e2e(rep, m, cfg, "--cells", "9.1:chromium+firefox,8.1:chromium",
                                        more=["--slots", "1"]), fake)
        ok &= check("dua engine gagal: sel pemicu = yang pertama di psm_e2e_browsers (firefox)",
                    rc == 3 and [r["reason"] for r in _hist(rep, "8.1", "chromium")]
                    == ["fail-fast after 9.1:firefox"])
    return ok


def test_e2e_fail_in_flight():
    """I/O 'Fail in flight': --slots 2, 9.1 gagal saat 8.1 jalan, 1.7.8 antre."""
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        fake = E2EChild(lambda v, e: (_child_payload(v, e, kind="fail"), 3) if v == "9.1"
                        else (_child_payload(v, e), 0), delay={"8.1": 0.5})
        rc, _err, out = _run_full(_e2e(rep, m, cfg, "--cells", THREE, more=["--slots", "2"]), fake)
        ok &= check("fail in flight: exit 3; 1.7.8 tak di-spawn", rc == 3
                    and sorted(_spawned(fake)) == ["8.1", "9.1"])
        ok &= check("fail in flight: 8.1 (sedang jalan) selesai & di-append (pass)",
                    [r["state"] for r in _hist(rep, "8.1", "chromium")] == ["pass"])
        ok &= check("fail in flight: 1.7.8 not-run, di-append SAAT pemicu (sebelum 8.1)",
                    [r["state"] for r in _hist(rep, "1.7.8", "chromium")] == ["not-run"]
                    and _line(out)["appended"] == ["9.1:chromium", "1.7.8:chromium", "8.1:chromium"])
    return ok


def test_e2e_no_failfast_cases():
    """I/O 'Exit 1 child' + exit-3 anak ber-output rusak (crash): tak ada fail-fast."""
    ok = True
    for label, behave, want_rc in (
            ("anak pertama inconclusive (exit 1)",
             lambda v, e: (_child_payload(v, e, kind="boot"), 1) if v == "9.1"
             else (_child_payload(v, e), 0), 1),
            ("anak exit 3 tapi output rusak -> crash",
             lambda v, e: ("{rusak", 3) if v == "9.1" else (_child_payload(v, e), 0), 1)):
        with tempfile.TemporaryDirectory() as tmp:
            rep, m = _e2e_env(tmp)
            cfg = _cfg(tmp)
            fake = E2EChild(behave)
            rc, _err, out = _run_full(_e2e(rep, m, cfg, "--cells", THREE, more=["--slots", "1"]),
                                      fake)
            recs = [r for v in ("9.1", "8.1", "1.7.8") for r in _hist(rep, v, "chromium")]
            ok &= check(f"{label}: tanpa fail-fast, sisa versi tetap jalan, exit {want_rc}",
                        rc == want_rc and _spawned(fake) == ["9.1", "8.1", "1.7.8"]
                        and not any(r["state"] == "not-run" for r in recs) and len(recs) == 3)
            if "crash" in label:
                ok &= check("exit 3 + output rusak -> rekaman crash (bukan fail)",
                            [r["reason"] for r in _hist(rep, "9.1", "chromium")] == ["crash"])
    return ok


def test_e2e_batch_fail_and_exit2():
    """`fail` (lebih awal di rencana) dan exit 2 di-reap dalam SATU batch -> alasan
    `fail-fast after <ver fail>:…` untuk sel antre, exit 2."""
    import threading
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        go = threading.Event()
        calls = {"n": 0}

        def behave(v, e):
            if v in ("9.1", "8.1"):
                go.wait(10)
            return {"9.1": (_child_payload(v, e, kind="fail"), 3), "8.1": (None, 2),
                    "1.7.8": (_child_payload(v, e), 0)}[v]

        def usage():
            calls["n"] += 1
            if calls["n"] == 2:  # hitungan pass kedua "menggantung": kedua anak selesai di sini
                go.set()
                time.sleep(0.4)
            return 0, [], None
        fake = E2EChild(behave)
        rc, _err, out = _run_full(_e2e(rep, m, cfg, "--cells", THREE, more=["--slots", "2"]),
                                  fake, usage=usage)
        ok &= check("satu batch: exit 2 (anak exit 2 tetap membuat run exit 2), baris ran",
                    rc == 2 and _line(out)["e2e_status"] == "ran")
        ok &= check("satu batch: urut rencana -> alasan = fail-fast after 9.1:chromium",
                    [r["reason"] for r in _hist(rep, "1.7.8", "chromium")]
                    == ["fail-fast after 9.1:chromium"] and "1.7.8" not in _spawned(fake))
        ok &= check("satu batch: 9.1 fail di-append, 8.1 (exit 2) tanpa rekaman",
                    [r["state"] for r in _hist(rep, "9.1", "chromium")] == ["fail"]
                    and _hist(rep, "8.1", "chromium") == [])
    return ok


def test_e2e_foreign_full():
    """I/O 'Foreign full': hitungan daemon = slot selamanya, `-- --startup-timeout 1` ->
    tiap sel no-slots, tak ada anak di-spawn, exit 1; `errors` menyebut isi cap."""
    ok = True
    counted = [{"job": "other-e2e-0900-beef", "host": "hostA", "run": "r1", "cost": 2},
               {"job": "orphan-e2e-0800-dead", "host": "hostB", "run": "r2", "cost": None}]
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        fake = E2EChild()
        t0 = time.monotonic()
        rc, err, out = _run_full(_e2e(rep, m, cfg, "--cells", "9.1:chromium+firefox,8.1:chromium",
                                      more=["--slots", "3"], extra=["--startup-timeout", "1"]),
                                 fake, usage=_usage(3, counted))
        took = time.monotonic() - t0
        recs = _hist(rep, "9.1", "chromium") + _hist(rep, "9.1", "firefox") + _hist(rep, "8.1", "chromium")
        want_err = ["other-e2e-0900-beef@hostA=2", "orphan-e2e-0800-dead@hostB=?"]
        ok &= check("foreign full: tak ada anak di-spawn, exit 1, ~startup-timeout ditunggu",
                    fake.cmds == [] and rc == 1 and took >= 0.9)
        ok &= check("foreign full: tiap sel no-slots (inconclusive, conclusive false)",
                    len(recs) == 3 and all((r["state"], r["conclusive"], r["reason"])
                                           == ("inconclusive", False, "no-slots") for r in recs))
        ok &= check("foreign full: errors = container terhitung <job>@<host>=<cost> (label rusak =?)",
                    all(r["errors"] == want_err for r in recs))
        ok &= check("foreign full: phase_durations = {wait-slots: no-slots}, run_id ps-run-layer",
                    all(set(r["phase_durations"]) == {"wait-slots"}
                        and r["phase_durations"]["wait-slots"]["outcome"] == "no-slots"
                        and r["run_id"] == FL.RUN_ID for r in recs))
        ok &= check("foreign full: baris output ran, appended ketiga sel",
                    _line(out)["e2e_status"] == "ran" and len(_line(out)["appended"]) == 3)
        for v in ("9.1", "8.1"):
            toks = [_tok(ln) for ln in _log_lines(rep, v)]
            ok &= check(f"foreign full: log {v} START wait-slots ... END no-slots + DONE rc=no-slots",
                        toks[0][0] == "START" and toks[-2][0] == "END"
                        and toks[-2][1].startswith("wait-slots no-slots")
                        and toks[-1] == ("DONE", "rc=no-slots"))
            alive = [d for t, d in toks if t == "ALIVE"]
            ok &= check(f"foreign full: ALIVE {v} menyebut isi cap, sisa budget & pass terakhir",
                        any("other-e2e-0900-beef@hostA=2, orphan-e2e-0800-dead@hostB=?" in d
                            and "budget" in d and "last pass" in d for d in alive))
    return ok


def test_e2e_own_queue():
    """I/O 'Own queue': --slots 1, dua versi, anak lebih lama dari startup timeout -> versi
    kedua menunggu melewatinya lalu jalan. + cleanup sekali, sesudah semua START wait-slots &
    sebelum hitungan pertama; klaim registry; tak ada SLOW."""
    ok = True
    saved = (FL.PROGRESS_SLOW_AFTER, dict(FL._PROGRESS))
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        calls = {"usage": 0, "cleanup": []}

        def usage():
            calls["usage"] += 1
            return 0, [], None

        def cleanup():
            calls["cleanup"].append({"usage_before": calls["usage"],
                                     "logs": {v: [_tok(ln) for ln in _log_lines(rep, v)]
                                              for v in ("9.1", "8.1")}})
            time.sleep(0.15)  # denyut ALIVE 'cleanup-orphans running' sempat ditulis
            return _no_cleanup()
        reg_claims = {}

        def hook(ver):
            entries = FL._registry_entries()
            own = [e for es in entries.values() for e in es if e.get("pid") == FL.OWNER_PID]
            reg_claims[ver] = [c["run"] for e in own for c in e.get("slot_claims") or []]
        fake = E2EChild(delay={"9.1": 1.5}, hook=hook)
        FL.PROGRESS_SLOW_AFTER = 0
        FL._PROGRESS["slow_after"] = 0.001
        try:
            rc, _err, out = _run_full(_e2e(rep, m, cfg, "--cells", "9.1:chromium,8.1:chromium",
                                           more=["--slots", "1"],
                                           extra=["--startup-timeout", "1"]),
                                      fake, usage=usage, cleanup=cleanup)
        finally:
            FL.PROGRESS_SLOW_AFTER = saved[0]
            FL._PROGRESS.clear()
            FL._PROGRESS.update(saved[1])
        r81 = (_hist(rep, "8.1", "chromium") or [{}])[0]
        ok &= check("own queue: kedua versi jalan berurutan, exit 0, tanpa no-slots",
                    rc == 0 and fake.done == ["9.1", "8.1"] and r81.get("state") == "pass")
        ws = (r81.get("phase_durations") or {}).get("wait-slots") or {}
        ok &= check("own queue: 8.1 menunggu MELEWATI startup timeout (wait-slots ok >= 1.2s)",
                    ws.get("outcome") == "ok" and ws.get("seconds", 0) >= 1.2)
        claims = dict(zip(_spawned(fake), fake.arg("--run-id")))
        ok &= check("klaim: registry memuat klaim versi itu saat spawn; klaim 9.1 dilepas saat reap",
                    reg_claims.get("9.1") == [claims["9.1"]] and reg_claims.get("8.1") == [claims["8.1"]])
        alive81 = [d for t, d in (_tok(ln) for ln in _log_lines(rep, "8.1")) if t == "ALIVE"]
        ok &= check("own queue: ALIVE wait-slots 8.1 menyebut klaim 9.1 & 'own queue'",
                    any("claim:" in d and claims["9.1"] in d and "own queue" in d for d in alive81))
        ok &= check("ALIVE wait-slots 'cleanup-orphans running' selama pembersihan",
                    any("cleanup-orphans running" in d for d in alive81))
        ok &= check("cleanup dipanggil TEPAT sekali, sebelum hitungan pertama",
                    len(calls["cleanup"]) == 1 and calls["cleanup"][0]["usage_before"] == 0)
        ok &= check("cleanup: saat itu log SETIAP versi antre sudah berisi START wait-slots",
                    bool(calls["cleanup"]) and all(
                        toks and toks[0][0] == "START" and toks[0][1].startswith("wait-slots")
                        for toks in calls["cleanup"][0]["logs"].values()))
        ok &= check("tak ada fase tunggu yang menulis SLOW (slow_after ~0)",
                    not any(_tok(ln)[0] == "SLOW" for v in ("9.1", "8.1")
                            for ln in _log_lines(rep, v)))
    return ok


def test_e2e_slots_suffice():
    """Slot cukup: cleanup tetap sekali & sebelum hitungan; tiap anak (dua engine) menerima
    --run-id <klaim> --progress-append --slot-cost 2 TANPA --sequential-browsers (CAP-7: biaya n
    paralel); log ditutup DONE bila anak tak menulisnya."""
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        calls = {"usage": 0, "cleanup": []}

        def usage():
            calls["usage"] += 1
            return 0, [], None

        def cleanup():
            calls["cleanup"].append((calls["usage"], {v: [_tok(ln) for ln in _log_lines(rep, v)]
                                                      for v in ("9.1", "8.1")}))
            return _no_cleanup()
        fake = E2EChild(lambda v, e: (_child_payload(v, e), 1 if v == "8.1" else 0))
        rc, err, _out = _run_full(_e2e(rep, m, cfg, "--versions", "9.1,8.1"), fake,
                                  usage=usage, cleanup=cleanup)
        ok &= check("slot cukup (default 6): kedua versi diadmisi pass pertama",
                    rc == 0 and sorted(_spawned(fake)) == ["8.1", "9.1"] and calls["usage"] == 1)
        ok &= check("slot cukup: cleanup sekali, sebelum hitungan, sesudah START wait-slots tiap log",
                    len(calls["cleanup"]) == 1 and calls["cleanup"][0][0] == 0
                    and all(t and t[0][0] == "START" for t in calls["cleanup"][0][1].values()))
        ok &= check("cleanup: ringkasannya di stderr", "cleanup-orphans otomatis" in err)
        ids = fake.arg("--run-id")
        ok &= check("tiap anak: --run-id <klaim hex12 unik> --progress-append --slot-cost 2, "
                    "tanpa --sequential-browsers",
                    all(re.fullmatch(r"[0-9a-f]{12}", i or "") for i in ids) and len(set(ids)) == 2
                    and fake.arg("--slot-cost") == ["2", "2"]
                    and all("--progress-append" in c and "--sequential-browsers" not in c
                            for c in fake.cmds))
        recs = _hist(rep, "9.1", "chromium") + _hist(rep, "8.1", "firefox")
        ok &= check("pass pertama: rekaman membawa wait-slots outcome ok",
                    all(r["phase_durations"]["wait-slots"]["outcome"] == "ok" for r in recs))
        t91 = [_tok(ln) for ln in _log_lines(rep, "9.1")]
        ok &= check("log: START wait-slots, END wait-slots ok, lalu DONE rc=<exit anak> (anak "
                    "tiruan tak menulis DONE)",
                    t91[0][0] == "START" and ("END", t91[1][1]) == t91[1]
                    and t91[1][1].startswith("wait-slots ok") and t91[-1] == ("DONE", "rc=0")
                    and [_tok(ln) for ln in _log_lines(rep, "8.1")][-1] == ("DONE", "rc=1"))
    return ok


def test_e2e_count_error():
    """I/O 'Count error': docker ps gagal = penuh -> no-slots sesudah batas (config 0 di sini),
    `errors` = `docker count failed: <ekor stderr>`."""
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp, psm_flashlight_startup_timeout="0")
        fake = E2EChild()
        msg = "Cannot connect to the Docker daemon.\n   Is the docker daemon running?"
        rc, _err, _out = _run_full(_e2e(rep, m, cfg, "--cells", "9.1:chromium"), fake,
                                   usage=_usage(err=msg))
        r = (_hist(rep, "9.1", "chromium") or [{}])[0]
        ok &= check("count error: tak spawn, no-slots, exit 1",
                    fake.cmds == [] and rc == 1 and r.get("reason") == "no-slots")
        ok &= check("count error: errors = 'docker count failed: ' + ekor (whitespace diringkas)",
                    r.get("errors") == ["docker count failed: Cannot connect to the Docker daemon. "
                                        "Is the docker daemon running?"])
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp, psm_flashlight_startup_timeout="0")
        rc, _err, _out = _run_full(_e2e(rep, m, cfg, "--cells", "9.1:chromium"), E2EChild(),
                                   usage=_usage(err="x" * 300 + "TAIL"))
        e = (_hist(rep, "9.1", "chromium") or [{}])[0].get("errors") or [""]
        ok &= check("count error: ekor dibatasi 200 karakter terakhir",
                    e[0] == "docker count failed: " + ("x" * 196 + "TAIL"))
    return ok


def test_e2e_claim_counting():
    """Klaim + container PS-nya = 1; klaim + container DB-nya saja (tak berlabel) = 1; klaim
    entri mati / asing = 0; cost klaim rusak = 1 (`=?`)."""
    import subprocess as sp
    ok = True
    job = "other-e2e-0900-beef"
    sleeper = sp.Popen(["sleep", "30"])
    dead = sp.Popen(["true"])
    dead.wait()
    try:
        cases = [
            ("klaim + container PS-nya (slot 1) -> penuh oleh container saja", "1",
             [{"run": "aaaaaaaaaaaa", "cost": 1}], sleeper.pid, {},
             [{"job": job, "host": "hostA", "run": "aaaaaaaaaaaa", "cost": 1}],
             ["other-e2e-0900-beef@hostA=1"]),
            ("klaim + container PS-nya (slot 2) -> = 1, masih muat", "2",
             [{"run": "aaaaaaaaaaaa", "cost": 1}], sleeper.pid, {},
             [{"job": job, "host": "hostA", "run": "aaaaaaaaaaaa", "cost": 1}], None),
            ("klaim tanpa container PS (DB tak berlabel) -> klaim = 1", "1",
             [{"run": "bbbbbbbbbbbb", "cost": 1}], sleeper.pid, {}, [],
             [f"claim:{job}/bbbbbbbbbbbb=1"]),
            ("klaim cost rusak -> dihitung 1, tampil =?", "1",
             [{"run": "cccccccccccc", "cost": "x"}], sleeper.pid, {}, [],
             [f"claim:{job}/cccccccccccc=?"]),
            ("klaim entri mati -> 0", "1", [{"run": "dddddddddddd", "cost": 1}], dead.pid, {},
             [], None),
            ("klaim entri host lain -> 0", "1", [{"run": "eeeeeeeeeeee", "cost": 1}],
             sleeper.pid, {"host": "host-lain"}, [], None),
        ]
        for label, slots, claims, pid, over, counted, want_err in cases:
            with tempfile.TemporaryDirectory() as tmp:
                rep, m = _e2e_env(tmp)
                cfg = _cfg(tmp)
                fake = E2EChild()
                used = sum(c["cost"] for c in counted)
                rc, _err, _out = _run_full(
                    _e2e(rep, m, cfg, "--cells", "9.1:chromium", more=["--slots", slots],
                         extra=["--startup-timeout", "0"]), fake,
                    usage=_usage(used, counted),
                    seed=lambda reg, c=claims, p=pid, o=over: _seed_entry(reg, job, p, c, **o))
                r = (_hist(rep, "9.1", "chromium") or [{}])[0]
                if want_err is None:
                    ok &= check(f"{label}: diadmisi", rc == 0 and _spawned(fake) == ["9.1"])
                else:
                    ok &= check(f"{label}: no-slots, errors {want_err}",
                                fake.cmds == [] and r.get("reason") == "no-slots"
                                and r.get("errors") == want_err)
    finally:
        sleeper.kill()
        sleeper.wait()
    return ok


def test_e2e_ac2_foreign_claim():
    """AC 2: --slots 1, --startup-timeout besar, entri registry `alive` milik run lain memegang
    satu klaim -> run menunggu di wait-slots (ALIVE menyebut claim:<job>/<run>=1) dan diadmisi
    begitu klaim itu dilepas."""
    import subprocess as sp
    import threading
    ok = True
    job, run = "other-e2e-0900-beef", "0123456789ab"
    sleeper = sp.Popen(["sleep", "60"])
    state = {}
    try:
        with tempfile.TemporaryDirectory() as tmp:
            rep, m = _e2e_env(tmp)
            cfg = _cfg(tmp)
            log = Path(rep) / "mymod-e2e-9.1.progress.log"

            def seed(reg):
                state["entry"] = _seed_entry(reg, job, sleeper.pid, [{"run": run, "cost": 1}])

            def watcher():
                deadline = time.monotonic() + 20
                while time.monotonic() < deadline:
                    text = log.read_text(encoding="utf-8") if log.is_file() else ""
                    if any(" ALIVE wait-slots " in ln and f"claim:{job}/{run}=1" in ln
                           for ln in text.splitlines()):
                        state["seen"] = True
                        break
                    time.sleep(0.02)
                time.sleep(0.2)  # tetap menunggu sebentar: tak boleh diadmisi selama klaim ada
                state["spawned_before_release"] = bool(fake.cmds)
                entry = state.get("entry")
                if entry is not None:
                    data = json.loads(entry.read_text(encoding="utf-8"))
                    data.pop("slot_claims", None)
                    entry.write_text(json.dumps(data), encoding="utf-8")
                state["released"] = time.monotonic()
            fake = E2EChild(hook=lambda v: state.setdefault("spawn_at", time.monotonic()))
            th = threading.Thread(target=watcher, daemon=True)
            th.start()
            rc, _err, _out = _run_full(_e2e(rep, m, cfg, "--cells", "9.1:chromium",
                                            more=["--slots", "1"],
                                            extra=["--startup-timeout", "600"]),
                                       fake, usage=_usage(0), seed=seed)
            th.join(timeout=30)
            ok &= check("AC 2: ALIVE wait-slots menyebut claim:<job>/<run>=1", state.get("seen") is True)
            ok &= check("AC 2: tak diadmisi selama klaim asing ada",
                        state.get("spawned_before_release") is False)
            ok &= check("AC 2: diadmisi begitu klaim dilepas, exit 0",
                        rc == 0 and _spawned(fake) == ["9.1"]
                        and state.get("spawn_at", 0) >= state.get("released", float("inf")))
    finally:
        sleeper.kill()
        sleeper.wait()
    return ok


def test_e2e_slots_input_errors():
    """I/O 'Bad input' (sisi runner) + flag RESERVED baru; kontrol positif sumber nilai slot."""
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        bad_x = _cfg(tmp, name="sx.json", psm_e2e_slots="x")
        bad_0 = _cfg(tmp, name="s0.json", psm_e2e_slots="0")
        cases = [
            ("--slots 0", _e2e(rep, m, cfg, "--versions", "9.1", more=["--slots", "0"]), None),
            ("--slots -1", _e2e(rep, m, cfg, "--versions", "9.1", more=["--slots=-1"]), None),
            ("--slots x", _e2e(rep, m, cfg, "--versions", "9.1", more=["--slots", "x"]), None),
            ("--slots 1.5", _e2e(rep, m, cfg, "--versions", "9.1", more=["--slots", "1.5"]), None),
            ("psm_e2e_slots 'x'", _e2e(rep, m, bad_x, "--versions", "9.1"), "psm_e2e_slots"),
            ("psm_e2e_slots '0'", _e2e(rep, m, bad_0, "--versions", "9.1"), "psm_e2e_slots"),
            ("psm_e2e_slots 'x' walau --slots 2", _e2e(rep, m, bad_x, "--versions", "9.1",
                                                        more=["--slots", "2"]), "psm_e2e_slots"),
            ("--jobs 2 --layer e2e", _e2e(rep, m, cfg, "--versions", "9.1", more=["--jobs", "2"]),
             "--slots"),
            ("--startup-timeout passthrough bukan bilangan",
             _e2e(rep, m, cfg, "--versions", "9.1", extra=["--startup-timeout", "abc"]),
             "--startup-timeout"),
            ("--slots dgn lapis flashlight", ["--layer", "flashlight", "--module", m,
                                              "--reports-dir", rep, "--versions", "9.1",
                                              "--slots", "2"], "--slots"),
        ]
        for flag in ("--run-id", "--slot-cost", "--progress-append", "--sequential-browsers"):
            cases.append((f"{flag} di passthrough", _e2e(rep, m, cfg, "--versions", "9.1",
                                                         extra=[flag, "1"]), flag))
        cases += [("--run-id=x di passthrough", _e2e(rep, m, cfg, "--versions", "9.1",
                                                     extra=["--run-id=0123456789ab"]), "--run-id"),
                  ("singkatan --slo di passthrough", _e2e(rep, m, cfg, "--versions", "9.1",
                                                          extra=["--slo", "2"]), "--slot-cost"),
                  ("singkatan --sequ di passthrough", _e2e(rep, m, cfg, "--versions", "9.1",
                                                           extra=["--sequ"]), "--sequential")]
        for name, argv, needle in cases:
            fake = E2EChild()
            rc, err, out = _run_full(argv, fake)
            ok &= check(f"input: {name} -> exit 2, tak spawn, tanpa baris output",
                        rc == 2 and fake.cmds == [] and out.strip() == ""
                        and (needle is None or needle in err))
        for flag in ("--run-id", "--slot-cost", "--progress-append", "--sequential-browsers"):
            ok &= check(f"RESERVED_PASSTHROUGH memuat {flag}", flag in mod.RESERVED_PASSTHROUGH)
        # Kontrol positif: sumber N = --slots > psm_e2e_slots > 6; kosong = default.
        for label, c, more, want in (
                ("default 6", cfg, [], "6 slot"),
                ("psm_e2e_slots kosong = default", _cfg(tmp, name="se.json", psm_e2e_slots=""),
                 [], "6 slot"),
                ("psm_e2e_slots '2'", _cfg(tmp, name="s2.json", psm_e2e_slots="2"), [], "2 slot"),
                ("--slots 4 menang atas psm_e2e_slots '2'", _cfg(tmp, name="s2b.json",
                                                                 psm_e2e_slots="2"),
                 ["--slots", "4"], "4 slot")):
            rc, err, _out = _run_full(_e2e(rep, m, c, "--cells", "9.1:chromium",
                                           more=[*more, "--verbose"]), E2EChild())
            ok &= check(f"slot: {label} -> {want}", rc == 0 and f"{want} sedaemon" in err)
    return ok


def test_e2e_child_not_run_kept():
    """Sel `not-run` dari anak (fail-fast antar-engine) dipertahankan tanpa derive_state."""
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)

        def behave(v, e):
            p = _child_payload(v, e, kind="fail")
            p["versions"][v]["cells"]["firefox"] = mod.e2e_module()._not_run_cell(
                f"fail-fast after {v}:chromium")
            return p, 3
        rc, _err, _out = _run_full(_e2e(rep, m, cfg, "--cells", "9.1:chromium+firefox"),
                                   E2EChild(behave))
        ff = (_hist(rep, "9.1", "firefox") or [{}])[0]
        ok &= check("anak not-run: state/conclusive/reason dipertahankan (bukan derive_state)",
                    (ff.get("state"), ff.get("conclusive"), ff.get("reason"))
                    == ("not-run", False, "fail-fast after 9.1:chromium")
                    and PL.derive_state(ff, "firefox")["state"] != "not-run")
        ok &= check("anak not-run: sisanya seperti sel yang tak di-drive (timestamp diisi, "
                    "phase_durations = wait-slots saja, field level-versi disalin)",
                    PL.parse_utc(ff.get("started_at")) and PL.parse_utc(ff.get("finished_at"))
                    and set(ff.get("phase_durations") or {}) == {"wait-slots"}
                    and ff.get("scenario_set") is None and ff.get("boot") == "cold")
        ok &= check("anak not-run: chromium fail, exit 3",
                    rc == 3 and _hist(rep, "9.1", "chromium")[0]["state"] == "fail")
    return ok


def test_e2e_own_exception():
    """ps-run-layer sendiri meledak (exception di pass admisi): tunggu terbuka berakhir
    `cancelled`, log antre ditutup DONE rc=crash, lalu exception dilempar ulang."""
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)

        def boom():
            raise RuntimeError("hitungan meledak")
        raised = False
        try:
            _run_full(_e2e(rep, m, cfg, "--cells", "9.1:chromium"), E2EChild(), usage=boom)
        except RuntimeError:
            raised = True
        toks = [_tok(ln) for ln in _log_lines(rep, "9.1")]
        ok &= check("exception sendiri: dilempar ulang; END wait-slots cancelled + DONE rc=crash",
                    raised and any(t == "END" and d.startswith("wait-slots cancelled")
                                   for t, d in toks) and toks[-1] == ("DONE", "rc=crash"))
    return ok


def test_e2e_append_error_cancels():
    """Galat append menghentikan admisi: tak ada not-run/no-slots menyusul, tunggu terbuka
    berakhir `cancelled`, log versi antre ditutup DONE rc=2."""
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        Path(PL.history_path(rep, "mymod", "9.1", "chromium")).mkdir()
        fake = E2EChild(lambda v, e: (_child_payload(v, e, kind="fail"), 3))
        rc, _err, out = _run_full(_e2e(rep, m, cfg, "--cells", "9.1:chromium,8.1:chromium",
                                       more=["--slots", "1"]), fake)
        toks = [_tok(ln) for ln in _log_lines(rep, "8.1")]
        ok &= check("append error: exit 2 tanpa baris output, 8.1 tak di-spawn & tanpa rekaman",
                    rc == 2 and out.strip() == "" and _spawned(fake) == ["9.1"]
                    and _hist(rep, "8.1", "chromium") == [])
        ok &= check("append error: wait-slots 8.1 END cancelled, lalu DONE rc=2",
                    any(t == "END" and d.startswith("wait-slots cancelled") for t, d in toks)
                    and toks[-1] == ("DONE", "rc=2"))
    return ok


# --- CAP-1: --tier & canary (spec-psm-e2e-cap1-tiered-gate > Design Notes > Runner) ---------
def test_e2e_tier_bad_input():
    """I/O 'Bad input' sisi runner: --tier absen/2, --tier dgn lapis lain atau --merge-only,
    canary di luar himpunan -> exit 2 sebelum spawn."""
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        webkit = _cfg(tmp, name="webkit.json", psm_e2e_canary="9.1:webkit")
        webkit_off = _cfg(tmp, name="webkit-off.json", psm_e2e_canary="9.1:webkit",
                          psm_e2e_enabled=False)
        cases = [
            ("e2e tanpa --tier", _e2e(rep, m, cfg, "--versions", "9.1", tier=None), "--tier"),
            ("--tier 2", _e2e(rep, m, cfg, "--versions", "9.1", tier="2"), "--tier"),
            ("--tier x", _e2e(rep, m, cfg, "--cells", "9.1:chromium", tier="x"), "--tier"),
            ("--tier kosong", _e2e(rep, m, cfg, "--cells", "9.1:chromium", tier=""), "--tier"),
            ("--tier dgn lapis flashlight", ["--layer", "flashlight", "--module", m,
                                             "--reports-dir", rep, "--versions", "9.1",
                                             "--tier", "0"], "--tier"),
            ("--tier dgn lapis scenario", ["--layer", "scenario", "--module", m,
                                           "--reports-dir", rep, "--versions", "9.1",
                                           "--tier", "1"], "--tier"),
            ("--tier dgn --merge-only e2e", ["--layer", "e2e", "--module", m, "--reports-dir",
                                             rep, "--config", cfg, "--merge-only",
                                             "--tier", "0"], "--tier"),
            ("--tier dgn --merge-only flashlight", ["--layer", "flashlight", "--module", m,
                                                    "--reports-dir", rep, "--versions", "9.1",
                                                    "--merge-only", "--tier", "0"], "--tier"),
            ("canary 9.1:webkit tak terkonfigurasi", _e2e(rep, m, webkit, "--versions", "9.1"),
             "psm_e2e_canary"),
            ("canary 9.1:webkit walau psm_e2e_enabled false",
             _e2e(rep, m, webkit_off, "--cells", "9.1:chromium"), "psm_e2e_canary"),
        ]
        for raw in ("9.1", "9.1:chromium:x", "7.0:chromium", 91):
            c = _cfg(tmp, name=f"canary-{raw}.json".replace(":", "_"), psm_e2e_canary=raw)
            cases.append((f"canary {raw!r}", _e2e(rep, m, c, "--versions", "9.1"),
                          "psm_e2e_canary"))
        for name, argv, needle in cases:
            fake = E2EChild()
            rc, err, out = _run_full(argv, fake)
            ok &= check(f"input: {name} -> exit 2, tak spawn, tanpa baris output, menyebut {needle}",
                        rc == 2 and fake.cmds == [] and out.strip() == "" and needle in err)
        ok &= check("tak ada histori tertulis oleh error input --tier/canary",
                    not list(Path(rep).glob("*.jsonl")))
        # Kontrol positif: canary sah (bentuk longgar) dan tier 1 diterima.
        loose = _cfg(tmp, name="loose.json", psm_e2e_canary=" 8.1 : Firefox ")
        fake = E2EChild()
        rc, _err, _out = _run_full(_e2e(rep, m, loose, "--cells", "9.1:chromium", tier="1"), fake)
        ok &= check("kontrol: canary ' 8.1 : Firefox ' + --tier 1 -> exit 0, anak di-spawn",
                    rc == 0 and len(fake.cmds) == 1)
        ok &= check("kontrol: merge-only e2e tanpa --tier tetap sah",
                    _run_full(["--layer", "e2e", "--module", m, "--reports-dir", rep,
                               "--config", cfg, "--merge-only"], E2EChild())[0] == 0)
    return ok


def test_e2e_tier_stamped():
    """`tier` = bilangan bulat JSON di SETIAP jenis rekaman: hasil anak, crash,
    browser-unavailable, no-slots, not-run."""
    ok = True

    def tiers(rep, cells):
        recs = [r for v, b in cells for r in _hist(rep, v, b)]
        return recs, [r.get("tier") for r in recs]

    def is_int(vals, want):
        return bool(vals) and all(type(t) is int and t == want for t in vals)

    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        rc, _e, _o = _run_full(_e2e(rep, m, cfg, "--cells", "9.1:chromium", tier="1"), E2EChild())
        recs, ts = tiers(rep, [("9.1", "chromium")])
        ok &= check("tier: rekaman hasil anak (pass) -> tier 1 int",
                    rc == 0 and [r["state"] for r in recs] == ["pass"] and is_int(ts, 1))
        rc, _e, _o = _run_full(_e2e(rep, m, cfg, "--cells", "8.1:chromium+firefox"),
                               E2EChild(lambda v, e: (None, 1)))
        recs, ts = tiers(rep, [("8.1", "chromium"), ("8.1", "firefox")])
        ok &= check("tier: rekaman crash -> tier 0 int",
                    rc == 1 and [r["reason"] for r in recs] == ["crash", "crash"] and is_int(ts, 0))
        rc, _e, _o = _run_full(_e2e(rep, m, cfg, "--cells", "1.7.8:chromium+firefox", tier="1"),
                               E2EChild(lambda v, e: (_child_payload(v, ["chromium"],
                                                                     available=["chromium"]), 0)))
        recs, ts = tiers(rep, [("1.7.8", "firefox")])
        ok &= check("tier: rekaman browser-unavailable -> tier 1 int",
                    [r["reason"] for r in recs] == ["browser-unavailable"] and is_int(ts, 1))
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        fake = E2EChild()
        rc, _e, _o = _run_full(_e2e(rep, m, cfg, "--cells", "9.1:chromium", tier="1",
                                    more=["--slots", "1"], extra=["--startup-timeout", "0"]),
                               fake, usage=_usage(1, [{"job": "x-e2e-0900-beef", "host": "h",
                                                       "run": "r", "cost": 1}]))
        recs, ts = tiers(rep, [("9.1", "chromium")])
        ok &= check("tier: rekaman no-slots -> tier 1 int",
                    fake.cmds == [] and [r["reason"] for r in recs] == ["no-slots"]
                    and is_int(ts, 1))
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        fake = E2EChild(lambda v, e: (_child_payload(v, e, kind="fail"), 3) if v == "9.1"
                        else (_child_payload(v, e), 0))
        rc, _e, _o = _run_full(_e2e(rep, m, cfg, "--cells", THREE, tier="1",
                                    more=["--slots", "1"]), fake, usage=_usage(0))
        recs, ts = tiers(rep, [("9.1", "chromium"), ("8.1", "chromium"), ("1.7.8", "chromium")])
        ok &= check("tier: rekaman fail anak + not-run fail-fast -> tier 1 int",
                    rc == 3 and [r["state"] for r in recs] == ["fail", "not-run", "not-run"]
                    and is_int(ts, 1))
        line = PL.history_path(rep, "mymod", "8.1", "chromium").read_text().strip()
        ok &= check("tier: tertulis di baris histori sebagai angka JSON, bukan string",
                    '"tier": 1' in line or '"tier":1' in line)
    return ok


def test_e2e_tier_passthrough():
    """`--ti 30` sesudah `--` tetap sampai ke anak (= --timeout); `--tier`/`--tie` ditolak."""
    ok = True
    ok &= check("RESERVED_PASSTHROUGH memuat --tier", "--tier" in mod.RESERVED_PASSTHROUGH)
    ok &= check("reserved_in_passthrough: --ti lolos, --tie/--tier/--tier=1 tertangkap",
                mod.reserved_in_passthrough(["--ti", "30"]) == []
                and mod.reserved_in_passthrough(["--tie", "1"]) == ["--tier"]
                and mod.reserved_in_passthrough(["--tier", "1"]) == ["--tier"]
                and mod.reserved_in_passthrough(["--tier=1"]) == ["--tier"])
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        fake = E2EChild()
        rc, err, _out = _run_full(_e2e(rep, m, cfg, "--cells", "9.1:chromium",
                                       extra=["--ti", "30"]), fake)
        cmd = fake.cmds[0] if fake.cmds else []
        ok &= check("--ti 30 sesudah `--` -> exit 0, anak menerima `--ti 30` apa adanya",
                    rc == 0 and len(fake.cmds) == 1 and "--ti" in cmd
                    and cmd[cmd.index("--ti") + 1] == "30")
        for extra in (["--tier", "1"], ["--tie", "1"], ["--tier=0"]):
            fake = E2EChild()
            rc, err, out = _run_full(_e2e(rep, m, cfg, "--cells", "9.1:chromium", extra=extra),
                                     fake)
            ok &= check(f"{extra[0]} sesudah `--` -> exit 2, tak spawn, menyebut --tier",
                        rc == 2 and fake.cmds == [] and out.strip() == "" and "--tier" in err)
    # Argparse anak asli memetakan `--ti` ke `--timeout` (bukti singkatan itu memang milik anak).
    p = subprocess.run([sys.executable, str(SCRIPTS / "ps-e2e-run.py"), "/tidak/ada", "--ti",
                        "bukan-angka"], capture_output=True, text=True, timeout=60)
    ok &= check("anak ps-e2e-run: `--ti` diurai sebagai --timeout",
                p.returncode == 2 and "--timeout" in p.stderr)
    return ok


# --- CAP-7: browser paralel — admisi biaya n / biaya 1, state yang diset anak -------------
SIX = "9.1:chromium+firefox,8.1:chromium+firefox,1.7.8:chromium+firefox"


def _cost_of(fake):
    """{versi: (--slot-cost, ada --sequential-browsers?)} per anak yang di-spawn."""
    return {_ver_of(c): (c[c.index("--slot-cost") + 1] if "--slot-cost" in c else None,
                         "--sequential-browsers" in c) for c in fake.cmds}


def _seed_hist(rep, ver, browser, *reasons, corrupt_tail=False):
    """Histori sel berisi rekaman minimal (urutan = urutan append; terakhir = terbaru)."""
    path = PL.history_path(rep, "mymod", ver, browser)
    for i, reason in enumerate(reasons):
        PL.append_record(path, {"version": ver, "browser": browser, "started_at": _iso(i),
                                "state": "inconclusive" if reason else "pass",
                                "reason": reason})
    if corrupt_tail:
        with open(path, "a", encoding="utf-8") as f:
            f.write("{rusak\n")
    return path


def test_e2e_cap7_admission():
    """I/O 'Admission' & 'Admission short': biaya n paralel bila n slot bebas, else biaya 1
    `--sequential-browsers`; klaim slot membawa biaya yang sama; tak muat = tunggu."""
    ok = True
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        calls = {"n": 0}

        def usage():
            calls["n"] += 1
            return 0, [], None
        fake = E2EChild()
        rc, _err, _out = _run_full(_e2e(rep, m, cfg, "--cells", SIX, more=["--slots", "6"]),
                                   fake, usage=usage)
        ok &= check("Admission: --slots 6, hitungan 0 -> tiga anak di pass pertama, biaya 2 "
                    "masing-masing, tanpa --sequential-browsers",
                    rc == 0 and calls["n"] == 1 and _cost_of(fake)
                    == {v: ("2", False) for v in ("9.1", "8.1", "1.7.8")})
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        seen, claims = {}, {}
        fake = E2EChild(delay={"9.1": 0.3, "8.1": 0.3},
                        hook=lambda v: claims.setdefault(v, [
                            c for es in FL._registry_entries().values() for e in es
                            if e.get("pid") == FL.OWNER_PID for c in e.get("slot_claims") or []]))

        def spawn(cmd):
            seen[_ver_of(cmd)] = list(fake.done)  # anak yang sudah selesai saat ini di-spawn
            return fake(cmd)
        rc, err, _out = _run_full(_e2e(rep, m, cfg, "--cells", SIX, more=["--slots", "3"]),
                                  spawn, usage=_usage(0))
        cost = _cost_of(fake)
        ok &= check("Admission short: 9.1 biaya 2 paralel; 8.1 biaya 1 --sequential-browsers",
                    rc == 0 and cost.get("9.1") == ("2", False)
                    and cost.get("8.1") == ("1", True))
        ok &= check("Admission short: 1.7.8 menunggu (di-spawn baru sesudah anak lain di-reap)",
                    seen.get("9.1") == [] and seen.get("8.1") == [] and seen.get("1.7.8")
                    and _hist(rep, "1.7.8", "chromium")[0]["phase_durations"]["wait-slots"]
                    ["seconds"] > 0)
        ok &= check("Admission short: klaim slot di registry membawa biaya admisi (2 dan 1)",
                    sorted(c["cost"] for c in claims.get("9.1") or []) == [1, 2])
        ok &= check("Admission short: fallback sekuensial di-log menyebut versinya",
                    "8.1" in err and "--sequential-browsers" in err)
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        fake = E2EChild()
        rc, _err, _out = _run_full(_e2e(rep, m, cfg, "--cells", "9.1:chromium,8.1:firefox",
                                        more=["--slots", "6"]), fake, usage=_usage(0))
        ok &= check("satu engine: biaya 1, tanpa --sequential-browsers",
                    rc == 0 and _cost_of(fake) == {"9.1": ("1", False), "8.1": ("1", False)})
    return ok


def test_e2e_cap7_unconfirmed_history():
    """I/O 'Unconfirmed history': rekaman TERBARU satu sel terkonfigurasi ber-reason
    `parallel-unconfirmed` -> biaya 1 `--sequential-browsers`, berapa pun slot bebas."""
    ok = True
    for label, seed, want91, want81 in (
            ("8.1:firefox terbaru parallel-unconfirmed",
             lambda rep: _seed_hist(rep, "8.1", "firefox", None, "parallel-unconfirmed"),
             ("2", False), ("1", True)),
            ("parallel-unconfirmed LAMA, terbaru pass -> tak dipaksa",
             lambda rep: _seed_hist(rep, "8.1", "firefox", "parallel-unconfirmed", None),
             ("2", False), ("2", False)),
            ("sel terkonfigurasi di luar --cells (8.1:firefox) tetap memaksa 8.1",
             lambda rep: _seed_hist(rep, "8.1", "firefox", "parallel-unconfirmed"),
             ("2", False), ("1", True)),
            ("ekor histori rusak -> dipaksa sekuensial (rekaman terbaru tak diketahui)",
             lambda rep: _seed_hist(rep, "8.1", "chromium", None, corrupt_tail=True),
             ("2", False), ("1", True))):
        with tempfile.TemporaryDirectory() as tmp:
            rep, m = _e2e_env(tmp)
            cfg = _cfg(tmp, browsers="chromium,firefox,webkit")
            seed(rep)
            cells = ("9.1:chromium+firefox,8.1:chromium+webkit" if "di luar" in label
                     else "9.1:chromium+firefox,8.1:chromium+firefox")
            fake = E2EChild()
            rc, err, _out = _run_full(_e2e(rep, m, cfg, "--cells", cells, more=["--slots", "6"]),
                                      fake, usage=_usage(0))
            cost = _cost_of(fake)
            ok &= check(f"{label}: 9.1 {want91}, 8.1 {want81}",
                        rc == 0 and cost.get("9.1") == want91 and cost.get("8.1") == want81)
            if want81[1]:
                ok &= check(f"{label}: alasan pemaksaan di-log", "8.1" in err
                            and ("parallel-unconfirmed" in err or "rusak" in err))
    return ok


def test_e2e_cap7_child_set_states():
    """State yang DISET anak (`parallel-unconfirmed`, `sequential-reset`, `crash`) dipertahankan
    tanpa derive_state; `errors` sel ditambahkan SESUDAH `errors` level-versi, tak ke saudara."""
    ok = True
    v_err = ["catatan level-versi"]

    def behave_pu(v, e):
        p = _child_payload(v, e)
        vres = p["versions"][v]
        vres["errors"] = list(v_err)
        vres["browser_mode"] = "parallel"
        vres["cells"]["chromium"].update(
            state="inconclusive", conclusive=False, reason="parallel-unconfirmed",
            errors=["reset-db: exit 1"], findings=[],
            parallel_only=[{"scenario": "a", "action": "expect_text", "step": 3}])
        return p, 1

    def behave_sr(v, e):
        p = _child_payload(v, e)
        vres = p["versions"][v]
        vres["errors"] = list(v_err)
        e2e = mod.e2e_module()
        vres["cells"]["chromium"] = e2e._child_state(e2e._new_cell(), "crash")
        vres["cells"]["firefox"] = e2e._child_state(e2e._new_cell(), "sequential-reset",
                                                    ["reset-files: timeout"])
        return p, 1
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        rc, _err, _out = _run_full(_e2e(rep, m, cfg, "--cells", "9.1:chromium+firefox"),
                                   E2EChild(behave_pu), usage=_usage(0))
        ch = (_hist(rep, "9.1", "chromium") or [{}])[0]
        ff = (_hist(rep, "9.1", "firefox") or [{}])[0]
        ok &= check("parallel-unconfirmed: state/conclusive/reason dipertahankan (bukan "
                    "derive_state)",
                    (ch.get("state"), ch.get("conclusive"), ch.get("reason"))
                    == ("inconclusive", False, "parallel-unconfirmed")
                    and PL.derive_state(ch, "chromium")["reason"] != "parallel-unconfirmed")
        ok &= check("parallel-unconfirmed: errors = level-versi lalu level-sel; parallel_only "
                    "dibawa", ch.get("errors") == [*v_err, "reset-db: exit 1"]
                    and ch.get("parallel_only") == [{"scenario": "a", "action": "expect_text",
                                                     "step": 3}])
        ok &= check("saudara (firefox, state derive_state): errors = level-versi saja",
                    ff.get("reason") != "parallel-unconfirmed" and ff.get("errors") == v_err
                    and set(ff) == RECORD_FIELDS and set(ch) == RECORD_FIELDS)
        ok &= check("parallel-unconfirmed -> exit 1", rc == 1)
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        rc, _err, _out = _run_full(_e2e(rep, m, cfg, "--cells", "9.1:chromium+firefox"),
                                   E2EChild(behave_sr), usage=_usage(0))
        ch = (_hist(rep, "9.1", "chromium") or [{}])[0]
        ff = (_hist(rep, "9.1", "firefox") or [{}])[0]
        ok &= check("crash worker (diset anak): inconclusive/crash dipertahankan, errors tanpa "
                    "tambahan sel, timestamp diisi",
                    (ch.get("state"), ch.get("reason")) == ("inconclusive", "crash")
                    and ch.get("errors") == v_err and bool(PL.parse_utc(ch.get("started_at")))
                    and bool(PL.parse_utc(ch.get("finished_at"))))
        ok &= check("sequential-reset: dipertahankan, errors = level-versi + sub-fase sel",
                    (ff.get("state"), ff.get("conclusive"), ff.get("reason"))
                    == ("inconclusive", False, "sequential-reset")
                    and ff.get("errors") == [*v_err, "reset-files: timeout"])
        ok &= check("crash/sequential-reset -> exit 1", rc == 1)
    return ok


def test_e2e_cap7_engine_worker_reserved():
    """`--engine-worker` (mode internal anak) DILARANG di passthrough, singkatannya juga."""
    ok = check("RESERVED_PASSTHROUGH memuat --engine-worker",
               "--engine-worker" in mod.RESERVED_PASSTHROUGH)
    ok &= check("--engine-worker & singkatan --engine-w tertangkap",
                mod.reserved_in_passthrough(["--engine-worker"]) == ["--engine-worker"]
                and mod.reserved_in_passthrough(["--engine-w"]) == ["--engine-worker"])
    with tempfile.TemporaryDirectory() as tmp:
        rep, m = _e2e_env(tmp)
        cfg = _cfg(tmp)
        for extra in (["--engine-worker"], ["--engine-wo"]):
            fake = E2EChild()
            rc, err, out = _run_full(_e2e(rep, m, cfg, "--versions", "9.1", extra=extra), fake)
            ok &= check(f"{extra[0]} di passthrough -> exit 2, tak spawn, tanpa baris output",
                        rc == 2 and fake.cmds == [] and out.strip() == ""
                        and "--engine-worker" in err)
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
                     ("test_e2e_failfast_ac", test_e2e_failfast_ac),
                     ("test_e2e_fail_in_flight", test_e2e_fail_in_flight),
                     ("test_e2e_no_failfast_cases", test_e2e_no_failfast_cases),
                     ("test_e2e_batch_fail_and_exit2", test_e2e_batch_fail_and_exit2),
                     ("test_e2e_foreign_full", test_e2e_foreign_full),
                     ("test_e2e_own_queue", test_e2e_own_queue),
                     ("test_e2e_slots_suffice", test_e2e_slots_suffice),
                     ("test_e2e_count_error", test_e2e_count_error),
                     ("test_e2e_claim_counting", test_e2e_claim_counting),
                     ("test_e2e_ac2_foreign_claim", test_e2e_ac2_foreign_claim),
                     ("test_e2e_slots_input_errors", test_e2e_slots_input_errors),
                     ("test_e2e_child_not_run_kept", test_e2e_child_not_run_kept),
                     ("test_e2e_append_error_cancels", test_e2e_append_error_cancels),
                     ("test_e2e_own_exception", test_e2e_own_exception),
                     ("test_e2e_tier_bad_input", test_e2e_tier_bad_input),
                     ("test_e2e_tier_stamped", test_e2e_tier_stamped),
                     ("test_e2e_tier_passthrough", test_e2e_tier_passthrough),
                     ("test_e2e_cap7_admission", test_e2e_cap7_admission),
                     ("test_e2e_cap7_unconfirmed_history", test_e2e_cap7_unconfirmed_history),
                     ("test_e2e_cap7_child_set_states", test_e2e_cap7_child_set_states),
                     ("test_e2e_cap7_engine_worker_reserved",
                      test_e2e_cap7_engine_worker_reserved),
                     ("test_help_prints_docstring", test_help_prints_docstring)):
        print(f"{name}:")
        ok &= fn()
    print()
    print("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
