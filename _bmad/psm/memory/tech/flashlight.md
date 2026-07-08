# prestashop-flashlight (lingkungan uji Docker)

Diseed 2026-06-29. Image: `prestashop/prestashop-flashlight` (Docker Hub).

## Status lokal (diverifikasi 2026-07-08)
- Docker 29.6.0 terpasang ✓
- Image lokal tersedia: `1.7.8.11`, `8.1.6-nginx`, `9.1.4-nginx`, `nightly` ✓ (semua target ada)
- `9.1.4-nginx` ditarik 2026-07-08 (1.53 GB, digest `sha256:3d8ad849…`).

## Tag map (dari config psm_flashlight_tag_map, diperbarui 2026-07-08)
`1.7.8=1.7.8.11`, `8.1=8.1.6-nginx`, `9.1=9.1.4-nginx`.

Target dinaikkan dari 9.0→**9.1** (stable kini 9.1.4, rilis 6/3/2026). Tag `9.1=9.1.4-nginx` **pinned** menggantikan `nightly` — reproducible, tak bergerak. Breaking 9.1 (Hummingbird/Bootstrap 5) → [[breaking-changes-9]].

**CATATAN tag scheme (diverifikasi 2026-07-08 via Docker Hub API):** skema tag per-patch + varian. Tag polos `9.1`/`9.1.4`/`9.0` **404** — wajib pakai bentuk `<patch>-nginx`. Terverifikasi HTTP 200: `1.7.8.11`, `8.1.6-nginx`, `8.2.7-nginx`, `9.1.4-nginx`, `nightly`. Selalu cek tag sebelum pull: `curl -s -o /dev/null -w "%{http_code}" https://hub.docker.com/v2/repositories/prestashop/prestashop-flashlight/tags/<tag>` → 200.

## ENV kunci
`INSTALL_MODULES_DIR`, `PS_DOMAIN`, `XDEBUG_ENABLED`, `BLACKFIRE_ENABLED`, `ON_INSTALL_MODULES_FAILURE=continue`, `DEBUG_MODE`.

## Use case
- Install module per tag target & cek instalasi sukses.
- "Validate a module with the PrestaShop coding standard" — jalankan PHPStan lvl5 + coding standard di dalam container. → [[validator-rules]].
- Compose: flashlight + MySQL.

Detail operasional ada di skill psm-validate (`{project-root}/skills/psm-validate/SKILL.md`).

Sumber: flashlight README (Docker Hub). Status & tag diverifikasi 2026-07-08.
