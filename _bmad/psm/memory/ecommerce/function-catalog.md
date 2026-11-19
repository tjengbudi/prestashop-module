# Katalog Fungsi E-commerce

Katalog lengkap (fungsi → hook → persistensi, per tujuan bisnis) hidup di `<skills-dir>/psm-develop/references/ecommerce-function-catalog.md` (`<skills-dir>` = direktori install skill psm-*). File ini = pointer + index agar tak duplikasi. Diseed 2026-06-29.

Pasangkan dengan [[cross-version-patterns]] (cara aman) dan [[hooks]] (hook per fungsi).

## Kelompok fungsi (lihat katalog untuk detail hook/data)
- **Konversi/AOV:** upsell/cross-sell, abandoned cart, countdown/stok rendah, free-shipping bar, exit-intent popup.
- **Retensi:** loyalty/poin, wishlist, reorder, notifikasi restock.
- **Katalog & penemuan:** faceted filter, badge produk, swatch varian, quick view.
- **Checkout & pembayaran:** metode pembayaran (`paymentOptions`), carrier, kustomisasi checkout, diskon dinamis (CartRule — JANGAN hitung harga di klien). Termasuk **keluarga pembayaran manual/offline → semi-otomatis**: transfer manual → instruksi & rekening dinamis → nominal unik → bukti bayar → moderasi admin → QR statis/dinamis → callback → auto-cancel → rekonsiliasi → refund.
- **SEO:** meta/JSON-LD structured data, sitemap/canonical, rich snippet review.
- **Marketing:** banner terjadwal, email campaign, segmentasi, popup first-order.
- **Analytics:** event tracking GA4/pixel (hormati consent), dashboard KPI, export CSV.
- **Multi-*:** konten per toko (`id_shop`), terjemahan UI, format mata uang.
- **GDPR:** consent banner & log, anonimisasi (WAJIB bila simpan data pelanggan).

## Lensa adjacency (memperdalam module dalam domainnya sendiri)
Kelompok di atas untuk maksud yang masih terbuka. Untuk "perkaya module ini" (tetap satu topik), kenali domain module dari bukti inventaris lalu gali lima arah: varian → kelengkapan alur → otomasi langkah manual → visibilitas → ketahanan & kepatuhan. Detail aturannya di katalog.

## Aturan menambah fungsi ke module existing
- Jangan ubah `$definition` ObjectModel tanpa migrasi; tambah kolom via `upgrade/upgrade-x.y.z.php`. → [[persistence]].
- Daftarkan hook baru di `install()` DAN sediakan upgrade script agar module terpasang ikut mendaftar.
- Fungsi yang menyentuh area legacy/modern → cabang versi.
- Fungsi yang simpan data pelanggan → pertimbangkan GDPR.

Pertimbangan default: hook display/action + ObjectModel + Configuration (aman semua versi). Pertimbangkan multistore, multilang, GDPR sejak awal.

## Verified additions 2026-11-18 `[core]`

Re-seeded in project `whatsappchat` (its copy carries the extended index with hook/persistence anchors and version tags per entry). Only genuine gaps are recorded here; the skill catalog stays canonical.
- Three function families the `psm-develop` catalog does not cover, each anchored in core hooks:
  - **Messaging / notifications** (chat, WhatsApp, e-mail/SMS alerts): `actionValidateOrder`, `actionOrderStatusUpdate`, `actionCartSave`, `actionObject*Update`, plus a tokened `ModuleFrontController` for cron/webhook entry; per-block schedule and display rules belong in module tables, global toggles in `Configuration`. `[all]`
  - **Marketplace / multi-vendor**: order splitting and vendor scoping ride `actionCarrierProcess` + `OrderHistory::changeIdState`, uploads for proof/voucher, and BO grid actions; beware `displayAdminOrderMain` / `displayAdminOrderSide` vs `displayAdminOrder` (1.7.7+) → [[breaking-changes-9]].
  - **B2B / quote-to-order**: cart rules for negotiated prices (server-side only), `paymentOptions` for invoiced/offline payment, customer-group scoping via `Configuration` + group tables.
- Adding any of these to an existing module still follows the rules at the end of this file: new hook registered in `install()` **and** in an upgrade script so already-installed shops pick it up.
