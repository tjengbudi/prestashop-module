#!/usr/bin/env python3
# /// script
# requires-python = ">=3.9"
# ///
"""Inventaris file yang DIBUANG dari module saat porting -> JSON untuk skrip upgrade pembersih.

Kenapa ada: deploy versi baru di atas instalasi lama (upload zip, rsync tanpa --delete,
salin folder) TIDAK menghapus file yang tak ada lagi di versi baru. File sisa itu tetap
hidup di toko: front controller lama masih bisa dirutekan lewat URL, override 1.x masih
terpasang di override/ root, dan semuanya memanggil API yang sudah dihapus core. psm-validate
tak pernah melihatnya karena selalu menguji instalasi BERSIH dari isi repo. Kasus nyata:
mycarrier_rj — repo bersih, server masih menjalankan controllers/front/AddressController.php
1.x dengan Tools::jsonEncode.

Skrip ini hanya menyusun FAKTA: path mana yang ada di versi lama tapi tak ada di versi kini,
kategorinya, dan md5 tiap versi historisnya (supaya skrip upgrade hanya menghapus file yang
isinya persis rilis lama — file yang diubah tangan merchant dilewati, bukan dihapus).
Merancang dan menulis skrip upgrade-nya tetap tugas orkestrator
(references/upgrade-cleanup.md).

Sumber versi lama (minimal satu, boleh digabung):
  --base-ref <ref>  ref git (tag/commit) versi lama; md5 diambil dari SEMUA versi historis
                    path itu yang bisa dijangkau dari ref tersebut.
  --git-history     semua path yang PERNAH dihapus di sejarah git module (dari HEAD) — tanpa
                    perlu tahu tag rilis lama; dipakai juga saat pindai statis sudah bersih.
  --old-dir <path>  folder rilis lama (zip yang diekstrak, folder _backup). Boleh berulang.

Tiap path membawa `covered_by` = skrip upgrade yang sudah menyebut path itu (heuristik teks),
dan `uncovered` = jumlah path yang belum disebut skrip upgrade mana pun.

Exit: 0 = inventaris tersusun (removed boleh kosong), 2 = error input.

Pemakaian:
  uv run scripts/ps-removed-files.py <module-path> --base-ref v1.4.0
  uv run scripts/ps-removed-files.py <module-path> --old-dir ../_backup/mymod-1.x -o removed.json
"""
import argparse
import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path, PurePosixPath

# Artefak kerja & metadata yang tak pernah dikapalkan ke toko — bukan "file sisa".
IGNORED_PARTS = {".git", "__pycache__", "node_modules", ".idea", ".vscode"}
IGNORED_NAMES = {".DS_Store", "Thumbs.db", ".psm-cross-plan.md", ".psm-develop-plan.md",
                 ".psm-develop-plan.json", ".memlog.md"}

# Folder pengembangan: biasanya tak dikapalkan, jadi tak pernah jadi sisa di toko. Tetap
# dilaporkan (bisa saja ikut ter-zip) tapi dengan kategori sendiri supaya tak membesarkan risiko.
DEV_DIRS = {"tests", ".github", ".gitlab", "_dev", "docs"}

ASSET_EXT = {".js", ".css", ".scss", ".map", ".png", ".jpg", ".jpeg", ".gif", ".svg",
             ".webp", ".ico", ".woff", ".woff2", ".ttf", ".eot"}
TEMPLATE_EXT = {".tpl", ".twig", ".html"}

VERSION_RE = re.compile(r"""\$this->version\s*=\s*['"]([^'"]+)['"]""")


def ignored(rel):
    p = PurePosixPath(rel)
    return p.name in IGNORED_NAMES or any(part in IGNORED_PARTS for part in p.parts)


