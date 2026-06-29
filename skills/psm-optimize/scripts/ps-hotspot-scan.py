#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Surface kandidat hotspot performa di module PrestaShop -> JSON.

Deterministik: temukan call-site yang berpotensi lambat agar model tak perlu
grep PHP mentah tiap run. Yang dideteksi (kandidat, bukan vonis):
- N+1: `Db::getInstance()->...` atau `new <X>(...)` (ObjectModel) di dalam blok loop (foreach/for/while)
- query langsung tanpa cache di hook
- jumlah baris per method hook (indikasi hook berat)

Model tetap memutuskan apakah kandidat itu N+1 nyata & cara perbaikan
version-safe-nya — itu judgment. Skrip hanya mengumpulkan situs kandidat.
"""
import argparse
import json
import re
import sys
from pathlib import Path

SKIP = {"vendor", "node_modules", ".git"}
LOOP_RE = re.compile(r"\b(foreach|for|while)\b")
QUERY_RE = re.compile(r"Db::getInstance\(\)|->executeS?\(|->getRow\(|new\s+ObjectModel|new\s+[A-Z]\w*\(")
HOOKDEF_RE = re.compile(r"function\s+(hook[A-Za-z0-9_]+)\s*\(")


def scan_file(path, module_dir):
    """Cari query/instansiasi di dalam blok loop via pelacakan kedalaman brace."""
    rel = str(path.relative_to(module_dir))
    try:
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
    except OSError:
        return [], []

    hotspots = []
    loop_stack = []  # (brace_depth_saat_loop_dibuka, line_no)
    depth = 0
    for i, line in enumerate(lines, 1):
        if LOOP_RE.search(line):
            loop_stack.append((depth, i))
        opens = line.count("{")
        closes = line.count("}")
        # query di dalam loop aktif
        if loop_stack and QUERY_RE.search(line):
            hotspots.append({"file": rel, "line": i, "loop_at": loop_stack[-1][1],
                             "snippet": line.strip()[:140], "kind": "query_in_loop"})
        depth += opens - closes
        # tutup loop yang brace-nya sudah selesai
        while loop_stack and depth <= loop_stack[-1][0]:
            loop_stack.pop()

    # hook berat: hitung baris per method hook (perkiraan kasar via brace depth)
    heavy_hooks = []
    for i, line in enumerate(lines, 1):
        m = HOOKDEF_RE.search(line)
        if m:
            # hitung baris sampai brace method tertutup
            d = 0
            started = False
            count = 0
            for l in lines[i - 1:]:
                d += l.count("{") - l.count("}")
                count += 1
                if "{" in l:
                    started = True
                if started and d <= 0:
                    break
            heavy_hooks.append({"file": rel, "line": i, "hook": m.group(1), "approx_lines": count})
    return hotspots, heavy_hooks


def main():
    ap = argparse.ArgumentParser(description="Surface kandidat hotspot performa module PrestaShop.")
    ap.add_argument("module_path")
    ap.add_argument("--heavy-hook-lines", type=int, default=40, help="Ambang baris method hook dianggap 'berat' (default 40)")
    ap.add_argument("-o", "--output")
    args = ap.parse_args()

    module_dir = Path(args.module_path).resolve()
    if not module_dir.is_dir():
        print(f"error: bukan folder: {module_dir}", file=sys.stderr)
        return 2

    all_hotspots, all_hooks = [], []
    for p in module_dir.rglob("*.php"):
        if any(part in SKIP for part in p.relative_to(module_dir).parts):
            continue
        hs, hh = scan_file(p, module_dir)
        all_hotspots.extend(hs)
        all_hooks.extend(hh)

    heavy = [h for h in all_hooks if h["approx_lines"] >= args.heavy_hook_lines]
    result = {
        "module": module_dir.name,
        "query_in_loop_candidates": all_hotspots,
        "query_in_loop_count": len(all_hotspots),
        "heavy_hook_candidates": heavy,
        "all_hooks_scanned": len(all_hooks),
        "note": "Kandidat, bukan vonis. Model memutuskan N+1 nyata & perbaikan version-safe.",
    }
    out = json.dumps(result, indent=2, ensure_ascii=False)
    (Path(args.output).write_text(out, encoding="utf-8") if args.output else print(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
