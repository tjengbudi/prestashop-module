# Aturan Validator PrestaShop

Ringkasan. Ruleset lengkap (regex per rule) ada di `{project-root}/.claude/skills/psm-validate/assets/ps-rules.json` — rujuk ke sana untuk deteksi, file ini untuk gambaran. Diseed 2026-06-29.

`affects` tiap rule menerima **major** (`1.7`/`8`/`9`) maupun **minor** (`9.1`, `8.2`) sejak 2026-07-30, jadi aturan khas-minor tak memblok minor tetangganya. Konsekuensi untuk pemanggil: sebut minor di `--versions` (`9.1`, bukan `9`) — target telanjang melewati aturan khas-minor dan Lapis 1 jadi tak konklusif (`minor_rules_skipped`).

## Wajib struktur
- `ps_versions_compliancy` ada di main file (error bila tidak). → [[composer-structure]].
- `index.php` tiap folder (warning).
- `Readme.md` ada, nama module huruf kecil, UTF-8 tanpa BOM.

## Dependency terlarang PS9 (error) — kind: dependency
guzzle, swiftmailer, league/tactician-bundle, sensio/framework-extra-bundle, anotasi PrestaShopBundle\Security (warning). → [[breaking-changes-9]].

## Kelas/method dihapus (error PS8/9)
`Attribute`, `HookDispatcher`, `Tools::jsonEncode/jsonDecode`, `Tools::addonsRequest`, `Validate::isPasswd`, `PrestaShopAutoload` (PS9), `FrameworkBundleAdminController` (warning PS9). → [[breaking-changes-8]], [[breaking-changes-9]].

## Hook dihapus (error PS9)
Login admin legacy, produk legacy. Khas 9.1 (warning): `displaySearch` (deprecated 9.1, **dihapus** di Hummingbird), `$HOOK_DISPLAYORDERDETAIL` → `displayOrderDetail`. → [[hooks]].

## Konstanta dihapus
`_PS_SMARTY_DIR_`/`_PS_TCPDF_*`/`_PS_SWIFT_DIR_` (PS8), `PS_LEGACY_IMAGES`/`PS_HIGHT_DPI` (PS9).

## Fungsi terlarang (error semua versi)
`eval`, `passthru`, `shell_exec`, `system`, `proc_open`, `popen`.

## Smarty
Variabel tak di-escape → error sejak v5.14.1. Pakai `{$var|escape:'html':'UTF-8'}` atau `{$var nofilter}`.
Nama theme di-hardcode (`/themes/classic/…`, `/themes/hummingbird/…`) → **error khas 9.1**: theme default instalasi baru 9.1 bukan lagi Classic, jadi path tetap itu putus. Resolve lewat `Context::getContext()->shop->theme_name` / `_THEME_DIR_`. → [[cross-version-patterns]].

## Cek lokal vs web
- Web Validator butuh login akun seller (PrestaShop Account) → tak bisa otomatis tanpa kredensial.
- Alternatif lokal di flashlight: **PHPStan level 5** (jalan terhadap 1.7.8.7, 8.0.0, 9) + **PrestaShop coding standard** (php-dev-tools). → [[flashlight]].

## Status changelog (diaudit 2026-07-08)
Latest **v5.14.2 (2026-06-09)** — hanya nambah test, tak ada rule baru. Ruleset KB masih current: rule terakhir yang berdampak adalah v5.14.0/5.14.1 (theme name hardcoded, `displaySearch`, `displayOrderDetail`, Smarty unescaped→error) — semua sudah kecatat di atas & di [[breaking-changes-9]].

Sumber: validator.prestashop.com/changelog (v5.x s/d v5.14.2), ps-rules.json.

## Verified additions 2026-11-18 `[core]`

Ruleset changes made in project `whatsappchat`, every claim verified against core in the pinned flashlight images (1.7.8.11 / 8.1.6-nginx / 9.1.4-nginx) — not against devdocs. `ps-rules.json` went **28 → 36 rules (29 error / 7 warning)**; all seven `psm-validate` suites pass.
- **Corrections:** `cls-attribute` narrowed + `negate_pattern` (`#[\Attribute]`, `new \Attribute`, `->getAttributes()` are PHP 8 attributes, and the false positive was really `new \Attribute` / `\Attribute::class` — `#[\Attribute]` itself never matched the old pattern); `cls-hookdispatcher` narrowed to `PrestaShopBundle\Service\Hook\HookDispatcher` (the `Core\Hook\` class and interface still exist at 9.1.4); `mth-hook-alias` raised `warning → error`; `mth-validate-ispasswd` no longer recommends the 9-removed `isPlaintextPassword`.
- **New rules:** `cls-hookdispatcher-aware-trait`, `mth-validate-isplaintextpassword`, `mth-validate-isanything`, `mth-validate-ispasswdadmin`, `mth-translate-getadmintranslation`, `fn-ajaxdie`, `dep-archive-tar` (all present 1.7.8 & 8.1, absent 9.1.4, archive_tar by vendor), plus `dep-symfony-components` for `symfony/{inflector,notifier,rate-limiter,semaphore,uid,workflow}`, which are absent from `vendor/` at **every** target and therefore affect 1.7/8/9.
- **Deliberately not a rule:** `soundasleep/html2text` — the 9.0 upgrade notes list it as removed but `vendor/soundasleep/html2text` is present at 9.1.4; a rule would have been a false positive.
- **Coverage of the documented 9 removal list is now 11 of 12 packages.** Line 16's bare `HookDispatcher` and line 19's hook list are otherwise still accurate; the 9.1 minor-key notes at line 5 are unchanged.
- Regression evidence: a fixture scan shows the narrowed rules firing only on legacy shapes and the `[9]`-only rules silent at target `8.1`; scanning the real `whatsappchat` module gives 0 errors on 1.7.8 / 8.1 / 9.1.
