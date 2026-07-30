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

- **Metode pembayaran** — implement `PaymentModule` / hook `paymentOptions` (1.7+, kembalikan objek `PaymentOption`). Untuk PS8/9 pastikan tak pakai API pembayaran lawas yang dihapus. Batasan currency/country/group diisi `PaymentModule::install()` (`$this->currencies`, tabel `module_currency`/`module_country`/`module_group`) — jangan tulis tabel itu manual.
- **Metode pengiriman / carrier** — `Carrier` + hook `actionCarrierProcess`, `displayCarrierExtraContent`.
- **One-page / kustomisasi checkout** — hook `displayPaymentTop`, `actionValidateOrder`. Hati-hati: alur checkout berubah antar versi.
- **Biaya/diskon dinamis** — `actionCartUpdateQuantityBefore`, CartRule API. JANGAN hitung harga di sisi klien (risiko manipulasi).

### Keluarga fungsi: pembayaran manual/offline → semi-otomatis

Tangga kematangan satu module pembayaran offline (bankwire-style). Tiap anak tangga
berdiri sendiri sebagai fungsi yang bisa ditambahkan, dan tiap yang di bawah jadi
prasyarat wajar bagi yang di atas. Dipakai saat memperdalam module pembayaran yang
sudah ada — lihat **Lensa adjacency** di bawah.

- **Transfer manual dasar** — `paymentOptions` menampilkan opsi offline; `PaymentModule::validateOrder()` membuat order pada `OrderState` custom "menunggu pembayaran". Buat `OrderState` di `install()`, simpan id-nya via `Configuration` (JANGAN hardcode id — beda per instalasi), hapus/nonaktifkan rapi di `uninstall()`.
- **Instruksi bayar & rincian rekening dinamis** — tampilkan nomor rekening/atas nama/catatan di halaman konfirmasi & email. Hook: `displayPaymentReturn` (halaman order-confirmation module pembayaran) + `displayOrderDetail`. Data: `Configuration` bila satu rekening, ObjectModel bila banyak rekening/bank. Multistore: kunci per `id_shop`; multilang: instruksi sebagai field lang.
- **Nominal unik / kode pembayaran per order** — tambahkan sedikit selisih atau kode referensi supaya mutasi bank bisa dicocokkan otomatis. Persistensi: ObjectModel transaksi (1 baris per order) — jangan tempel ke `$definition` Order. Hati-hati: nominal unik mengubah total yang dibayar, bukan total order — jangan tulis balik ke `Order::total_paid` (memecah akuntansi & invoice).
- **Bukti bayar (upload pelanggan)** — front controller module untuk terima file + form di halaman detail order. Simpan **di luar** web root atau di direktori ber-`.htaccess`/`index.php` penjaga; validasi ekstensi & MIME sisi server (`ImageManager`/`finfo`), tolak berdasar konten bukan nama; nama file di-generate, jangan pakai input pengguna. Persistensi: ObjectModel bukti (id_order, path, waktu, status). GDPR: bukti bayar = data pribadi → ikut `actionExportGDPRData`/`actionDeleteGDPRCustomer`.
- **Moderasi / konfirmasi admin** — panel di halaman order admin untuk approve/tolak bukti, lalu ubah status order. Hook: `displayAdminOrderMain`/`displayAdminOrderSide` (1.7.7+; `displayAdminOrder` legacy — verifikasi ketersediaannya per versi target sebelum dipakai). Transisi status lewat `OrderHistory::changeIdOrderState()`, jangan `UPDATE` tabel order langsung (melewati email, invoice, dan stok). Aksi approve/tolak wajib ber-token admin.
- **QR statis (mis. QRIS merchant)** — satu payload QR tetap untuk semua order; gambar diunggah admin atau payload di-render. Paling murah: tak butuh callback, rekonsiliasi tetap manual. Praktis = "transfer manual dengan instruksi berupa gambar", jadi tetap butuh anak tangga bukti bayar/konfirmasi.
- **QR dinamis / VA per order** — payload berisi nominal & referensi order, di-generate saat order dibuat. Rendering QR: pilih render sisi klien dari string payload (nol dependensi) atau library PHP yang di-vendor. Cross-version: `vendor/` milik module berisiko bentrok dengan autoload core lintas 1.7/8/9 — bila terpaksa mem-vendor, kunci versi & uji ketiga versi, dan pertimbangkan render sisi klien lebih dulu.
- **Callback / webhook gateway** — endpoint `ModuleFrontController` yang dipanggil server gateway (tanpa sesi pelanggan). Verifikasi keaslian lewat signature/HMAC dari gateway — token CSRF PrestaShop tak berlaku di sini. Wajib idempoten (callback bisa datang berkali-kali) dan jangan percaya nominal dari payload tanpa cek ulang ke order. Ubah status via `OrderHistory`, bukan tulis langsung.
- **Kedaluwarsa & auto-cancel** — batalkan order yang tak dibayar setelah N jam. PrestaShop tak punya scheduler inti: pakai front controller ber-token yang dipanggil cron eksternal (atau modul cronjob), bukan pemicu saat request pelanggan. Pengembalian stok mengikuti perilaku core saat transisi ke status batal — verifikasi dulu, jangan gandakan manual (risiko stok dobel).
- **Rekonsiliasi & pelaporan** — daftar order menunggu bayar vs bukti masuk vs terkonfirmasi; export CSV mutasi. Tab admin via `ModuleAdminController` (legacy, aman lintas versi) + HelperList/Grid. Sumber data: ObjectModel transaksi, bukan scraping tabel order.
- **Refund / pembatalan pasca-bayar** — untuk metode offline, refund adalah proses manual yang dicatat. Hook: `actionOrderSlipAdd`; artefaknya `OrderSlip`. Jangan bikin jalur refund sendiri yang tak terlihat di akuntansi core.

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

