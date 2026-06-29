# Katalog Fungsi E-commerce

Katalog lengkap (fungsi → hook → persistensi, per tujuan bisnis) hidup di `{project-root}/skills/psm-develop/references/ecommerce-function-catalog.md`. File ini = pointer + index agar tak duplikasi. Diseed 2026-06-29.

Pasangkan dengan [[cross-version-patterns]] (cara aman) dan [[hooks]] (hook per fungsi).

## Kelompok fungsi (lihat katalog untuk detail hook/data)
- **Konversi/AOV:** upsell/cross-sell, abandoned cart, countdown/stok rendah, free-shipping bar, exit-intent popup.
- **Retensi:** loyalty/poin, wishlist, reorder, notifikasi restock.
- **Katalog & penemuan:** faceted filter, badge produk, swatch varian, quick view.
- **Checkout & pembayaran:** metode pembayaran (`paymentOptions`), carrier, kustomisasi checkout, diskon dinamis (CartRule — JANGAN hitung harga di klien).
- **SEO:** meta/JSON-LD structured data, sitemap/canonical, rich snippet review.
- **Marketing:** banner terjadwal, email campaign, segmentasi, popup first-order.
- **Analytics:** event tracking GA4/pixel (hormati consent), dashboard KPI, export CSV.
- **Multi-*:** konten per toko (`id_shop`), terjemahan UI, format mata uang.
- **GDPR:** consent banner & log, anonimisasi (WAJIB bila simpan data pelanggan).

## Aturan menambah fungsi ke module existing
- Jangan ubah `$definition` ObjectModel tanpa migrasi; tambah kolom via `upgrade/upgrade-x.y.z.php`. → [[persistence]].
- Daftarkan hook baru di `install()` DAN sediakan upgrade script agar module terpasang ikut mendaftar.
- Fungsi yang menyentuh area legacy/modern → cabang versi.
- Fungsi yang simpan data pelanggan → pertimbangkan GDPR.

Pertimbangan default: hook display/action + ObjectModel + Configuration (aman semua versi). Pertimbangkan multistore, multilang, GDPR sejak awal.
