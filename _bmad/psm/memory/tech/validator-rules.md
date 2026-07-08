# Aturan Validator PrestaShop

Ringkasan. Ruleset lengkap (regex per rule) ada di `{project-root}/skills/psm-validate/assets/ps-rules.json` — rujuk ke sana untuk deteksi, file ini untuk gambaran. Diseed 2026-06-29.

## Wajib struktur
- `ps_versions_compliancy` ada di main file (error bila tidak). → [[composer-structure]].
- `index.php` tiap folder (warning).
- `Readme.md` ada, nama module huruf kecil, UTF-8 tanpa BOM.

## Dependency terlarang PS9 (error) — kind: dependency
guzzle, swiftmailer, league/tactician-bundle, sensio/framework-extra-bundle, anotasi PrestaShopBundle\Security (warning). → [[breaking-changes-9]].

## Kelas/method dihapus (error PS8/9)
`Attribute`, `HookDispatcher`, `Tools::jsonEncode/jsonDecode`, `Tools::addonsRequest`, `Validate::isPasswd`, `PrestaShopAutoload` (PS9), `FrameworkBundleAdminController` (warning PS9). → [[breaking-changes-8]], [[breaking-changes-9]].

## Hook dihapus (error PS9)
Login admin legacy, produk legacy, `displaySearch` (warning 9.1+). → [[hooks]].

## Konstanta dihapus
`_PS_SMARTY_DIR_`/`_PS_TCPDF_*`/`_PS_SWIFT_DIR_` (PS8), `PS_LEGACY_IMAGES`/`PS_HIGHT_DPI` (PS9).

## Fungsi terlarang (error semua versi)
`eval`, `passthru`, `shell_exec`, `system`, `proc_open`, `popen`.

## Smarty
Variabel tak di-escape → error sejak v5.14.1. Pakai `{$var|escape:'html':'UTF-8'}` atau `{$var nofilter}`.

## Cek lokal vs web
- Web Validator butuh login akun seller (PrestaShop Account) → tak bisa otomatis tanpa kredensial.
- Alternatif lokal di flashlight: **PHPStan level 5** (jalan terhadap 1.7.8.7, 8.0.0, 9) + **PrestaShop coding standard** (php-dev-tools). → [[flashlight]].

## Status changelog (diaudit 2026-07-08)
Latest **v5.14.2 (2026-06-09)** — hanya nambah test, tak ada rule baru. Ruleset KB masih current: rule terakhir yang berdampak adalah v5.14.0/5.14.1 (theme name hardcoded, `displaySearch`, `displayOrderDetail`, Smarty unescaped→error) — semua sudah kecatat di atas & di [[breaking-changes-9]].

Sumber: validator.prestashop.com/changelog (v5.x s/d v5.14.2), ps-rules.json.
