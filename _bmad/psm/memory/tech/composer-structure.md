# composer.json & struktur module

Diseed 2026-06-29 dari katalog cross-version + riset devdocs composer.

## composer.json
- WAJIB `"config": {"prepend-autoloader": false}` — kalau true, dependency module override core dan merusak PrestaShop.
- `require.php`: serendah versi target terendah (mis. `>=7.2` bila dukung 1.7.x lawas; PS9 butuh PHP 8.1 — pisahkan via compliancy).
- PSR-4 map ke `src/`.
- Build rilis: `composer dump-autoload -o --no-dev`, sertakan `vendor/`, jangan sertakan dev-deps.

## ps_versions_compliancy (WAJIB, divalidasi Validator sejak v5.2.0)
```php
$this->ps_versions_compliancy = ['min' => '1.7.0.0', 'max' => _PS_VERSION_];
```
Di constructor main file. Range hingga 9.0.x didukung generator (v5.13.3). → [[validator-rules]].

## Struktur folder
- `src/` (PSR-4), `controllers/front/`, `controllers/admin/`, `views/templates/hook/`, `config/` (services.yml), `translations/`, `upgrade/`.
- `index.php` standar WAJIB di tiap subfolder (redirect ke FO).
- `Readme.md` ada; nama module huruf kecil; encoding UTF-8 tanpa BOM; tak ada `Thumbs.db`/`__MACOSX`.

## Dependency terlarang PS9
Lihat [[breaking-changes-9]] — guzzle, swiftmailer, tactician, framework-extra-bundle. Bundle sendiri atau ganti.

Pola → [[cross-version-patterns]].

Sumber: devdocs.prestashop-project.org/9/modules/concepts/composer.

## Verified additions 2026-11-18 `[core]`

- `main_class` is a **1.7-era Addons concept**: the string appears at 1.7.8.11 only, in `src/Core/Addon/Module/ModuleRepository.php`, and nowhere under `classes/`, `src/` or `config/` at 8.1.6-nginx or 9.1.4-nginx. Module discovery on 8/9 relies on `name` + `ps_versions_compliancy` (line 11), not on it.
- The literal `upgrade.php` appears nowhere in `classes/module/Module.php` on any of the three tags — module upgrade dispatch is not wired in `Module`; keep the SQL in `upgrade/upgrade-x.y.z.php` and expect the core/Update Assistant path to drive it. → [[persistence]]
- Dependency rules now also cover `pear/archive_tar` (gone in 9) and the six Symfony components never shipped on these targets; `soundasleep/html2text` is still in core vendor at 9.1.4 despite the upgrade notes. → [[validator-rules]]
