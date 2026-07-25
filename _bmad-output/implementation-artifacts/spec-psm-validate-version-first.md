---
title: 'psm-validate: siklus perbaikan version-first (konvergensi per-versi + sweep rilis)'
type: 'feature'
created: '2026-07-25'
status: 'done'
review_loop_iteration: 0
context: []
baseline_commit: '656d468a961e9b43c9511c743f460b72a48f2a3c'
---

<frozen-after-approval reason="human-owned intent — do not modify unless human renegotiates">

## Intent

**Problem:** Validasi cross-version (1.7.8/8.1/9.1) memvonis atas file lapis **kanonik** yang satu-untuk-semua-versi. Karena source module tunggal, satu patch (mis. fix PS9) membasikan kanonik untuk SEMUA versi via gerbang mtime (`ps-plan-layers.py:127`), dan menjalankan ulang satu versi menimpa bukti versi lain — jadi tiap fix memaksa sweep penuh lintas-versi. Operator ingin konvergen per versi dulu (fix → cek ulang versi ITU saja) sampai bersih, baru sweep penuh sekali di akhir sebagai gerbang rilis.

**Approach:** Kembalikan file lapis **per-versi** `<module>-<lapis>-<versi>.json` sebagai artefak persisten (dihapus di commit 5b3a49b). `ps-plan-layers.py` dapat mode `--per-version` yang memvonis reuse/rerun tiap (lapis, versi) independen. `ps-run-layer.py` (pemilik tunggal penggabungan) dapat: mode persist per-versi, dan mode `--merge-only` yang menyatukan file per-versi jadi kanonik untuk sweep akhir — nama file DITURUNKAN by construction (bukan daftar yang diketik model), sehingga gerbang kesegaran/identitas/kelengkapan tetap utuh. SKILL.md ditulis ulang jadi dua fase: konvergensi per-versi lalu gerbang rilis.

## Boundaries & Constraints

**Always:**
- Vonis milik SKRIP, bukan model/prompt. Determinisme `ps-plan-layers.py`: input sama → keputusan byte-identik.
- Nama file per-versi & kanonik DITURUNKAN dari (reports-dir, module, lapis, versi) di dalam skrip — tak pernah dari daftar yang diketik pemanggil.
- `merge-only` menyetempel mtime kanonik = **min** mtime file per-versi inputnya (kanonik tak lebih segar dari bukti tertuanya).
- `ready` jujur tetap butuh sweep lintas-versi terakhir: fase rilis WAJIB jalankan `ps-plan-layers.py --per-version` atas SEMUA versi & pastikan semua `reuse` sebelum merge+aggregate. Versi tanpa bukti terkini → dihilangkan, agregat tak konklusif, `ready` jatuh.
- Pertahankan gerbang kejujuran lama: konklusivitas (`flashlight_conclusive`/`e2e_conclusive`), `e2e_smoke_only`, `layers_run`, degrade-jujur runner tanpa Docker/browser.
- TDD: tulis/aktifkan test lebih dulu; semua test lama tetap hijau.
- Prosa SKILL.md hanya menyebut flag yang BENAR-BENAR ada di scripts/.

**Ask First:**
- Menyentuh skrip lapis matang (`ps-static-scan.py`, `ps-flashlight-run.py`, `ps-e2e-run.py`) atau `ps-aggregate.py` — desain ini tak butuh; bila ternyata perlu, HALT.

**Never:**
- Menghidupkan ulang `ps-merge-versions.py` standalone (CLI daftar-file yang melucuti gerbang — sengaja dibunuh 5b3a49b).
- Mengubah bentuk output / exit code mode kanonik `ps-plan-layers.py` (regresi).
- Memindahkan logika reuse ke prompt, atau mengendurkan gerbang mtime.

## I/O & Edge-Case Matrix

