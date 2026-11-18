#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Unit test untuk ps-removed-files.py — inventaris file sisa untuk skrip upgrade pembersih.

Kontrak: path yang ada di versi lama tapi tak ada di versi kini = "dibuang"; md5 memuat
SETIAP versi historis path itu (skrip upgrade hanya menghapus file yang isinya persis rilis
lama); artefak kerja tak pernah masuk; module di SUBFOLDER repo tetap benar (pathspec git
relatif-cwd vs `<sha>:<path>` relatif-root). Jalankan: uv run scripts/tests/test-ps-removed-files.py
"""
import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

MOD_PATH = Path(__file__).resolve().parent.parent / "ps-removed-files.py"
spec = importlib.util.spec_from_file_location("ps_removed_files", MOD_PATH)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}: {name}")
    return cond


def md5(text):
    return hashlib.md5(text.encode()).hexdigest()


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def sh(cwd, *args):
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


def by_path(result):
    return {i["path"]: i for i in result["removed"]}


def main():
    ok = True
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)

        # --- repo git, module di SUBFOLDER (bentuk repo pengiriman/modules/mycarrier_rj)
        repo = root / "repo"
        mdir = repo / "modules" / "mymod"
        sh(root, "init", "-q", "repo")
        sh(repo, "config", "user.email", "t@t")
        sh(repo, "config", "user.name", "t")
        write(mdir / "mymod.php", "<?php class MyMod { function __construct() { $this->version = '1.0.0'; } }")
        write(mdir / "controllers/front/address.php", "v1")
        write(mdir / "override/classes/Cart.php", "<?php class Cart extends CartCore {}")
        write(mdir / "views/js/old.js", "js")
        write(mdir / ".psm-cross-plan.md", "rencana")
        sh(repo, "add", "-A")
        sh(repo, "commit", "-q", "-m", "v1")
        write(mdir / "controllers/front/address.php", "v1.1")   # versi historis kedua
        sh(repo, "add", "-A")
        sh(repo, "commit", "-q", "-m", "v1.1")
        sh(repo, "tag", "old")

        # porting: buang 3 file, ganti nama satu, bump versi
        (mdir / "controllers/front/address.php").unlink()
        (mdir / "override/classes/Cart.php").unlink()
        (mdir / "views/js/old.js").unlink()
        write(mdir / "mymod.php", "<?php class MyMod { function __construct() { $this->version = '2.0.0'; } }")
        write(mdir / "upgrade/upgrade-1.5.0.php", "<?php")

        r = mod.build(mdir.resolve(), base_ref="old")
        got = by_path(r)
        ok &= check("tiga file dibuang terdeteksi (module di subfolder repo)",
                    set(got) == {"controllers/front/address.php", "override/classes/Cart.php",
                                 "views/js/old.js"})
        ok &= check("artefak kerja (.psm-cross-plan.md) tak dianggap file sisa",
                    ".psm-cross-plan.md" not in got)
        addr = got.get("controllers/front/address.php", {})
        ok &= check("md5 memuat KEDUA versi historis front controller",
                    sorted(addr.get("md5", [])) == sorted([md5("v1"), md5("v1.1")]))
        ok &= check("kategori front_controller", addr.get("category") == "front_controller")
        cart = got.get("override/classes/Cart.php", {})
        ok &= check("override punya override_class = Cart",
                    cart.get("category") == "override" and cart.get("override_class") == "Cart")
        ok &= check("asset terkategori", got.get("views/js/old.js", {}).get("category") == "asset")
        ok &= check("versi module kini terbaca dari file utama", r["module_version"] == "2.0.0")
        ok &= check("upgrade yang sudah ada terdaftar", r["existing_upgrade_versions"] == ["1.5.0"])
        ok &= check("counts konsisten", sum(r["counts"].values()) == len(r["removed"]))

        # --- --old-dir (folder _backup, bukan git) digabung dengan git
        old = root / "backup-1x"
        write(old / "controllers/front/address.php", "edit-tangan-rilis-zip")
        write(old / "classes/Legacy.php", "<?php")
        write(old / "mymod.php", "x")  # masih ada di versi kini -> bukan sisa
        r2 = mod.build(mdir.resolve(), base_ref="old", old_dirs=[old.resolve()])
        got2 = by_path(r2)
        ok &= check("--old-dir menambah path yang tak ada di git", "classes/Legacy.php" in got2)
        ok &= check("file yang masih ada di versi kini bukan sisa", "mymod.php" not in got2)
        a2 = got2["controllers/front/address.php"]
        ok &= check("md5 dari git & --old-dir digabung tanpa duplikat",
                    sorted(a2["md5"]) == sorted([md5("v1"), md5("v1.1"), md5("edit-tangan-rilis-zip")]))
        ok &= check("sumber dicatat dari keduanya", len(a2["sources"]) == 2)

        # --- --git-history: semua path yang PERNAH dihapus, tanpa tag rilis lama.
        #     Kasus mycarrier_rj: porting sudah di-commit, pindai statis bersih, tapi file
        #     yang dibuang di commit lampau tetap jadi sisa di toko yang memasang rilis lama.
        sh(repo, "add", "-A")
        sh(repo, "commit", "-q", "-m", "porting")
        write(mdir / "tests/e2e/old.json", "{}")
        sh(repo, "add", "-A")
        sh(repo, "commit", "-q", "-m", "spec")
        (mdir / "tests/e2e/old.json").unlink()
        sh(repo, "add", "-A")
        sh(repo, "commit", "-q", "-m", "hapus spec")
        r4 = mod.build(mdir.resolve(), git_history=True)
        got4 = by_path(r4)
        ok &= check("--git-history menemukan path yang dihapus di commit lampau",
                    {"controllers/front/address.php", "override/classes/Cart.php",
                     "views/js/old.js"} <= set(got4))
        ok &= check("--git-history: md5 semua versi historis",
                    sorted(got4["controllers/front/address.php"]["md5"]) == sorted([md5("v1"), md5("v1.1")]))
        ok &= check("tests/ berkategori dev", got4.get("tests/e2e/old.json", {}).get("category") == "dev")
        ok &= check("path yang belum disebut skrip upgrade -> covered_by kosong, terhitung uncovered",
                    got4["views/js/old.js"]["covered_by"] == [] and r4["uncovered"] == len(r4["removed"]))
        write(mdir / "upgrade/upgrade-2.0.0.php",
              "<?php $files = array('controllers/front/address.php' => array());")
        r5 = mod.build(mdir.resolve(), git_history=True)
        ok &= check("skrip upgrade yang menyebut path -> covered_by berisi versinya",
                    by_path(r5)["controllers/front/address.php"]["covered_by"] == ["2.0.0"])
        ok &= check("uncovered berkurang satu", r5["uncovered"] == r4["uncovered"] - 1)
        ok &= check("--git-history di luar repo git -> exit 2",
                    mod.main([str(root / "backup-1x"), "--git-history"]) == 2)

        # --- tanpa perubahan -> removed kosong, exit 0
        same = root / "same"
        write(same / "same.php", "<?php")
        old_same = root / "same-old"
        write(old_same / "same.php", "<?php")
        r3 = mod.build(same.resolve(), old_dirs=[old_same.resolve()])
        ok &= check("tak ada file dibuang -> removed kosong", r3["removed"] == [] and r3["counts"] == {})

        # --- error input -> exit 2
        ok &= check("tanpa sumber versi lama -> exit 2", mod.main([str(mdir)]) == 2)
        ok &= check("module-path bukan folder -> exit 2",
                    mod.main([str(root / "nope"), "--old-dir", str(old)]) == 2)
        ok &= check("--old-dir == module-path -> exit 2",
                    mod.main([str(mdir), "--old-dir", str(mdir)]) == 2)
        ok &= check("ref git tak dikenal -> exit 2",
                    mod.main([str(mdir), "--base-ref", "tidak-ada"]) == 2)
        ok &= check("--base-ref di luar repo git -> exit 2",
                    mod.main([str(same), "--base-ref", "HEAD"]) == 2)

        # --- CLI menulis JSON valid ke -o
        outf = root / "out.json"
        ok &= check("CLI exit 0", mod.main([str(mdir), "--base-ref", "old", "-o", str(outf)]) == 0)
        ok &= check("output JSON terbaca", json.loads(outf.read_text())["module"] == "mymod")

    print("\n" + ("SEMUA TEST LOLOS" if ok else "ADA TEST GAGAL"))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