## Lensa adjacency (memperdalam module dalam domainnya sendiri)

Seksi-seksi di atas memetakan fungsi **lintas domain** — berguna saat maksud Budi
masih terbuka. Tapi permintaan "perkaya module ini" biasanya bermaksud lain:
tetap di satu topik, gali lebih dalam. Untuk itu jangan mencocokkan module ke
seluruh katalog; kenali domainnya lalu telusuri lima arah berikut.

Kenali domain module dari bukti inventaris, bukan dari namanya: hook terdaftar,
nama tabel ObjectModel, controller, dan `$this->tab`. Hook `paymentOptions` →
domain pembayaran; `actionCarrierProcess` → pengiriman; `displayHome` +
ObjectModel konten → marketing. Bila keluarga fungsi untuk domain itu sudah
dipetakan di atas (mis. **Keluarga fungsi: pembayaran manual/offline**), posisikan
module di tangga itu dan tawarkan anak tangga berikutnya.

Lima arah penggalian, urut dari yang paling murah:

1. **Varian dari yang sudah ada** — mekanisme sejenis dengan cara berbeda (transfer manual → QR statis → QR dinamis/VA). Titik sisip sama, logika beda.
2. **Kelengkapan alur** — langkah yang hilang di jalur yang sudah dilayani module (order dibuat, tapi bagaimana pelanggan memberi tahu sudah bayar? bagaimana admin memutuskan? apa yang terjadi bila tak pernah dibayar?). Ini biasanya yang paling terasa buat merchant.
3. **Otomasi langkah manual** — apa yang kini dikerjakan tangan tiap hari: pencocokan mutasi, ubah status satu-satu, kirim pengingat. Nominal unik, callback, auto-cancel hidup di sini.
4. **Visibilitas** — module bekerja, tapi merchant tak bisa melihat hasilnya: daftar rekonsiliasi, export, notifikasi. Murah dan sering diremehkan.
5. **Ketahanan & kepatuhan** — jalur gagal dan kewajiban: retry/idempotensi, refund, GDPR atas data yang module simpan, jejak audit perubahan status.

Aturan pakai lensa ini:

- **Kaitkan ke bukti, bukan angan.** Tiap fungsi yang ditawarkan sebut titik sisipnya di module ini (hook/ObjectModel/controller yang benar-benar ada di inventaris), atau sebut eksplisit bahwa ia butuh titik sisip baru.
- **Sebut prasyaratnya.** Anak tangga yang melompat (callback tanpa ObjectModel transaksi; moderasi tanpa bukti bayar) bukan satu fungsi — sebutkan urutannya, jangan sembunyikan biayanya.
- **Tandai yang menyentuh data existing.** Perluasan sedomain sering ingin menambah kolom ke tabel module yang sudah terpakai — itu perubahan bermigrasi, bukan penambahan murni. Angkat sebagai keputusan cakupan, jangan diam-diam masukkan rencana.
- **Tawarkan 3–5, jangan borong.** Lensa ini memperluas ruang ide; Budi yang memilih. Sertakan satu kalimat dampak bisnis per fungsi supaya pilihannya bisa dibuat.

## Aturan saat menambah fungsi ke module existing

- Jangan ubah `$definition` ObjectModel yang sudah dipakai tanpa migrasi (tabel existing). Tambah kolom via SQL upgrade (`upgrade/upgrade-x.y.z.php`).
- Daftarkan hook baru di `install()` DAN sediakan upgrade script agar module yang sudah terpasang ikut mendaftar.
- Setiap fungsi baru tetap pakai cabang versi bila menyentuh area legacy/modern.
- Setiap fungsi yang menyimpan data pelanggan → pertimbangkan GDPR.
