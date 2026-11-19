# Dua fase run psm-validate — perintah dan konvensi

Bentuknya ada di SKILL.md (konvergensi per versi dulu, gerbang rilis sekali di akhir).
File ini memegang perintah persisnya. Semua path relatif ke `scripts/` skill ini.

## Konvensi file lapis

Nama file **selalu diturunkan, tak pernah diketik** — segmen module yang salah ketik menulis
bukti ke himpunan bukti module lain, dan agregat mengkreditkan vonisnya ke sana. Beri
`--reports-dir <psm_reports_dir>`, tambah `--per-version` untuk bentuk per-versi:

| Lapis | Skrip | Per-versi |
| --- | --- | --- |
| 1 static | `ps-static-scan.py --reports-dir … --per-version` | ya (tepat satu `--versions`) |
| 2 flashlight | `ps-run-layer.py --layer flashlight --per-version` | ya |
| 3 adversarial | — (4 subagent per lensa) | **tidak**: satu review lintas-versi di awal Fase 2 |
| 4 e2e | `ps-run-layer.py --layer e2e --per-version` | ya |

Teruskan `--config <psm_reports_dir>/psm-config.json` ke Lapis 1/2/4 dan ke plan, plus
`--tag-map`/`--extra-rules` yang sama bila dipakai — plan yang tak melihat tag yang berlaku
membaca bukti dari image lain sebagai segar.

## Pantau run Docker (anti-macet)

Skrip lapis Docker (flashlight/e2e/scenario) menulis satu baris per kejadian ke log kemajuan.
`ps-run-layer.py` menurunkan path-nya per versi — `<psm_reports_dir>/<module>-<lapis>-<versi>.progress.log`
(dicetak ke stderr di awal run); skrip yang dipanggil langsung butuh `--progress-file <path>`.
File dikosongkan tiap run baru.

```
2026-11-19T10:02:15 job=bankwire-e2e-1002-a3f9 pid=4242 run=1a2b3c4d5e6f v=8.1 ALIVE wait-healthy 45s/180s … starting
```

| Token | Arti | Tindakan |
| --- | --- | --- |
| `START` / `END` | fase mulai / selesai (`ok`, `timeout`, `gagal`, …) | lanjut memantau |
| `ALIVE` | fase masih jalan (denyut tiap 15 dtk, `durasi/batas`) | normal |
| `SLOW` | fase melewati ambang (180 dtk; `pull` 900 dtk; `--slow-after`) | **diduga macet** — laporkan |
| `DONE` | proses selesai (`rc=<kode>` / `rc=crash`) | baca file lapis |

Fase: `pull`, `bring-up`, `wait-healthy`, `install+phpstan` (Lapis 2), `install`, `wait-http`,
`warmup-bo`, `browser:<engine>` (Lapis 4), `snapshot-db`, `scenario` (Lapis 5), `teardown`.

**Ritme:** jalankan di latar (mis. Claude Code: Bash `run_in_background`, lalu baca ekor log
tiap 30–60 dtk), dan beri Budi satu baris per cek — versi, fase, durasi. Harness tanpa
eksekusi latar: jalankan satu versi per panggilan (`--versions V --jobs 1`) supaya tiap
panggilan pendek, dan baca log-nya di antara panggilan.

**Diduga macet** bila (a) baris terakhir `SLOW`, atau (b) mtime log tak berubah ±3 menit dan
belum ada `DONE` — artinya proses menggantung di luar fase berlog atau sudah mati. Laporkan
ke Budi: job, versi, fase, durasi. Tawarkan pilihan: tunggu sampai batas waktu fasenya (skrip
lalu degrade jujur sendiri), atau hentikan job itu (`--stop-job`, di bawah). **Jangan
menghentikan sendiri tanpa persetujuan** — run sesi lain bisa sedang berbagi daemon yang
sama, dan `SLOW` saat banyak sesi jalan sering berarti lambat, bukan mati. Macet berulang di
`wait-healthy`/`bring-up` saat banyak sesi paralel biasanya tanda RAM/daemon penuh: turunkan
`--jobs`.

## Job ID — menghentikan secara terarah

Tiap pemanggilan uji Docker adalah satu **job** dengan ID terlihat `<module>-<lapis>-<HHMM>-<hex>`
(mis. `bankwire-e2e-1002-a3f9`). `ps-run-layer.py` membuat SATU ID untuk semua versi anaknya;
skrip lapis yang dipanggil langsung membuat sendiri (`--job-id` untuk menentukannya). ID
dicetak ke stderr di awal (`JOB <id>  (hentikan terarah: …)`), ada di tiap baris log
kemajuan (`job=`), dicap label `psm.job`, dan menjadi bagian nama container/project
(`psm-fl-<job>-…`), jadi `docker ps` pun menunjukkan siapa pemiliknya. **Catat ID job yang
kamu mulai** — itu satu-satunya pegangan untuk menghentikannya.

