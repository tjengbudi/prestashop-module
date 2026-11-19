# Lensa Elicitation Fungsi E-commerce

Lensa untuk menggali kebutuhan saat brainstorm fungsi module (dipakai oleh references/brainstorm-ecommerce.md). Diseed 2026-06-29; perbarui saat pola baru terbukti berguna.

Saat Budi sebut maksud module, gali lewat lensa berikut — tawarkan, jangan paksakan:

- **Tujuan bisnis:** module ini menaikkan apa? Konversi, AOV, retensi, traffic, efisiensi operasional? → arahkan ke kelompok [[function-catalog]] yang relevan.
- **Tahap funnel:** menyentuh discovery, product page, cart, checkout, post-purchase, atau akun pelanggan? Hook berbeda per tahap → [[hooks]].
- **Fungsi pendamping yang lazim:** banner → +penjadwalan +segmentasi; loyalty → +tier +notifikasi; wishlist → +share +restock alert; checkout → +upsell +diskon dinamis.
- **Data & state:** butuh tabel (ObjectModel) atau cukup Configuration? Per-customer? Multistore/multilang? → [[persistence]].
- **Risiko versi:** fungsi menyentuh area yang berubah antar 1.7/8/9 (admin Symfony, payment, search)? Sebut eksplisit jalur aman → [[cross-version-patterns]].
- **Kepatuhan:** simpan data pelanggan → GDPR (export/hapus/anonimisasi). Hitung harga → server-side, jangan klien.
- **Operasional merchant:** siapa yang mengelola (config BO)? Perlu penjadwalan/cron? Perlu laporan?

Tujuan: dari satu kalimat maksud module → daftar fungsi konkret + pertimbangan teknis siap di-scaffold/develop.

## Verified additions 2026-11-18 `[core]`

- Recorded in project `whatsappchat` with the handoff format that makes an idea actionable for `psm-plan` / `psm-develop`: **candidate function → hook anchor → persistence anchor → cross-version note → effort**. Without the last three the next workflow has to re-derive them, and the idea loses the context that justified it.
- The five adjacency directions are quoted from the `psm-develop` catalog and stay there: varian → kelengkapan alur → otomasi langkah manual → visibilitas → ketahanan & kepatuhan. Use them for "perkaya module ini" (one topic); use the business lenses (konversi, AOV, retensi, effort) for open-ended exploration.
- `bmad-advanced-elicitation` owns the generic questioning technique — do not restate it here; only the e-commerce lens selection belongs to this file.
