# Persistence (data) lintas versi

Diseed 2026-06-29 dari katalog cross-version + riset devdocs doctrine.

## Pilihan
- **ObjectModel** — aman SEMUA versi (1.7/8/9), default untuk maksimal kompatibilitas. Definisikan `$definition`, buat tabel via SQL di `install()`.
- **Doctrine** (PrestaShop pakai 2.15) — hanya target ≥1.7.6 + konteks modern. Entity di `src/Entity/`, auto-scan untuk module terinstall, butuh namespace via composer.
- **Db::getInstance() + DbQuery** — aman lintas versi untuk query langsung.

## Aturan Doctrine
- **JANGAN pakai doctrine schema tool untuk bikin tabel** — bikin FK tak kompatibel struktur PrestaShop. Bikin tabel via SQL install. Boleh `doctrine:schema:update --dump-sql` untuk generate SQL saja.
- Mapping annotation (`@ORM\Entity`, `@ORM\Table`, `@ORM\Column`). PS9/Symfony 6.4: annotation tetap jalan, cek deprecation; pertimbangkan atribut PHP 8.
- Konvensi nama tabel: CamelCase class → snake_case + prefix `ps_` (ProductComment → ps_product_comment).
- Akses: `container->get('doctrine.orm.entity_manager')` → `persist()` + `flush()`; repository `getRepository()` (magic `findByX`).

## Aturan aman cross-version
- Module sederhana → ObjectModel. Butuh ORM & target tanpa 1.7 lawas → Doctrine, tapi satu jalur, jangan campur untuk entity yang sama.
- Tambah kolom ke tabel existing → SQL `upgrade/upgrade-x.y.z.php`, jangan ubah `$definition` tanpa migrasi.
- Selalu simpan `id_shop` untuk multistore; `Shop::getContextShopID()`.

Pola → [[cross-version-patterns]], [[services-di]]. Fungsi → [[function-catalog]].

Sumber: devdocs.prestashop-project.org/9/modules/concepts/doctrine.
