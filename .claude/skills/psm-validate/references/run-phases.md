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
| 4 e2e | `ps-run-layer.py --layer e2e --cells …` | **tidak**: histori append-only per sel `<module>-e2e-<ver>-<browser>.jsonl` (`--per-version` = exit 2); `<module>-e2e.json` dari `--merge-only` cuma tampilan laporan, bukan bukti |
| 5 scenario | `ps-run-layer.py --layer scenario --per-version` | ya |

`<cfg>` = `<psm_reports_dir>/psm-config.json` (headless: salinan config, `headless.md`).
Teruskan `--config <cfg>` ke Lapis 1, plan, agregat, dan `ps-run-layer.py` sebagai flag-nya
sendiri untuk tiap lapis — **bukan** sesudah `--` (`--config`/`--browsers`/`--engines` di
passthrough = exit 2). Plan, run E2E, dan agregat **menolak (exit 2)** bila `<psm_reports_dir>/psm-config.json`
ada tapi `--config` tak diberikan — tanpanya himpunan sel wajib jatuh ke default skrip dan
menyempit diam-diam. `--session <t>` (SKILL.md > On Activation) wajib di **tiap** panggilan
plan dan tiap run E2E (tidak di `--merge-only`). `--tag-map`/`--extra-tag-map` bila dipakai:
identik ke tiap plan, `ps-run-layer.py` (sesudah `--`) dan agregat; `--extra-rules` yang sama
ke Lapis 1 dan plan — plan yang tak melihat tag yang berlaku membaca bukti dari image lain
sebagai segar.

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
| `SLOW` | fase melewati ambang (180 dtk; `pull` 900 dtk; `--slow-after`) — tak pernah untuk `wait-slots` | **diduga macet** — laporkan |
| `DONE` | proses selesai: `rc=<kode>`, `rc=crash`, `rc=stopped`, `rc=not-run <reason>` (sel versi itu tak satu pun dimulai — fail-fast), `rc=no-slots` (cap slot penuh sampai batas) | baca file lapis / output run |

Fase: `wait-slots` (Lapis 4, lihat di bawah), `pull`, `bring-up`, `wait-healthy`, `install+phpstan`
(Lapis 2), `install`, `wait-http`, `warmup-bo`, `browser:<engine>` (Lapis 4), `snapshot-db`,
`scenario` (Lapis 5), `teardown`.

**`wait-slots`** (Lapis 4, ditulis `ps-run-layer.py`): dibuka di log tiap versi yang diantre
begitu run mulai (log dikosongkan dulu), berakhir saat versi itu diadmisi (`END wait-slots ok`,
lalu anak menulis fasenya sendiri ke log yang sama), atau `no-slots`/`cancelled`. Denyut
`ALIVE` menyebut isi cap: container terhitung `<psm.job>@<host>=<cost>`, klaim
`claim:<job>/<run>=<cost>`, lalu `own queue` (menunggu anak run ini sendiri — tanpa batas) atau
`budget <n>s left`, dan `last pass <n>s ago`; sebelum hitungan pertama `cleanup-orphans
running` / `first count pending`. Tak pernah `SLOW`: lamanya = lamanya fase yang ditunggu,
yang punya batasnya sendiri. Versi yang di-fail-fast: log = satu baris `DONE rc=not-run …`.

**Ritme:** jalankan di latar (mis. Claude Code: Bash `run_in_background`, lalu baca ekor log
tiap 30–60 dtk), dan beri Budi satu baris per cek — versi, fase, durasi. Harness tanpa
eksekusi latar: jalankan satu versi per panggilan (Lapis 2/5 `--versions V --jobs 1`; Lapis 4 satu
versi per panggilan `--cells V:…`) supaya tiap panggilan pendek, dan baca log-nya di antara panggilan.

**Diduga macet** bila (a) baris terakhir `SLOW`, atau (b) mtime log tak berubah ±3 menit dan
belum ada `DONE` — artinya proses menggantung di luar fase berlog atau sudah mati. Laporkan
ke Budi: job, versi, fase, durasi. Tawarkan pilihan: tunggu sampai batas waktu fasenya (skrip
lalu degrade jujur sendiri), atau hentikan job itu (`--stop-job`, di bawah). **Jangan
menghentikan sendiri tanpa persetujuan** — run sesi lain bisa sedang berbagi daemon yang
sama, dan `SLOW` saat banyak sesi jalan sering berarti lambat, bukan mati. Macet berulang di
`wait-healthy`/`bring-up` saat banyak sesi paralel biasanya tanda RAM/daemon penuh: Lapis 2/5
turunkan `--jobs`; Lapis 4 turunkan `psm_e2e_slots` (cap sedaemon — container Lapis 2/5 tak
pernah dihitung di dalamnya) atau satu versi per panggilan `--cells`.

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

