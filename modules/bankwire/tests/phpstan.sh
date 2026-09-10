#!/bin/bash
# Jalankan PHPStan atas module bankwire di dalam PrestaShop core asli (image flashlight),
# per versi target. Config neon di tests/phpstan/phpstan-<versi>.neon menyertakan
# ps-module-extension.neon (stub Module/Tab) supaya $this->module dsb ter-resolve.
#
# Pemakaian: ./tests/phpstan.sh <versi>   (versi: 1.7.8 | 8.1 | 9.1)
# Butuh Docker. Image flashlight ditarik otomatis bila belum ada lokal.

PS_VERSION=$1

set -e

if [ -z "$PS_VERSION" ]; then
    echo "Pemakaian: $0 <versi>   (1.7.8 | 8.1 | 9.1)"
    exit 1
fi

# Pemetaan versi target -> tag image flashlight yang tervalidasi.
case "$PS_VERSION" in
    1.7.8) PS_TAG="1.7.8.11" ;;
    8.1)   PS_TAG="8.1.6-nginx" ;;
    9.1)   PS_TAG="9.1.4-nginx" ;;
    *) echo "Versi tak dikenal: $PS_VERSION (pakai 1.7.8 | 8.1 | 9.1)"; exit 1 ;;
esac

IMAGE="prestashop/prestashop-flashlight:${PS_TAG}"

echo "PHPStan bankwire terhadap ${IMAGE} (level 5)"

# Extension resmi PrestaShop di image flashlight (bukan di vendor/ modul). Neon commit
# (tests/phpstan/phpstan.neon) menunjuk path composer standar agar portable di luar
# flashlight; untuk run ini kita rakit neon sementara dengan path image yang benar.
EXT=/var/opt/prestashop/coding-standards/phpstan/ps-module-extension.neon

# Core flashlight sudah membawa phpstan; mount module lalu analisa. --entrypoint melewati
# skrip boot web image (yang menuntut PS_DOMAIN) — analisis statis tak melayani HTTP.
docker run --rm \
    --entrypoint sh \
    -v "$PWD":/var/www/html/modules/bankwire \
    -e _PS_ROOT_DIR_=/var/www/html \
    --workdir=/var/www/html/modules/bankwire \
    "$IMAGE" \
    -c "M=/var/www/html/modules/bankwire; \
        printf 'includes:\n    - %s\nparameters:\n    level: 5\n    paths:\n        - %s/bankwire.php\n        - %s/classes\n        - %s/controllers\n        - %s/upgrade\n' '$EXT' \"\$M\" \"\$M\" \"\$M\" \"\$M\" > /tmp/phpstan-run.neon && \
        phpstan analyse --no-progress --memory-limit=-1 -c /tmp/phpstan-run.neon"
