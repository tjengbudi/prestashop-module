# Konteks module whatsappchat

Diseed 2026-11-12 dari inspeksi kode v2.0.9 (ps-module-inventory + baca whatsappchat.php). Diperbarui 2026-11-18 oleh psm-cross-version.

## Konvensi module
- **Fork vendor.** Module idnovate v2.0.9 dipelihara sendiri; suntingan langsung di file vendor, tapi upayakan jalur override/upgrade-safe supaya masih bisa dibandingkan dengan upgrade resmi.
- **Produksi cuma 8.1 dan 9.1.** 1.7 tidak jalan di produksi, jadi cabang `version_compare(_PS_VERSION_, '1.7', '<')`, folder `backward_compatibility/`, `views/js/whatsappchat16.js`, dan hook warisan 1.4–1.6 (`header`, `footer`, `leftColumn`, `extraLeft`, dst.) adalah dead path — jangan dipelihara, jangan ditiru untuk kode baru. `controllers/admin/AdminWhatsappChatController14.php` sudah DIHAPUS 2026-11-12; rujukan lamanya di `whatsappchat.php:793` ikut mati di cabang `<1.5`.
- **Satu funnel render.** Semua metode hook di `whatsappchat.php` tipis dan delegasi ke `displayBlock($hook)` (baris 612). Template widget FO yang benar-benar dirender: `views/templates/hook/template.tpl` (baris 744/747/767) — `views/templates/hook/widget.tpl` **yatim**, nol rujukan (dikonfirmasi 2026-11-18). Ubah tampilan di funnel/template itu, bukan di 57 metode hook.
- **Konfigurasi terbagi dua.** Global = 4 key `Configuration`: `WA_CHAT_MOBILE`, `WA_CHAT_MESSAGE`, `WA_BADGE_MESSAGE`, `WA_BADGE_POSITION`. Selebihnya per-blok di DB (`schedule`, `display_on`, `only_mobile`/`only_desktop`/`only_tablet`, `custom_css`/`custom_js`, `filter_by_customer`, `customers`, `countries`, `zones`, `languages`, `currencies`).
- **Tabel `_lang` tanpa ObjectModel.** `whatsappchatblock_lang` (`message`, `def_message`, `offline_message`, `offline_link`, `mobile_phone`) dan `whatsappchatblock_agent_lang` (`department`) diakses manual via `Db::getInstance()`, jadi tak terlihat inventaris — jangan disimpulkan tidak ada. Pola yang benar: `[[persistence]]`.
- **Penamaan baru:** prefix tabel `whatsappchat*`, class `WhatsappChat*`, controller admin `AdminWhatsappChat*`, aset di `views/{css,js,img}/`.
- **Terjemahan:** string disunting di `translations/id.php`, jangan di-hardcode di PHP/tpl.
- **`backward_compatibility/` tidak dibekukan** — boleh disentuh bila perlu, tapi itu lapisan 1.4–1.6, bukan tempat logika module.
- **Mobile_Detect sudah aman lintas versi** (terverifikasi 2026-11-12, bukan asumsi): tiga jalur include di `__construct` cocok dengan kelasnya — PS>=9 & `_TB_VERSION_` → `Detection\MobileDetect`/`MobileDetect`, PS 1.7/8 → `Mobile_Detect`; kedua pemakaian (`whatsappchat.php:653`, `1168`) bercabang benar, tanpa `new Mobile_Detect()` telanjang. Bukan titik rawan 9.1.
- **Tombol WA di grid BO = JS sisi-klien di atas hook legacy** (terverifikasi jalan di 1.7.8/8.1/9.1, 2026-11-18): `displayBackOfficeHeader` tetap di-dispatch core untuk halaman Symfony (`Layout/head_tag.html.twig:53`) maupun legacy (`LegacyLayout/head_tag.html.twig:57`), dan `Dispatcher::getController()` di halaman Symfony tetap mengembalikan nama controller legacy. Tapi injeksi tombolnya mencocokkan `table#order_grid_table` / `table#customer_grid_table` — markup yang tak dijamin core. probes BO WAJIB pakai token valid: tanpa token PS menyodorkan interstitial "Invalid token" (HTTP 200) yang bikin hook terlihat mati.

