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
| 3 adversarial | — | **tidak**: satu review lintas-versi, inline, di awal Fase 2 |
| 4 e2e | `ps-run-layer.py --layer e2e --per-version` | ya |

Teruskan `--config <psm_reports_dir>/psm-config.json` ke Lapis 1/2/4 dan ke plan, plus
`--tag-map`/`--extra-rules` yang sama bila dipakai — plan yang tak melihat tag yang berlaku
membaca bukti dari image lain sebagai segar.

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

**Mulai dari Lapis 3** bila plan menandainya `rerun`: ia review inline oleh model, jadi apa pun
yang kamu baca lebih dulu mewarnai vonisnya — output sweep lapis lain sekalipun. Prosedur
empat-lensa dan higiene konteksnya: `references/adversarial-lens.md`. Baru setelah itu,
lapis skrip.

Segarkan tiap (lapis, versi) yang masih `rerun` dalam SATU panggilan per lapis:

```bash
uv run scripts/ps-run-layer.py --layer <flashlight|e2e> --module <module-path> \
  --versions <yang rerun> --reports-dir <psm_reports_dir> --per-version --jobs <N>
```

`--jobs` mengatur berapa versi boot serentak (default 3; tiap job satu container PS + DB —
turunkan di mesin kecil). Saat `all_reuse` true, satukan jadi kanonik dengan perintah yang
sama ber-`--versions <semua> --merge-only`; versi tanpa file dihilangkan, jadi agregat tak
konklusif dan `ready` jatuh.

Lapis 1 & Lapis 3 dijalankan sekali lintas-versi langsung ke file kanonik — Lapis 3 di awal
fase (lihat atas).

**Read-merge wajib pada file adversarial.** `<psm_reports_dir>/<module>-adversarial.json`
ditulis dari dua arah dan berkali-kali — satu tulisan per lensa Lapis 3, plus cacat visual
Lapis 4 — jadi **tiap** tulisan wajib membaca `findings` yang ada, menambahkan miliknya, lalu
menulis balik. Menimpanya membuang temuan pemblokir yang sudah dikonfirmasi, diam-diam, dan
`ready` tetap true di atasnya.
