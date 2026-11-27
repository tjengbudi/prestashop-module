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
| 4 e2e | `ps-run-layer.py --layer e2e --cells <e2e_cells_arg> --tier <e2e_tier>` | **tidak**: histori append-only per sel `<module>-e2e-<ver>-<browser>.jsonl` (`--per-version` = exit 2); `<module>-e2e.json` dari `--merge-only` cuma tampilan laporan, bukan bukti |
| 5 scenario | `ps-run-layer.py --layer scenario --per-version` | ya |

`<cfg>` = `<psm_reports_dir>/psm-config.json` (headless: salinan config, `headless.md`).
Teruskan `--config <cfg>` ke Lapis 1, plan, agregat, dan `ps-run-layer.py` sebagai flag-nya
sendiri untuk tiap lapis — **bukan** sesudah `--` (`--config`/`--browsers`/`--engines` di
passthrough = exit 2). Plan, run E2E, dan agregat **menolak (exit 2)** bila `<psm_reports_dir>/psm-config.json`
ada tapi `--config` tak diberikan — tanpanya himpunan sel wajib jatuh ke default skrip dan
menyempit diam-diam. `--session <t>` (SKILL.md > On Activation) wajib di **tiap** panggilan
plan dan tiap run E2E, `--tier <e2e_tier>` di tiap run E2E (keduanya tidak di `--merge-only`). `--tag-map`/`--extra-tag-map` bila dipakai:
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
| `SLOW` | fase melewati ambang (180 dtk; `pull` 900 dtk; `--slow-after`) — tak pernah untuk `wait-slots`, `lock-wait:<engine>`, `barrier-wait:<engine>` | **diduga macet** — laporkan |
| `DONE` | proses selesai: `rc=<kode>`, `rc=crash`, `rc=stopped`, `rc=not-run <reason>` (sel versi itu tak satu pun dimulai — fail-fast), `rc=no-slots` (cap slot penuh sampai batas) | baca file lapis / output run |

Fase: `wait-slots` (Lapis 4, lihat di bawah), `pull`, `bring-up`, `wait-healthy`, `install+phpstan`
(Lapis 2), `install`, `wait-http`, `warmup-bo`, `browser:<engine>` (Lapis 4), `snapshot-db`
(Lapis 5; Lapis 4 bila versi men-drive > 1 browser), `scenario` (Lapis 5), `teardown`; Lapis 4
dua browser juga `lock-wait:<engine>`, `barrier-wait:<engine>`, `rerun-seq:<engine>`,
`reset-db`, `reset-files`, `reset-opcache` (di bawah).

**`wait-slots`** (Lapis 4, ditulis `ps-run-layer.py`): dibuka di log tiap versi yang diantre
begitu run mulai (log dikosongkan dulu), berakhir saat versi itu diadmisi (`END wait-slots ok`,
lalu anak menulis fasenya sendiri ke log yang sama), atau `no-slots`/`cancelled`. Denyut
`ALIVE` menyebut isi cap: container terhitung `<psm.job>@<host>=<cost>`, klaim
`claim:<job>/<run>=<cost>`, lalu `own queue` (menunggu anak run ini sendiri — tanpa batas) atau
`budget <n>s left`, dan `last pass <n>s ago`; sebelum hitungan pertama `cleanup-orphans
running` / `first count pending`. Tak pernah `SLOW`: lamanya = lamanya fase yang ditunggu,
yang punya batasnya sendiri. Versi yang di-fail-fast: log = satu baris `DONE rc=not-run …`.

**Browser paralel** (Lapis 4, versi diadmisi biaya n — Slot sedaemon di bawah): sesudah
`warmup-bo` proses versi mengambil `snapshot-db`, lalu tiap engine di-drive worker sendiri yang
menulis ke log versi yang sama — baris worker ber-`pid` lain (job & run sama), nama fasenya
menyebut engine (`browser:<engine>`, `lock-wait:<engine>`, `barrier-wait:<engine>`), dan worker
tak pernah menulis `DONE` (hanya proses versi). `lock-wait:<engine>` = menunggu kunci BO
(`ALIVE` menyebut engine pemegangnya), `barrier-wait:<engine>` = menunggu engine lain
menyelesaikan step lockstep (`ALIVE` menyebut yang belum); keduanya tanpa batas waktu sendiri
dan tak pernah `SLOW`. Sesudah semua worker selesai, pass konfirmasi sekuensial per engine:
`rerun-seq:<engine>` (membungkus health, reset, dan drive; END `<sub-fase>-failed` bila reset
gagal) atau, bila login BO engine itu saja yang gagal, `browser:<engine>` kedua (detail START
menyebut fallback login BO); keduanya diawali reset `reset-db`, `reset-files`, `reset-opcache`,
lalu `wait-http`, `warmup-bo` lagi. Di rekaman, fase berulang berakhiran `#2`, `#3`
(`browser:<engine>#2`, `wait-http#2`). Biaya 1 (`--sequential-browsers`): engine berurutan dalam
proses, `snapshot-db` lalu reset yang sama sebelum tiap engine berikutnya, tanpa
`lock-wait`/`barrier-wait`/`rerun-seq`.

