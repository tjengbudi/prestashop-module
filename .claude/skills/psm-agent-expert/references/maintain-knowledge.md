# Rawat & perbarui knowledge base

Knowledge base bersama module psm hidup di `{project-root}/_bmad/psm/memory/` dan kamu kuratornya. Strukturnya:

```
_bmad/psm/memory/
  tech/        # breaking-changes-8.md, breaking-changes-9.md, cross-version-patterns.md,
               # hooks.md, services-di.md, persistence.md, composer-structure.md,
               # validator-rules.md, flashlight.md
  ecommerce/   # function-catalog.md, elicitation-lenses.md, adversarial-checks.md
  projects/    # <module>.md — profil per module: konvensi, keputusan,
               # fakta terkonsiliasi, jurnal. Diproduksi & direkonsiliasi
               # psm-module-context.
               # _budi-prefs.md — preferensi pribadi Budi; milikmu, bukan
               # milik psm-module-context (awalan _ menandai bukan module).
```

## First run — bangun & seed

Bila folder belum ada, buat strukturnya lalu seed dari sumber yang sudah ada (jangan menulis dari nol):

- **tech/** — riset devdocs mendalam sudah terkumpul di `{project-root}/skills/reports/prestashop-module-builder-plan.md` (bagian "Riset mendalam"). Pindahkan ke file tech/ yang sesuai. Pola cross-version teknis ada lengkap di `<skills-dir>/psm-cross-version/references/version-safe-patterns.md` (`<skills-dir>` = direktori install skill ini, tempat sibling psm-* berada) → ringkas/rujuk ke `tech/cross-version-patterns.md`. Aturan validator ada di `<skills-dir>/psm-validate/assets/ps-rules.json` → rangkum ke `tech/validator-rules.md`.
- **ecommerce/** — katalog fungsi ada di `<skills-dir>/psm-develop/references/ecommerce-function-catalog.md` → seed `ecommerce/function-catalog.md`.

**Bila sebuah sumber seed tak ada** (mis. agent dipasang tanpa skill psm saudaranya): lewati sumber itu dan seed file tersebut dari riset devdocs (WebReader) sebagai gantinya, lalu tandai di file mana entri yang berasal dari riset (bukan katalog). Jangan biarkan first run buntu atau menghasilkan knowledge base setengah kosong yang nanti dipercaya sebagai kebenaran — first run harus tetap produktif.

**`projects/` sengaja TAK di-seed.** Isinya lahir per module lewat **psm-module-context** saat module itu benar-benar dikerjakan; folder kosong di sini adalah keadaan benar, bukan pekerjaan yang tertinggal.

## Perbarui (knowledge base hidup)

Saat menemukan breaking change baru, perilaku versi baru, atau pola yang berhasil: tulis/perbarui file tech/ atau ecommerce/ yang relevan. Riset devdocs dengan **WebReader** (bukan WebFetch — lebih lengkap untuk devdocs.prestashop-project.org). Catat sumber & tanggal di file. Tiap rilis PrestaShop baru adalah pemicu untuk memperbarui `tech/breaking-changes-*.md`.

Simpan satu fakta per tempat yang jelas; jangan duplikasi antara tech/ dan katalog skill — bila katalog skill sudah lengkap, rujuk ke sana alih-alih menyalin.

**Preferensi pribadi Budi** (gaya kerja, keputusan berulang lintas module) disimpan di `projects/_budi-prefs.md`, terpisah dari knowledge teknis bersama — dan kamu satu-satunya penulisnya. Tulis saat Budi menyatakan preferensi yang bakal berulang, satu butir per baris beserta tanggal; jangan menyimpulkannya dari satu kejadian. Yang khusus **satu** module bukan tempatnya di sini — itu Konvensi module di `projects/<module>.md` (lihat batas kurasi di bawah). File ini tak pernah di-seed: ia lahir saat preferensi pertama muncul.

**Batas kurasi di `projects/<module>.md`:** boleh sunting tangan seksi **Konvensi module**, **Keputusan**, dan **Ringkasan**. **Jangan pernah** sunting **Fakta terkonsiliasi** atau **Jurnal** — keduanya milik `ps-module-context.py` (`claim`/`drop`/`note`); suntingan tangan di sana muncul sebagai drift saat rekonsiliasi berikutnya.
