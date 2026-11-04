"""커머스API 연결기·엑셀 배치 양식 시험 (실서버 호출 없음)"""
import base64, csv, importlib, json, os, shutil, sys, tempfile, unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
KST = timezone(timedelta(hours=9))


class ConnTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        shutil.copytree(HERE / "data", self.tmp / "data")
        os.environ.update(KINGS_OPS_DATA=str(self.tmp / "data"), KINGS_OPS_STATE=str(self.tmp / "state"),
                          KINGS_OPS_REPORTS=str(self.tmp / "reports"))
        for p in (HERE, HERE / "connectors"):
            sys.path.insert(0, str(p))
        import smartstore_api, kings_ops
        self.api = importlib.reload(smartstore_api)
        self.k = importlib.reload(kings_ops)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_sign_is_bcrypt_of_id_and_timestamp(self):
        import bcrypt
        secret = bcrypt.gensalt(10).decode()  # 실제 시크릿도 $2a$10$… 형식
        sig = self.api.sign("CID", secret, 1730700000000)
        self.assertTrue(bcrypt.checkpw(b"CID_1730700000000", base64.b64decode(sig)))

    def fixture(self, rows):
        p = self.tmp / "fx.json"
        p.write_text(json.dumps({"data": {"lastChangeStatuses": rows}}), encoding="utf-8")
        return str(p)

    def test_fixture_upsert_idempotent_and_late_alert(self):
        old = (datetime.now(KST) - timedelta(hours=30)).isoformat(timespec="milliseconds")
        fx = self.fixture([{"productOrderId": "2026110411111", "orderId": "O1", "productOrderStatus": "PAYED",
                            "lastChangedType": "PAYED", "lastChangedDate": old}])
        self.api.OUT = self.tmp / "data" / "smartstore_orders_api.csv"
        self.api.main(["--fixture", fx]); self.api.main(["--fixture", fx])
        rows = list(csv.DictReader(self.api.OUT.open(encoding="utf-8")))
        self.assertEqual(len(rows), 1)  # 두 번 넣어도 1건
        F = self.k.Findings(); ss = self.k.smartstore(F)
        self.assertEqual(ss["api_waiting"], 1)
        self.assertTrue(any(i["area"] == "출고·지연(API)" for i in F.by("긴급")))

    def test_excel_batch_template_is_read(self):
        import openpyxl
        wb = openpyxl.load_workbook(HERE / "templates" / "배치기록_양식.xlsx")
        ws, ex = wb["배치기록"], wb["예시"]
        for row in list(ex.iter_rows(min_row=3, values_only=True)):
            r = list(row); r[0] = "B-2025-01"; r[13] = "N"
            if r[2] == "병입": r[11] = 40
            ws.append(r)
        wb.save(self.tmp / "data" / "batches.xlsx")
        F = self.k.Findings(); lf = self.k.reconcile_localfood(F)
        bt = self.k.batches(F, lf)
        self.assertEqual(bt["real_complete"], 1)
        self.assertEqual(bt["inventory"][0]["counted_on_hand"], 40)


if __name__ == "__main__":
    unittest.main()
