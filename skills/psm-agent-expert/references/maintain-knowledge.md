# Rawat & perbarui knowledge base

Knowledge base bersama module psm hidup di `{project-root}/_bmad/psm/memory/` dan kamu kuratornya. Strukturnya:

```
_bmad/psm/memory/
  tech/        # breaking-changes-8.md, breaking-changes-9.md, cross-version-patterns.md,
               # hooks.md, services-di.md, persistence.md, composer-structure.md,
               # validator-rules.md, flashlight.md
  ecommerce/   # function-catalog.md
  projects/    # <module>.md — state per module; _budi-prefs.md — preferensi pribadi Budi
```

## First run — bangun & seed

Struktur direktori & daftar file punya satu bentuk benar — itu plumbing, bukan judgment. Jalankan `uv run {skill-root}/scripts/init-kb.py {project-root}/_bmad/psm/memory` untuk membuat pohon & stub secara deterministik (idempoten, tak menimpa isi yang sudah ada; keluaran `needs_seed` = file yang masih perlu kamu isi). Lalu seed ISI file itu dari sumber yang sudah ada (jangan menulis dari nol) — itu bagian judgment-mu:

- **tech/** — riset devdocs mendalam sudah terkumpul di `{project-root}/skills/reports/prestashop-module-builder-plan.md` (bagian "Riset mendalam"). Pindahkan ke file tech/ yang sesuai. Pola cross-version teknis ada lengkap di `{project-root}/skills/psm-cross-version/references/version-safe-patterns.md` → ringkas/rujuk ke `tech/cross-version-patterns.md`. Aturan validator ada di `{project-root}/skills/psm-validate/assets/ps-rules.json` → rangkum ke `tech/validator-rules.md`.
- **ecommerce/** — katalog fungsi ada di `{project-root}/skills/psm-develop/references/ecommerce-function-catalog.md` → seed `ecommerce/function-catalog.md`.

**Bila sebuah sumber seed tak ada** (mis. agent dipasang tanpa skill psm saudaranya): lewati sumber itu dan seed file tersebut dari riset devdocs (WebReader) sebagai gantinya, lalu tandai di file mana entri yang berasal dari riset (bukan katalog). Jangan biarkan first run buntu atau menghasilkan knowledge base setengah kosong yang nanti dipercaya sebagai kebenaran — first run harus tetap produktif.

## Perbarui (knowledge base hidup)

Saat menemukan breaking change baru, perilaku versi baru, atau pola yang berhasil: tulis/perbarui file tech/ atau ecommerce/ yang relevan. Riset devdocs devdocs.prestashop-project.org dengan **WebReader**, bukan WebFetch — WebReader lebih lengkap untuk situs itu. Ini rumah kanonik aturan tool tersebut; kapabilitas lain yang perlu meriset devdocs merujuk ke sini. Catat sumber & tanggal di file. Tiap rilis PrestaShop baru adalah pemicu untuk memperbarui `tech/breaking-changes-*.md`.

**Bila riset baru bertentangan dengan fakta terkurasi yang ada** (mis. perilaku berubah di patch berikutnya): jangan diam-diam mempercayai yang lama atau menimpa yang lama tanpa jejak. Tandai konflik ke Budi, utamakan fakta bersumber yang lebih baru, dan perbarui entri dengan catatan lama→baru + sumber & tanggal — supaya KB tak mengeras jadi jawaban usang yang dipercaya sebagai kebenaran.

Simpan satu fakta per tempat yang jelas; jangan duplikasi antara tech/ dan katalog skill — bila katalog skill sudah lengkap, rujuk ke sana alih-alih menyalin.

**Preferensi pribadi Budi** (gaya kerja, keputusan berulang) disimpan di `projects/_budi-prefs.md`, terpisah dari knowledge teknis bersama. On Activation membacanya bila ada; kamu yang menulis/memperbaruinya saat Budi menyatakan preferensi yang bakal berulang.

**Dipanggil non-interaktif** (mis. terpicu rilis PrestaShop baru — "perbarui KB untuk PS9"): riset topik/file sasaran, tulis pembaruannya, dan kembalikan ringkasan terse — file yang tersentuh, sumber, tanggal — tanpa pembuka percakapan.
