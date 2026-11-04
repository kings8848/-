"""전사 가치사슬 시험: 빈칸은 계산 안 함, 채우면 손익·세금·투자회수 계산"""
import copy, importlib, json, os, sys, tempfile, unittest
from pathlib import Path

HERE = Path(__file__).resolve().parents[1]


class VCTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        sys.path.insert(0, str(HERE / "enterprise")); sys.path.insert(0, str(HERE))
        self.m = json.loads((HERE / "enterprise" / "master.json").read_text(encoding="utf-8"))
        import value_chain
        self.v = importlib.reload(value_chain)

    def test_blank_inputs_are_not_computed(self):
        u = self.v.unit_economics(self.m, "금배주 25", "로컬푸드", 0.05)
        self.assertNotIn("operating_profit", u)
        self.assertTrue(any("원가" in x for x in u["missing"]))
        self.assertEqual(u["fee"], 1950)  # 13% 실측 수수료는 계산됨

    def test_filled_inputs_compute_profit_tax_and_payback(self):
        m = copy.deepcopy(self.m)
        p = m["products"]["금배주 25"]
        p["factory_price"] = 8000
        p["unit_cost"] = {"원료": 1500, "병·마개": 900, "라벨·포장": 400, "에너지·인건": 600}
        u = self.v.unit_economics(m, "금배주 25", "로컬푸드", 50)  # 50kl → 경감 50%
        self.assertEqual(u["liquor_tax"], round(8000 * 0.72 * 0.5))
        self.assertEqual(u["education_tax"], round(8000 * 0.72 * 0.5 * 0.3))
        self.assertFalse(u["tax_verified"])
        exp = round(15000 / 1.1 - 1950 - 3400 - 8000 * 0.72 * 0.5 * 1.3)
        self.assertEqual(u["operating_profit"], exp)
        m["investments"] = [{"name": "발효조 2기", "amount": 30000000, "added_bottles_year": 10000}]
        inv = self.v.investments(m, u["operating_profit"])
        self.assertEqual(inv[0]["payback_years"], round(30000000 / (u["operating_profit"] * 10000), 1))

    def test_scenario_crosses_tax_tier(self):
        sc = self.v.scenario_100b(self.m)
        self.assertEqual(sc["bottles_year"], 666667)
        self.assertEqual(sc["kl_year"], 250.0)
        self.assertEqual(sc["reduction_at_target"], 0.0)  # 200kl 초과 → 경감 없음(미확정 구간 기준)
        self.assertEqual(self.v.reduction_rate(150, self.m["tax"]["traditional_reduction_tiers_kl"]["value"]), 0.3)


if __name__ == "__main__":
    unittest.main()
