"""B2B 파이프라인 시험(가상 매장): 페어링 판별·법규 게이트·팔로업"""
import csv, importlib, json, os, sys, tempfile, unittest
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
F = ["lead_id","name","segment","menu","area","contact","email","source","consent","status","proposal","sent_at","last_reply","note"]


class B2BTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ.update(KINGS_LEADS=str(self.tmp / "leads.csv"), KINGS_PROPOSALS=str(self.tmp / "p"), KINGS_WF_STATE=str(self.tmp / "o.json"))
        sys.path.insert(0, str(HERE / "sales")); import b2b
        self.b = importlib.reload(b2b)

    def write(self, rows):
        with (self.tmp / "leads.csv").open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=F); w.writeheader(); w.writerows([{**{k: "" for k in F}, **r} for r in rows])

    def test_classify(self):
        self.assertEqual(self.b.classify({"menu": "한우 숯불 오마카세"})["product"], "금배주 25")
        self.assertEqual(self.b.classify({"menu": "해산물 코스"})["product"], "봉신설주 17")
        self.assertFalse(self.b.classify({"menu": "전통주 바"})["reason_ok"])
        self.assertEqual(self.b.classify({"menu": "분식"})["segment"], "미분류")

    def test_gates_block_cold_email_and_missing_price(self):
        self.write([{"lead_id": "T1", "name": "가상한우A", "menu": "한우 구이", "source": "naver_api", "consent": "N"},
                    {"lead_id": "T2", "name": "가상한우B", "menu": "한우 구이", "source": "inbound"}])
        s = self.b.run(today=date(2026, 11, 5), create_tasks=False)
        self.assertEqual(s["ready"], [])
        self.assertEqual(s["call_list"], ["T1"])
        why = {b["lead"]: " ".join(b["why"]) for b in s["blocked"]}
        self.assertIn("사전 동의", why["T1"])
        self.assertNotIn("사전 동의", why["T2"])
        self.assertIn("공급 단가 미입력", why["T2"])
        html = (self.tmp / "p" / "T2.html").read_text(encoding="utf-8")
        self.assertIn("[B2B 공급 단가 대표 확정 후 기재]", html)
        self.assertNotIn("시음 키트", html)  # 세무서 사전승인 증빙 없음
        self.assertIn("19세 미만", html)

    def test_ready_lead_creates_outbox_task_when_all_gates_pass(self):
        m = json.loads((HERE / "enterprise" / "master.json").read_text(encoding="utf-8"))
        m["products"]["금배주 25"]["price"]["B2B"] = 20000
        reg = json.loads((HERE / "company" / "compliance_register.json").read_text(encoding="utf-8"))
        for i in reg["items"]:
            if i["id"] == "NTS-DIRECT-SUPPLY": i["evidence"] = "OO세무서 확인 2026-11-10"
        self.write([{"lead_id": "T3", "name": "가상한우C", "menu": "한우 오마카세", "source": "inbound"}])
        os.environ["KINGS_NO_NOTIFY"] = "1"
        s = self.b.run(today=date(2026, 11, 5), create_tasks=True, master=m, register=reg)
        self.assertEqual(s["ready"], ["T3"])
        db = json.loads((self.tmp / "o.json").read_text(encoding="utf-8"))
        t = list(db["tasks"].values())[0]
        self.assertEqual((t["owner"], t["external"], t["channel"]), ("B2B영업", True, "메일"))

    def test_followup_after_5_days(self):
        self.write([{"lead_id": "T4", "name": "가상바", "status": "제안완료", "sent_at": "2026-11-01"}])
        self.assertEqual(self.b.run(today=date(2026, 11, 6), create_tasks=False)["followup"], ["T4"])
        self.write([{"lead_id": "T4", "name": "가상바", "status": "제안완료", "sent_at": "2026-11-01"}])
        self.assertEqual(self.b.run(today=date(2026, 11, 4), create_tasks=False)["followup"], [])


if __name__ == "__main__":
    unittest.main()
