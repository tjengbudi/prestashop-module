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
| 3 adversarial | — | **tidak**: satu review lintas-versi di Fase 2 |
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

Segarkan tiap (lapis, versi) yang masih `rerun` dalam SATU panggilan per lapis:

```bash
uv run scripts/ps-run-layer.py --layer <flashlight|e2e> --module <module-path> \
  --versions <yang rerun> --reports-dir <psm_reports_dir> --per-version --jobs <N>
```

`--jobs` mengatur berapa versi boot serentak (default 3; tiap job satu container PS + DB —
turunkan di mesin kecil). Saat `all_reuse` true, satukan jadi kanonik dengan perintah yang
sama ber-`--versions <semua> --merge-only`; versi tanpa file dihilangkan, jadi agregat tak
konklusif dan `ready` jatuh.

Lapis 1 & Lapis 3 dijalankan sekali lintas-versi langsung ke file kanonik.

**Read-merge wajib pada file adversarial.** Bila `<psm_reports_dir>/<module>-adversarial.json`
sudah memuat temuan (mis. cacat visual dari Lapis 4), Lapis 3 harus membaca `findings` yang
ada, menambahkan miliknya, lalu menulis balik. Menimpanya membuang temuan pemblokir yang
sudah dikonfirmasi peninjau, diam-diam, dan `ready` tetap true di atasnya.
