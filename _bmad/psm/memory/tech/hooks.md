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

## Verified additions 2026-11-18 `[core]`

Re-seeded in project `whatsappchat`; everything below verified against real core inside the pinned flashlight images (1.7.8.11 / 8.1.6-nginx / 9.1.4-nginx), not documentation.
- `Module::isRegisteredInHook()` exists on all three targets — usable without a version branch.
- The hook alias API is **removed** in 8, not just deprecated: `Hook::getHookAliasList` / `Hook::getRetroHookName` present at 1.7.8.11, zero matches at 8.1.6 and 9.1.4. Line 9 of this file and the `mth-hook-alias` rule were both softened wording; the rule is now `error`. → [[validator-rules]]
- `PrestaShop\PrestaShop\Core\Hook\HookDispatcherAwareTrait` is present at 1.7.8.11 and 8.1.6 and **gone at 9.1.4** — a module using it fatals on 9 and no rule caught it before 2026-11-18. `src/Core/Hook/` at 9.1.4 = `Hook.php`, `HookDescription.php`, `HookDispatcher(Interface).php`, `HookInterface.php`, `HookModuleFilter(Interface).php`, `Extractor/`, `Generator/`, `Provider/`.
- `Translate::getAdminTranslation` present 1.7.8 & 8.1, gone in 9 → `$this->trans('Text', 'Domain.Sub')`, `transCount()` for plurals.
- `ajaxDie()` present 1.7.8 & 8.1, gone in 9 → `return new JsonResponse([...])`, or `echo json_encode($d); exit;` in a legacy controller.
- The version-branch registration snippet above is the right shape for the 9.1-only hooks it lists; the same branch is mandatory because registering an unknown hook on 1.7/8/9.0 leaves a dead row.
