#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Generate kerangka module PrestaShop baru yang cross-version (1.7/8/9).

Deterministik: nama+namespace+versi sama -> kerangka sama. Menghasilkan struktur
minimal yang dijamin lolos psm-validate sejak awal: main file dengan
ps_versions_compliancy + install/uninstall, composer.json (prepend-autoloader:false,
PSR-4), dan index.php di setiap folder.

Tidak menulis hook/views contoh (kerangka telanjang) — itu diisi belakangan oleh
Budi atau psm-develop.
"""
import argparse
import json
import re
import sys
from pathlib import Path

INDEX_PHP = """<?php
/**
 * Security: redirect ke halaman utama, cegah listing direktori.
 */
header('Expires: Mon, 26 Jul 1997 05:00:00 GMT');
header('Last-Modified: ' . gmdate('D, d M Y H:i:s') . ' GMT');
header('Cache-Control: no-store, no-cache, must-revalidate');
header('Cache-Control: post-check=0, pre-check=0', false);
header('Pragma: no-cache');
header('Location: ../');
exit;
"""


def to_class_name(module_name):
    """ps_mymodule -> PsMymodule (PascalCase nama kelas main file)."""
    return "".join(part.capitalize() for part in re.split(r"[_\-]", module_name) if part)


def main_file_php(module_name, class_name, author, display_name, ps_min, ps_max):
    return f"""<?php
/**
 * {display_name}
 * Module PrestaShop cross-version (1.7.x / 8.x / 9.x).
 */
if (!defined('_PS_VERSION_')) {{
    exit;
}}

