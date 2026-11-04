"""파이프라인·자동화 정책 시험"""
import json, sys, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]


class PolicyTest(unittest.TestCase):
    def test_every_outbound_channel_needs_approval(self):
        sys.path.insert(0, str(HERE / "company")); import workflow
        pol = json.loads((HERE / "company" / "자동화_정책.json").read_text(encoding="utf-8"))["actions"]
        self.assertEqual({v for v in pol.values()} - {"auto", "approve", "forbidden"}, set())
        sends = [k for k in pol if "초안" not in k and any(w in k for w in ("발송", "게시", "제출", "환불", "결제", "변경"))]
        self.assertTrue(sends)
        for k in sends:
            self.assertIn(pol[k], ("approve", "forbidden"), k)
        self.assertEqual(set(workflow.DAILY_CAP), {"고객안내", "메일", "제출", "상품수정", "SNS"})

    def test_leverage_counts(self):
        sys.path.insert(0, str(HERE)); import pipeline
        import tempfile
        p = Path(tempfile.mkdtemp()) / "o.json"
        p.write_text(json.dumps({"orders": {"D-1": {"questions": [{"answer": None}, {"answer": "예"}]}},
                                 "tasks": {"T-1": {"status": "완료", "evidence": "최신 실행에서 경보 사라짐"},
                                           "T-2": {"status": "대표승인대기"}, "T-3": {"status": "배정"}}}), encoding="utf-8")
        lv = pipeline.leverage(p)
        self.assertEqual((lv["auto_closed"], lv["ceo_pending"], lv["ceo_questions"]), (1, 2, 1))


if __name__ == "__main__":
    unittest.main()
