# Mode headless psm-validate

Berlaku saat skill dipanggil workflow lain (psm-develop, psm-cross-version, psm-optimize,
psm-scaffold) atau dengan `--headless`. Interaktif tak pernah memuat file ini.

## Input dan asumsi

Lewati pertanyaan klarifikasi: ambil module-path, versi, dan browser dari argumen/konteks,
jalankan lapis yang tersedia, tulis JSON. Tak ada operator untuk ditanya, jadi tawaran
cakupan uji tak berlaku — pakai `psm_target_versions` dan `psm_e2e_browsers` dari resolver
bila argumen tak menyebutnya.

Catat asumsi yang diambil (module-path di-infer, default resolver dipakai) ke
`<psm_reports_dir>/<module>-validate.memlog.md` via
`uv run {project-root}/_bmad/scripts/memlog.py` — `init --path <file> --field skill=psm-validate`
dulu bila file itu belum ada (`append` ke file absen gagal), lalu
`append --path <file> --type assumption --text <asumsi>`.

## Kembalian

Objek JSON kecil, bukan prosa: `status` (`complete`|`blocked`), path laporan, path memlog,
`ready`, `pass`, dan konklusivitas (`flashlight_conclusive`, `e2e_conclusive`, `layers_run`,
plus `e2e_smoke_only` bila E2E jalan).

`blocked` + `reason` satu baris bila skill tak bisa menilai sama sekali: module-path tak
resolve, `main_file_reason: no_php_at_root` (bukan module PrestaShop), Lapis 1 tak
menghasilkan JSON, atau exit 2 error input.

Gerbang CI membaca **`ready`**: lolos + lapis yang di-`--require` tuntas (default keempatnya).
Runner tanpa Docker/browser menghasilkan `ready: false` — jujur, bukan cacat module; `pass`
tetap menampung temuan nyata. Menggating lebih sempit: nyatakan di `--require`.

## Yang tak boleh di headless

- **Jangan pernah** teruskan `--allow-image-pull` ke Lapis 2/4 — jangan tarik image tanpa
  manusia. Pemanggil yang memang mau menarik meneruskannya eksplisit.
- Lewati verifikasi visual Lapis 4: tak ada peninjau, jadi `--screenshot-dir` tak berguna
  dan tak ada yang boleh menulis cacat visual ke file lapis adversarial.