**Ritme:** jalankan di latar (mis. Claude Code: Bash `run_in_background`, lalu baca ekor log
tiap 30–60 dtk), dan beri Budi satu baris per cek — versi, fase, durasi. Harness tanpa
eksekusi latar: Lapis 2/5 satu versi per panggilan (`--versions V --jobs 1`) supaya tiap panggilan
pendek, dan baca log-nya di antara panggilan; Lapis 4 tetap persis `e2e_cells_arg` plan.

**Diduga macet** bila (a) baris terakhir `SLOW` — kecuali `SLOW browser:<engine>` worker
paralel selagi `lock-wait:<engine>`/`barrier-wait:<engine>` engine itu masih ber-`ALIVE`
(fase luarnya ikut menghitung waktu tunggu; yang menunggu = engine lain, lihat fasenya), atau (b) mtime log tak berubah ±3 menit dan
belum ada `DONE` — artinya proses menggantung di luar fase berlog atau sudah mati. Laporkan
ke Budi: job, versi, fase, durasi. Tawarkan pilihan: tunggu sampai batas waktu fasenya (skrip
lalu degrade jujur sendiri), atau hentikan job itu (`--stop-job`, di bawah). **Jangan
menghentikan sendiri tanpa persetujuan** — run sesi lain bisa sedang berbagi daemon yang
sama, dan `SLOW` saat banyak sesi jalan sering berarti lambat, bukan mati. Macet berulang di
`wait-healthy`/`bring-up` saat banyak sesi paralel biasanya tanda RAM/daemon penuh: Lapis 2/5
turunkan `--jobs`; Lapis 4 turunkan `psm_e2e_slots` (cap sedaemon — container Lapis 2/5 tak
pernah dihitung di dalamnya).

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

## Istilah E2E (tier, CAP-1)

- **Cakupan run** = versi × browser pilihan On Activation langkah 2 (headless: semua sel
  terkonfigurasi di `<cfg>`). **Plan cakupan-run** = satu-satunya panggilan plan yang field
  E2E-nya (dan `rerun_matrix`) dibaca; `--versions`/`--browsers` = cakupan run (boleh dihilangkan
  bila cakupan = semua terkonfigurasi):

  ```bash
  uv run scripts/ps-plan-layers.py <module-path> --reports-dir <psm_reports_dir> \
    --versions <versi cakupan> --browsers <browser cakupan> --per-version --session <t> --config <cfg>
  ```

  Plan loop Fase 1 (`--versions V`) hanya dibaca `per_version[V]`, field E2E-nya tidak.
- **Tier milik plan** (`ps-plan-layers.py --help`): `e2e_step` tier 0 = `focus` (sel fokus),
  `cold-version` (versi sel fokus × semua browser), `cold-canary` (canary); tier 1 = `gate` (sel
  yang belum terbukti); tanpa tier = `done`, `blocked-not-gradeable`, `blocked-infra`;
  `blocked-by-scope` = langkah ber-tier yang selnya di luar cakupan run (`e2e_required_cells`
  menyebut sel yang dibutuhkan). Canary = `psm_e2e_canary` (kosong = versi target terbaru ×
  chromium). `e2e_focus_cell` = sel gagal terbaru, atau canary; `e2e_focus_recorded_failure` = sel
  itu punya kegagalan tercatat.
- **Run E2E = persis plan.** Jalankan tepat `--cells <e2e_cells_arg> --tier <e2e_tier>` dari plan
  cakupan-run terbaru (`e2e_cells_arg` null → tanpa run); jangan pernah memilih sel atau tier
  dengan judgment. Interim sampai CAP-4/5: tiap run dingin dan skenario penuh, satu boot per
  versi — browser paralel bila versi diadmisi biaya n, berurutan dengan reset ke snapshot di
  antara engine bila biaya 1 (Slot sedaemon, di bawah) — `e2e_warm` dan `e2e_scenarios:
  failed-only` diabaikan. Akibatnya pass dingin penuh di loop perbaikan sudah membersihkan sel gagal:
  `cold-version` terlewati dan browser lain versinya dibuktikan ulang di tier 1 — diurut ulang,
  tak pernah dibuang.
