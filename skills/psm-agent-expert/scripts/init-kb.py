#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Scaffold struktur knowledge base bersama module psm — deterministik.

Membuat pohon `{project-root}/_bmad/psm/memory/` (tech/ ecommerce/ projects/)
dan menulis file stub untuk tiap entri yang dikenal, bila belum ada. Idempoten:
file yang sudah ada TAK ditimpa (agar seed/kurasi tak hilang). Yang deterministik
— layout direktori & daftar nama file — dikerjakan di sini; pengisian ISI (seed
dari riset/katalog) tetap tugas agent karena itu judgment.

Output JSON ke stdout: apa yang dibuat vs sudah ada, plus daftar file yang masih
kosong (butuh di-seed agent). Exit 0 = sukses, 2 = error.
"""
import argparse
import json
import sys
from pathlib import Path

# Layout kanonik KB. Satu-satunya sumber kebenaran untuk struktur.
TREE = {
    "tech": [
        "breaking-changes-8.md",
        "breaking-changes-9.md",
        "cross-version-patterns.md",
        "hooks.md",
        "services-di.md",
        "persistence.md",
        "composer-structure.md",
        "validator-rules.md",
        "flashlight.md",
    ],
    "ecommerce": [
        "function-catalog.md",
    ],
    "projects": [],  # diisi per-module saat runtime, tak ada stub tetap
}


def stub_body(rel_path):
    """Placeholder yang menandai file butuh seed — agent mengisi isinya."""
    title = Path(rel_path).stem.replace("-", " ")
    return (
        f"# {title}\n\n"
        "<!-- STUB — belum di-seed. Kurator (psm-agent-expert) mengisi dari "
        "riset devdocs / katalog skill saudara. Catat sumber & tanggal. -->\n"
    )


def main():
    ap = argparse.ArgumentParser(
        description="Scaffold struktur KB bersama psm (idempoten, tak menimpa)."
    )
    ap.add_argument(
        "memory_root",
        help="Path {project-root}/_bmad/psm/memory (dibuat bila belum ada).",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Laporkan yang akan dibuat tanpa menyentuh disk.",
    )
    args = ap.parse_args()

    root = Path(args.memory_root)
    created_dirs, created_files, existing, empty = [], [], [], []

    try:
        for subdir, files in TREE.items():
            d = root / subdir
            if not d.exists():
                created_dirs.append(str(d))
                if not args.dry_run:
                    d.mkdir(parents=True, exist_ok=True)
            for fname in files:
                f = d / fname
                rel = f"{subdir}/{fname}"
                if f.exists():
                    existing.append(rel)
                    text = f.read_text(encoding="utf-8", errors="ignore")
                    # Un-seeded if empty or still carrying our own stub marker
                    # line. Match the marker line, not a bare substring, so a
                    # real doc that merely mentions "STUB" isn't re-flagged.
                    if f.stat().st_size == 0 or "<!-- STUB" in text:
                        empty.append(rel)
                else:
                    created_files.append(rel)
                    empty.append(rel)
                    if not args.dry_run:
                        f.write_text(stub_body(rel), encoding="utf-8")
    except OSError as e:
        print(json.dumps({"status": "error", "reason": str(e)}), file=sys.stderr)
        return 2

    print(
        json.dumps(
            {
                "status": "ok",
                "dry_run": args.dry_run,
                "memory_root": str(root),
                "created_dirs": created_dirs,
                "created_files": created_files,
                "existing_files": existing,
                "needs_seed": empty,  # file yang agent harus isi
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
