#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Inventaris struktur module PrestaShop existing -> JSON compact, plus validasi rencana.

Deterministik: emit fakta struktur yang dibutuhkan untuk merancang penambahan
fungsi dengan aman, sehingga model tak perlu mem-parse PHP mentah tiap run:
- hook yang sudah terdaftar (registerHook + method hookXxx)
- ObjectModel + nama tabel ($definition['table'], dicari di body class masing-masing)
- controller (front/admin — legacy ModuleAdmin/FrontController + Symfony
  FrameworkBundleAdminController/PrestaShopAdminController)
- daftar file
- versi module & keberadaan folder upgrade/
- looks_like_module: ada .php DAN minimal satu sinyal struktur (versi/hook/
  ObjectModel/controller) — dipakai Gerbang target di SKILL.md
- detection: "direct-parent-only" — class dikenali hanya dari parent langsung;
  inheritance tak langsung (extends subclass konkret) tak terdeteksi

Tiga mode:
- default: emit JSON inventaris (peta titik sisip aman).
- --validate-plan <plan.json>: cocokkan item rencana dengan inventaris dan emit
  mismatch deterministik per item (set/list-membership yang punya satu jawaban
  benar per input) — hook direncanakan sudah ada di registered_hooks; titik sisip
  file tak ada; ObjectModel diubah tanpa folder upgrade/. Penilaian bermaksud
  (apakah $definition yang diubah sedang terpakai) tetap urusan model, bukan skrip.
- --reconcile <plan.json>: saat resume, cek item ber-status 'diterapkan' yang
  buktinya hilang dari inventaris (drift, mis. Budi git-revert) — inversi
  validate-plan. Keputusan atas drift (koreksi status/tanya Budi) tetap milik model.
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


def build_inventory(module_dir):
    registered_hooks = set()       # dari registerHook('x')
    implemented_hooks = set()       # dari method hookX()
    object_models = []              # {class, table, file}
    controllers = []                # {type, class, file}
    module_version = None
    php_count = 0

    ADMIN_PARENTS = ("ModuleAdminController", "FrameworkBundleAdminController",
                     "PrestaShopAdminController")

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
        php_count += 1
        rel = str(f.relative_to(module_dir))
        for m in reg_re.finditer(text):
            registered_hooks.add(m.group(1))
        for m in hookm_re.finditer(text):
            implemented_hooks.add("hook" + m.group(1))
        if module_version is None:
            vm = ver_re.search(text)
            if vm:
                module_version = vm.group(1)
        class_matches = list(class_re.finditer(text))
        for i, cm in enumerate(class_matches):
            cls, parent = cm.group(1), cm.group(2).lstrip("\\")
            if "ObjectModel" in parent:
                # cari 'table' hanya di body class ini (sampai class berikutnya),
                # bukan file-wide — file multi-class tak boleh saling menular tabel
                region = text[cm.end():class_matches[i + 1].start()] if i + 1 < len(class_matches) else text[cm.end():]
                tm = table_re.search(region)
                object_models.append({"class": cls, "table": tm.group(1) if tm else None, "file": rel})
            elif "ModuleFrontController" in parent:
                controllers.append({"type": "front", "class": cls, "file": rel})
            elif any(a in parent for a in ADMIN_PARENTS):
                controllers.append({"type": "admin", "class": cls, "file": rel})

    file_list = sorted(str(p.relative_to(module_dir)) for p in module_dir.rglob("*")
                       if p.is_file() and not any(d in p.relative_to(module_dir).parts for d in SKIP_DIRS))

    return {
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
        # aturan pasti Gerbang target: ada .php DAN minimal satu sinyal struktur
        "looks_like_module": php_count > 0 and bool(
            module_version or registered_hooks or implemented_hooks or object_models or controllers),
        "detection": "direct-parent-only",
    }


