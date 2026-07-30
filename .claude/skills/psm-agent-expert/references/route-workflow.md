# Arahkan ke workflow

Saat permintaan Budi butuh kerja multi-langkah, arahkan ke workflow psm yang tepat dengan konteks yang sudah disiapkan, alih-alih mengerjakannya sebagai obrolan.

Pemetaan maksud → workflow (panggil dengan nama skill-nya):

| Maksud Budi | Workflow |
| --- | --- |
| "module-ku jalan nggak di 8/9", buat compatible lintas versi | `psm-cross-version` |
| "bikin module baru" | `psm-scaffold` |
| "perkaya module ini", "kembangkan lebih jauh dalam topik yang sama" | `psm-ideate` |
| "tambah fitur/fungsi ke module yang ada" | `psm-develop` |
| "cek/validasi module", audit sebelum rilis | `psm-validate` |
| "module-ku lambat", optimasi performa / tuning cache-service | `psm-optimize` |

Sebelum memanggil, siapkan konteks: path module, versi target (`psm_target_versions`), dan — bila relevan — fungsi e-commerce hasil brainstorm. Khusus handoff ke `psm-validate`: cek dulu Docker + image flashlight tersedia; bila belum, bantu Budi menyiapkan (lihat `<skills-dir>/psm-validate/SKILL.md`; `<skills-dir>` = direktori install skill ini, tempat sibling psm-* berada). Bila `{project-root}/_bmad/psm/memory/projects/<module>.md` ada, baca dulu agar tahu "di mana kita tadi" dan teruskan ke workflow. Setelah workflow selesai, ringkas hasilnya ke Budi — **workflow itu sendiri** yang merekonsiliasi & menulis balik ke `projects/<module>.md`; perkembangan masuk lewat **psm-module-context**, bukan disunting tangan.

Bila ragu antara dua workflow (mis. menambah fitur ke module yang juga belum cross-version), sebutkan urutannya: biasanya cross-version dulu agar fondasi aman, baru develop; dan validasi dulu sebelum optimasi agar baseline perilakunya jelas.

Antara `psm-ideate` dan `psm-plan`: pembedanya jumlah ide, bukan besar fiturnya. Satu fungsi yang sudah jelas → langsung `psm-plan`. Penggalian yang melahirkan banyak ide dan hanya sebagian dikerjakan sekarang → `psm-ideate` dulu agar sisanya bertahan sebagai backlog, baru `psm-plan` atas yang dipilih.

Bila maksud & path module sudah diberikan lengkap (mis. dipanggil non-interaktif), arahkan langsung ke workflow yang tepat tanpa pembuka percakapan.
