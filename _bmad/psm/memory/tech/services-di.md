# Services / Dependency Injection lintas versi

Diseed 2026-06-29 dari katalog cross-version + riset devdocs.

- Akses service core berbeda antar versi & konteks. Untuk portabilitas pakai `prestashop/module-lib-service-container` (library resmi) — akses service seragam lintas versi.
- Definisi service module:
  - Symfony modern: `config/services.yml`.
  - Legacy container per konteks: `config/admin/services.yml` & `config/front/services.yml` (+ Doctrine).
  - Wildcard resource WAJIB exclude `index.php`.
- Override service core berisiko lintas versi (nama service berubah). Prefer **decorate** daripada override; pakai sehemat mungkin.
- `Context` singleton dipecah jadi service di PS9 (`EmployeeContext`, `ShopContext`, dll). Baca masih aman via `Context::getContext()` lintas versi; tulis auth pakai jalur modern PS9 (cabang versi). → [[breaking-changes-9]].
- Doctrine entity manager: `$this->container->get('doctrine.orm.entity_manager')`. → [[persistence]].

Pola → [[cross-version-patterns]].

Sumber: devdocs.prestashop-project.org concepts/services, core-updates/9.0.

## Verified additions 2026-11-18 `[core]`

Verified inside the pinned flashlight images (1.7.8.11 / 8.1.6-nginx / 9.1.4-nginx).
- `Module::getServices()` and `presetStaticServices()` are **not core** — zero matches in `classes/module/Module.php` on all three tags. What exists everywhere is `Module::getContainer()` and `Module::get()`.
- Core's own `ServiceLocator` lives at `src/Adapter/ServiceLocator.php`; core callers pass a **FQCN string** (`ServiceLocator::get('\PrestaShop\PrestaShop\Core\ConfigurationInterface')`), not a `'service.container'` id. That is exactly why the portable route above is the PrestaShopCorp `prestashop/module-lib-service-container` rather than a core locator.
- `PrestaShop\PrestaShop\Core\Hook\HookDispatcherAwareTrait` is gone in 9.1.4 (present 1.7.8 & 8.1) — inject `HookDispatcherInterface` yourself instead of relying on the trait. → [[hooks]]
- In 9, modern Symfony controllers must be services and `$this->get('svc')` only works through a deprecated `FrameworkBundleAdminController` hack (removed in 10); the module main file keeps `get()`/`getContainer()`, so a legacy single-file module is unaffected as long as it does not extend a Symfony controller.