def categorize(rel):
    """Kategori menentukan risiko & perlakuan di skrip upgrade (references/upgrade-cleanup.md)."""
    p = PurePosixPath(rel)
    parts = p.parts
    ext = p.suffix.lower()
    if parts[0] in DEV_DIRS:
        return "dev"
    if parts[0] == "override" and ext == ".php":
        return "override"
    if parts[:2] == ("controllers", "front") and ext == ".php":
        return "front_controller"
    if parts[:2] == ("controllers", "admin") and ext == ".php":
        return "admin_controller"
    if parts[0] == "upgrade":
        return "upgrade_script"
    if parts[0] == "vendor":
        return "vendor"
    if ext == ".php":
        return "php"
    if ext in TEMPLATE_EXT:
        return "template"
    if ext in ASSET_EXT:
        return "asset"
    return "other"


def md5_bytes(data):
    return hashlib.md5(data).hexdigest()


def list_dir(root):
    out = {}
    for f in root.rglob("*"):
        if f.is_file():
            rel = f.relative_to(root).as_posix()
            if not ignored(rel):
                out[rel] = f
    return out


def _git(args, cwd):
    cp = subprocess.run(["git", *args], cwd=cwd, capture_output=True)
    return cp.stdout if cp.returncode == 0 else None


def git(args, cwd):
    """stdout git sebagai teks, atau None bila gagal."""
    out = _git(args, cwd)
    return None if out is None else out.decode("utf-8", "replace")


def git_blob(args, cwd):
    """stdout git sebagai bytes mentah (isi file untuk md5), atau None bila gagal."""
    return _git(args, cwd)


def git_root(module):
    """(root repo, path module relatif ke root berakhiran '/' atau '') — atau None.

    Semua perintah git berikutnya dijalankan dari ROOT repo: pathspec rev-list/ls-tree
    relatif ke cwd, sedangkan `<sha>:<path>` relatif ke root — mencampur keduanya dari
    subfolder module membuat path menunjuk tempat yang salah tanpa error.
    """
    top = git(["rev-parse", "--show-toplevel"], module)
    if top is None:
        return None
    pre = git(["rev-parse", "--show-prefix"], module)
    return Path(top.strip()), (pre or "").strip()


def git_files_at(top, prefix, ref):
    out = git(["ls-tree", "-r", "--name-only", "-z", ref, "--", prefix or "."], top)
    if out is None:
        return None
    files = []
    for full in out.split("\0"):
        if not full:
            continue
        rel = full[len(prefix):] if prefix and full.startswith(prefix) else full
        if not ignored(rel):
            files.append(rel)
    return files


def git_hashes(top, prefix, ref, rel):
    """md5 tiap versi berbeda dari path itu sepanjang sejarah yang terjangkau dari ref."""
    full = prefix + rel
    revs = git(["rev-list", ref, "--", full], top)
    hashes = []
    for sha in (revs or "").split():
        blob = git_blob(["show", f"{sha}:{full}"], top)
        if blob is None:  # commit yang menghapus path itu
            continue
        h = md5_bytes(blob)
        if h not in hashes:
            hashes.append(h)
    return hashes


def module_version(module):
    main = module / f"{module.name}.php"
    if not main.is_file():
        return None
    m = VERSION_RE.search(main.read_text(encoding="utf-8", errors="replace"))
    return m.group(1) if m else None


def git_deleted_paths(top, prefix):
    """Path di bawah module yang PERNAH dihapus di sejarah git yang terjangkau dari HEAD."""
    out = git(["log", "HEAD", "--diff-filter=D", "--name-only", "--format=", "-z",
               "--", prefix or "."], top)
    paths = set()
    for full in (out or "").split("\0"):
        full = full.strip("\n")
        if not full:
            continue
        rel = full[len(prefix):] if prefix and full.startswith(prefix) else full
        if not ignored(rel):
            paths.add(rel)
    return paths


def upgrade_mentions(module):
    """{versi: isi} skrip upgrade yang ada — untuk menandai path yang sudah dibersihkan."""
    upgrade_dir = module / "upgrade"
    if not upgrade_dir.is_dir():
        return {}
    return {p.stem[len("upgrade-"):]: p.read_text(encoding="utf-8", errors="replace")
            for p in sorted(upgrade_dir.glob("upgrade-*.php"))}


