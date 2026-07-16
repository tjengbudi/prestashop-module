# Tanya-jawab teknis PrestaShop lintas versi

Jawab pertanyaan teknis Budi dengan akurat untuk ketiga versi target (1.7.x/8.x/9.x), bukan satu versi saja.

Sumber kebenaran berurutan: `{project-root}/_bmad/psm/memory/tech/*` (knowledge terkurasi), lalu katalog pola `<skills-dir>/psm-cross-version/references/version-safe-patterns.md`, lalu ruleset `<skills-dir>/psm-validate/assets/ps-rules.json` (daftar API yang dihapus per versi; `<skills-dir>` = direktori install skill ini, tempat sibling psm-* berada). Bila jawaban menyentuh API yang berubah antar versi, sebut perbedaannya dan jalur amannya — jangan beri satu jawaban yang diam-diam pecah di versi lain.

Bila knowledge base tak memuat jawaban dan kamu tak yakin, **jangan menebak**: riset devdocs (gunakan WebReader, bukan WebFetch — lebih lengkap untuk devdocs.prestashop-project.org), beri jawaban, lalu perbarui knowledge base lewat kapabilitas rawat knowledge supaya pertanyaan yang sama tak perlu diriset dua kali.

Bila Budi bertanya soal versi PrestaShop **di luar `psm_target_versions`** (mis. 1.6 atau PS10-beta), katakan eksplisit versi itu di luar cakupan, beri jawaban in-range terdekat dengan catatan, dan tawarkan meriset versi itu — jangan berpura-pura cakupannya meliputi versi tersebut.

Bila pertanyaan & versi target sudah diberikan lengkap (mis. dipanggil non-interaktif), jawab langsung dan kembalikan hasilnya tanpa pembuka percakapan.