class {class_name} extends Module
{{
    public function __construct()
    {{
        $this->name = '{module_name}';
        $this->tab = 'others';
        $this->version = '1.0.0';
        $this->author = '{author}';
        $this->need_instance = 0;
        // Kompatibilitas lintas versi — WAJIB (divalidasi PrestaShop Validator).
        $this->ps_versions_compliancy = ['min' => '{ps_min}', 'max' => '{ps_max}'];
        $this->bootstrap = true;

        parent::__construct();

        $this->displayName = $this->trans('{display_name}', [], 'Modules.{class_name}.Admin');
        $this->description = $this->trans('Module {display_name}.', [], 'Modules.{class_name}.Admin');
    }}

    public function install()
    {{
        return parent::install();
    }}

    public function uninstall()
    {{
        return parent::uninstall();
    }}
}}
"""


def composer_json(module_name, namespace, author, php_require):
    return json.dumps({
        "name": f"{author.lower().replace(' ', '')}/{module_name}",
        "description": f"Module PrestaShop {module_name}",
        "type": "prestashop-module",
        "authors": [{"name": author}],
        "require": {"php": php_require},
        "autoload": {"psr-4": {f"{namespace}\\": "src/"}},
        "config": {"prefer-stable": True, "prepend-autoloader": False},
    }, indent=4)


def php_require_for(ps_min):
    """PS 1.7 lawas -> PHP >=7.2; bila min sudah 8.x -> >=8.1."""
    return ">=8.1" if ps_min.startswith(("8.", "9.")) else ">=7.2"


def _semver_key(v):
    """Tuple int untuk sort semver toleran ('1.7.8' -> (1,7,8,0)); non-angka -> 0."""
    parts = [int(p) if p.isdigit() else 0 for p in v.strip().split(".")]
    return tuple((parts + [0, 0, 0, 0])[:4])


def compliancy_from_targets(target_versions):
    """Daftar versi target -> (ps_min, ps_max) deterministik untuk ps_versions_compliancy.

    min = versi target terkecil dinormalkan ke 4 bagian (mis. '1.7.8' -> '1.7.8.0').
    max = major terbesar dengan patch terbuka (mis. target tertinggi 9.0 -> '9.99.99').
    Transform ini deterministik dan diuji, jadi model tak perlu sort/compare versi sendiri.
    """
    versions = [v.strip() for v in target_versions.split(",") if v.strip()]
    if not versions:
        raise ValueError("target-versions kosong")
    ordered = sorted(versions, key=_semver_key)
    lo = _semver_key(ordered[0])
    ps_min = ".".join(str(n) for n in lo)
    hi_major = _semver_key(ordered[-1])[0]
    ps_max = f"{hi_major}.99.99"
    return ps_min, ps_max


def main():
    ap = argparse.ArgumentParser(description="Generate kerangka module PrestaShop cross-version.")
    ap.add_argument("module_name", help="Nama module (lowercase, mis. ps_mybanner)")
    ap.add_argument("--dest", required=True, help="Folder induk tempat module dibuat")
    ap.add_argument("--namespace", help="Namespace PSR-4 (default: PrestaShop\\Module\\<Class>)")
    ap.add_argument("--author", default="PrestaShop Module Builder", help="Nama author")
    ap.add_argument("--display-name", help="Nama tampilan (default: dari nama module)")
    ap.add_argument("--target-versions",
                    help="Daftar versi target dipisah koma (mis. 1.7.8,8.1,9.0); min/max ps_versions_compliancy dihitung deterministik dari sini")
    ap.add_argument("--ps-min", help="Versi PrestaShop minimum (override; default diturunkan dari --target-versions atau 1.7.0.0)")
    ap.add_argument("--ps-max", help="Versi PrestaShop maksimum (override; default diturunkan dari --target-versions atau 9.99.99)")
    ap.add_argument("-o", "--output", help="Tulis ringkasan JSON ke file (default stdout)")
    ap.add_argument("--force", action="store_true", help="Timpa bila folder module sudah ada")
    args = ap.parse_args()

    name = args.module_name.strip().lower()
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        print(f"error: nama module tak valid '{name}' (huruf kecil, angka, underscore; mulai huruf)", file=sys.stderr)
        return 2

    # Turunkan min/max deterministik dari --target-versions; --ps-min/--ps-max override eksplisit.
    if args.target_versions:
        try:
            derived_min, derived_max = compliancy_from_targets(args.target_versions)
        except ValueError as e:
            print(f"error: --target-versions tak valid ({e})", file=sys.stderr)
            return 2
    else:
        derived_min, derived_max = "1.7.0.0", "9.99.99"
    ps_min = args.ps_min or derived_min
    ps_max = args.ps_max or derived_max

    class_name = to_class_name(name)
    namespace = args.namespace or f"PrestaShop\\Module\\{class_name}"
    display_name = args.display_name or class_name
    module_dir = Path(args.dest).resolve() / name
    if module_dir.exists() and not args.force:
        print(f"error: {module_dir} sudah ada (pakai --force untuk timpa)", file=sys.stderr)
        return 2

    # Struktur folder minimal telanjang.
    dirs = [module_dir, module_dir / "src", module_dir / "views",
            module_dir / "views" / "templates", module_dir / "translations"]
    try:
        for d in dirs:
            d.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        print(f"error: gagal membuat folder module di '{args.dest}' ({e.strerror or e})", file=sys.stderr)
        return 2

    php_require = php_require_for(ps_min)
    files = {
        module_dir / f"{name}.php": main_file_php(name, class_name, args.author, display_name, ps_min, ps_max),
        module_dir / "composer.json": composer_json(name, namespace, args.author, php_require),
    }
    for path, content in files.items():
        path.write_text(content, encoding="utf-8")

    # index.php di SETIAP folder (keamanan + syarat Validator).
    index_dirs = [module_dir, *[p for p in module_dir.rglob("*") if p.is_dir()]]
    for d in index_dirs:
        (d / "index.php").write_text(INDEX_PHP, encoding="utf-8")

    try:
        rel_module_dir = str(module_dir.relative_to(Path.cwd()))
    except ValueError:
        rel_module_dir = str(module_dir)

    result = {
        "module": name, "class": class_name, "namespace": namespace,
        "path": rel_module_dir, "php_require": php_require,
        "ps_compliancy": {"min": ps_min, "max": ps_max},
        "files_created": sorted(str(p.relative_to(module_dir)) for p in module_dir.rglob("*") if p.is_file()),
        "next": "Jalankan 'composer dump-autoload' di folder module, lalu psm-validate.",
    }
    out = json.dumps(result, indent=2, ensure_ascii=False)
    (Path(args.output).write_text(out, encoding="utf-8") if args.output else print(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
