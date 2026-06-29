# Pola Cross-Version (1.7.x / 8.x / 9.x)

Sumber lengkap: `{project-root}/skills/psm-cross-version/references/version-safe-patterns.md`.
File ini = ringkasan + pointer. Untuk *perbaikan* detail, rujuk file itu.

Prinsip inti: **deteksi versi saat runtime via `_PS_VERSION_` + `version_compare`, pilih jalur aman.** Jangan pakai API yang hilang di versi target tanpa cabang. Aturan pelanggaran konkret ada di [[validator-rules]].

## Fondasi
```php
if (version_compare(_PS_VERSION_, '8.0.0', '>=')) { /* PS8/9 modern */ }
else { /* 1.7.x legacy */ }
```
Bungkus jadi helper privat (`isPs8Plus()`), jangan sebar cek versi.

## Pilihan default paling portable
- **Persistence:** ObjectModel (aman semua versi). Doctrine hanya bila butuh ORM & target ≥1.7.6. Tabel SELALU via SQL di `install()`, jangan doctrine schema tool. Detail → [[persistence]].
- **Front logic:** `ModuleFrontController` (aman lintas versi).
- **Admin:** `ModuleAdminController` legacy + `getContent()` (paling portable). Symfony controller berubah besar di PS9. Detail → [[breaking-changes-9]].
- **Template:** Smarty `.tpl` via `$this->display(__FILE__, ...)`. Escape variabel.
- **Service akses:** `prestashop/module-lib-service-container`. Detail → [[services-di]].
- **Email:** `Mail::send` core (aman lintas versi).

## Checklist cross-version-safe
- [ ] `ps_versions_compliancy` range benar
- [ ] Tak ada dependency terlarang PS9 (atau dibundel)
- [ ] Tak ada kelas/method/konstanta/hook dihapus tanpa cabang versi
- [ ] Semua cabang pakai `_PS_VERSION_`/`version_compare`
- [ ] composer `prepend-autoloader: false`, autoload benar
- [ ] index.php tiap folder, Smarty di-escape
- [ ] Lolos psm-validate di 1.7.x, 8.x, 9.x

Sumber: devdocs.prestashop-project.org (core-updates 8.0/9.0). Diseed 2026-06-29 dari katalog skill.
