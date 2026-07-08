# prestashop-flashlight (lingkungan uji Docker)

Diseed 2026-06-29. Image: `prestashop/prestashop-flashlight` (Docker Hub).

## Status lokal (per 2026-06-29)
- Docker 29.6.0 terpasang ✓
- Image tersedia: `prestashop/prestashop-flashlight:nightly` (untuk 9.0) ✓
- Ditarik 2026-06-29: `1.7.8.11` (1.7.8) & `8.1.6-nginx` (8.1).

## Tag map (dari config psm_flashlight_tag_map)
`1.7.8=1.7.8.11`, `8.1=8.1.6-nginx`, `9.0=nightly`.

**CATATAN tag scheme (2026-06-29):** skema tag flashlight berubah — tag `8.1` polos **tidak ada lagi**. Sekarang per-patch + varian, mis. `8.1.6-nginx`, `8.2.7-nginx`. Untuk lini 8.1 pakai patch tertinggi yang ada (`8.1.6-nginx`). `1.7.8.11` masih valid. Verifikasi tag via Docker Hub API sebelum pull: `curl .../tags/<tag>` → HTTP 200.

## ENV kunci
`INSTALL_MODULES_DIR`, `PS_DOMAIN`, `XDEBUG_ENABLED`, `BLACKFIRE_ENABLED`, `ON_INSTALL_MODULES_FAILURE=continue`, `DEBUG_MODE`.

## Use case
- Install module per tag target & cek instalasi sukses.
- "Validate a module with the PrestaShop coding standard" — jalankan PHPStan lvl5 + coding standard di dalam container. → [[validator-rules]].
- Compose: flashlight + MySQL.

Detail operasional ada di skill psm-validate (`{project-root}/skills/psm-validate/SKILL.md`).

Sumber: flashlight README (Docker Hub).
