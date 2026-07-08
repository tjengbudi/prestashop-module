# Breaking Changes PrestaShop 9.x

Hal yang pecah saat module 1.7/8 dibawa ke PS9. Symfony 6.4, PHP 8.1 minimum. Diseed 2026-06-29 dari riset devdocs (core-updates 9.0) + ruleset psm-validate. **Diaudit 2026-07-08:** stable kini **9.1.4** (rilis 6/3/2026); ditambah bagian 9.1.x di bawah.

## Dependency dihapus dari core (bundle sendiri atau ganti)
- `guzzlehttp/guzzle` → Symfony HTTP Client, atau bundle guzzle di vendor module.
- `swiftmailer/swiftmailer` → Symfony Mailer (atau `Mail::send` core bila cukup).
- `league/tactician-bundle` → Symfony Messenger.
- `sensio/framework-extra-bundle` → atribut Symfony 6.4 native.
- Anotasi `PrestaShopBundle\Security` → atribut keamanan `PrestaShopAdminController` (warning).

## Kelas / Method
- `PrestaShopAutoload` → dihapus. Pakai `prestashop/autoload` + composer autoload module.
- `FrameworkBundleAdminController` → deprecated di PS9, dihapus di PS10. Migrasi ke `PrestaShopAdminController`.
- Override `initContent`/`initHeader`/`initFooter` legacy controller → tak dipanggil langsung untuk halaman termigrasi.
- `Context` singleton dipecah jadi service (`EmployeeContext`, `ShopContext`, dll). Baca masih aman via `Context::getContext()`; tulis auth pakai jalur modern.

## Konstanta / Variabel
- `PS_LEGACY_IMAGES`, `PS_HIGHT_DPI` → dihapus, fitur tidak ada lagi.

## Hooks dihapus
- Login admin: `actionAdminLoginControllerBefore/After/Forgot/Reset` → `actionBackOfficeLoginForm` / `actionEmployeeRequestPasswordResetForm`.
- Produk legacy: `actionAdminProductsController*`, `actionAdminActivate/Deactivate/Delete/SortBefore/After` → halaman produk lama dihapus, pakai hook modern.
- `displaySearch` → deprecated untuk PS9.1+.

## Smarty / Template
- Hard-coded nama theme → error Validator PS9.1+.
- `displayOrderDetail` handling khusus PS9.1+.

## Breaking changes 9.1.x (minor, tetap jaga BC dengan 9.0)
Diaudit 2026-07-08 dari devdocs core-updates/9.1. 9.1 janji backward-compatible dgn 9.0; breaking hanya bila perlu.

- **PHP 8.5 didukung** (rekomendasi baru); 8.1–8.4 tetap jalan. `require.php` module tak wajib naik.
- **`Theme::getDefaultTheme()` tak lagi return hardcoded `"classic"`** → kini return theme default dari config (bisa `hummingbird`). Jangan asumsikan "classic"; baca dinamis.
- **D3 & NVD3 di-update** → bila module bikin widget/chart dashboard pakai lib ini, uji ulang.
- **Hummingbird jadi default theme instalasi baru 9.1** (upgrade dari 9.0 tetap pakai theme lama). Bikin compatibility break vs Classic:
  - `displaySearch` **dihapus** di Hummingbird (dulu inject ps_searchbar ke 404, konflik duplikat). → jangan andalkan.
  - `displayOrderDetail` **menggantikan** variable hook `$HOOK_DISPLAYORDERDETAIL` (nama konvensi standar).
  - **Bootstrap 4.0.0-alpha.5 → 5.3.3** di Hummingbird: kelas .tpl/css berubah masif (`.no-gutters`→`.g-0`, `.ml-*/.mr-*`→`.ms-*/.me-*`, `.custom-control`→`.form-check`, `.btn-block`→`.d-grid`, `.badge-*`→`.bg-*`, `.sr-only`→`.visually-hidden`, `data-toggle`→`data-bs-toggle`, dst). Template yg target Hummingbird wajib direview.
  - **jQuery deprecated** di Hummingbird, dihapus di PS10. Dorong Vanilla JS + Bootstrap 5 native.
  - **JS selector** non-standar pindah ke data attribute `data-ps-ref/action/target` (progresif).
- **Sistem diskon baru** & **multi-shipment** (order dipecah multi-carrier) → di balik **feature flag, default OFF**, masih WIP. Pakai cart rules di bawahnya tapi arsitektur & UI berubah; module yg sentuh diskon/promo & shipment/carrier siap-siap adaptasi. Dokumentasi dev menyusul.
- **Skema DB berubah** (dukung multi-shipment & diskon baru) → lihat `9.1.0.sql`.
- Build asset: **Node.js 20.19.5** default.

## Hook baru 9.1.x
Detail per-fungsi → [[hooks]].
- `actionModuleEnable` / `actionModuleDisable` / `actionModuleUpgradeAfter` — lifecycle module.
- `actionConfigurationUpdateValueBefore` — sebelum `Configuration::updateValue()`.
- `displayModalContent` (Hummingbird) — inject konten ke container modal.

## CLI baru 9.1.x
- `bin/console prestashop:thumbnails:regenerate` — regen thumbnail produk (batch, cocok cron).
- `bin/console prestashop:search:index` — rebuild index pencarian (cron / setelah import massal).
- `bin/console prestashop:module:export-translations <module>` — export terjemahan module.

Lihat juga [[breaking-changes-8]], [[cross-version-patterns]], [[validator-rules]], [[services-di]], [[hooks]].

Sumber: devdocs.prestashop-project.org/9/modules/core-updates/9.0 & /9.1, validator.prestashop.com/changelog (v5.10–5.14.2). Audit 2026-07-08.