```bash
uv run scripts/ps-flashlight-run.py --list-jobs          # job di host ini: proses + container
uv run scripts/ps-flashlight-run.py --stop-job <job-id>  # hentikan SATU job
```

`--stop-job` mengirim SIGTERM ke proses job itu saja (identitas PID diverifikasi: host, boot,
PID namespace, dan nama skrip — PID daur-ulang tak tersentuh), skrip menangkapnya dan
membongkar container miliknya sendiri (log: `DONE rc=stopped`); yang belum keluar sesudah 60
dtk di-SIGKILL, lalu container/network berlabel **persis** `psm.job=<id>` dihapus. Job lain —
paralel di sesi ini atau milik sesi lain — tak tersentuh. Hentikan hanya job yang kamu mulai;
job lain hanya atas izin Budi.

**Dilarang** (semuanya ikut membunuh job lain): `pkill`/`killall`/`kill` atas PID yang bukan
dari job-mu, `docker rm|kill|stop` berdasarkan nama, prefix `psm-fl`, atau
`$(docker ps -q …)`, `docker compose down` tanpa project job-mu, dan `docker … prune`. Sisa
run yang prosesnya sudah mati: `--cleanup-orphans`.

Semua perintah docker pendek (run/network/inspect/rm/down) berbatas waktu 120 dtk; bongkar yang
timeout meninggalkan artefak berlabel yang dibereskan `--cleanup-orphans` setelah proses keluar.

## Fase 1 — konvergensi per versi

Untuk versi V:

```bash
uv run scripts/ps-plan-layers.py <module-path> --reports-dir <psm_reports_dir> \
  --versions V --per-version --config <psm_reports_dir>/psm-config.json
```

Ia menandai per (lapis, versi) mana yang `rerun`. Baca `rerun_matrix`; **`all_reuse` adalah
gerbangnya** — jangan union boolean sendiri. Jalankan hanya lapis itu untuk V, perbaiki error
pemblokir di source, ulangi plan+rerun untuk V SAJA sampai bersih.

File per-versi versi lain tak disentuh, jadi buktinya menetap: cek ulang satu versi = boot
Docker 1×, bukan 3×. Perbaiki spec di `e2e_scenario_notes` sebelum Lapis 4 boot.

## Fase 2 — gerbang rilis

**Mulai dari Lapis 3** bila plan menandainya `rerun`: spawn keempat subagent lensa dalam satu
giliran, lalu lanjutkan lapis skrip selagi mereka bekerja — konteks mereka bersih, jadi output
sweep tak mewarnai vonisnya selama tak kamu teruskan ke mereka. Isi prompt, aturan gabung, dan
fallback inline (yang justru WAJIB dikerjakan sebelum kamu membaca output sweep apa pun):
`references/adversarial-lens.md`.

Segarkan tiap (lapis, versi) yang masih `rerun` dalam SATU panggilan per lapis:

```bash
uv run scripts/ps-run-layer.py --layer <flashlight|e2e> --module <module-path> \
  --versions <yang rerun> --reports-dir <psm_reports_dir> --per-version --jobs <N>
```

`--jobs` mengatur berapa versi boot serentak (default 3; tiap job satu container PS + DB —
turunkan di mesin kecil). Saat `all_reuse` true, satukan jadi kanonik dengan perintah yang
sama ber-`--versions <semua> --merge-only`; versi tanpa file dihilangkan, jadi agregat tak
konklusif dan `ready` jatuh.

Lapis 1 & Lapis 3 dijalankan sekali lintas-versi langsung ke file kanonik — Lapis 3 di-spawn
di awal fase dan digabung sebelum agregat (lihat atas).

**Read-merge wajib pada file adversarial.** `<psm_reports_dir>/<module>-adversarial.json`
ditulis dari dua arah — gabungan keempat lensa Lapis 3 (atau satu tulisan per lensa di
fallback inline), plus cacat visual Lapis 4 — jadi **tiap** tulisan wajib membaca `findings` yang ada, menambahkan miliknya, lalu
menulis balik dengan `versions` top-level di-union. Menimpanya membuang temuan pemblokir yang sudah dikonfirmasi, diam-diam, dan
`ready` tetap true di atasnya.
