#!/usr/bin/env python3
# /// script
# requires-python = ">=3.10"
# ///
"""Unit test ps-idea-backlog.py. Jalankan: uv run scripts/tests/test-ps-idea-backlog.py"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

BL = Path(__file__).resolve().parent.parent / "ps-idea-backlog.py"


def check(name, cond):
    print(f"  {'PASS' if cond else 'FAIL'}: {name}")
    return cond


def run(*args):
    return subprocess.run([sys.executable, str(BL), *args], capture_output=True, text=True)


def plan_file(root, items):
    p = root / ".psm-develop-plan.json"
    p.write_text(json.dumps({"items": items}), encoding="utf-8")
    return p


def main():
    ok = True
    with tempfile.TemporaryDirectory() as td:
        root = Path(td)
        mod = root / "psbankwire"
        mod.mkdir()
        art = mod / ".psm-ideas.md"
        addr = ("--module-path", str(mod))

        # 1 — init menghasilkan kerangka bergaya rumah KB
        r = run("init", *addr, "--domain", "Pembayaran offline; tangga: transfer manual.")
        text = art.read_text(encoding="utf-8") if art.exists() else ""
        ok &= check("init rc=0", r.returncode == 0)
        ok &= check("init: H1 + provenance + 2 seksi + domain terisi",
                    text.startswith("# Backlog ide module psbankwire")
                    and "\nDibuat " in text
                    and "## Domain & posisi" in text and "## Backlog" in text
                    and "transfer manual" in text)

        # 2 — init di file existing = invokasi salah, bukan drift
        ok &= check("init ulang rc=2", run("init", *addr).returncode == 2)

        # 3 — add menulis marker terbaca; catatan berspasi tak memecah parsing
        r = run("add", *addr, "--key", "bukti-bayar", "--status", "baru",
                "--arah", "kelengkapan", "--catatan", "pelanggan upload bukti; status=palsu di sini")
        ok &= check("add rc=0", r.returncode == 0)
        r = run("list", *addr)
        data = json.loads(r.stdout)
        idea = data["ideas"][0]
        ok &= check("add: field terbaca utuh",
                    idea["key"] == "bukti-bayar" and idea["status"] == "baru"
                    and idea["arah"] == "kelengkapan")
        ok &= check("catatan berspasi utuh sampai akhir baris (tak di-split field)",
                    idea["catatan"] == "pelanggan upload bukti; status=palsu di sini")
        ok &= check("list: tak ada malformed", data["malformed"] == [])

        # 4 — status/arah di luar himpunan ditolak, bukan ditulis diam
        ok &= check("status asing rc=1", run("add", *addr, "--key", "x", "--status", "mungkin",
                                             "--arah", "varian").returncode != 0)
        ok &= check("arah asing rc=1", run("add", *addr, "--key", "x", "--status", "baru",
                                           "--arah", "estetika").returncode != 0)

        # 5 — add ulang = upsert by key, dan 'sejak' kelahiran dipertahankan
        born = idea["sejak"]
        run("add", *addr, "--key", "bukti-bayar", "--status", "dipilih", "--arah", "kelengkapan",
            "--rencana", "Upload bukti bayar")
        data = json.loads(run("list", *addr).stdout)
        ok &= check("upsert: tetap 1 baris", len(data["ideas"]) == 1)
        ok &= check("upsert: status berubah", data["ideas"][0]["status"] == "dipilih")
        ok &= check("upsert: sejak (kelahiran ide) dipertahankan",
                    data["ideas"][0]["sejak"] == born)
        # Menaikkan status adalah pemakaian terbanyak add-ulang; catatan yang
        # hilang di situ membuang justru alasan ide ini bisa dinilai ulang nanti.
        ok &= check("upsert: catatan diwarisi saat tak disebut",
                    data["ideas"][0].get("catatan", "").startswith("pelanggan upload bukti"))
        run("add", *addr, "--key", "bukti-bayar", "--status", "dipilih", "--arah", "kelengkapan",
            "--catatan", "")
        ok &= check("upsert: catatan bisa dikosongkan eksplisit",
                    json.loads(run("list", *addr).stdout)["ideas"][0].get("catatan", "") == "")
        run("add", *addr, "--key", "bukti-bayar", "--status", "dipilih", "--arah", "kelengkapan",
            "--rencana", "Upload bukti bayar", "--catatan", "pelanggan upload bukti")

        # 6 — sync: 'dipilih' tanpa item rencana = drift
        pf = plan_file(root, [])
        r = run("sync", *addr, "--plan", str(pf))
        out = json.loads(r.stdout)
        ok &= check("sync rc=1 saat drift", r.returncode == 1)
        ok &= check("dipilih_tanpa_rencana terdeteksi",
                    any(d["kind"] == "dipilih_tanpa_rencana" for d in out["drift"]))

        # 7 — pencocokan lewat field 'rencana', bukan 'key'
        pf = plan_file(root, [{"function": "Upload bukti bayar", "status": "direncanakan"}])
        r = run("sync", *addr, "--plan", str(pf))
        ok &= check("sync rc=0 saat rencana cocok via field rencana", r.returncode == 0)

        # 8 — INTI: item rencana diterapkan tapi ide masih 'dipilih' = backlog basi.
        # Tanpa ini, psm-ideate menawarkan ulang fungsi yang sudah dibangun.
        pf = plan_file(root, [{"function": "Upload bukti bayar", "status": "diterapkan"}])
        r = run("sync", *addr, "--plan", str(pf))
        out = json.loads(r.stdout)
        ok &= check("terwujud_belum_ditandai terdeteksi (backlog basi)",
                    r.returncode == 1
                    and any(d["kind"] == "terwujud_belum_ditandai" for d in out["drift"]))

        # 9 — setelah ditandai terwujud, bukti cocok -> bersih
        run("add", *addr, "--key", "bukti-bayar", "--status", "terwujud", "--arah", "kelengkapan",
            "--rencana", "Upload bukti bayar")
        ok &= check("terwujud + bukti diterapkan -> rc=0",
                    run("sync", *addr, "--plan", str(pf)).returncode == 0)

        # 10 — terwujud tanpa bukti (mis. rencana di-revert) = drift arah sebaliknya
        pf = plan_file(root, [{"function": "Upload bukti bayar", "status": "direncanakan"}])
        out = json.loads(run("sync", *addr, "--plan", str(pf)).stdout)
        ok &= check("terwujud_tanpa_bukti terdeteksi",
                    any(d["kind"] == "terwujud_tanpa_bukti" for d in out["drift"]))

        # 11 — prasyarat: anak tangga yang dilompati diangkat saat 'dipilih'
        pf = plan_file(root, [{"function": "Upload bukti bayar", "status": "diterapkan"},
                              {"function": "moderasi-admin", "status": "direncanakan"}])
        run("add", *addr, "--key", "bukti-bayar", "--status", "terwujud", "--arah", "kelengkapan",
            "--rencana", "Upload bukti bayar")
        run("add", *addr, "--key", "callback", "--status", "baru", "--arah", "otomasi")
        run("add", *addr, "--key", "moderasi-admin", "--status", "dipilih", "--arah", "kelengkapan",
            "--prasyarat", "bukti-bayar,callback")
        out = json.loads(run("sync", *addr, "--plan", str(pf)).stdout)
        pre = [d for d in out["drift"] if d["kind"] == "prasyarat_belum_terwujud"]
        ok &= check("prasyarat belum terwujud diangkat (callback), yang terwujud tidak",
                    len(pre) == 1 and "callback" in pre[0]["detail"])

        # 12 — 'ditolak' dilewati sync, tapi tetap tersimpan (jangan ditawarkan ulang)
        run("add", *addr, "--key", "qr-dinamis", "--status", "ditolak", "--arah", "varian",
            "--catatan", "vendor QR bentrok autoload PS9")
        out = json.loads(run("sync", *addr, "--plan", str(pf)).stdout)
        ok &= check("ide ditolak tak memunculkan drift",
                    not any(d["key"] == "qr-dinamis" for d in out["drift"]))
        ok &= check("ide ditolak tetap ada di backlog",
                    any(i["key"] == "qr-dinamis"
                        for i in json.loads(run("list", *addr).stdout)["ideas"]))

        # 13 — item rencana tanpa ide = info, bukan drift (backlog bukan cermin rencana)
        pf = plan_file(root, [{"function": "fungsi-lain", "status": "direncanakan"}])
        out = json.loads(run("sync", *addr, "--plan", str(pf)).stdout)
        ok &= check("rencana_tanpa_ide masuk info, bukan drift",
                    any(i["kind"] == "rencana_tanpa_ide" for i in out["info"])
                    and not any(d["kind"] == "rencana_tanpa_ide" for d in out["drift"]))

        # 14 — baris rusak dilaporkan, tak lolos diam sebagai backlog bersih
        art.write_text(art.read_text(encoding="utf-8") + "\n- Ide: status=baru arah=varian\n",
                       encoding="utf-8")
        r = run("sync", *addr, "--plan", str(pf))
        out = json.loads(r.stdout)
        ok &= check("marker rusak -> malformed + ok=false",
                    r.returncode == 1 and out.get("malformed") and out["ok"] is False)

        # 15 — seksi prosa disalin byte-for-byte oleh write skrip
        art2 = mod / ".psm-ideas.md"
        before = art2.read_text(encoding="utf-8")
        marker = "PROSA-TAK-BOLEH-HILANG"
        art2.write_text(before.replace("## Backlog", f"{marker}\n\n## Backlog"), encoding="utf-8")
        run("add", *addr, "--key", "rekonsiliasi", "--status", "baru", "--arah", "visibilitas")
        ok &= check("prosa Domain & posisi utuh setelah write",
                    marker in art2.read_text(encoding="utf-8"))

        # 16 — drop
        ok &= check("drop rc=0", run("drop", *addr, "--key", "rekonsiliasi").returncode == 0)
        ok &= check("drop ide tak ada rc=2",
                    run("drop", *addr, "--key", "hantu").returncode == 2)

        # 17 — artefak absen: add auto-init, mode baca menolak
        kosong = root / "modkosong"
        kosong.mkdir()
        ok &= check("list di artefak absen rc=2",
                    run("list", "--module-path", str(kosong)).returncode == 2)
        ok &= check("add auto-init rc=0",
                    run("add", "--module-path", str(kosong), "--key", "a",
                        "--status", "baru", "--arah", "varian").returncode == 0)
        ok &= check("auto-init membuat artefak", (kosong / ".psm-ideas.md").exists())

        # 18 — rencana hilang / bukan JSON = error invokasi, bukan "tak ada drift"
        ok &= check("plan hilang rc=2",
                    run("sync", *addr, "--plan", str(root / "nihil.json")).returncode == 2)
        bad = root / "bad.json"
        bad.write_text("{bukan json", encoding="utf-8")
        ok &= check("plan bukan JSON rc=2",
                    run("sync", *addr, "--plan", str(bad)).returncode == 2)

    print("\nSEMUA LULUS" if ok else "\nADA YANG GAGAL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