| Scenario | Input / State | Expected Output / Behavior | Error Handling |
|----------|--------------|---------------------------|----------------|
| plan `--per-version`, 9.1 basi/8.1 segar | `<M>-flashlight-9.1.json` mtime<source, `<M>-flashlight-8.1.json` mtime>source | `per_version["8.1"].flashlight.reuse=true`; `per_version["9.1"].flashlight.reuse=false`, "flashlight" ∈ `per_version["9.1"].rerun` | N/A |
| plan `--per-version`, file per-versi absen | `<M>-static-8.1.json` tak ada | `reuse=false`, reason "file lapis belum ada" | N/A |
| plan `--per-version`, cakupan salah | `<M>-e2e-9.1.json` isinya `versions:{8.1:…}` | `reuse=false`, reason "cakupan kurang: 9.1" | N/A |
| plan mode kanonik (tanpa flag) | reports lama | Output & exit code IDENTIK versi sebelumnya (tanpa `mode`/`per_version`) | N/A |
| run-layer `--per-version` | `--layer flashlight --versions 9.1` | Tulis persisten `<M>-flashlight-9.1.json` (mtime=run start); TAK tulis kanonik | gerbang bentuk/tolak/token seperti default |
| run-layer `--merge-only` | file per-versi 3 versi ada | Baca+validasi+gabung → kanonik `<M>-flashlight.json`, mtime=min(input), exit 0 | konflik isi/bentuk → exit 2 |
| merge-only, satu versi absen | `<M>-flashlight-8.1.json` hilang | Kanonik memuat versi yang ada, 8.1 dihilangkan+disebut, exit 1 | N/A |
| merge-only, nol input ditemukan | tak ada file per-versi | Kanonik TAK ditulis, exit 1, alasan disebut | N/A |
| `--per-version` + `--merge-only` bersama | keduanya diset | exit 2, saling eksklusif | pesan stderr |
| merge-only + passthrough `-- …` | ada `--` extra | exit 2 (tak ada yang dijalankan) | pesan stderr |

</frozen-after-approval>

## Code Map

- `.claude/skills/psm-validate/scripts/ps-plan-layers.py` -- tambah mode `--per-version`; refactor `main()` ekstrak `prov_for(layer, versions, ruleset, tag_map)` + `plan_per_version(...)`; mode kanonik tak berubah.
- `.claude/skills/psm-validate/scripts/ps-run-layer.py` -- tambah `per_version_file()` (nama diturunkan), flag `--per-version` (persist) & `--merge-only` (assemble); pakai ulang `collect`/`validate_layer_shape`/`merge_versions_field`/`merge_toplevel`.
- `.claude/skills/psm-validate/SKILL.md` -- tulis ulang "Validate" + "Vonis dan output": Fase konvergensi per-versi & Fase gerbang rilis; subagent per-versi DEFAULT saat versi>1 kecuali skill jalan sebagai subagent (fallback serial dipertahankan).
- `.claude/skills/psm-validate/scripts/tests/test-ps-plan-layers.py` -- test per-versi (bukti selesai) + regresi kanonik.
- `.claude/skills/psm-validate/scripts/tests/test-ps-run-layer.py` -- test persist + merge-only (fungsi `test_*` baru didaftarkan di `main()`).

## Tasks & Acceptance

**Execution:**
- [x] `test-ps-plan-layers.py` -- TDD dulu: tambah `_layer_pv()` helper; check granularitas per-versi (9.1 rerun / 8.1 reuse), file absen→rerun, cakupan salah→rerun, provenance image per-versi, determinisme CLI (dua run identik), regresi mode kanonik.
- [x] `ps-plan-layers.py` -- `--per-version`: loop (versi × lapis) panggil `plan_layer(path_pv, [versi], src_mtime, rel, prov_for(...))`; output `mode:"per-version"`, `per_version:{versi:{layers,rerun}}`; ekstrak `prov_for`/`plan_per_version`. Kanonik tak tersentuh.
- [x] `test-ps-run-layer.py` -- TDD dulu: `test_per_version_persist` (N file per-versi ditulis, kanonik tidak, mtime=run start), `test_merge_only` (assemble+min-mtime+exit0; versi absen→exit1; nol→exit1; konflik→exit2), `test_modes_exclusive` (dua flag→exit2), `test_merge_only_rejects_passthrough`. Daftarkan di `main()`.
- [x] `ps-run-layer.py` -- `per_version_file()`; `--per-version` alihkan langkah tulis (kanonik→N persisten, mtime=started), sisanya (merge-untuk-exit, missing/degrade, exit code) tak berubah; `--merge-only` baca file per-versi persisten→validasi→gabung→kanonik(mtime=min). Guard eksklusif + tolak passthrough.
- [x] `SKILL.md` -- dua fase + konvensi nama file per-versi; hanya flag nyata.

**Acceptance Criteria:**
- Given source dipatch lalu HANYA `<M>-flashlight-9.1.json` dibasikan (mtime lebih tua) sementara `<M>-flashlight-8.1.json` segar, when `ps-plan-layers.py --per-version`, then 8.1 `reuse`, hanya 9.1 `rerun` (bukti selesai — dibuktikan skrip nyata).
- Given file per-versi 3 versi segar, when `ps-run-layer.py --merge-only`, then kanonik = union ketiganya dengan mtime = min(input), exit 0.
- Given semua test lama, when `uv run` tiap test, then hijau (nol regresi mode kanonik & default).

## Design Notes

