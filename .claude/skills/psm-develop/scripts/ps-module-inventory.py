#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Inventaris struktur module PrestaShop existing -> JSON compact.

Deterministik: emit fakta struktur yang dibutuhkan untuk merancang penambahan
fungsi dengan aman, sehingga model tak perlu mem-parse PHP mentah tiap run:
- hook yang sudah terdaftar (registerHook + method hookXxx)
- ObjectModel + nama tabel ($definition['table'])
- controller (front/admin)
- daftar file
- versi module & keberadaan folder upgrade/

Dipakai psm-develop untuk (a) memetakan titik sisip aman, (b) validasi rencana
pra-apply (mis. hook yang mau ditambah ternyata sudah terdaftar).
"""
import argparse
import json
import re
import sys
from pathlib import Path

SKIP_DIRS = {"vendor", "node_modules", ".git"}


def iter_php(module_dir):
    for p in module_dir.rglob("*.php"):
        if not any(part in SKIP_DIRS for part in p.relative_to(module_dir).parts):
            yield p


def main():
    ap = argparse.ArgumentParser(description="Inventaris struktur module PrestaShop -> JSON.")
    ap.add_argument("module_path", help="Path folder module")
    ap.add_argument("-o", "--output", help="Tulis JSON ke file (default stdout)")
    args = ap.parse_args()

    module_dir = Path(args.module_path).resolve()
    if not module_dir.is_dir():
        print(f"error: bukan folder: {module_dir}", file=sys.stderr)
        return 2

    registered_hooks = set()       # dari registerHook('x')
    implemented_hooks = set()       # dari method hookX()
    object_models = []              # {class, table, file}
    controllers = []                # {type, class, file}
    module_version = None

    reg_re = re.compile(r"registerHook\(\s*['\"]([A-Za-z0-9_]+)['\"]", re.IGNORECASE)
    hookm_re = re.compile(r"function\s+hook([A-Za-z0-9_]+)\s*\(")
    table_re = re.compile(r"['\"]table['\"]\s*=>\s*['\"]([A-Za-z0-9_]+)['\"]")
    class_re = re.compile(r"class\s+([A-Za-z0-9_]+)\s+extends\s+([A-Za-z0-9_\\]+)")
    ver_re = re.compile(r"\$this->version\s*=\s*['\"]([^'\"]+)['\"]")

    for f in iter_php(module_dir):
        try:
            text = f.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        rel = str(f.relative_to(module_dir))
        for m in reg_re.finditer(text):
            registered_hooks.add(m.group(1))
        for m in hookm_re.finditer(text):
            implemented_hooks.add("hook" + m.group(1))
        if module_version is None:
            vm = ver_re.search(text)
            if vm:
                module_version = vm.group(1)
        for cm in class_re.finditer(text):
            cls, parent = cm.group(1), cm.group(2).lstrip("\\")
            if "ObjectModel" in parent:
                tm = table_re.search(text)
                object_models.append({"class": cls, "table": tm.group(1) if tm else None, "file": rel})
            elif "ModuleFrontController" in parent:
                controllers.append({"type": "front", "class": cls, "file": rel})
            elif "ModuleAdminController" in parent:
                controllers.append({"type": "admin", "class": cls, "file": rel})

    file_list = sorted(str(p.relative_to(module_dir)) for p in module_dir.rglob("*")
                       if p.is_file() and not any(d in p.relative_to(module_dir).parts for d in SKIP_DIRS))

    result = {
        "module": module_dir.name,
        "module_path": str(module_dir),
        "module_version": module_version,
        "registered_hooks": sorted(registered_hooks),
        "implemented_hooks": sorted(implemented_hooks),
        "object_models": object_models,
        "controllers": controllers,
        "has_upgrade_dir": (module_dir / "upgrade").is_dir(),
        "file_count": len(file_list),
        "files": file_list,
    }
    out = json.dumps(result, indent=2, ensure_ascii=False)
    (Path(args.output).write_text(out, encoding="utf-8") if args.output else print(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
