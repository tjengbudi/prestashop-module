# Katalog Fungsi E-commerce untuk Module PrestaShop

Peta fungsi yang umum ditambahkan ke toko PrestaShop, dikelompokkan per tujuan
bisnis, dengan pertimbangan teknis lintas versi. Dipakai untuk **menawarkan** ide
fungsi yang relevan dengan maksud module dan **merancang** implementasinya.

Pasangkan dengan pola teknis di
`<skills-dir>/psm-cross-version/references/version-safe-patterns.md`
(`<skills-dir>` = direktori install skill ini, tempat sibling psm-* berada;
cara aman pakai hook/service/persistence lintas 1.7/8/9). File ini = *fungsi apa*;
file itu = *cara aman membangunnya*.

Pertimbangan umum lintas versi: prefer **hook display/action** + **ObjectModel**
+ **Configuration** (aman semua versi). Hindari API yang dihapus PS8/9 (lihat
ruleset psm-validate). Pertimbangkan **multistore** (`Shop::getContextShopID`),
**multilang** (field lang di ObjectModel), dan **GDPR** sejak awal.

## Konversi (naikkan rasio beli & AOV)

- **Upsell / cross-sell** — produk terkait di halaman produk/cart. Hook: `displayProductAdditionalInfo`, `displayShoppingCartFooter`, `displayFooterProduct`. Data: relasi produk via ObjectModel atau query `accessories`.
- **Abandoned cart reminder** — email/notifikasi cart ditinggal. Hook: `actionCartSave`; cron/CLI untuk kirim. Persistensi: ObjectModel cart-snapshot.
- **Countdown / urgency & stok rendah** — pemicu urgensi di halaman produk. Hook: `displayProductPriceBlock`. Data: `StockAvailable`.
- **Free-shipping bar / progress** — "kurang Rpxx untuk gratis ongkir". Hook: `displayShoppingCartFooter`, `actionCarrierProcess`.
- **Exit-intent / popup promo** — JS front via `actionFrontControllerSetMedia` + hook `displayHeader`.

## Retensi (pembeli kembali)

- **Loyalty / poin** — akumulasi poin per order. Hook: `actionValidateOrder`, `actionOrderStatusUpdate`. Persistensi: ObjectModel poin + tabel transaksi.
- **Wishlist** — simpan produk favorit. Hook: `displayProductActions`; front controller untuk add/remove; ObjectModel wishlist (per customer, multishop-aware).
- **Reorder / "beli lagi"** — dari riwayat order. Hook akun pelanggan `displayCustomerAccount`.
- **Notifikasi restock** — daftar tunggu stok. Hook: `actionUpdateQuantity`; email saat stok kembali.

## Katalog & penemuan produk

- **Faceted/filter tambahan** — atribut filter custom. Integrasi dengan modul faceted search core; hook `actionProductSearchAfter`.
- **Badge produk** (baru/diskon/terlaris) — Hook: `displayProductListReviews`, `displayProductPriceBlock`. Logika dari Product/SpecificPrice.
- **Varian/swatch tampilan** — override template kombinasi; hati-hati Smarty vs assets modern.
- **Quick view** — modal detail produk via AJAX front controller.

## Checkout & pembayaran

- **Metode pembayaran** — implement `PaymentModule` / hook `paymentOptions` (1.7+). Untuk PS8/9 pastikan tak pakai API pembayaran lawas yang dihapus.
- **Metode pengiriman / carrier** — `Carrier` + hook `actionCarrierProcess`, `displayCarrierExtraContent`.
- **One-page / kustomisasi checkout** — hook `displayPaymentTop`, `actionValidateOrder`. Hati-hati: alur checkout berubah antar versi.
- **Biaya/diskon dinamis** — `actionCartUpdateQuantityBefore`, CartRule API. JANGAN hitung harga di sisi klien (risiko manipulasi).

## SEO

- **Meta & structured data** — Hook: `displayHeader` untuk JSON-LD. Multilang meta via ObjectModel lang.
- **Sitemap tambahan / canonical** — front controller; hati-hati URL rewriting per versi.
- **Rich snippet review/rating** — gabung dengan modul review.

## Marketing

- **Promo banner terjadwal** — Hook: `displayHome`, `displayHeader`. Configuration untuk jadwal; ObjectModel bila banyak banner. Multistore-aware.
- **Email campaign / newsletter hook** — `actionCustomerAccountAdd`, integrasi `Mail::send` (aman lintas versi).
- **Segmentasi pelanggan** — grup pelanggan + CartRule bertarget.
- **Pop-up diskon first-order** — JS + Configuration flag per customer/cookie.

## Analytics & pelaporan

- **Event tracking** (GA4/pixel) — Hook: `displayHeader`, `actionValidateOrder` (purchase event). Hormati consent GDPR.
- **Dashboard KPI module** — tab admin (`ModuleAdminController` legacy, aman lintas versi) + HelperList/Grid.
- **Export laporan** — CSV via controller; hindari API export lawas yang berubah.

## Multistore / multilang / multicurrency

- **Konten per toko** — selalu simpan `id_shop` di ObjectModel; baca `Shop::getContextShopID()`.
- **Terjemahan UI module** — `$this->trans(..., 'Modules.<Name>.<Domain>')`; file di `translations/` (PS8+ memindahkan path translation).
- **Harga/format mata uang** — `Context::getContext()->currency`, `Tools::displayPrice` (cek signature lintas versi).

## GDPR / legal

- **Consent banner & log** — integrasi modul GDPR resmi (`actionDeleteGDPRCustomer`, `actionExportGDPRData`, `registerGDPR`). Module yang menyimpan data pelanggan WAJIB mendukung export & hapus.
- **Anonimisasi data** — saat hapus customer, bersihkan data module terkait.

## Aturan saat menambah fungsi ke module existing

- Jangan ubah `$definition` ObjectModel yang sudah dipakai tanpa migrasi (tabel existing). Tambah kolom via SQL upgrade (`upgrade/upgrade-x.y.z.php`).
- Daftarkan hook baru di `install()` DAN sediakan upgrade script agar module yang sudah terpasang ikut mendaftar.
- Setiap fungsi baru tetap pakai cabang versi bila menyentuh area legacy/modern.
- Setiap fungsi yang menyimpan data pelanggan → pertimbangkan GDPR.
