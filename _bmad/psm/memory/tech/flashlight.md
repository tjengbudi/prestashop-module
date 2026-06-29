# prestashop-flashlight (lingkungan uji Docker)

Diseed 2026-06-29. Image: `prestashop/prestashop-flashlight` (Docker Hub).

## Status lokal (per 2026-06-29)
- Docker 29.6.0 terpasang ✓
- Image tersedia: `prestashop/prestashop-flashlight:nightly` (untuk 9.0) ✓
- BELUM ada: tag `1.7.8.11` (untuk 1.7.8) dan `8.1` — perlu `docker pull` saat uji versi itu.

## Tag map (dari config psm_flashlight_tag_map)
`1.7.8=1.7.8.11`, `8.1=8.1`, `9.0=nightly`.

## ENV kunci
`INSTALL_MODULES_DIR`, `PS_DOMAIN`, `XDEBUG_ENABLED`, `BLACKFIRE_ENABLED`, `ON_INSTALL_MODULES_FAILURE=continue`, `DEBUG_MODE`.

## Use case
- Install module per tag target & cek instalasi sukses.
- "Validate a module with the PrestaShop coding standard" — jalankan PHPStan lvl5 + coding standard di dalam container. → [[validator-rules]].
- Compose: flashlight + MySQL.

Detail operasional ada di skill psm-validate (`{project-root}/skills/psm-validate/SKILL.md`).

Sumber: flashlight README (Docker Hub).
