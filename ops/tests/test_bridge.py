"""두 계층 연결 시험: 경보 → 업무, 재실행 무중복, 경보 사라지면 해소"""
import importlib, json, os, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]


class BridgeTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        os.environ.update(KINGS_OPS_REPORTS=str(self.tmp), KINGS_BRIDGE_STATE=str(self.tmp / "bridge.json"),
                          KINGS_WF_STATE=str(self.tmp / "orders.json"))
        sys.path.insert(0, str(HERE / "company"))
        import workflow, bridge
        self.w = importlib.reload(workflow)
        self.b = importlib.reload(bridge)
        self.db = {"orders": {}, "tasks": {}}

    def write(self, findings, day="20261104"):
        (self.tmp / f"역량평가_{day}.json").write_text(json.dumps({"findings": findings}, ensure_ascii=False), encoding="utf-8")

    def test_route_dedupe_and_close(self):
        urgent = {"level": "긴급", "area": "출고·지연", "msg": "발송대기 1건 2일째", "action": "오늘 발송", "ref": ""}
        tax = {"level": "확인", "area": "정산·세무", "msg": "세액 6,820", "action": "세무사 확인", "ref": ""}
        info = {"level": "정보", "area": "정산·중복", "msg": "사본", "action": "이동", "ref": ""}
        self.write([urgent, tax, info])
        r1 = self.b.run(self.db)
        self.assertEqual(len(r1["created"]), 2)  # 정보는 업무로 안 받음
        t_ship = self.db["tasks"][r1["created"][0]]
        self.assertEqual((t_ship["owner"], t_ship["external"], t_ship["channel"]), ("출고재고", True, "고객안내"))
        self.assertEqual(self.db["tasks"][r1["created"][1]]["owner"], "컴플라이언스")
        urgent2 = dict(urgent, msg="발송대기 1건 3일째")  # 숫자만 바뀐 같은 경보
        self.write([urgent2, tax], "20261105")
        self.assertEqual(self.b.run(self.db)["created"], [])
        self.write([urgent2], "20261106")  # 세무 경보 사라짐
        r3 = self.b.run(self.db)
        self.assertEqual(r3["closed"], [r1["created"][1]])
        self.assertEqual(self.db["tasks"][r1["created"][1]]["status"], "완료")


if __name__ == "__main__":
    unittest.main()