def validate_plan(inv, plan):
    """Cocokkan item rencana dengan inventaris; emit mismatch deterministik per item.

    Bentuk plan: {"items": [{"function": str, "add_hooks": [str],
    "insert_files": [str], "changes_objectmodel": bool}]}. Hanya cek yang
    punya satu jawaban benar per input; penilaian bermaksud tetap milik model.
    """
    # nama hook PrestaShop case-insensitive; normalkan agar konsisten dgn reconcile_plan
    registered = {h.lower() for h in inv["registered_hooks"]}
    files = set(inv["files"])
    has_upgrade = inv["has_upgrade_dir"]
    mismatches = []
    for item in plan.get("items", []):
        fn = item.get("function", "?")
        for h in item.get("add_hooks", []):
            if h.lower() in registered:
                mismatches.append({"function": fn, "kind": "hook_already_registered",
                                   "detail": f"hook '{h}' sudah ada di registered_hooks"})
        for path in item.get("insert_files", []):
            if path not in files:
                mismatches.append({"function": fn, "kind": "insert_file_missing",
                                   "detail": f"titik sisip '{path}' tak ada di module"})
        if item.get("changes_objectmodel") and not has_upgrade:
            mismatches.append({"function": fn, "kind": "objectmodel_change_without_upgrade",
                               "detail": "mengubah ObjectModel tanpa folder upgrade/ — sediakan upgrade script"})
    return {"module": inv["module"], "ok": not mismatches, "mismatches": mismatches}


def reconcile_plan(inv, plan):
    """Cek drift status 'diterapkan' saat resume: item yang plan klaim sudah
    diterapkan tapi buktinya hilang dari inventaris (mis. Budi git-revert).

    Inversi validate_plan: di sini bukti yang *ada* itu benar; yang *hilang* itu drift.
    Bentuk plan sama; hanya item dengan status 'diterapkan'/'applied' yang dicek.
    """
    # implemented_hooks berprefiks 'hook' (mis. 'hookDisplayHeader'); normalkan ke
    # bentuk bare + lowercase agar cocok dengan add_hooks/registered_hooks (case-insensitive)
    present_hooks = {h.lower() for h in inv["registered_hooks"]}
    present_hooks |= {re.sub(r"^hook", "", h, flags=re.IGNORECASE).lower() for h in inv["implemented_hooks"]}
    files = set(inv["files"])
    tables = {o["table"] for o in inv["object_models"] if o["table"]}
    classes = {o["class"] for o in inv["object_models"]}
    drift = []
    for item in plan.get("items", []):
        if str(item.get("status", "")).lower() not in ("diterapkan", "applied"):
            continue
        fn = item.get("function", "?")
        for h in item.get("add_hooks", []):
            if h.lower() not in present_hooks:
                drift.append({"function": fn, "kind": "hook_missing",
                              "detail": f"hook '{h}' diklaim diterapkan tapi tak ada di registered/implemented"})
        for path in item.get("insert_files", []):
            if path not in files:
                drift.append({"function": fn, "kind": "file_missing",
                              "detail": f"file '{path}' diklaim diterapkan tapi tak ada di module"})
        for t in item.get("add_tables", []):
            if t not in tables:
                drift.append({"function": fn, "kind": "table_missing",
                              "detail": f"tabel/ObjectModel '{t}' diklaim diterapkan tapi tak ada di inventaris"})
        for c in item.get("add_classes", []):
            if c not in classes:
                drift.append({"function": fn, "kind": "class_missing",
                              "detail": f"class '{c}' diklaim diterapkan tapi tak ada di inventaris"})
    return {"module": inv["module"], "ok": not drift, "drift": drift}


def main():
    ap = argparse.ArgumentParser(description="Inventaris struktur module PrestaShop + validasi/rekonsiliasi rencana -> JSON.")
    ap.add_argument("module_path", help="Path folder module")
    ap.add_argument("-o", "--output", help="Tulis JSON ke file (default stdout)")
    ap.add_argument("--validate-plan", metavar="PLAN.json",
                    help="Cocokkan rencana dengan inventaris, emit mismatch per item (rc=1 bila ada mismatch)")
    ap.add_argument("--reconcile", metavar="PLAN.json",
                    help="Cek drift status 'diterapkan' vs bukti aktual saat resume (rc=1 bila ada drift)")
    args = ap.parse_args()

    module_dir = Path(args.module_path).resolve()
    if not module_dir.is_dir():
        print(f"error: bukan folder: {module_dir}", file=sys.stderr)
        return 2

    inv = build_inventory(module_dir)

    if args.validate_plan or args.reconcile:
        plan_path = Path(args.validate_plan or args.reconcile)
        try:
            plan = json.loads(plan_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            print(f"error: gagal baca plan {plan_path}: {e}", file=sys.stderr)
            return 2
        result = validate_plan(inv, plan) if args.validate_plan else reconcile_plan(inv, plan)
        out = json.dumps(result, indent=2, ensure_ascii=False)
        (Path(args.output).write_text(out, encoding="utf-8") if args.output else print(out))
        return 0 if result["ok"] else 1

    out = json.dumps(inv, indent=2, ensure_ascii=False)
    (Path(args.output).write_text(out, encoding="utf-8") if args.output else print(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
