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

Detail operasional ada di skill psm-validate (`{project-root}/.claude/skills/psm-validate/SKILL.md`).

Sumber: flashlight README (Docker Hub). Status & tag diverifikasi 2026-07-08.

## Verified additions 2026-11-18 `[core]`

- Local status: Docker 29.7.0; images present locally — `1.7.8.11`, `8.1.6-nginx`, `9.1.4-nginx` plus `latest` and `nightly`. Tag pins unchanged, so the 2026-07-08 tag-scheme note still holds (plain `9.1` / `9.1.4` are not pullable; use the `-nginx` patch tag).
- Runtime measured inside the images: 1.7.8.11 → PHP 7.4, 8.1.6-nginx → PHP 8.1, 9.1.4-nginx → PHP 8.5.
- Harness coordinates as resolved by config and `scripts/ps-flashlight-run.py` defaults: db image `mariadb:lts`, orchestrator `auto`, `PS_DOMAIN=localhost:8000`, startup timeout 180s, tag map `1.7.8=1.7.8.11, 8.1=8.1.6-nginx, 9.1=9.1.4-nginx`; Lapis 4 publishes the host port (8000) and the other layers do not.
- Verification trap worth repeating: a BO HTTP probe without a valid security token gets an "Invalid token" interstitial at HTTP 200 — a hook looks dead when it is not.
- Four unresolved inconsistencies in the `psm-validate` references (recorded rather than smoothed): `run-phases.md` says Lapis 1 is per-version in its layer table and once-cross-version in its phase-2 text; the "full 4-layer verdict" example in `e2e-quickstart.md` omits the Lapis 2 and Lapis 3 inputs that `headless.md` treats as default-required; all three describe four layers while `ps-run-layer.py --layer scenario` (Lapis 5) exists; port handling is described as floating per version in `e2e-quickstart.md` but forwarded as uniform coordinates in `run-phases.md`.