**`--cleanup-orphans` otomatis (Lapis 4).** Tiap run `ps-run-layer.py --layer e2e` menjalankan
rutin `--cleanup-orphans` sendiri, **sekali per run**, di dalam `wait-slots` sebelum hitungan
slot pertama, interaktif maupun headless; ringkasannya di stderr, galatnya tak pernah
menggagalkan run. Ia hanya menghapus container/network yang pemiliknya **terbukti mati** di
host ini — yatim milik host lain tetap terhitung sampai dibersihkan dari host pemiliknya
(`ALIVE wait-slots` / `errors` `no-slots` menyebut `psm.job` & host-nya).

## Istilah E2E (interim, sampai CAP-1)

- **Cakupan run** = versi × browser pilihan On Activation langkah 2 (headless: semua sel
  terkonfigurasi di `<cfg>`). **Entri e2e tercakup** = entri e2e `rerun_matrix` (ber-`browser`
  + `reason`) di dalam cakupan run. **Browser tercakup V** = browser entri tercakup V, urut
  `psm_e2e_browsers`.
- **V bersih**: `per_version[V].rerun` hanya memuat `adversarial`/`e2e`, dan file per-versi
  Lapis 1/2/5 V tanpa temuan pemblokir (dinilai seperti biasa). Run Lapis 2/5 V yang
  melaporkan skipped (Docker absen) di sesi ini = sudah. Budi menolak memperbaiki temuan
  pemblokir Lapis 1/2/5 V di sesi ini = bersih (laporan mendaftarnya sebagai terbuka).
  Headless: bersih begitu lapis basinya jalan sekali.
- **Loop E2E berakhir** (sesi-wide) bila salah satu: run E2E mencetak `skipped`; run E2E exit 2
  karena anak exit 2 (baris output `e2e_status: ran` tercetak — laporkan stderr-nya); run E2E
  dihentikan (exit 143; interaktif: kecuali Budi minta ulang; headless: `headless.md`);
  `psm_e2e_enabled` false atau `--require` tanpa `e2e`; Budi menolak mem-patch `fail` E2E,
  menolak infra retry, atau infra retry masih menyisakan alasan infra.
- **Exit 2 pra-spawn** (sebelum anak mana pun di-spawn: error input, tanpa baris output — mis.
  `--cells` salah, `--session` absen) **tak** mengakhiri loop: perbaiki input, ulangi
  (headless: `blocked`).
- **Langkah E2E V jatuh tempo** bila loop E2E belum berakhir, V punya entri e2e tercakup, dan
  belum ada run E2E V sesi ini yang mencetak `source_fingerprint` plan sekarang, atau infra
  retry V tertunda.
- **Hasil run** dibaca dari panggilan plan berikutnya, **tak pernah** dari histori: entri
  tercakup V ber-`reason` `fail` = kegagalan untuk dipatch; tanpa `fail` tapi ada
  `inconclusive`/`inconclusive-steps`/`browser-notes` = run meninggalkan alasan infra (sebabnya,
  mis. image hilang, `browser-unavailable` atau `no-slots`, ada di stderr dan log kemajuan);
  `not-run` = bukan kegagalan maupun alasan infra (lihat `not-run` di bawah).
- **Infra retry** (interaktif saja): laporkan sebabnya, minta Budi memperbaiki lingkungan
  (mis. `--allow-image-pull`, `playwright install`; untuk `no-slots`: bebaskan slot atau tunggu,
  atau perbaiki Docker bila `docker count failed` — bukan install) atau menolak. Diperbaiki → infra retry V
  tertunda sampai run E2E V berikutnya (perintah sama, di Fase 1 atau pass Fase 2 berikutnya);
  ditolak → loop E2E berakhir. Headless tanpa retry: langkah V tak jatuh tempo, selnya tetap
  tak terbukti.