## Keputusan
- 2026-11-12 — Ganti `Tools::jsonEncode` → `json_encode` native di `AdminWhatsappChatController14.php`: `Tools::jsonEncode` sudah dihapus di PS8+ dan produksi kita 8.1/9.1; menggantinya murah dan menghapus satu jebakan upgrade.
- 2026-11-12 — `uninstallDb()` dibiarkan tanpa `DROP TABLE`: data blok, agen, dan terjemahannya harus selamat dari uninstall-reinstall, karena konfigurasi widget dianggap aset toko, bukan artefak install.
- 2026-11-12 — Target kerja 8.1 + 9.1 saja, 1.7 keluar dari produksi: cabang versi 1.4–1.6 tak usah dipelihara, jadi pemangkasan legal dan memang disengaja.
- 2026-11-12 — Gembok AJAX BO (`isBoLogged` + cek `employee->id`) diaktifkan dan `AdminWhatsappChatController14.php` dihapus: keduanya vektor PII anonim — `Controller::run()` memanggil `init()` sebelum `checkAccess()`, dan file warisan itu me-bootstrap core sendiri tanpa auth, jadi tetap hidup di 8.1/9.1 meski cabangnya mati. Ini temuan keamanan, bukan kepecahan versi.
- 2026-11-12 — Vonis `psm-validate` diterima apa adanya: 8.1 & 9.1 `ready` true, 1.7.8 `pass` tapi `ready` false karena satu assertion BO tak konklusif di firefox. Tidak dikecualikan via `--require`, tidak diulang dengan chromium-saja — 1.7 di luar produksi, jadi cakupan BO-nya sengaja dibiarkan tercatat sebagai celah, bukan ditutup-tutupi.

## Fakta terkonsiliasi
_Milik `ps-module-context.py` (claim/drop). Jangan sunting tangan._
- Fakta: kind=table key=whatsappchatblock status=live sejak=2026-11-12 oleh=psm-module-context catatan=ObjectModel WhatsappChatBlock; 1 baris = 1 blok widget (id_shop, id_hook, schedule, display_on, only_mobile/desktop/tablet, custom_css/js)
- Fakta: kind=table key=whatsappchatblock_agent status=live sejak=2026-11-12 oleh=psm-module-context catatan=ObjectModel WhatsappChatBlockAgent; agen per blok (nama, HP, gambar, jadwal)
- Fakta: kind=class key=WhatsappChatBlock status=live sejak=2026-11-12 oleh=psm-module-context catatan=classes/WhatsappChatBlock.php; tabel whatsappchatblock
- Fakta: kind=class key=WhatsappChatBlockAgent status=live sejak=2026-11-12 oleh=psm-module-context catatan=classes/WhatsappChatBlockAgent.php; tabel whatsappchatblock_agent
- Fakta: kind=file key=controllers/admin/AdminWhatsappChatController.php status=live sejak=2026-11-12 oleh=psm-module-context catatan=Konfigurasi blok (AdminWhatsappChat, renderForm di 799)
- Fakta: kind=file key=controllers/admin/AdminWhatsappChatAgentController.php status=live sejak=2026-11-12 oleh=psm-module-context catatan=CRUD agen (AdminWhatsappChatAgent)
- Fakta: kind=file key=controllers/admin/AdminWhatsappChatController14.php status=retired sejak=2026-11-12 oleh=psm-cross-version catatan=dihapus 2026-11-12: vektor PII anonim tanpa auth; cabang <1.5 mati di 1.7/8/9. Rujukan mati tersisa di whatsappchat.php:793 (dead branch)
- Fakta: kind=file key=backward_compatibility/backward.php status=live sejak=2026-11-12 oleh=psm-module-context catatan=Lapisan kompatibilitas 1.4-1.6 warisan; jangan disentuh sebagai kode module
- Fakta: kind=hook key=displayWhatsAppChat status=live sejak=2026-11-12 oleh=psm-module-context catatan=Hook custom module ini; titik render utama widget
- Fakta: kind=hook key=displayWhatsAppProductSocialButtons status=live sejak=2026-11-12 oleh=psm-module-context catatan=Hook custom module ini; tombol share WA produk
- Fakta: kind=hook key=displayHeader status=live sejak=2026-11-12 oleh=psm-module-context catatan=Daftar CSS/JS (whatsapp.css, jBox) lalu delegasi ke displayBlock
- Fakta: kind=hook key=displayFooter status=live sejak=2026-11-12 oleh=psm-module-context catatan=Render blok bottomWidth; di PS<1.7 juga echo (output dobel)
- Fakta: kind=hook key=displayBackOfficeHeader status=live sejak=2026-11-12 oleh=psm-module-context catatan=Aset admin
- Fakta: kind=hook key=displayBeforeBodyClosingTag status=live sejak=2026-11-12 oleh=psm-module-context catatan=Registrasi hanya PS>=1.7; injeksi markup penutup body