- **V bersih** = `per_version[V].clean` dari plan loop V, kecuali (state sesi-mu): (a) **tanpa
  Docker** — run Lapis 2/5 V yang melaporkan `skipped` dihitung sudah, dan V bersih bila file
  Lapis 1 per-versi V tak punya temuan ber-severity `error` (plan tetap `clean: false` di sana,
  karena `phase1_reuse` false — penilaianmu yang menang); (b) headless: bersih begitu loop V
  menjalankan lapis basinya sekali, apa pun temuannya.
- **Versi tuan rumah** = versi `e2e_focus_cell` dari plan cakupan-run di awal sesi dan di tiap
  loop-balik (di luar cakupan → versi tercakup pertama, urut numerik). Loop-nya jalan pertama dan
  menampung semua langkah tier 0 sampai selesai, walau sel fokus pindah versi.
- **Loop E2E berakhir** (sesi-wide; dilaporkan, tak pernah lolos, langkahnya tak diulang): run
  mencetak `skipped`; langkah `blocked-*` (sebut `e2e_required_cells` dan `e2e_blocked_causes`);
  `psm_e2e_enabled` false atau `--require` tanpa `e2e`; stop konvergensi (Fase 1); aturan exit dan
  sebab infra di bawah. Loop tuan rumah berhenti menunggu `gate`/`done`; Fase 2 tetap menjalankan
  lapis lainnya.
- **Hasil run** dibaca dari plan cakupan-run berikutnya, **tak pernah** dari histori (satu
  pengecualian: Tinjauan visual, di bawah, membaca `screenshots` baris terbarunya). Per exit
  `ps-run-layer.py --layer e2e`:
  - 0, 1 atau 3 dengan baris output → baca lewat plan berikutnya (juga anak yang dihentikan:
    selnya tak mendapat rekaman dan mempertahankan rekaman lamanya);
  - 2 dengan baris output (anak exit 2) → loop E2E berakhir; laporkan stderr-nya;
  - 2 tanpa baris output (error input pra-spawn atau gagal append) → loop **tak** berakhir:
    interaktif perbaiki lalu ulangi; headless `blocked` + stderr seketika, tanpa wrap-up;
  - 143 (`--stop-job`) → interaktif: loop E2E berakhir kecuali Budi minta ulang; headless:
    `headless.md`;
  - lainnya (130, atau 1 tanpa baris output, mis. traceback) → interaktif: tampilkan stderr, tanya
    Budi ulang atau akhiri loop E2E; headless `blocked` + stderr, tanpa wrap-up.

  Tiap ulang = plan cakupan-run baru dan `e2e_cells_arg`-nya.
- **Sebab infra per versi V** (di bawah `blocked-infra`): run meninggalkannya untuk V bila plan
  berikutnya memberi entri e2e `rerun_matrix` ber-`reason` `inconclusive`, `inconclusive-steps`
  atau `browser-notes` untuk sel V yang ada di `appended` baris output run itu (run tanpa baris
  output tak meninggalkan apa-apa; `not-run` dan `fail` tak pernah sebab infra). Sebutkan sebabnya
  dari stderr dan log kemajuan (mis. image hilang, `browser-unavailable`, `no-slots`). Sebelum run
  berikutnya yang `e2e_next_cells`-nya memuat sel V, interaktif minta Budi memperbaiki lingkungan
  (mis. `--allow-image-pull`, `playwright install`; `no-slots`: di bawah) atau menolak; menolak →
  loop E2E berakhir. Sebab V terhapus begitu Budi menjawab "sudah" atau plan berikutnya tak lagi
  memberi alasan itu untuk sel V. Dua rekaman infra beruntun satu sel dalam sesi → plan sendiri
  memberi `blocked-infra`.
- **`not-run`** (rekaman, `conclusive: false`): sel yang tak pernah dimulai karena fail-fast —
  `fail-fast after <ver>:<browser>` (anak lain meng-append `fail`) atau `input-error after <ver>`
  (anak lain exit 2). Bukan kegagalan dan bukan alasan infra (plan: reason `not-run`); tak
  pernah lulus, tak pernah gate-grade; plan menurunkannya lagi di langkah berikutnya (anak exit 2
  tetap mengakhiri loop E2E). Fail-fast hanya menghemat waktu untuk sel yang **masih antre**:
  anak yang sudah jalan selesai dan di-append.
