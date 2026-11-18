# Kontrak review adversarial e-commerce (Lapis 3)

Kontrak WAJIB untuk Lapis 3 psm-validate — berlaku di **setiap** run. Default: **empat
subagent reviewer paralel, satu per lensa**, masing-masing berkonteks bersih; orkestrator
hanya men-spawn, lalu menggabungkan kembalian mereka ("Delegasi" di bawah). Subagent tak
tersedia → orkestrator meninjau sendiri ("Fallback inline") dan **menyebutnya di ringkasan**.
File ini memegang sikap, lensa, prosedur, dan bentuk kembalian yang ditegakkan skrip agregat.

Yang dibeli delegasi adalah **konteks bersih**, bukan kecepatan: peninjau yang sudah melihat
hasil Lapis 1/2/4 membaca pindai hijau sebagai bukti sehat. Satu lensa per subagent membuat
tiap peninjau membuka source dengan SATU pertanyaan, tak tercampur temuan lensa lain.

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

## Aturan peninjau (berlaku untuk subagent maupun fallback)

1. **Bukti, bukan ingatan.** Tiap temuan wajib `location` file:line yang kamu baca sendiri.
   Tak bisa menunjuk barisnya = belum ditemukan; jangan ditulis.
2. **Pindai hijau bukan bukti sehat.** Dilarang menurunkan `severity` atau membatalkan temuan
   karena Lapis 1/2/4 lolos — yang dicari lapis ini justru cacat yang lolos mereka.
3. **Tetap di lensamu.** Cacat di luar lensa yang kebetulan terlihat boleh dicatat sebagai
   `warning`, tapi jangan berburu di luar lensa — itu tugas peninjau lain.

## Delegasi (default)

**Kapan.** Sekali per run, lintas versi, di awal **Fase 2** — setelah source berhenti dipatch
(patch Fase 1 membasikan review). Plan menandai adversarial `reuse`? Jangan spawn. Spawn
keempatnya **dalam satu giliran** supaya jalan paralel; selagi mereka bekerja, lanjutkan lapis
skrip Fase 2. Agregat **tak boleh** jalan sebelum keempat kembalian digabung.

**Isi prompt tiap subagent** — hanya ini, tak lebih:

- path module dan versi target (juga saat cakupan dipersempit);
- **nama lensanya** (satu dari empat di atas) dan perintah membaca file ini:
  sikap, lensa itu, "Aturan peninjau", dan "Bentuk kembalian";
- `{project-root}/_bmad/psm/memory/ecommerce/adversarial-checks.md` bila ada, sebagai
  pertanyaan tambahan — bagian yang relevan dengan lensanya;
- `{project-root}/_bmad/psm/memory/projects/<module>.md` bila ada (konvensi module);
- perintah: id temuan berawalan `adv-<lensa>-` (`sec`, `cart`, `xver`, `perf`) supaya tak
  bertabrakan, dan kembalikan **HANYA JSON** — jangan menulis file apa pun.

**Jangan** beri path `<psm_reports_dir>`, output skrip, ringkasan lapis lain, atau temuan
lensa lain. Satu kalimat "Lapis 1 hijau" saja sudah mencemari konteks yang dibayar mahal.

**Gabung (orkestrator, sekali).** Setelah keempatnya kembali: validasi tiap kembalian
terhadap "Bentuk kembalian"; baca `<psm_reports_dir>/<module>-adversarial.json` bila ada (bisa
sudah memuat cacat visual Lapis 4); tambahkan `findings` keempat lensa; `versions` top-level =
**union** cakupan yang ada + cakupan keempat peninjau; tulis balik sebagai JSON utuh. Jangan
menilai ulang, menurunkan `severity`, atau membuang temuan peninjau — kamu penggabung, bukan
peninjau kelima.

**Kembalian gagal.** Subagent error, atau JSON-nya tak lolos bentuk? Ulangi lensa itu sekali.
Masih gagal → kerjakan lensa itu lewat "Fallback inline" dan sebut di ringkasan. Jangan
pernah menggabung tanpa lensa itu diam-diam: `versions` yang dinyatakan berarti keempat lensa
sudah meninjau versi itu.

## Fallback inline (subagent tak tersedia)

Berlaku bila harness tak bisa men-spawn subagent (menolak, atau psm-validate sendiri sedang
berjalan sebagai subagent). Isolasi hilang, jadi higienenya ditegakkan urutan kerja dan file:

1. **Kapan.** Langkah **pertama Fase 2**, **sebelum** kamu membaca hasil lapis lain di fase
   itu, termasuk output sweep-nya. Terlanjur membacanya? Tetap kerjakan sekarang — jangan
   ditunda ke akhir — dan sebut itu di ringkasan.
2. **Satu lensa, satu pass**, urut: keamanan transaksi → edge case cart/order/stock →
   kompatibilitas lintas versi → performa. Lensa berikutnya mulai hanya setelah lensa sekarang
   tuntas ditulis.
3. **Tulis, lalu lepaskan.** Selesai satu lensa: read-merge ke
   `<psm_reports_dir>/<module>-adversarial.json` dengan aturan "Gabung" di atas, lalu **jangan
   bawa kutipan source lensa itu ke lensa berikutnya**: file itu ingatan lapis ini.
4. Ringkasan run **wajib menyebut** review dikerjakan inline tanpa konteks bersih.

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
