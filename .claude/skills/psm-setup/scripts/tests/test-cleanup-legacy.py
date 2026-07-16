#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# dependencies = []
# ///
"""Unit test untuk cleanup-legacy.py — deteksi skill, verifikasi aman, hapus dir.

Jalankan: uv run scripts/tests/test-cleanup-legacy.py
Exit 0 = semua lolos, 1 = ada yang gagal.
"""
import contextlib
import importlib.util
import io
import sys
import tempfile
from pathlib import Path

MOD_PATH = Path(__file__).resolve().parent.parent / "cleanup-legacy.py"
spec = importlib.util.spec_from_file_location("cleanup_legacy", MOD_PATH)
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

_fail = []


def check(name, cond):
    print(f"  {'ok' if cond else 'FAIL'}: {name}")
    if not cond:
        _fail.append(name)


def expect_exit(fn, code=1):
    try:
        with contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            fn()
        return False
    except SystemExit as e:
        return e.code == code


def _mkskill(base, name):
    d = Path(base) / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "SKILL.md").write_text("x", encoding="utf-8")
    return d


def test_find_skill_dirs():
    with tempfile.TemporaryDirectory() as td:
        _mkskill(td, "pkg/skill-a")
        _mkskill(td, "pkg/nested/skill-b")
        (Path(td) / "pkg" / "not-a-skill").mkdir(parents=True)
        found = mod.find_skill_dirs(str(Path(td) / "pkg"))
        check("temukan dir berisi SKILL.md", found == ["skill-a", "skill-b"])
        check("dir tanpa SKILL.md tak dihitung", "not-a-skill" not in found)
        check("base tak ada -> list kosong", mod.find_skill_dirs(str(Path(td) / "ghost")) == [])


def test_verify_skills_installed():
    with tempfile.TemporaryDirectory() as td:
        bmad = Path(td) / "_bmad"
        _mkskill(bmad, "psm/skill-a")          # legacy copy under module dir
        (bmad / "_config").mkdir(parents=True)  # dir tanpa skill (di-skip)
        skills = Path(td) / "skills"
        (skills / "skill-a").mkdir(parents=True)  # terinstal
        verified = mod.verify_skills_installed(str(bmad), ["psm", "_config"], str(skills))
        check("skill terinstal -> terverifikasi", verified == ["skill-a"])
        # skill TAK terinstal -> exit 1 (blokir penghapusan)
        skills_empty = Path(td) / "skills-empty"
        skills_empty.mkdir()
        check("skill hilang di installed -> exit 1",
              expect_exit(lambda: mod.verify_skills_installed(str(bmad), ["psm"], str(skills_empty)), 1))


def test_cleanup_directories():
    with tempfile.TemporaryDirectory() as td:
        bmad = Path(td) / "_bmad"
        (bmad / "psm").mkdir(parents=True)
        (bmad / "psm" / "f.txt").write_text("x", encoding="utf-8")
        (bmad / "psm" / "sub").mkdir()
        (bmad / "psm" / "sub" / "g.txt").write_text("y", encoding="utf-8")
        removed, not_found, total, preserved = mod.cleanup_directories(str(bmad), ["psm", "absent"])
        check("dir ada dihapus", removed == ["psm"] and not (bmad / "psm").exists())
        check("dir tak ada -> not_found", not_found == ["absent"])
        check("hitung file rekursif benar", total == 2)
        check("tanpa --preserve -> preserved kosong", preserved == [])


def test_cleanup_preserve():
    with tempfile.TemporaryDirectory() as td:
        bmad = Path(td) / "_bmad"
        mem = bmad / "psm" / "memory" / "tech"
        mem.mkdir(parents=True)
        (mem / "kb.md").write_text("seeded", encoding="utf-8")
        (bmad / "psm" / "pkg.txt").write_text("x", encoding="utf-8")
        (bmad / "psm" / "skills").mkdir()
        (bmad / "psm" / "skills" / "s.md").write_text("y", encoding="utf-8")
        (bmad / "core").mkdir()
        (bmad / "core" / "c.txt").write_text("z", encoding="utf-8")
        removed, _, total, preserved = mod.cleanup_directories(
            str(bmad), ["psm", "core"], preserve=["memory"]
        )
        check("subtree preserve selamat + isinya utuh",
              (mem / "kb.md").read_text(encoding="utf-8") == "seeded")
        check("sekitar preserve dihapus",
              not (bmad / "psm" / "pkg.txt").exists() and not (bmad / "psm" / "skills").exists())
        check("dir ber-preserve dilaporkan preserved, bukan removed",
              removed == ["core"] and len(preserved) == 1 and preserved[0]["directory"] == "psm")
        check("dir tanpa subtree preserve tetap dihapus penuh", not (bmad / "core").exists())
        check("hitung file terhapus benar (pkg+skills+core, kb selamat)", total == 3)
        # idempoten: run kedua — psm kini hanya berisi memory/
        _, _, total2, preserved2 = mod.cleanup_directories(
            str(bmad), ["psm", "core"], preserve=["memory"]
        )
        check("run kedua: preserve tetap, nol file terhapus",
              total2 == 0 and (mem / "kb.md").exists() and preserved2[0]["directory"] == "psm")


def test_reject_unresolved_paths():
    check("{project-root} di path arg -> exit 1",
          expect_exit(lambda: mod.reject_unresolved_paths([("--bmad-dir", "{project-root}/_bmad")]), 1))
    ok = True
    try:
        mod.reject_unresolved_paths([("--bmad-dir", "/abs/_bmad"), ("--skills-dir", None)])
    except SystemExit:
        ok = False
    check("path teresolusi/None -> tak exit", ok)


def main():
    for t in (test_find_skill_dirs, test_verify_skills_installed, test_cleanup_directories,
              test_cleanup_preserve, test_reject_unresolved_paths):
        print(f"{t.__name__}:")
        t()
    print("\n" + (f"{len(_fail)} GAGAL" if _fail else "SEMUA TEST LOLOS"))
    return 1 if _fail else 0


if __name__ == "__main__":
    sys.exit(main())
