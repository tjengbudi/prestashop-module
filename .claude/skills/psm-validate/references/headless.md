# Mode headless psm-validate

Berlaku saat skill dipanggil workflow lain (psm-develop, psm-cross-version, psm-optimize,
psm-scaffold) atau dengan `--headless`. Interaktif tak pernah memuat file ini.

## Input dan asumsi

Lewati pertanyaan klarifikasi: ambil module-path, versi, dan browser dari argumen/konteks,
jalankan lapis yang tersedia, tulis JSON. Tak ada operator untuk ditanya, jadi tawaran
cakupan uji tak berlaku — pakai `psm_target_versions` dan `psm_e2e_browsers` dari resolver
bila argumen tak menyebutnya.

**Sesi dan config (tiap panggilan).** Cetak token baru `<t>` lewat
`uv run scripts/ps-plan-layers.py --new-session`. Sebelum plan pertama, salin
`<psm_reports_dir>/psm-config.json` apa adanya ke
`<psm_reports_dir>/<module>-psm-config.headless.<t>.json`, hanya menimpa `psm_target_versions`
dan `psm_e2e_browsers` dengan versi dan browser pemanggil sebagai string dipisah koma (default
resolver bila pemanggil tak menyebutnya). Salinan itu = `<cfg>`: teruskan sebagai `--config` ke
tiap plan, `ps-run-layer.py`, dan agregat, dan `--session <t>` ke tiap plan dan run E2E — jadi
`ready` dan `versions` mencakup persis sel pemanggil. Cakupan run = semua sel di salinan itu.

Catat asumsi yang diambil (module-path di-infer, default resolver dipakai) ke
`<psm_reports_dir>/<module>-validate.memlog.md` via
`uv run {project-root}/_bmad/scripts/memlog.py` — `init --path <file> --field skill=psm-validate`
dulu bila file itu belum ada (`append` ke file absen gagal), lalu
`append --path <file> --type assumption --text <asumsi>`.

Lapis 3 tetap empat subagent lensa seperti interaktif (kontrak `references/adversarial-lens.md`).
Bila jatuh ke fallback inline — seluruhnya atau satu lensa — tak ada ringkasan prosa untuk
mengakuinya: catat satu `assumption` ke memlog yang menyebut lensa mana yang ditinjau inline
tanpa konteks bersih.

## Kembalian

Objek JSON kecil, bukan prosa: `status` (`complete`|`blocked`), path laporan, path memlog,
`ready`, `pass`, dan konklusivitas (`flashlight_conclusive`, `e2e_conclusive`, `layers_run`,
plus `e2e_smoke_only` bila E2E jalan).

`blocked` + `reason` satu baris bila skill tak bisa menilai sama sekali: module-path tak
resolve, `main_file_reason: no_php_at_root` (bukan module PrestaShop), Lapis 1 tak
menghasilkan JSON, atau exit 2 error input — termasuk exit 2 run E2E pra-spawn (tanpa baris
output; `reason` = stderr-nya). Exit 2 run E2E yang berasal dari anak (baris output
`e2e_status: ran` tercetak) **bukan** `blocked`: loop E2E berakhir (`references/run-phases.md`
> Istilah E2E), sisa run jalan sampai agregat.

Gerbang CI membaca **`ready`**: lolos + lapis yang di-`--require` tuntas (default keempatnya).
Runner tanpa Docker/browser menghasilkan `ready: false` — jujur, bukan cacat module; `pass`
tetap menampung temuan nyata. Menggating lebih sempit: nyatakan di `--require`.

## Pemantauan & menghentikan job (tanpa operator)

Log kemajuan dan Job ID tetap berlaku (`references/run-phases.md`), tapi tak ada Budi untuk
diberi laporan atau dimintai izin — jadi aturannya lebih sempit, bukan lebih longgar:

- **`SLOW` → tunggu.** Tiap fase dibatasi batas waktunya sendiri, lalu skrip degrade jujur
  (tak konklusif, bukan lolos). Menghentikan job yang cuma lambat karena daemon sedang ramai
  membuang bukti yang hampir jadi.
- **Log diam ±3 menit tanpa `DONE`** (proses menggantung di luar fase berlog) → hentikan
  **hanya job yang dimulai run ini**: `uv run scripts/ps-flashlight-run.py --stop-job <id>`
  (`<id>` dari baris `JOB` / `job=`). Catat satu `assumption` ke memlog (job, versi, fase
  terakhir), lalu kembalikan `blocked` + `reason` yang menyebut job & fasenya — seketika,
juga untuk job E2E (exit 143).
- Job yang **bukan** dimulai run ini tak pernah disentuh — tak ada operator yang bisa
  mengizinkannya. Larangan perintah luas di SKILL.md (pkill, `docker rm|kill|stop` berdasarkan
  nama/prefix, `compose down` tanpa project, prune) berlaku penuh.

## Yang tak boleh di headless

- **Jangan pernah** teruskan `--allow-image-pull` ke Lapis 2/4 — jangan tarik image tanpa
  manusia. Pemanggil yang memang mau menarik meneruskannya eksplisit.
- Lewati verifikasi visual Lapis 4: tak ada peninjau, jadi `--screenshot-dir` tak berguna
  dan tak ada yang boleh menulis cacat visual ke file lapis adversarial.
