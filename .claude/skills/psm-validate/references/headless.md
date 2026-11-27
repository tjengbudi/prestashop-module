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

**Canary di salinan.** Aturan tangan (tak ada mode skrip): bila `psm_e2e_canary` berbentuk sah —
di-trim, tepat satu `:`, dua bagian tak kosong — dan, dinormalisasi (versi di-trim; browser
di-trim dan huruf kecil), selnya di luar versi × browser pemanggil, set `psm_e2e_canary` salinan
ke `""` (canary default) dan catat `assumption` yang menyebut nilai yang dibuang. Nilai lain
dibiarkan apa adanya (yang salah bentuk biar exit 2 plan mengembalikan `blocked`). Contoh: pemanggil hanya 9.1,
canary `8.1:chromium` → salinan ber-`psm_e2e_canary: ""` + assumption "psm_e2e_canary
`8.1:chromium` di luar sel pemanggil — dikosongkan ke default".

Catat asumsi yang diambil (module-path di-infer, default resolver dipakai) ke
`<psm_reports_dir>/<module>-validate.memlog.md` via
`uv run {project-root}/_bmad/scripts/memlog.py` — `init --path <file> --field skill=psm-validate`
dulu bila file itu belum ada (`append` ke file absen gagal), lalu
`append --path <file> --type assumption --text <asumsi>`.

Lapis 3 tetap empat subagent lensa seperti interaktif (kontrak `references/adversarial-lens.md`).
Bila jatuh ke fallback inline — seluruhnya atau satu lensa — tak ada ringkasan prosa untuk
mengakuinya: catat satu `assumption` ke memlog yang menyebut lensa mana yang ditinjau inline
tanpa konteks bersih.

## Langkah E2E: berhenti di langkah tak bersih pertama

Alur dua fase sama dengan interaktif (`references/run-phases.md`), tanpa operator: tak ada patch,
tak ada tanya sebab infra, tak ada warm container — `e2e_warm` dan `e2e_scenarios` diabaikan,
tiap run dingin dan skenario penuh, jadi tiap langkah meninggalkan bukti gate-grade. Tiap run tetap
persis `--cells <e2e_cells_arg> --tier <e2e_tier>` plan cakupan-run.

- Sesudah tiap run E2E, satu plan dengan flag yang sama. Langkah itu **bersih** bila tak satu pun
  sel di `e2e_next_cells` plan yang memilih run itu punya entri e2e `rerun_matrix` selain ber-`reason`
  `not-gradeable`. `blocked-by-scope`, `blocked-not-gradeable` dan `blocked-infra` tak bersih.
- Anak exit 2 (baris output tercetak) atau exit 143 = langkah tak bersih. Selama rekaman `stopped`
  belum ada, sel job yang dihentikan mempertahankan rekaman lamanya.
- Langkah tak bersih pertama mengakhiri **hanya** langkah E2E: loop Fase 1 tiap versi tetap
  menjalankan Lapis 1, 2 dan 5. Di mana pun berhenti, lalu wrap-up (lensa Lapis 3 di-spawn dulu bila
  berhenti sebelum Fase 2), jadi tiap kembalian menjalankan agregat — dengan `--session <t>`.

## Kembalian

Objek JSON kecil, bukan prosa: `status` (`complete`|`blocked`), path laporan, path memlog,
`ready`, `pass`, dan konklusivitas (`flashlight_conclusive`, `e2e_conclusive`, `layers_run`,
plus `e2e_smoke_only` bila E2E jalan), plus:

- `versions: {<ver>: {e2e_state, reason}}` dan `not_run_cells`, disalin dari agregat ber-`--session
  <t>`; versi ber-`reached: false` mempertahankan `e2e_state`-nya dan, kecuali `fail`, mendapat
  `reason` `not reached: stopped at <step>`.
- `e2e_tier_reached` = `{tier, step}` dari plan cakupan-run terakhir — atau, bila berhenti sesudah
  run yang tak bersih, dari plan yang memilih run itu (langkah tempat berhenti). `<step>` di
  `not reached` sama.

Tiap kembalian awal — langkah tak bersih (termasuk job E2E yang dihentikan aturan log diam),
`blocked-*`, E2E `skipped` — adalah `status: complete` dengan `ready: false`.

`blocked` + `reason` satu baris hanya bila skill tak bisa menilai sama sekali: module-path tak
resolve, `main_file_reason: no_php_at_root` (bukan module PrestaShop), Lapis 1 tak menghasilkan
JSON, exit 2 error input — termasuk exit 2 run E2E tanpa baris output (pra-spawn atau gagal
append) dan exit run E2E lain tanpa baris output (130, 1 mis. traceback), seketika, tanpa wrap-up,
`reason` = stderr-nya — atau job lapis lain yang dihentikan (di bawah). Exit 2 run E2E dari anak
(baris output `e2e_status: ran`) **bukan** `blocked`: langkah tak bersih.

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
  terakhir). Job lapis lain → kembalikan `blocked` + `reason` yang menyebut job & fasenya,
  seketika. Job E2E (exit 143) → langkah tak bersih: wrap-up, lalu `complete`.
- Job yang **bukan** dimulai run ini tak pernah disentuh — tak ada operator yang bisa
  mengizinkannya. Larangan perintah luas di SKILL.md (pkill, `docker rm|kill|stop` berdasarkan
  nama/prefix, `compose down` tanpa project, prune) berlaku penuh.
- **Satu pengecualian, otomatis:** tiap run `ps-run-layer.py --layer e2e` menjalankan rutin
  `--cleanup-orphans` sekali di dalam `wait-slots`, sebelum hitungan slot pertama — juga
  headless. Ia hanya menghapus container/network yang pemiliknya **terbukti mati** di host ini
  (`references/run-phases.md` > Job ID); job hidup milik siapa pun tetap tak tersentuh.
  Jangan menambah pembersihan lain.
- **`no-slots` / `not-run` bukan `blocked`.** Cap slot penuh (`no-slots`, alasan infra) atau
  sel yang dilewati fail-fast (`not-run`) hanya membuat sel itu tak terbukti: langkahnya tak
  bersih, jadi langkah E2E berhenti di situ (di atas).

## Yang tak boleh di headless

- **Jangan pernah** teruskan `--allow-image-pull` ke Lapis 2/4 — jangan tarik image tanpa
  manusia. Pemanggil yang memang mau menarik meneruskannya eksplisit.
- Lewati verifikasi visual Lapis 4: tak ada peninjau, jadi `--screenshot-dir` tak berguna
  dan tak ada yang boleh menulis cacat visual (`visual-pending.json` maupun file adversarial).