- **`no-slots`** (rekaman `inconclusive`, reason `no-slots`; plan: `inconclusive`): cap slot
  sedaemon penuh selama batas startup (`--startup-timeout` passthrough, else
  `psm_flashlight_startup_timeout`, else 180 dtk; dihitung hanya saat tak ada anak run ini yang
  jalan). Alasan infra; `errors` menyebut isi cap. Diperbaiki dengan membebaskan slot (job lain
  selesai/dihentikan atas izin Budi, yatim dibersihkan) atau menunggu, atau — bila `errors`
  berkata `docker count failed` — memperbaiki Docker; **tak pernah** dengan install
  (`--allow-image-pull`, `playwright install`).
- **`parallel-unconfirmed`**, **`sequential-reset`**, **`crash`** worker (rekaman `inconclusive`;
  plan: `inconclusive`): alasan infra (Sebab infra per versi, di atas), tak pernah lulus.
  `parallel-unconfirmed` = run browser paralel punya temuan yang wajib dikonfirmasi sekuensial,
  tapi `snapshot-db`, health container, atau reset (`reset-db`/`reset-files`/`reset-opcache`/
  `wait-http`) gagal: `findings` kosong, temuan paralelnya di `parallel_only`, sub-fase gagal di
  `errors` sel. `sequential-reset` = di fallback sekuensial (biaya 1) snapshot, health, atau
  reset sebelum engine berikutnya gagal: engine yang belum jalan tak di-drive, sub-fase di
  `errors` selnya. `crash` worker = worker engine mode paralel keluar tanpa hasil terbaca (exit
  code di `browser_notes`); engine lain tak terdampak. Diperbaiki dengan run ulang (sesudah
  `parallel-unconfirmed` run berikutnya versi itu otomatis diadmisi biaya 1 sekuensial), setelah
  memeriksa kesehatan container (RAM/daemon; `health: <status>` di `errors`), stderr anak, dan
  baris `END` `snapshot-db`/`reset-*`/`rerun-seq:<engine>` di log kemajuan; **tak pernah**
  dengan install.
- **Slot sedaemon**: N = `psm_e2e_slots` dari `<cfg>` (`--slots` hanya override manual; jangan
  diberikan). Terpakai = jumlah label `psm.slots` semua container E2E yang jalan di daemon (run
  dan sesi lain, juga `ps-e2e-run.py` langsung — yang ikut terhitung tapi melewati admisi) +
  klaim run lain yang container-nya belum jalan, dibandingkan dengan N **run ini**:
  `psm_e2e_slots` yang sama di semua sesi = satu langit-langit bersama. Klaim dari folder temp
  lain baru terlihat begitu container-nya jalan. Container Lapis 2/5 tak dihitung (mereka tetap
  `--jobs`). Biaya: versi yang men-drive n browser diadmisi biaya n (browser paralel dalam satu
  boot) bila n slot bebas, else biaya 1 dengan `--sequential-browsers` (berurutan, reset di
  antara engine); `ps-e2e-run.py` langsung berlabel n bila paralel, else 1. Versi yang salah
  satu sel terkonfigurasinya punya rekaman terbaru `parallel-unconfirmed` (juga histori tak
  terbaca atau berekor rusak) selalu biaya 1 sekuensial, berapa pun slot bebas.
- **Tinjauan visual** (interaktif saja): hanya run dingin
  skenario penuh — interim itu semua run, termasuk `focus`. Tiap run interaktif ber-`--
  --screenshot-dir <psm_reports_dir>/e2e-shots`; untuk tiap sel di `appended` yang di-drive
  (`pass`/`fail`), tinjau file di `screenshots` baris **terbaru** histori selnya
  `<psm_reports_dir>/<module>-e2e-<ver>-<browser>.jsonl` (pola path dari `ps-run-layer.py
  --help`) — satu-satunya baca histori yang sah. Run dir berstempel ada di baris stderr
  `screenshots:`; di bawahnya `<ver>/`, mode paralel `<ver>/<engine>/` atau, sesudah pass
  konfirmasi, `<ver>/<engine>-seq/`. Cacat
  yang kamu yakini memblok → read-merge ke `<psm_reports_dir>/<module>-visual-pending.json`
  (bentuk `findings` seperti file adversarial; tiap entri bertanda `session` `<t>` dan
  `source_fingerprint` baris output run-nya). Tak pernah mengubah state sel atau memicu
  loop-balik; digabung di wrap-up.

