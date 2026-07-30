# Brainstorm fungsi e-commerce

Bantu Budi menemukan fungsi e-commerce yang layak ditambahkan ke sebuah module, digali lebih dalam dari permintaan awalnya, dengan dampak bisnis yang jelas.

Pakai katalog `<skills-dir>/psm-develop/references/ecommerce-function-catalog.md` (peta fungsi per domain: konversi, retensi, katalog, checkout, SEO, marketing, analytics, multistore, GDPR; `<skills-dir>` = direktori install skill ini, tempat sibling psm-* berada) sebagai sumber ide; augment dengan `{project-root}/_bmad/psm/memory/ecommerce/function-catalog.md` bila ada.

Bila Budi ingin memperdalam satu module dalam topiknya sendiri (bukan menjelajah lintas domain), pakai **Lensa adjacency** di katalog itu — kenali domain module, posisikan di keluarga fungsi domainnya bila ada, lalu gali lima arahnya. Karena kapabilitas ini percakapan murni tanpa inventaris, sebut fungsi yang muncul sebagai kandidat dan serahkan pemastian titik sisipnya ke `psm-plan`/`psm-develop` yang menjalankan inventaris.

Gali dengan teknik elicitation berlensa e-commerce — bila skill `bmad-advanced-elicitation` tersedia, gunakan tekniknya; jangan menduplikasi metodenya. Lensa yang dipakai: dampak ke konversi, AOV, retensi, dan effort implementasi. Untuk tiap fungsi yang muncul, kaitkan ke hook/persistensi PrestaShop yang relevan (dari katalog) dan catat titik cross-version yang perlu diperhatikan, sehingga ide langsung bisa diteruskan ke `psm-scaffold` (module baru) atau `psm-develop` (module existing).

Tawarkan, jangan paksakan — Budi yang memilih fungsi mana yang masuk.

Bila sesi ini melahirkan lebih banyak ide daripada yang akan dikerjakan sekarang, arahkan ke **psm-ideate**: ia menjalankan inventaris, mengaitkan tiap ide ke titik sisip nyata, dan memarkir sisanya di `<module-path>/.psm-ideas.md` supaya tak menguap begitu percakapan ini ditutup.
