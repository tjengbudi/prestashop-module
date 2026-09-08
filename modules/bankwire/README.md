# Bankwire (multi-bank)

## Tentang

Terima pembayaran lewat transfer bank ke **banyak rekening** yang bisa Anda tambah,
hapus, aktif/nonaktifkan, dan urutkan secara dinamis dari back office — masing-masing
dengan icon, detail rekening, dan catatan informatif per bahasa sendiri.

Berbeda dari modul wire transfer bawaan (satu rekening global), Bankwire menyimpan tiap
rekening sebagai entitas tersendiri. Saat checkout, pelanggan memilih bank tujuan; halaman
konfirmasi dan email menampilkan rekening yang benar-benar ia pilih untuk order itu.

## Fitur

- **Multi-rekening dinamis** — CRUD bank dari admin (nama, pemilik, detail, alamat, icon).
- **Aktif/nonaktif + urutan** — kontrol bank mana yang tampil di checkout dan urutannya.
- **Catatan per bank, multibahasa** (`custom_text`) — instruksi khusus per bank
  (mis. "BCA proses instan", "Jenius 1×24 jam kerja"), satu teks per bahasa toko.
- **Masa reservasi hybrid** — default global (`BANKWIRE_RESERVATION_DAYS`, default 7 hari)
  yang bisa di-override per bank; bank yang diset 0 mengikuti default global.
- **Email transfer** — instruksi pembayaran dikirim per bank (EN/ID), termasuk email
  saat status order berubah, dalam bahasa order pelanggan.
- **Aman multistore** — rekening terisolasi per toko (tabel `bankwire_account_shop`).

## Kompatibilitas

PrestaShop: **1.7.7.0** atau lebih baru — tervalidasi di **1.7.8**, **8.1**, dan **9.1**.

## Kompatibilitas multistore

Modul kompatibel dengan multistore. Setiap rekening dikaitkan ke toko pada konteks saat
dibuat, dan hanya tampil (di admin maupun checkout) untuk toko yang terkait — sehingga
tiap toko bisa punya daftar bank sendiri.

## Cara menguji

1. **Aktifkan modul** dan set minimal satu mata uang (Modules > Bankwire > konfigurasi).
2. **Tambah beberapa bank** lewat "Tambah rekening bank": isi nama, pemilik, detail
   rekening; unggah icon (jpg/png/gif); isi catatan per bahasa bila perlu; set masa
   reservasi (0 = ikut default global).
3. **Setting global** di atas daftar bank: atur masa reservasi default.
4. **Front office** — mulai checkout dengan mata uang yang diizinkan: tiap bank aktif
   muncul sebagai opsi pembayaran (dengan icon). Bank nonaktif tidak muncul.
5. **Pilih satu bank** → detail rekening + catatan bank tampil. Selesaikan order.
6. **Halaman konfirmasi** menampilkan rekening bank yang dipilih + catatannya, dan email
   konfirmasi berisi instruksi transfer bank tersebut.

## Analisis statis (PHPStan)

Config PHPStan lintas versi tersedia di `tests/phpstan/`. Jalankan terhadap core
PrestaShop asli (butuh Docker):

```bash
./tests/phpstan.sh 1.7.8   # atau 8.1 | 9.1
```

Skrip mem-mount modul ke dalam image `prestashop/prestashop-flashlight` versi terkait dan
menjalankan `phpstan analyse` dengan extension resmi PrestaShop (`ps-module-extension.neon`).

## Basis data

Modul membuat tabel berikut saat install (dihapus saat uninstall):

- `bankwire_account` — data rekening (nama, pemilik, detail, alamat, icon, aktif, posisi,
  reservation_days).
- `bankwire_account_lang` — catatan `custom_text` per rekening per bahasa.
- `bankwire_account_shop` — asosiasi rekening ↔ toko (isolasi multistore).
- `bankwire_order` — pemetaan order → rekening yang dipilih pelanggan.

## Lisensi

Academic Free License 3.0 (AFL-3.0).
