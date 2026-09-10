# Konteks module bankwire

Diseed 2026-09-08 dari inventaris ps-module-inventory + sesi workflow psm. Diperbarui 2026-09-09 oleh psm-develop.

## Konvensi module
_Konvensi khusus module ini: namespace, layout service, prefix tabel, kesepakatan tim._
_Yang benar untuk PrestaShop umum TIDAK ditulis di sini — rujuk `[[cross-version-patterns]]`,
`[[persistence]]`, `[[services-di]]` di `tech/`._

## Keputusan
_Butir bertanggal: keputusan yang diambil dan alasannya._

## Fakta terkonsiliasi
_Milik `ps-module-context.py` (claim/drop). Jangan sunting tangan._
- Fakta: kind=file key=mails/_core_restore/core-8.html status=live sejak=2026-09-08 oleh=psm-develop
- Fakta: kind=file key=upgrade/upgrade-1.0.6.php status=live sejak=2026-09-08 oleh=psm-develop
- Fakta: kind=file key=mails/en/bankwire_multibank.html status=live sejak=2026-09-08 oleh=psm-develop

## Jurnal
_Milik `ps-module-context.py` (note), append-only. Jangan sunting tangan._
- (vonis by psm-validate) Validasi penuh 4 lapis (1.7.8/8.1/9.1): pass=false, ready=false. Lapis 1 bersih, Lapis 2 install ok + phpstan 0 (advisory) di ketiga core asli, Lapis 4 chromium pass dgn 12 authored assertion/versi (e2e_smoke_only=false). PEMBLOKIR tunggal dari Lapis 3: adv-core-mail-template-clobber — copyMailTemplates() menimpa mails/<iso>/bankwire.html|txt milik CORE (template OrderState 10 PS_OS_BANKWIRE, pemiliknya ps_wirepayment), Mail::getTemplateBasePath memilih root sebelum folder module jadi file tertimpa itu yang dikirim, uninstall tak memulihkan; email order ps_wirepayment mengirim placeholder mentah {bankwire_bank}. Diverifikasi di container 9.1.4 (image bersih vs terpasang). Plus 5 warning: order-state hijack, order lahir tanpa peta bank di jalur catch, ObjectModel::update(array('icon')) sebenarnya null_values=true, GET_LOCK lewat getValue() ber-cache jadi no-op, signing key shop-scoped jatuh ke sha1 deterministik di multistore. GAP RUNNER (bukan cacat module): checkout-with-bank.json dilewati — aksi select & wait_for_text tak didukung ps-e2e-run.
- (decision by psm-develop) psm-develop 1.0.6: pemblokir adv-core-mail-template-clobber TERTUTUP & bertahan 3 ronde (md5 file email core identik sebelum/sesudah install di 1.7.8/8.1/9.1) — module tak lagi merusak ps_wirepayment permanen. TAPI cap 3 percobaan verifikasi TERCAPAI dengan pass=false (2 error/8 warning), loop DIHENTIKAN. AKAR yang belum disentuh & butuh keputusan Budi: module memakai ps_configuration sbg sumber kebenaran kepemilikan OrderState, padahal ps_order_state tak berdimensi toko sementara ps_configuration berdimensi toko, dan ps_order_state.module_name='bankwire' adalah sumber yang jauh lebih otoritatif tapi tak pernah dipakai primer. Konsolidasi state tanpa migrasi order selalu menelantarkan satu populasi. Arah disarankan (BELUM diterapkan): ps_order_state jadi sumber kebenaran, ps_configuration turun jadi cache, konsolidasi wajib memindahkan ps_orders.current_state + ps_order_history. Backup pra-perubahan ada di scratchpad sesi; modules/ belum ter-track git.
- (decision by psm-develop) SESI BERHENTI atas keputusan Budi (cap 3/3, ronde-8: 4 error/8 warning). TERBUKTI TERTUTUP & bertahan: (1) pemblokir clobber template email core, (2) akar kepemilikan OrderState — ps_order_state.module_name jadi sumber kebenaran, konsolidasi memindahkan order (STRANDED=0), (3) order pra-1.0.6 dapat rekeningnya sendiri & order ps_wirepayment tak tersentuh, (4) tombol Reset BO tak lagi menelantarkan order (ditekan sungguhan lewat HTTP di 3 versi). BELUM DIVERIFIKASI L3: catch(Throwable) utk Error PHP8, send_email dipulihkan di kedua cabang adopsi, peta order dikembalikan ikut DROP. KEPUTUSAN SKEMA MENUNGGU: bankwire_order perlu SNAPSHOT detail bank saat order dibuat supaya riwayat tak bergantung id rekening — menutup peta yatim/bank salah + riwayat hilang saat Reset + email order lama tanpa nama bank sekaligus. PELAJARAN: mempertahankan peta sementara tabel rekening di-DROP JUSTRU LEBIH BERBAHAYA (AUTO_INCREMENT reset -> order lama menampilkan bank yang belum ada saat dibuat); sudah dikembalikan. Sesi berikutnya WAJIB konteks bersih.

## Ringkasan
_Opsional, dikurasi psm-agent-expert. Tak dibaca workflow._

Sumber: sesi workflow psm + inventaris ps-module-inventory.py; pengetahuan PrestaShop umum di `tech/`.