def build(module, base_ref=None, old_dirs=(), git_history=False):
    current = set(list_dir(module))
    removed = {}  # rel -> list md5
    sources = {}  # rel -> list sumber

    def add(rel, hashes, source):
        bucket = removed.setdefault(rel, [])
        for h in hashes:
            if h not in bucket:
                bucket.append(h)
        sources.setdefault(rel, []).append(source)

    if base_ref or git_history:
        root = git_root(module)
        if root is None:
            raise ValueError(f"--base-ref/--git-history butuh module di dalam repo git: {module}")
        top, prefix = root

    if git_history:
        for rel in sorted(git_deleted_paths(top, prefix)):
            if rel not in current:
                add(rel, git_hashes(top, prefix, "HEAD", rel), "git:history")

    if base_ref:
        if git(["rev-parse", "--verify", "--quiet", f"{base_ref}^{{commit}}"], top) is None:
            raise ValueError(f"ref git tak dikenal: {base_ref}")
        files = git_files_at(top, prefix, base_ref)
        if files is None:
            raise ValueError(f"ref git tak terbaca: {base_ref}")
        for rel in files:
            if rel not in current:
                add(rel, git_hashes(top, prefix, base_ref, rel), f"git:{base_ref}")

    for od in old_dirs:
        for rel, f in list_dir(od).items():
            if rel not in current:
                add(rel, [md5_bytes(f.read_bytes())], f"dir:{od}")

    mentions = upgrade_mentions(module)
    items = []
    for rel in sorted(removed):
        item = {"path": rel, "category": categorize(rel), "md5": removed[rel],
                "sources": sources[rel],
                # Heuristik teks: skrip upgrade yang MENYEBUT path ini. Bukan bukti ia
                # menghapusnya — kosong pasti belum tertangani, terisi wajib dibaca.
                "covered_by": [v for v, txt in mentions.items() if rel in txt]}
        if item["category"] == "override":
            item["override_class"] = PurePosixPath(rel).stem
        items.append(item)

    counts = {}
    for it in items:
        counts[it["category"]] = counts.get(it["category"], 0) + 1

    return {
        "module": module.name,
        "module_version": module_version(module),
        "existing_upgrade_versions": sorted(mentions),
        "base_ref": base_ref,
        "git_history": git_history,
        "old_dirs": [str(d) for d in old_dirs],
        "removed": items,
        "counts": counts,
        "uncovered": sum(1 for it in items if not it["covered_by"]),
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=(__doc__ or "").split("\n\n")[0])
    ap.add_argument("module_path")
    ap.add_argument("--base-ref", help="ref git versi lama (tag/commit)")
    ap.add_argument("--git-history", action="store_true",
                    help="semua path yang pernah dihapus di sejarah git module (tanpa tag rilis)")
    ap.add_argument("--old-dir", action="append", default=[],
                    help="folder rilis lama (boleh berulang)")
    ap.add_argument("-o", "--output", help="tulis JSON ke file (default: stdout)")
    args = ap.parse_args(argv)

    module = Path(args.module_path).resolve()
    if not module.is_dir():
        print(f"error: module-path bukan folder: {module}", file=sys.stderr)
        return 2
    if not (args.base_ref or args.old_dir or args.git_history):
        print("error: beri minimal satu sumber versi lama: --base-ref, --git-history, atau --old-dir",
              file=sys.stderr)
        return 2
    old_dirs = []
    for od in args.old_dir:
        p = Path(od).resolve()
        if not p.is_dir():
            print(f"error: --old-dir bukan folder: {p}", file=sys.stderr)
            return 2
        if p == module:
            print("error: --old-dir sama dengan module-path; beri folder rilis LAMA",
                  file=sys.stderr)
            return 2
        old_dirs.append(p)

    try:
        result = build(module, args.base_ref, old_dirs, args.git_history)
    except ValueError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2

    text = json.dumps(result, indent=2, ensure_ascii=False)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    else:
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