Baris terakhir stdout run E2E: `{"e2e_status": "ran"|"skipped", "reason", "appended":
["<ver>:<browser>", …], "source_fingerprint"}`. Exit 0 = semua pass atau `skipped`; 1 = ada
inconclusive/`not-run`/`no-slots`; 3 = ada `fail`; 2 = error input pra-spawn (tanpa baris) atau
anak exit 2 (baris `ran`); 143 = dihentikan `--stop-job` (tanpa baris). `--tier` wajib di tiap
run non-`--merge-only` dan dilarang bersama `--merge-only` (exit 2); `--jobs` dengan lapis e2e =
exit 2 (konkurensi E2E = slot, di atas).

## Fase 1 — konvergensi per versi

Awal sesi (dan tiap loop-balik): plan cakupan-run → versi tuan rumah. Loop tuan rumah jalan
pertama, lalu loop tiap versi cakupan lain. Satu iterasi loop V:

```bash
uv run scripts/ps-plan-layers.py <module-path> --reports-dir <psm_reports_dir> \
  --versions V --per-version --session <t> --config <cfg>
```

1. Jalankan lapis di `per_version[V].rerun` selain `adversarial` dan `e2e` (Lapis 1:
   `ps-static-scan.py <module-path> --versions V --reports-dir <psm_reports_dir> --per-version
   --config <cfg>`; Lapis 2/5: `ps-run-layer.py --layer <flashlight|scenario> --module
   <module-path> --versions V --reports-dir <psm_reports_dir> --per-version --config <cfg>`).
2. V tak bersih → patch temuan pemblokir (atau stop konvergensi), ulangi dari plan.
3. Hanya loop tuan rumah, begitu V bersih: plan cakupan-run; langkah tier 0 (`focus`,
   `cold-version`, `cold-canary`) dengan `e2e_cells_arg` tak null →

   ```bash
   uv run scripts/ps-run-layer.py --layer e2e --module <module-path> \
     --reports-dir <psm_reports_dir> --cells <e2e_cells_arg> --tier <e2e_tier> \
     --session <t> --config <cfg> -- --screenshot-dir <psm_reports_dir>/e2e-shots
   ```

   (`-- --screenshot-dir …` interaktif saja.) Plan cakupan-run sesudahnya: sel fokus gagal
   (`e2e_focus_recorded_failure` true) → patch (atau stop konvergensi), ulangi dari plan V;
   langkah tier 0 lain → iterasi berikutnya.

Loop versi lain selesai begitu V bersih; loop tuan rumah begitu V bersih **dan** `e2e_step`
`gate` atau `done`, atau loop E2E berakhir.

**Stop konvergensi** (interaktif, aksi Budi — untuk temuan Lapis 1/2/5 atau kegagalan E2E sel
fokus yang tak akan diperbaiki sesi ini). Tawarkan di samping patch di tiap iterasi Fase 1 saat V
tak bersih atau `e2e_focus_recorded_failure` plan cakupan-run terbaru true (juga di loop versi
lain — hanya run E2E yang mengubahnya); jalan hanya bila Budi memilihnya. Efeknya: loop E2E dan
semua loop Fase 1 berakhir seketika, cek masuk Fase 2 dilewati, tak ada langkah E2E lagi (tier 1
tak jalan); spawn lensa Lapis 3, lalu wrap-up. Vonis `ready: false` apa pun kata agregat.
Laporan: konvergensi dihentikan operator di `e2e_step` `<step>` (tier `<e2e_tier>`) plan
terakhir, temuan Lapis 1/2/5 terbuka per versi, sel E2E yang gagal, dan tiap sel terkonfigurasi
tanpa bukti lulus gate-grade sebagai tak terbukti. Headless tak punya prompt ini: ia berhenti di
langkah E2E tak bersih pertama (`headless.md`).

`all_reuse` hanya informatif (per-versi `rerun` selalu memuat `adversarial`) — gerbangnya
`clean`/`phase1_reuse` dan `e2e_step`. Perbaiki spec di `e2e_scenario_notes` sebelum Lapis 4
boot. File per-versi dan histori versi lain tak disentuh, jadi buktinya menetap: cek ulang satu
versi = boot Docker 1×, bukan 3×.

## Fase 2 — gerbang rilis