- **`not-run`** (rekaman, `conclusive: false`): sel yang tak pernah dimulai karena fail-fast —
  `fail-fast after <ver>:<browser>` (anak lain meng-append `fail`) atau `input-error after <ver>`
  (anak lain exit 2). Bukan kegagalan dan bukan alasan infra (plan: reason `not-run`); tak
  pernah lulus, tak pernah gate-grade. `fail-fast after …` jatuh tempo lagi begitu source
  berubah (patch `fail`-nya); `input-error after …` begitu input yang ditolak diperbaiki —
  tapi anak exit 2 tetap mengakhiri loop E2E untuk sesi ini. Fail-fast hanya menghemat waktu
  untuk sel yang **masih antre**: anak yang sudah jalan selesai dan di-append.
- **`no-slots`** (rekaman `inconclusive`, reason `no-slots`; plan: `inconclusive`): cap slot
  sedaemon penuh selama batas startup (`--startup-timeout` passthrough, else
  `psm_flashlight_startup_timeout`, else 180 dtk; dihitung hanya saat tak ada anak run ini yang
  jalan). Alasan infra; `errors` menyebut isi cap. Diperbaiki dengan membebaskan slot (job lain
  selesai/dihentikan atas izin Budi, yatim dibersihkan) atau menunggu, atau — bila `errors`
  berkata `docker count failed` — memperbaiki Docker; **tak pernah** dengan install
  (`--allow-image-pull`, `playwright install`).
- **Slot sedaemon**: N = `psm_e2e_slots` dari `<cfg>` (`--slots` hanya override manual; jangan
  diberikan). Terpakai = jumlah label `psm.slots` semua container E2E yang jalan di daemon (run
  dan sesi lain, juga `ps-e2e-run.py` langsung — yang ikut terhitung tapi melewati admisi) +
  klaim run lain yang container-nya belum jalan, dibandingkan dengan N **run ini**:
  `psm_e2e_slots` yang sama di semua sesi = satu langit-langit bersama. Klaim dari folder temp
  lain baru terlihat begitu container-nya jalan. Container Lapis 2/5 tak dihitung (mereka tetap
  `--jobs`).

Baris terakhir stdout run E2E: `{"e2e_status": "ran"|"skipped", "reason", "appended":
["<ver>:<browser>", …], "source_fingerprint"}`. Exit 0 = semua pass atau `skipped`; 1 = ada
inconclusive/`not-run`/`no-slots`; 3 = ada `fail`; 2 = error input pra-spawn (tanpa baris) atau
anak exit 2 (baris `ran`); 143 = dihentikan `--stop-job` (tanpa baris). `--jobs` dengan lapis
e2e = exit 2 (konkurensi E2E = slot, di atas).

## Fase 1 — konvergensi per versi

Untuk tiap versi V di cakupan run:

```bash
uv run scripts/ps-plan-layers.py <module-path> --reports-dir <psm_reports_dir> \
  --versions V --per-version --session <t> --config <cfg>
```

1. Jalankan lapis di `per_version[V].rerun` selain `adversarial` dan `e2e` (Lapis 1:
   `ps-static-scan.py <module-path> --versions V --reports-dir <psm_reports_dir> --per-version
   --config <cfg>`; Lapis 2/5: `ps-run-layer.py --layer <flashlight|scenario> --module
   <module-path> --versions V --reports-dir <psm_reports_dir> --per-version --config <cfg>`).
2. Begitu V bersih dan langkah E2E-nya jatuh tempo:

   ```bash
   uv run scripts/ps-run-layer.py --layer e2e --module <module-path> \
     --reports-dir <psm_reports_dir> --cells V:<browser tercakup V digabung +> \
     --session <t> --config <cfg> -- --screenshot-dir <psm_reports_dir>/e2e-shots
   ```

   (`-- --screenshot-dir …` interaktif saja; tinjauan visual: SKILL.md > Lapis 4.)
3. Patch temuan pemblokir atau `fail` E2E, ulangi dari plan.

Loop V selesai bila V bersih, langkah E2E-nya tak jatuh tempo, dan (interaktif, kecuali loop
E2E berakhir) plan terakhir tak menunjukkan entri e2e tercakup V ber-`reason` `fail`.

