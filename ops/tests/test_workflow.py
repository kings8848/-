"""지시 파이프라인 규칙 시험: python3 -m unittest ops/tests/test_workflow.py"""
import importlib, json, os, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]
REPO = HERE.parent


class WFTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ["KINGS_WF_STATE"] = str(self.tmp / "orders.json")
        sys.path.insert(0, str(HERE / "company"))
        import workflow
        self.w = importlib.reload(workflow)
        self.db = {"orders": {}, "tasks": {}}
        self.oid = self.w.new_order(self.db, "45점을 90점으로 만들어라")

    def out(self, name, first):
        p = self.tmp / name
        p.write_text(first + "\n본문", encoding="utf-8")
        return os.path.relpath(p, REPO)

    def test_original_sealed(self):
        self.assertEqual(self.w.verify(self.db), [])
        self.db["orders"][self.oid]["original"] += " (수정)"
        self.assertEqual(self.w.verify(self.db), [self.oid])

    def test_no_split_before_interpretation_and_criteria_locked(self):
        with self.assertRaises(self.w.WFError):
            self.w.add_task(self.db, self.oid, "정산원가", "x.md", ["기준"])
        self.w.interpret(self.db, self.oid, "실증 증거 확보")
        with self.assertRaises(self.w.WFError):
            self.w.add_task(self.db, self.oid, "정산원가", "x.md", [])
        tid = self.w.add_task(self.db, self.oid, "정산원가", "x.md", ["합계 일치"])
        with self.assertRaises(self.w.WFError):
            self.w.add_criteria(self.db, tid, "새 기준")

    def test_reviewer_cannot_own_task_and_advice_keeps_status(self):
        self.w.interpret(self.db, self.oid, "해석")
        with self.assertRaises(self.w.WFError):
            self.w.add_task(self.db, self.oid, "독립검토", "x.md", ["기준"])
        tid = self.w.add_task(self.db, self.oid, "정산원가", self.out("a.md", "이 문서에서 알 수 있는 것: 요약"), ["기준"])
        self.w.submit(self.db, tid)
        self.w.advise(self.db, tid, "세액 산식 재확인 권고")
        self.assertEqual(self.db["tasks"][tid]["status"], "제출")

    def test_predecessor_and_first_line_and_escalation(self):
        self.w.interpret(self.db, self.oid, "해석")
        t1 = self.w.add_task(self.db, self.oid, "제조기록", self.out("b.md", "요약 없음"), ["6공정"])
        t2 = self.w.add_task(self.db, self.oid, "출고재고", "y.md", ["실사"], after=[t1])
        with self.assertRaises(self.w.WFError):
            self.w.submit(self.db, t2)
        for n in range(1, 4):
            self.w.submit(self.db, t1)
            r = self.w.review(self.db, passes=[t1])  # 첫 줄 없어서 자동 반려
            self.assertEqual(r[t1], "대표상신" if n == 3 else "재작업")
        self.assertEqual(len(self.db["tasks"][t1]["history"]), 3)
        self.assertIn("1회차", self.w.brief(self.db, t1))

    def test_external_needs_ceo_approval(self):
        self.w.interpret(self.db, self.oid, "해석")
        tid = self.w.add_task(self.db, self.oid, "지원사업", self.out("c.md", "이 문서에서 알 수 있는 것: 제출본"), ["양식 준수"], external=True)
        self.w.submit(self.db, tid)
        self.assertEqual(self.w.review(self.db, passes=[tid])[tid], "대표승인대기")
        self.w.approve(self.db, tid)
        self.assertEqual(self.db["tasks"][tid]["status"], "완료")


if __name__ == "__main__":
    unittest.main()
