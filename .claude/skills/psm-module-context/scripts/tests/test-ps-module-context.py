#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Unit test ps-module-context.py. Jalankan: uv run scripts/tests/test-ps-module-context.py"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

CTX = Path(__file__).resolve().parent.parent / "ps-module-context.py"

# Inventaris tiruan: bentuk sama dengan output ps-module-inventory.py.
# implemented_hooks sengaja berprefiks 'hook' dan beda case dari registered_hooks —
# itu justru normalisasi yang harus dicerminkan reconcile.
INV = {
    "module": "ctxmod",
    "registered_hooks": ["displayHeader"],
    "implemented_hooks": ["hookDisplayHeader", "hookActionValidateOrder"],
    "object_models": [{"class": "Banner", "table": "ctxmod_banner"}],
    "files": ["ctxmod.php", "views/templates/hook/banner.tpl"],
}


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}: {name}")
    return cond


def run(*args, stdin=None):
    return subprocess.run([sys.executable, str(CTX), *args], capture_output=True,
                          text=True, input=stdin)


def main():
    ok = True
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        mem = root / "mem"
        prof = mem / "projects" / "ctxmod.md"
        addr = ("--memory-dir", str(mem), "--module", "ctxmod")
        inv_file = root / "inv.json"
        inv_file.write_text(json.dumps(INV), encoding="utf-8")

        # 1 — init menghasilkan kerangka lengkap bergaya rumah KB
        r = run("init", *addr)
        text = prof.read_text(encoding="utf-8") if prof.exists() else ""
        ok &= check("init rc=0", r.returncode == 0)
        ok &= check("init: H1 + provenance baris-3 + 5 seksi + penutup Sumber:",
                    text.startswith("# Konteks module ctxmod")
                    and "\nDiseed " in text
                    and all(f"## {s}" in text for s in
                            ("Konvensi module", "Keputusan", "Fakta terkonsiliasi",
                             "Jurnal", "Ringkasan"))
                    and "Sumber:" in text)

        # 2 — init di file existing = invokasi salah, bukan drift
        ok &= check("init ulang rc=2", run("init", *addr).returncode == 2)

        # 3 — note di artefak absen auto-init (menyimpang sadar dari memlog)
        mem2 = root / "mem2"
        addr2 = ("--memory-dir", str(mem2), "--module", "ctxmod")
        r = run("note", *addr2, "--text", "entri pertama", "--by", "psm-plan")
        ack = json.loads(r.stdout) if r.stdout.strip() else {}
        ok &= check("note auto-init rc=0 + journal=1",
                    r.returncode == 0 and ack.get("journal") == 1
                    and (mem2 / "projects" / "ctxmod.md").exists())

        # 4 — entri mendarat di akhir, kronologis; --text multi-baris dikolapskan
        run("note", *addr, "--text", "entri A", "--by", "psm-plan", "--type", "decision")
        run("note", *addr, "--text", "baris satu\nbaris dua   spasi", "--by", "psm-validate")
        jurnal = prof.read_text(encoding="utf-8").split("## Jurnal")[1].split("## ")[0]
        entries = [ln for ln in jurnal.splitlines() if ln.startswith("- ")]
        ok &= check("note: urutan kronologis, entri terakhir di akhir",
                    len(entries) == 2 and "entri A" in entries[0])
        ok &= check("note: multi-baris dikolapskan jadi satu baris",
                    entries[1].endswith("baris satu baris dua spasi"))

        # 5 — claim (kind,key) sama 2x -> satu baris, terbaru menang
        run("claim", *addr, "--kind", "hook", "--key", "displayHeader",
            "--status", "live", "--by", "psm-develop", "--note", "versi lama")
        r = run("claim", *addr, "--kind", "hook", "--key", "displayHeader",
                "--status", "live", "--by", "psm-develop", "--note", "versi baru")
        fakta = prof.read_text(encoding="utf-8").split("## Fakta terkonsiliasi")[1].split("## ")[0]
        lines = [ln for ln in fakta.splitlines() if "Fakta:" in ln]
        ok &= check("claim: upsert by (kind,key) — satu baris, terbaru menang",
                    len(lines) == 1 and "versi baru" in lines[0] and "versi lama" not in fakta)

        # 6 — himpunan kind tertutup: konvensi bukan Fakta
        ok &= check("claim --kind konvensi rc=2",
                    run("claim", *addr, "--kind", "konvensi", "--key", "namespace",
                        "--status", "live").returncode == 2)

        # 7 — drop menghapus tepat satu, menyisakan saudaranya
        run("claim", *addr, "--kind", "table", "--key", "ctxmod_banner",
            "--status", "live", "--by", "psm-develop")
        run("claim", *addr, "--kind", "class", "--key", "Banner",
            "--status", "live", "--by", "psm-develop")
        run("drop", *addr, "--kind", "class", "--key", "Banner")
        fakta = prof.read_text(encoding="utf-8").split("## Fakta terkonsiliasi")[1].split("## ")[0]
        ok &= check("drop: hapus tepat satu, saudara utuh",
                    "key=Banner " not in fakta and "key=ctxmod_banner" in fakta
                    and "key=displayHeader" in fakta)

        # 8 — reconcile klaim yang semuanya cocok
        r = run("reconcile", *addr, "--inventory", str(inv_file))
        res = json.loads(r.stdout)
        ok &= check("reconcile cocok rc=0 + ok:true",
                    r.returncode == 0 and res["ok"] and not res["drift"])

        # 9 + 11 + 12 — drift dua arah, dan planned diabaikan
        run("claim", *addr, "--kind", "table", "--key", "ctxmod_hilang",
            "--status", "live", "--by", "psm-develop")
        run("claim", *addr, "--kind", "hook", "--key", "actionValidateOrder",
            "--status", "retired", "--by", "psm-cross-version")
        run("claim", *addr, "--kind", "table", "--key", "ctxmod_nanti",
            "--status", "planned", "--by", "psm-plan")
        r = run("reconcile", *addr, "--inventory", str(inv_file))
        res = json.loads(r.stdout)
        kinds = {(d["kind"], d["key"]) for d in res["drift"]}
        ok &= check("reconcile drift rc=1", r.returncode == 1 and not res["ok"])
        ok &= check("drift live_but_missing terdeteksi",
                    ("live_but_missing", "ctxmod_hilang") in kinds)
        ok &= check("drift retired_but_present terdeteksi",
                    ("retired_but_present", "actionValidateOrder") in kinds)
        ok &= check("status=planned diabaikan reconcile",
                    not any(d["key"] == "ctxmod_nanti" for d in res["drift"]))

        # 10 — normalisasi hook: case-fold + awalan 'hook' (cermin reconcile_plan)
        mem3 = root / "mem3"
        addr3 = ("--memory-dir", str(mem3), "--module", "ctxmod")
        run("claim", *addr3, "--kind", "hook", "--key", "displayheader",
            "--status", "live", "--by", "t")
        run("claim", *addr3, "--kind", "hook", "--key", "actionValidateOrder",
            "--status", "live", "--by", "t")
        r = run("reconcile", *addr3, "--inventory", str(inv_file))
        ok &= check("hook case-fold + bare-vs-hook-prefix: tak ada drift palsu",
                    r.returncode == 0 and json.loads(r.stdout)["ok"])

        # 13 — uncovered informasional, TAK PERNAH rc=1 (regresi yang mematikan fitur)
        res3 = json.loads(run("reconcile", *addr3, "--inventory", str(inv_file)).stdout)
        ok &= check("uncovered terisi tapi rc tetap 0",
                    res3["ok"] and "ctxmod_banner" in res3["uncovered"]["table"]
                    and "ctxmod.php" in res3["uncovered"]["file"])

        # 14 — pasangan salah = invokasi salah
        wrong = root / "wrong.json"
        wrong.write_text(json.dumps({**INV, "module": "modul_lain"}), encoding="utf-8")
        ok &= check("inventory module != --module rc=2",
                    run("reconcile", *addr, "--inventory", str(wrong)).returncode == 2)

        # 15 — inventaris rusak = invokasi salah
        bad = root / "bad.json"
        bad.write_text("{ini bukan json", encoding="utf-8")
        ok &= check("inventaris JSON rusak rc=2",
                    run("reconcile", *addr, "--inventory", str(bad)).returncode == 2)

        # 16 — artefak salah -> drift, BUKAN rc=2 (cermin no_markers di pair_check)
        mem4 = root / "mem4"
        addr4 = ("--memory-dir", str(mem4), "--module", "ctxmod")
        run("init", *addr4)
        p4 = mem4 / "projects" / "ctxmod.md"
        p4.write_text(p4.read_text(encoding="utf-8").replace(
            "## Fakta terkonsiliasi\n", "## Fakta terkonsiliasi\n- Fakta: ngawur tanpa field\n"),
            encoding="utf-8")
        r = run("reconcile", *addr4, "--inventory", str(inv_file))
        ok &= check("baris Fakta dirusak tangan -> rc=1 claim_malformed",
                    r.returncode == 1
                    and any(d["kind"] == "claim_malformed" for d in json.loads(r.stdout)["drift"]))

        # 17 — toleransi marker: bullet + bold (cermin parse_md_statuses)
        mem5 = root / "mem5"
        addr5 = ("--memory-dir", str(mem5), "--module", "ctxmod")
        run("init", *addr5)
        p5 = mem5 / "projects" / "ctxmod.md"
        p5.write_text(p5.read_text(encoding="utf-8").replace(
            "## Fakta terkonsiliasi\n",
            "## Fakta terkonsiliasi\n- **Fakta:** kind=hook key=displayHeader status=live "
            "sejak=2026-07-30 oleh=t\n"), encoding="utf-8")
        r = run("reconcile", *addr5, "--inventory", str(inv_file))
        ok &= check("marker ber-bold tetap ter-parse (bukan claim_malformed)",
                    r.returncode == 0 and json.loads(r.stdout)["claims_checked"] == 1)

        # 18 — INVARIAN STRUKTURAL: zona terkurasi tak tersentuh jalur tulis skrip.
        # Ini yang membuat "satu jalur tulis" jadi fakta, bukan niat.
        mem6 = root / "mem6"
        addr6 = ("--memory-dir", str(mem6), "--module", "ctxmod")
        run("init", *addr6)
        p6 = mem6 / "projects" / "ctxmod.md"
        prosa_k = ("Namespace PSR-4 `Budi\\CtxMod\\`, service di `config/services.yml`.\n"
                   "Prefix tabel `ctxmod_`. Umum PrestaShop -> [[persistence]].")
        prosa_d = "- 2026-07-12 — Doctrine ditolak, ObjectModel dipakai: target masih 1.7.8."
        t6 = p6.read_text(encoding="utf-8")
        t6 = t6.replace("## Konvensi module\n", f"## Konvensi module\n{prosa_k}\n")
        t6 = t6.replace("## Keputusan\n", f"## Keputusan\n{prosa_d}\n")
        p6.write_text(t6, encoding="utf-8")
        before = p6.read_text(encoding="utf-8")
        h2_before = [ln for ln in before.splitlines() if ln.startswith("## ")]
        for i in range(3):
            run("note", *addr6, "--text", f"entri {i}", "--by", "psm-develop")
        run("claim", *addr6, "--kind", "hook", "--key", "displayHeader", "--status", "live", "--by", "t")
        run("claim", *addr6, "--kind", "table", "--key", "ctxmod_banner", "--status", "live", "--by", "t")
        run("drop", *addr6, "--kind", "table", "--key", "ctxmod_banner")
        after = p6.read_text(encoding="utf-8")
        sec_k = after.split("## Konvensi module")[1].split("## ")[0]
        sec_d = after.split("## Keputusan")[1].split("## ")[0]
        h2_after = [ln for ln in after.splitlines() if ln.startswith("## ")]
        ok &= check("invarian: '## Konvensi module' byte-identik setelah 6 write",
                    sec_k == before.split("## Konvensi module")[1].split("## ")[0])
        ok &= check("invarian: '## Keputusan' byte-identik setelah 6 write",
                    sec_d == before.split("## Keputusan")[1].split("## ")[0])
        ok &= check("invarian: urutan H2 tak berubah", h2_before == h2_after)

        # 19 — --help mengangkut kontrak marker (SKILL.md hanya menunjuk ke sini)
        h = run("--help").stdout
        ok &= check("--help memuat kontrak marker + himpunan tertutup",
                    "Fakta: kind=" in h
                    and all(k in h for k in ("hook", "table", "class", "file"))
                    and all(s in h for s in ("live", "retired", "planned")))

        # 20 — catatan non-ASCII & yang memuat 'status=' tak merusak parsing
        mem7 = root / "mem7"
        addr7 = ("--memory-dir", str(mem7), "--module", "ctxmod")
        run("claim", *addr7, "--kind", "hook", "--key", "displayHeader", "--status", "live",
            "--by", "t", "--note", "dipakai buat status=aktif — ada tanda—panjang")
        r = run("reconcile", *addr7, "--inventory", str(inv_file))
        ok &= check("catatan bebas (non-ASCII + memuat 'status=') tak merusak parsing",
                    r.returncode == 0 and json.loads(r.stdout)["ok"])

    print("semua lolos" if ok else "ADA YANG GAGAL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