`all_reuse` hanya informatif (per-versi `rerun` selalu memuat `adversarial`) — tak ada loop
yang menggerbang padanya. Perbaiki spec di `e2e_scenario_notes` sebelum Lapis 4 boot. File
per-versi dan histori versi lain tak disentuh, jadi buktinya menetap: cek ulang satu versi =
boot Docker 1×, bukan 3×.

## Fase 2 — gerbang rilis

1. Satu plan atas versi cakupan: `--versions <cakupan> --per-version --session <t> --config
   <cfg>`. Versi yang tak bersih masuk lagi ke loop Fase 1-nya dulu (patch membasikan file
   Lapis 1/2/5 versi lain).
2. **Lapis 3**: spawn keempat subagent lensa dalam satu giliran (`references/adversarial-lens.md`),
   kecuali plan kanonik (flag sama tanpa `--per-version`) menunjukkan `layers.adversarial.reuse`
   true, atau lensa yang di-spawn di bawah `source_fingerprint` plan yang sama masih belum
   digabung. Dinilai lagi tiap Fase 2 mulai ulang. Hasil lensa yang belum digabung dari
   `source_fingerprint` lain dibuang, tak pernah digabung. Konteks mereka bersih, jadi lanjutkan
   lapis skrip selagi mereka bekerja — selama outputnya tak kamu teruskan ke mereka (fallback
   inline justru WAJIB dikerjakan sebelum kamu membaca output apa pun).
3. Kelompokkan entri e2e tercakup dari versi yang langkah E2E-nya jatuh tempo ke SATU panggilan
   (tak ada → tanpa panggilan):

   ```bash
   uv run scripts/ps-run-layer.py --layer e2e --module <module-path> \
     --reports-dir <psm_reports_dir> --cells <ver>:<b>[+<b>],… \
     --session <t> --config <cfg> -- --screenshot-dir <psm_reports_dir>/e2e-shots
   ```

4. `fail` yang ter-append → masuk lagi ke Fase 1 versi itu (interaktif; iterasi pertamanya mulai
   dengan patch atau penolakan Budi), lalu Fase 2 mulai ulang dari plan-nya. Headless
   melaporkannya.

## Wrap-up (sekali)

Begitu satu pass Fase 2 tak punya langkah E2E jatuh tempo dan tak ada masuk-ulang, jalankan
sekali, **tanpa** gerbang `all_reuse`, urut:

1. Read-merge Lapis 3 (bila di-spawn; hanya hasil yang di-spawn di bawah `source_fingerprint`
   plan terakhir).
2. Cacat visual Lapis 4 yang ditahan (hanya dari run yang `source_fingerprint` baris output-nya
   = plan terakhir).
3. `--merge-only` Lapis 2 dan 5 (Lapis 5 bila module punya skenario) atas **versi dalam cakupan
   run saja** — file per-versi versi lain tak pernah di-plan ulang sesi ini, jadi bisa basi dan
   agregat tak bisa melihatnya. Versi yang dihilangkan jadi tak konklusif dan `ready` jatuh:

   ```bash
   uv run scripts/ps-run-layer.py --layer <flashlight|scenario> --module <module-path> \
     --reports-dir <psm_reports_dir> --versions <versi dalam cakupan run> --merge-only
   ```

4. Tampilan laporan E2E (bukan bukti; tanpa `--versions`/`--cells`/`--session`/passthrough):

   ```bash
   uv run scripts/ps-run-layer.py --layer e2e --module <module-path> \
     --reports-dir <psm_reports_dir> --config <cfg> --merge-only
   ```

5. Pindai Lapis 1 lintas-versi ke `<module>-static.json`: `ps-static-scan.py <module-path>
   --versions <semua terkonfigurasi> --reports-dir <psm_reports_dir> --config <cfg>`.
6. `ps-aggregate.py --reports-dir <psm_reports_dir> --module <module-path> --config <cfg>`
   (SKILL.md > Vonis).

**Read-merge wajib pada file adversarial.** `<psm_reports_dir>/<module>-adversarial.json`
ditulis dari dua arah — gabungan keempat lensa Lapis 3 (atau satu tulisan per lensa di
fallback inline), plus cacat visual Lapis 4 — jadi **tiap** tulisan wajib membaca `findings` yang ada, menambahkan miliknya, lalu
menulis balik dengan `versions` top-level di-union. Menimpanya membuang temuan pemblokir yang sudah dikonfirmasi, diam-diam, dan
`ready` tetap true di atasnya.
