# Breaking Changes PrestaShop 9.x

Hal yang pecah saat module 1.7/8 dibawa ke PS9. Symfony 6.4, PHP 8.1 minimum. Diseed 2026-06-29 dari riset devdocs (core-updates 9.0) + ruleset psm-validate.

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

Lihat juga [[breaking-changes-8]], [[cross-version-patterns]], [[validator-rules]], [[services-di]].

Sumber: devdocs.prestashop-project.org/9/modules, validator.prestashop.com/changelog (v5.10–5.14).