1. **Cek masuk**: plan cakupan-run sesudah loop terakhir selesai harus menunjukkan tiap versi
   cakupan bersih dan `e2e_step` `gate` atau `done` — kecuali loop E2E berakhir atau konvergensi
   dihentikan. Tidak → loop versi yang kotor jalan lagi, dan untuk langkah tier 0 loop tuan rumah
   (versi `e2e_focus_cell` panggilan ini), lalu cek lagi: patch di loop mana pun membuka ulang
   tiap versi yang Lapis 1/2/5 atau bukti canary-nya ia basikan.
2. **Lapis 3**: spawn keempat subagent lensa dalam satu giliran (`references/adversarial-lens.md`),
   kecuali plan kanonik (flag sama tanpa `--per-version`) menunjukkan `layers.adversarial.reuse`
   true, atau lensa yang di-spawn di bawah `source_fingerprint` plan yang sama masih belum
   digabung. Hasil lensa yang belum digabung dibuang di tiap loop-balik (dan bila
   `source_fingerprint`-nya lain), tak pernah digabung. Konteks mereka bersih, jadi lanjutkan
   lapis skrip selagi mereka bekerja — selama outputnya tak kamu teruskan ke mereka (fallback
   inline justru WAJIB dikerjakan sebelum kamu membaca output apa pun).
3. **Loop tier 1**, selama `e2e_step` `gate`: jalankan perintah run E2E Fase 1 langkah 3 dengan
   `e2e_cells_arg` dan `--tier <e2e_tier>` plan terbaru, lalu plan cakupan-run lagi. `gate` →
   ulangi; langkah tier 0 → **loop-balik**: buang hasil Lapis 3 yang belum digabung, masuk lagi
   ke Fase 1 (tuan rumah = versi `e2e_focus_cell`), lalu Fase 2 dari cek masuk; `done` atau loop
   E2E berakhir → wrap-up.

## Wrap-up (sekali, tanpa boot)

Sesudah loop tier 1 keluar (atau stop konvergensi), sekali, **tanpa** gerbang `all_reuse`, urut:

1. Read-merge Lapis 3 (bila di-spawn; hanya hasil yang di-spawn di bawah `source_fingerprint`
   plan terakhir).
2. `<module>-visual-pending.json` (bila ada): read-merge `findings`-nya ke file adversarial,
   kecuali entri sesi lain atau ber-`source_fingerprint` ≠ plan terakhir, lalu hapus file itu.
3. `--merge-only` Lapis 2 dan 5 (Lapis 5 bila module punya skenario) atas **versi dalam cakupan
   run saja** — file per-versi versi lain tak pernah di-plan ulang sesi ini, jadi bisa basi dan
   agregat tak bisa melihatnya. Versi yang dihilangkan jadi tak konklusif dan `ready` jatuh:

   ```bash
   uv run scripts/ps-run-layer.py --layer <flashlight|scenario> --module <module-path> \
     --reports-dir <psm_reports_dir> --versions <versi dalam cakupan run> --merge-only
   ```

4. Tampilan laporan E2E (bukan bukti; tanpa `--versions`/`--cells`/`--session`/`--tier`/passthrough):

   ```bash
   uv run scripts/ps-run-layer.py --layer e2e --module <module-path> \
     --reports-dir <psm_reports_dir> --config <cfg> --merge-only
   ```

5. Pindai Lapis 1 lintas-versi ke `<module>-static.json`: `ps-static-scan.py <module-path>
   --versions <semua terkonfigurasi> --reports-dir <psm_reports_dir> --config <cfg>`.
6. `ps-aggregate.py --reports-dir <psm_reports_dir> --module <module-path> --config <cfg>`
   (headless: `+ --session <t>`; SKILL.md > Vonis). Laporan menyebut tiap sel terkonfigurasi tanpa
   bukti lulus gate-grade sebagai tak terbukti, dan loop E2E yang berakhir beserta sebabnya.

**Read-merge wajib pada file adversarial.** `<psm_reports_dir>/<module>-adversarial.json`
ditulis dari dua arah — gabungan keempat lensa Lapis 3 (atau satu tulisan per lensa di
fallback inline), plus cacat visual Lapis 4 dari `visual-pending.json` (yang juga ditulis lewat
read-merge) — jadi **tiap** tulisan wajib membaca `findings` yang ada, menambahkan miliknya, lalu
menulis balik dengan `versions` top-level di-union. Menimpanya membuang temuan pemblokir yang sudah dikonfirmasi, diam-diam, dan
`ready` tetap true di atasnya.
