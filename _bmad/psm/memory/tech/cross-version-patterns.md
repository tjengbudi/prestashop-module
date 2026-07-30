# Pola Cross-Version (1.7.x / 8.x / 9.x)

Sumber lengkap: `{project-root}/.claude/skills/psm-cross-version/references/version-safe-patterns.md`.
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

## Batas versi minor: 9.0 vs 9.1 (target default kini 9.1)

9.1 janji BC dengan 9.0, jadi jarang perlu cabang `version_compare` baru. Yang menggigit adalah **theme**: instalasi baru 9.1 default ke Hummingbird (Bootstrap 5), upgrade dari 9.0 tetap Classic (Bootstrap 4). Satu module bisa ketemu keduanya di major yang sama — jangan asumsikan theme dari nomor versi. Daftar penuh → [[breaking-changes-9]].

- **Jangan hardcode nama theme.** `Theme::getDefaultTheme()` tak lagi return `"classic"` di 9.1 — kini dari config. Baca dinamis; nama theme hardcoded = error Validator 9.1+.
- **Template yang menargetkan Hummingbird wajib direview**: Bootstrap 4.0.0-alpha.5 → 5.3.3. Kelas berubah masif (`.no-gutters`→`.g-0`, `.ml-*/.mr-*`→`.ms-*/.me-*`, `.custom-control`→`.form-check`, `.btn-block`→`.d-grid`, `.badge-*`→`.bg-*`, `.sr-only`→`.visually-hidden`, `data-toggle`→`data-bs-toggle`). Markup yang jalan di Classic bisa ambruk diam-diam di Hummingbird — cacat layout, bukan error PHP; ketahuannya di Lapis 4 E2E, bukan di static scan.
- **`displaySearch` dihapus di Hummingbird** (di Classic masih ada, deprecated). Jangan andalkan untuk 9.1+; sediakan jalur lain bila fitur bergantung padanya.
- **`displayOrderDetail`** menggantikan variable hook `$HOOK_DISPLAYORDERDETAIL`.
- **jQuery deprecated** di Hummingbird (dihapus PS10). Untuk kode baru dorong Vanilla JS + Bootstrap 5 native, jangan tambah ketergantungan jQuery baru.
- **Hook 9.1-only** (`actionModuleEnable/Disable/UpgradeAfter`, `actionConfigurationUpdateValueBefore`, `displayModalContent`): cabang versi bila didaftarkan — tak dikenal di 1.7/8/9.0. Detail → [[hooks]].
- **Diskon baru & multi-shipment** di balik feature flag (default OFF, masih WIP) + skema DB berubah (`9.1.0.sql`). Module yang menyentuh promo/carrier: jangan bangun di atasnya sekarang, tapi hindari asumsi "satu order = satu shipment".
- PHP 8.5 didukung (8.1–8.4 tetap jalan) — `require.php` module tak wajib naik.

**Catatan gerbang:** static scan psm-validate memetakan versi ke major key (`1.7`/`8`/`9`), jadi aturan yang khas-9.1 belum bisa dipisahkan dari 9.0 di Lapis 1. Beda 9.0/9.1 dibuktikan di Lapis 2/4 (image `9.1.4-nginx`) atau review manual — jangan anggap Lapis 1 bersih berarti aman di Hummingbird.

## Checklist cross-version-safe
- [ ] `ps_versions_compliancy` range benar
- [ ] Tak ada dependency terlarang PS9 (atau dibundel)
- [ ] Tak ada kelas/method/konstanta/hook dihapus tanpa cabang versi
- [ ] Semua cabang pakai `_PS_VERSION_`/`version_compare`
- [ ] composer `prepend-autoloader: false`, autoload benar
- [ ] index.php tiap folder, Smarty di-escape
- [ ] Nama theme tak di-hardcode; template diuji di Classic **dan** Hummingbird bila target 9.1
- [ ] Lolos psm-validate di 1.7.x, 8.x, 9.x

Sumber: devdocs.prestashop-project.org (core-updates 8.0/9.0/9.1). Diseed 2026-06-29 dari katalog skill; bagian 9.0↔9.1 ditambah 2026-07-30 dari [[breaking-changes-9]] (audit 2026-07-08).
