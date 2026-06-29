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