Bentuk output `--per-version` (mode kanonik tetap seperti sekarang, TANPA `mode`/`per_version`):
```json
{ "module":"mymod","versions":["1.7.8","8.1","9.1"],"newest_source":"mymod.php",
  "mode":"per-version",
  "per_version":{ "8.1":{"layers":{"static":{"reuse":true,…},"flashlight":{…},
     "adversarial":{…},"e2e":{…}},"rerun":["e2e"]}, "9.1":{…} } }
```
`--per-version` (run-layer) = mode default PERSIS, hanya target tulis berubah: tetap `collect`→`validate_layer_shape`→merge (untuk keputusan exit/degrade), tapi tulis tiap payload per-versi ke `<reports>/<M>-<lapis>-<versi>.json` (mtime=run start), bukan satu kanonik. `--merge-only` tak men-spawn apa pun. Nama file per-versi untuk static/adversarial diproduksi skrip/subagent-nya sendiri via `-o` (didokumentasikan SKILL.md); hanya flashlight/e2e lewat run-layer.

Kejujuran mtime: satu patch source membasikan SEMUA file per-versi — "cek ulang satu versi" adalah disiplin workflow (boot Docker 1× bukan 3×), bukan sihir mtime. Fase rilis me-rerun versi mana pun yang basi lalu merge; `mtime=min(input)` merambatkan kebasian ke kanonik sebagai jaring pengaman kedua.

## Verification

**Commands:**
- `uv run .claude/skills/psm-validate/scripts/tests/test-ps-plan-layers.py` -- expected: SEMUA TEST LOLOS
- `uv run .claude/skills/psm-validate/scripts/tests/test-ps-run-layer.py` -- expected: SEMUA TEST LOLOS
- `uv run .claude/skills/psm-validate/scripts/tests/test-ps-aggregate.py` -- expected: hijau (tak tersentuh, bukti nol regresi hilir)
- Bukti nyata selesai: skrip kecil yang menulis dua file per-versi (9.1 tua, 8.1 muda) lalu `ps-plan-layers.py --per-version` → 8.1 reuse / 9.1 rerun.

## Suggested Review Order

**Verdict per-versi (inti desain)**

- Entry point: keputusan reuse/rerun tiap (lapis, versi), tiap versi dinilai sendiri.
  [`ps-plan-layers.py:200`](../../.claude/skills/psm-validate/scripts/ps-plan-layers.py#L200)

- Provenance satu-pemilik — dipakai mode kanonik & per-versi, jadi tak bisa mendrift.
  [`ps-plan-layers.py:185`](../../.claude/skills/psm-validate/scripts/ps-plan-layers.py#L185)

- Nama file per-versi diturunkan by construction (bukan diketik pemanggil).
  [`ps-plan-layers.py:174`](../../.claude/skills/psm-validate/scripts/ps-plan-layers.py#L174)

- Branch mode di `main()`; mode kanonik tetap byte-identik (nol regresi).
  [`ps-plan-layers.py:300`](../../.claude/skills/psm-validate/scripts/ps-plan-layers.py#L300)

**Persist & merge (orkestrator — pemilik tunggal penggabungan)**

- `merge-only`: satukan file per-versi → kanonik, mtime = bukti tertua, tanpa spawn.
  [`ps-run-layer.py:361`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L361)

- Guard identitas pada baca: file salah-label → exit 2 (temuan review B).
  [`ps-run-layer.py:400`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L400)

- Exit mengikuti run serial: pass-aware + degrade all-skip (temuan review A/C).
  [`ps-run-layer.py:446`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L446)

- `--per-version` persist; payload skip tak ditulis jadi file kosong (temuan review #3).
  [`ps-run-layer.py:602`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L602)

- Guard dua mode saling eksklusif + `merge-only` tolak passthrough.
  [`ps-run-layer.py:490`](../../.claude/skills/psm-validate/scripts/ps-run-layer.py#L490)

**Alur SKILL.md (kontrak model)**

- Fase 1 — konvergensi per-versi (loop perbaikan, boot Docker 1× per iterasi).
  [`SKILL.md:27`](../../.claude/skills/psm-validate/SKILL.md#L27)

- Fase 2 — gerbang rilis: sweep lintas-versi → merge → agregasi untuk `ready` jujur.
  [`SKILL.md:29`](../../.claude/skills/psm-validate/SKILL.md#L29)

- Subagent per-versi DEFAULT saat versi > 1, kecuali skill jalan sebagai subagent (fallback serial).
  [`SKILL.md:31`](../../.claude/skills/psm-validate/SKILL.md#L31)

**Tes (pendukung)**

- Bukti selesai + regresi kanonik: 8.1 reuse / 9.1 rerun, granularitas per-versi.
  [`test-ps-plan-layers.py:310`](../../.claude/skills/psm-validate/scripts/tests/test-ps-plan-layers.py#L310)

- Persist, merge-only, guard, + regresi temuan review (A/B/C, all-skip).
  [`test-ps-run-layer.py:583`](../../.claude/skills/psm-validate/scripts/tests/test-ps-run-layer.py#L583)
