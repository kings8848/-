"""운영 검증 엔진 회귀 시험: python3 -m unittest ops/tests/test_ops.py"""
import csv, importlib, json, os, shutil, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]


class OpsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(HERE / "data", self.tmp / "data")
        os.environ.update(KINGS_OPS_DATA=str(self.tmp / "data"), KINGS_OPS_STATE=str(self.tmp / "state"),
                          KINGS_OPS_REPORTS=str(self.tmp / "reports"))
        sys.path.insert(0, str(HERE))
        import kings_ops
        self.m = importlib.reload(kings_ops)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def run_once(self):
        F = self.m.Findings()
        lf = self.m.reconcile_localfood(F); ss = self.m.smartstore(F)
        return F, lf, ss, self.m.ingest(lf, ss)

    def test_real_settlements_reconcile(self):
        F, lf, ss, _ = self.run_once()
        self.assertEqual(lf["checks_total"], lf["checks_pass"])
        self.assertEqual(len(lf["periods"]), 13)
        self.assertEqual(lf["totals"]["payout"], 1753270)

    def test_duplicate_file_detected(self):
        _, lf, _, _ = self.run_once()
        self.assertEqual([x[0] for x in lf["duplicates"]], ["17_VfKQxbm6yGIPCJ2g5ouRKzDf5zGaNQ"])

    def test_idempotent_rerun(self):
        _, _, _, first = self.run_once()
        _, _, _, second = self.run_once()
        self.assertEqual(first["added"], first["offered"])
        self.assertEqual(second["added"], 0)
        self.assertEqual(first["ledger_size"], second["ledger_size"])

    def test_tampered_amount_is_caught(self):
        p = self.tmp / "data" / "localfood_lines.csv"
        rows = list(csv.reader(p.open(encoding="utf-8")))
        rows[1][9] = str(int(rows[1][9]) - 100)  # 정산금액 100원 조작
        csv.writer(p.open("w", newline="", encoding="utf-8")).writerows(rows)
        F, lf, _, _ = self.run_once()
        self.assertLess(lf["checks_pass"], lf["checks_total"])
        self.assertTrue(any("불일치" in i["msg"] for i in F.items))

    def test_open_shipping_alert(self):
        F, _, ss, _ = self.run_once()
        self.assertTrue(ss["open_alert"])
        self.assertEqual(len(F.by("긴급")), 1)

    def test_gmail_id_date(self):
        self.assertEqual(self.m.gmail_id_to_kst("1a19b281206e37a1").strftime("%Y-%m-%d %H:%M"), "2026-11-02 16:27")

    def test_sample_batch_excluded_but_real_batch_validates(self):
        src = (HERE / "templates" / "batch_record_template.csv").read_text(encoding="utf-8").splitlines()
        body = [l for l in src if not l.startswith("#")]
        (self.tmp / "data" / "batches.csv").write_text("\n".join(body), encoding="utf-8")
        F, lf, ss, _ = self.run_once()
        self.assertEqual(self.m.batches(F, lf)["real_complete"], 0)  # 예시는 제외
        real = [body[0]] + [l.replace("EX-0001", "T-1").replace(",Y,", ",N,") for l in body[1:]]
        real[-1] = real[-1].replace("병입실,,", "병입실,40,")
        (self.tmp / "data" / "batches.csv").write_text("\n".join(real), encoding="utf-8")
        bt = self.m.batches(self.m.Findings(), lf)
        self.assertEqual(bt["real_complete"], 1)
        inv = bt["inventory"][0]
        self.assertEqual(inv["sold_localfood"], 135)  # 2025-06-10 이후 금배주25 로컬푸드 순판매(반품 상계 후)
        self.assertEqual(inv["counted_on_hand"], 40)

    def test_alcohol_balance_violation(self):
        src = (HERE / "templates" / "batch_record_template.csv").read_text(encoding="utf-8").splitlines()
        body = [l for l in src if not l.startswith("#")]
        real = [body[0]] + [l.replace(",Y,", ",N,") for l in body[1:]]
        real[-1] = real[-1].replace(",500,병,25,", ",900,병,25,")  # 900병×0.375L×25% = 84L > 90L×60%=54L
        (self.tmp / "data" / "batches.csv").write_text("\n".join(real), encoding="utf-8")
        F = self.m.Findings(); _, lf, _, _ = self.run_once()
        bt = self.m.batches(F, lf)
        self.assertFalse(bt["batches"][0]["balance_ok"])


if __name__ == "__main__":
    unittest.main()
