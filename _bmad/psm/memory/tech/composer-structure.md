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
