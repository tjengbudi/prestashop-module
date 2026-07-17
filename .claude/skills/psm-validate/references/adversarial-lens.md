# Kontrak review adversarial e-commerce (Lapis 3)

Briefing WAJIB untuk subagent reviewer psm-validate — diberikan di **setiap** run.
File ini memegang sikap dan bentuk kembalian yang ditegakkan skrip agregat.

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
  (`"8.1"`, atau bentuk major `"8"`), bukan angka.
- `findings` harus list of object.

`versions` top-level = cakupan yang kamu tinjau (beda dari `versions` per temuan =
versi terpengaruh). Nyatakan JUJUR: versi yang tak kamu tinjau ditandai **tak konklusif**
oleh agregat dan menjatuhkan `ready` — itu memang jawaban yang benar, dan jauh lebih baik
daripada vonis "siap rilis" atas review yang tak pernah terjadi. Cakupan yang lebih luas
dari target satu run tetap sah (review penuh boleh dipakai ulang di run yang dipersempit);
`ps-plan-layers.py` memakainya untuk tahu file ini masih mencakup versi yang diminta.
