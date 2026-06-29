# Cek Adversarial Fungsi E-commerce

Pertanyaan tajam untuk mengkritik module sebelum dianggap matang (teknik dari review-adversarial, dikhususkan e-commerce). Diseed 2026-06-29; tambah saat menemukan kelemahan baru.

## Keamanan & integritas
- Harga/diskon dihitung server-side? CartRule API, bukan JS klien (risiko manipulasi)?
- Input front controller divalidasi & di-escape? CSRF token pada aksi tulis?
- Smarty variabel di-escape? → [[validator-rules]].

## Cross-version
- Tiap area legacy/modern punya cabang `_PS_VERSION_`? Tak ada API dihapus tanpa cabang? → [[breaking-changes-8]], [[breaking-changes-9]].
- Hook yang dipakai masih ada di semua versi target?
- Lolos psm-validate di 1.7/8/9?

## Data & skala
- Tabel pakai ObjectModel + SQL install (bukan doctrine schema)? Migrasi via upgrade script? → [[persistence]].
- `id_shop` disimpan (multistore)? Field lang (multilang)?
- Query efisien? Index di kolom yang difilter? N+1 di loop hook display?

## E-commerce / UX
- Fungsi menangani edge: cart kosong, stok 0, produk dihapus, customer tamu vs login?
- Multicurrency: harga diformat via `Tools::displayPrice` / context currency?
- Gagal anggun bila dependency/config belum diset?

## Kepatuhan & operasional
- Simpan data pelanggan → support GDPR export/hapus/anonimisasi?
- Merchant bisa kelola dari BO? Aksi berat pakai cron/CLI, bukan request front?
- Uninstall bersih (hapus tabel/config/hook)?

Pakai sebelum module dianggap selesai; temuan jadi backlog perbaikan.
