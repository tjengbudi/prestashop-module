# Kontrak review adversarial e-commerce (Lapis 3)

Kontrak WAJIB untuk Lapis 3 psm-validate — berlaku di **setiap** run. Lapis ini dikerjakan
**inline oleh psm-validate sendiri**, tak didelegasikan ke peninjau lain: empat lensa
dikerjakan satu per satu dan tiap lensa ditulis ke file sebelum lensa berikutnya mulai
("Prosedur inline" di bawah). File ini memegang sikap, lensa, prosedur, dan bentuk
kembalian yang ditegakkan skrip agregat.

**Konteksmu tidak bersih.** Kamu sudah melihat — atau akan melihat — hasil Lapis 1/2/4 di
run yang sama, dan pindai hijau membaca dirinya sebagai bukti sehat. Yang melawan bias itu
prosedur di bawah, bukan niat baik; dan ringkasan run **wajib menyebut** review dikerjakan
inline.

`{project-root}/_bmad/psm/memory/ecommerce/adversarial-checks.md` (bila ada) MENAMBAH
pertanyaan domain di atas ini; ia tak pernah menggantikan kontrak di bawah.

Sikap: **skeptis, berasumsi ada yang salah**. Yang dicari adalah cacat yang LOLOS pindai
statis dan LOLOS install di core asli — yaitu yang hanya kelihatan lewat penalaran atas
alur bisnis, bukan pencocokan pola.

## Empat lensa inti

**Keamanan transaksi.** Validasi input order/pembayaran; SQL injection; CSRF; harga atau
diskon yang bisa dimanipulasi dari sisi klien.

**Edge case cart/order/stock.** Stok negatif; race saat checkout; mata uang, pajak,
multistore; status order yang tak konsisten.

**Kompatibilitas lintas versi.** Perilaku yang diam-diam berbeda antar 1.7/8/9 walau
lolos pindai statis — mis. API yang masih ada tapi semantiknya bergeser, default yang
berubah, atau hook yang dipanggil pada titik siklus hidup berbeda.

**Performa.** Query di dalam loop; hook berat; ketiadaan cache pada jalur yang sering
dilewati.

## Prosedur inline (higiene konteks)

Isolasi subagent tak ada di sini, jadi higienenya ditegakkan urutan kerja dan file — bukan harness.

1. **Kapan.** Sekali per run, lintas versi, sebagai langkah **pertama Fase 2**: setelah source
   berhenti dipatch (patch Fase 1 membasikan review) dan **sebelum** kamu membaca hasil lapis
   lain di fase itu, termasuk output sweep-nya. Plan menandai adversarial `reuse`? Jangan
   tinjau ulang. Terlanjur membaca hasil lapis lain? Tetap kerjakan sekarang — jangan ditunda
   ke akhir — dan sebut itu di ringkasan.
2. **Satu lensa, satu pass.** Buka source hanya dengan pertanyaan lensa yang sedang jalan,
   urut: keamanan transaksi → edge case cart/order/stock → kompatibilitas lintas versi →
   performa. Lensa berikutnya mulai **hanya setelah** lensa sekarang tuntas ditulis.
3. **Tulis, lalu lepaskan.** Selesai satu lensa: read-merge ke
   `<psm_reports_dir>/<module>-adversarial.json` — baca `findings` yang ada (di situ bisa sudah
   ada cacat visual Lapis 4), tambahkan milikmu, tulis balik sebagai JSON utuh berbentuk persis
   di bawah (file belum ada → buat). Lalu **jangan bawa kutipan source lensa itu ke lensa
   berikutnya**: file itu ingatan lapis ini, konteksmu bukan.
4. **Bukti, bukan ingatan.** Tiap temuan wajib `location` file:line yang kamu baca di pass itu.
   Tak bisa menunjuk barisnya = belum ditemukan; jangan ditulis.
5. **Pindai hijau bukan bukti sehat.** Dilarang menurunkan `severity` atau membatalkan temuan
   karena Lapis 1/2/4 lolos — yang dicari lapis ini justru cacat yang lolos mereka.
6. **`versions` top-level digabung (union)**, tak pernah dipersempit: mempersempit cakupan yang
   sudah tertulis di file membuang temuan penulis lain lewat filter cakupan agregat.

## Bentuk kembalian (HANYA JSON ini, tanpa prosa)

```json
{"versions": ["<versi yang kamu TINJAU — token sama dengan versi target yang diberikan>"],
 "findings": [
  {"id": "adv-<slug>",
   "severity": "error|warning",
   "message": "<apa yang salah>",
   "location": "<file:line>",
   "fix": "<perbaikannya>",
   "versions": ["<versi TERPENGARUH, token sama dengan versi target yang diberikan; kosongkan bila semua target>"]}
]}
```

Aturan kembalian yang ditegakkan skrip agregat (pelanggaran = exit 2, bukan vonis):

- `versions` top-level **wajib ada** dan berisi minimal satu versi (string tak kosong).
- `severity` hanya `error` atau `warning`. Token lain (`critical`, `high`, `blocker`)
  ditolak — dan seandainya lolos, tak akan pernah memblok.
- Tiap entri `versions` harus resolve ke salah satu versi target: tulis sebagai string
  (`"8.1"`, atau bentuk major `"8"`), bukan angka. Bentuk major menjangkau semua minor
  di bawahnya; bentuk minor **tidak** menjangkau minor tetangganya — `"9.0"` tak lagi
  ikut memblok 9.1 (dan sebaliknya), jadi batasi ke minor hanya bila memang khas minor itu.
- `findings` harus list of object.

`versions` top-level = cakupan yang kamu tinjau (beda dari `versions` per temuan =
versi terpengaruh). Nyatakan JUJUR: versi yang tak kamu tinjau ditandai **tak konklusif**
oleh agregat dan menjatuhkan `ready` — itu memang jawaban yang benar, dan jauh lebih baik
daripada vonis "siap rilis" atas review yang tak pernah terjadi. Cakupan yang lebih luas
dari target satu run tetap sah (review penuh boleh dipakai ulang di run yang dipersempit);
`ps-plan-layers.py` memakainya untuk tahu file ini masih mencakup versi yang diminta.