## Jurnal
_Milik `ps-module-context.py` (note), append-only. Jangan sunting tangan._
- (note by psm-module-context) Sesi pertama: artefak dibangun, 14 faktaLive terekonsiliasi (rc=0, tanpa drift), konvensi+3 keputusan ditulis; produksi 8.1/9.1, 1.7 dead path.
- (decision by psm-cross-version) Cross-version 1.7.8/8.1/9.1: C1 json_encode native, C2 gembok isBoLogged di AJAX init (bukti runtime: anonim = Permission denied), C3 hapus AdminWhatsappChatController14 + 3 spec e2e; pass 3 versi, ready 8.1+9.1 true, 1.7.8 false hanya karena login BO firefox tak konklusif.
- (note by psm-ideate) Ideate sesi 1: backlog .psm-ideas.md dibuat; hanya 'notifikasi-order-agen' disimpan (status dipilih, hook baru actionValidateOrder + tautan WA konteks order); 4 ide lain (pesan dinamis, lead capture offline, log klik, GDPR) tak disimpan ke backlog.
- (note by psm-ideate) Ideate sesi 2: 'routing-departemen-otomatis' (pakai field department agen) & 'pratinjau-bo-blok' (jalur $from_bo) disimpan dipilih; 'override-libur-tanggal' & 'masking-nomor-agen' tak disimpan; drift dipilih_tanpa_rencana utk notifikasi-order-agen (psm-plan belum jalan).
- (vonis by psm-validate) 2026-11-15 vonis psm-validate (target 8.1+9.1 saja, chromium+firefox): ready TRUE kedua versi — static 0 error (9.1 1 warning initContent), flashlight pass (phpstan 0 error, 77/79 warning advisory), e2e pass 8 assertion/versi tanpa findings/inconclusive, Lapis 3 11 temuan semua warning (7 baru: jam overnight mati, opsi hook Header tak pernah dirender, wa.me prefix 0 lokal, N+1 list BO, katalog penuh di form BO, Mobile_Detect per blok, {hook} tanpa id); Lapis 5 tak jalan (module tanpa tests/scenarios), 1.7.8 di luar cakupan run.
- (decision by psm-cross-version) Re-check cross-version 1.7.8/8.1/9.1 (2026-11-18): source identik dengan pohon vonis 2026-11-12 (diff *.php/*.tpl/*.js/*.xml kosong), scan 0 error di ketiga versi, sumbu PHP 7.2-8.4 bersih (nol each()/utf8_encode/interpolasi ${}/implisit-nullable; polyfill array_column terbenteng function_exists). Budi: vonis lama diterima apa adanya (ready 8.1+9.1 true, 1.7.8 false karena assertion BO firefox), C4 stub index.php .forgejo/ di-skip, verify_attempts tetap 2, nol suntingan.
- (note by psm-cross-version) Verifikasi 2 celah cakupan (2026-11-18) di 3 stack flashlight 1.7.8/8.1/9.1 dengan 1 blok bottomWidth + 1 agen: (1) widget FO benar-benar render — bar fixed bottom + popup jBox berisi agen + link wa.me, di Hummingbird 9.1 CSS/JS ter-bundle (theme-*.css, bottom-*.js; jQuery 3.7.1 & window.jBox ada), tanpa agen anchor jadi link wa.me langsung dan jBox tak dimuat (by design). (2) tombol WA grid BO jalan di ketiganya (orders 5/5, customers 4/2) termasuk halaman Symfony: displayBackOfficeHeader di-dispatch Layout/head_tag.html.twig:53 maupun LegacyLayout:57, getController()='AdminCustomers' via LegacyControllerContextProxy. Penyebab catatan lama salah: probe BO tanpa token kena interstitial 'Invalid token' (HTTP 200). Koreksi: views/templates/hook/widget.tpl yatim, hanya template.tpl yang dirender. Bukti: _bmad-output/psm-validate/probe-2026-11-18/*.png

## Ringkasan
WhatsApp Chat (idnovate v2.0.9) — fork yang dipelihara Budi. Widget WhatsApp dengan blok per-hook, agen per-blok, penjadwalan, segmentasi (grup pelanggan, negara, zona, bahasa, mata uang), plus kondisi mobile/desktop/tablet. Arsitektur warisan 1.4–1.6; yang benar-benar produksi 8.1 dan 9.1.

Sumber: sesi workflow psm + inventaris ps-module-inventory.py; pengetahuan PrestaShop umum di `tech/`.
