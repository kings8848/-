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


class ContextErrorTest(unittest.TestCase):
    def test_context_finds_compliance_item(self):
        sys.path.insert(0, str(HERE / "company")); import context
        hits = context.search("봉신설주 품목제조보고")
        self.assertTrue(any("MFDS-ITEM-REPORT" in h["text"] or "품목제조보고" in h["text"] for h in hits))

    def test_error_workflow_writes_report_and_stops(self):
        sys.path.insert(0, str(HERE)); import importlib, pipeline
        pipeline = importlib.reload(pipeline)
        pipeline.STEPS_OVERRIDE = [("일부러 실패", ["company/does_not_exist.py"]), ("다음 단계", ["company/bridge.py"])]
        before = set((HERE / "reports").glob("오류_*.md"))
        rc = pipeline.main([])
        new = set((HERE / "reports").glob("오류_*.md")) - before
        self.assertEqual(rc, 1)
        self.assertEqual(len(new), 1)
        for p in new: p.unlink()
        pipeline.STEPS_OVERRIDE = None

    def test_brief_includes_tools_and_context(self):
        sys.path.insert(0, str(HERE / "company")); import workflow
        db = {"orders": {}, "tasks": {}}
        oid = workflow.new_order(db, "식약청 위생검사 대응 서류 준비")
        workflow.interpret(db, oid, "해석")
        tid = workflow.add_task(db, oid, "식품안전", "x.md", ["서류철"])
        b = workflow.brief(db, tid)
        self.assertIn("쓸 수 있는 도구", b)
        self.assertIn("관련 지식", b)


class SixIndustryTest(unittest.TestCase):
    def test_product_is_zero_without_raw_and_batch_evidence(self):
        sys.path.insert(0, str(HERE / "marketing")); import six_industry
        m = six_industry.measure()
        self.assertEqual(m["3차"]["score"], 1)
        self.assertEqual(m["3차"]["consign_fee_rate"], 0.13)
        if m["1차"]["records"] == 0 or m["2차"]["real_batches"] == 0:
            self.assertEqual(m["product"], 0)
