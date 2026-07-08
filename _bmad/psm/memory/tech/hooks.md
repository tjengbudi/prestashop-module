# Hooks lintas versi

Diseed 2026-06-29 dari katalog cross-version + function-catalog.

## Dasar (sama lintas versi)
- Registrasi: `$this->registerHook('displayHeader')` di `install()`.
- Implementasi: `hookDisplayHeader(array $params)`.
- Jangan daftarkan hook tanpa implementasi method (PS8+ dev mode lempar exception).
- Jangan pakai hook alias (deprecated PS8).

## Cabang versi untuk hook yang dihapus
```php
public function install() {
    $hooks = ['displayHeader', 'actionFrontControllerSetMedia'];
    if (version_compare(_PS_VERSION_, '9.0.0', '>=')) {
        $hooks[] = 'actionBackOfficeLoginForm';      // PS9
    } else {
        $hooks[] = 'actionAdminLoginControllerBefore'; // legacy
    }
    foreach ($hooks as $h) { $this->registerHook($h); }
}
```
Implementasikan KEDUA method bila perlu; yang tak terdaftar di suatu versi cukup tak dipanggil. Hook yang dihapus PS9 → [[breaking-changes-9]].

## Hook baru PS9.1.x (diaudit 2026-07-08)
Hanya ada di 9.1+; cabang versi bila daftarkan (jangan register di 1.7/8/9.0 — hook tak dikenal).
- `actionModuleEnable` / `actionModuleDisable` / `actionModuleUpgradeAfter` — lifecycle: setelah module di-enable/disable/upgrade.
- `actionConfigurationUpdateValueBefore` — sebelum `Configuration::updateValue()` dipanggil.
- `displayModalContent` (theme Hummingbird) — inject konten ke container modal.

**Catatan Hummingbird (default theme instalasi baru 9.1):** `displaySearch` **dihapus** (bukan sekadar deprecated) — jangan andalkan untuk 9.1+. `displayOrderDetail` menggantikan variable hook `$HOOK_DISPLAYORDERDETAIL`. Detail → [[breaking-changes-9]].

## Hook umum per fungsi e-commerce
- Upsell/cross-sell: `displayProductAdditionalInfo`, `displayShoppingCartFooter`, `displayFooterProduct`.
- Abandoned cart: `actionCartSave`.
- Loyalty/poin: `actionValidateOrder`, `actionOrderStatusUpdate`.
- Banner/marketing: `displayHome`, `displayHeader`.
- JS/CSS front: `actionFrontControllerSetMedia`.
- GDPR: `actionDeleteGDPRCustomer`, `actionExportGDPRData`, `registerGDPR`.
- Pembayaran: `paymentOptions` (1.7+).
- Carrier: `actionCarrierProcess`, `displayCarrierExtraContent`.

Katalog penuh fungsi→hook → [[function-catalog]]. Pola → [[cross-version-patterns]].

Sumber: devdocs.prestashop-project.org concepts/hooks.
