#!/usr/bin/env python3
"""킹스 전사 가치사슬 엔진 — 입고 → 생산(공장가동) → 재고 → 출고·판매 → 세금 → 영업이익 → 시설투자 → 100억 시나리오

원칙: 마스터(master.json)의 null 값은 계산하지 않고 '입력 필요'로 보고한다. verified=false 값으로 낸 숫자는 '미확정'.
  python3 ops/enterprise/value_chain.py            # 보고서 ops/reports/전사_가치사슬_YYYYMMDD.md
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OPS = HERE.parent
sys.path.insert(0, str(OPS))
import kings_ops as K  # noqa: E402

KST = timezone(timedelta(hours=9))
MASTER = Path(os.environ.get("KINGS_MASTER", HERE / "master.json"))


def load_master():
    return json.loads(MASTER.read_text(encoding="utf-8"))


def reduction_rate(kl_last_year: float, tiers) -> float:
    for limit, rate in tiers:
        if kl_last_year <= limit:
            return rate
    return 0.0


def liquor_tax(base: float, kl_last_year: float, m) -> dict:
    t = m["tax"]
    rate = t["liquor_tax_rate"]["value"]
    red = reduction_rate(kl_last_year, t["traditional_reduction_tiers_kl"]["value"])
    lt = base * rate * (1 - red)
    edu = lt * t["education_tax_rate"]["value"]
    verified = all(t[k]["verified"] for k in ("liquor_tax_rate", "education_tax_rate", "traditional_reduction_tiers_kl"))
    return {"liquor_tax": lt, "education_tax": edu, "reduction": red, "verified": verified}


def unit_economics(m, product: str, channel: str, kl_last_year: float) -> dict:
    """병당 영업이익 = 판매가(부가세 제외) − 수수료 − 원가 − 주세·교육세. 빈칸은 missing에 남김."""
    p = m["products"][product]
    missing = []
    price = (p.get("price") or {}).get(channel)
    fee_rate = m["channels"].get(channel, {}).get("fee_rate")
    if price is None: missing.append(f"{product}·{channel} 판매가")
    if fee_rate is None: missing.append(f"{channel} 수수료율")
    costs = p.get("unit_cost") or {}
    if not costs or any(v is None for v in costs.values()): missing.append(f"{product} 병당 원가 항목")
    if p.get("factory_price") is None: missing.append(f"{product} 제조장 반출가격(주세 과세표준)")
    out = {"product": product, "channel": channel, "missing": missing}
    if price is not None and fee_rate is not None:
        net = price / (1 + m["tax"]["vat_rate"]["value"])
        out.update(price=price, net_of_vat=round(net), fee=round(price * fee_rate))
    if not missing:
        tx = liquor_tax(p["factory_price"], kl_last_year, m)
        cogs = sum(costs.values())
        op = out["net_of_vat"] - out["fee"] - cogs - tx["liquor_tax"] - tx["education_tax"]
        out.update(cogs=cogs, liquor_tax=round(tx["liquor_tax"]), education_tax=round(tx["education_tax"]),
                   operating_profit=round(op), tax_verified=tx["verified"])
    return out


def scenario_100b(m, product="금배주 25", channel="로컬푸드") -> dict:
    """현재 확인된 단가로 100억을 채우려면 필요한 물량·주세 구간·생산능력."""
    p = m["products"][product]
    price = (p.get("price") or {}).get(channel)
    bottles = m["target_annual_revenue"] / price
    kl = bottles * p["volume_l"] / 1000
    tiers = m["tax"]["traditional_reduction_tiers_kl"]["value"]
    cap = m["capacity"]
    cap_ok = all(cap.get(k) for k in ("bottles_per_batch", "batch_days", "parallel_vessels", "operating_days_year"))
    annual_cap = (cap["bottles_per_batch"] * cap["parallel_vessels"] * cap["operating_days_year"] / cap["batch_days"]) if cap_ok else None
    return {"product": product, "channel": channel, "unit_price": price, "bottles_year": round(bottles),
            "bottles_day": round(bottles / 365), "kl_year": round(kl, 1),
            "reduction_at_target": reduction_rate(kl, tiers), "tier_limits": [t[0] for t in tiers],
            "annual_capacity": annual_cap, "capacity_gap": (round(bottles - annual_cap) if annual_cap else None)}


def investments(m, unit_op: float | None) -> list[dict]:
    out = []
    for inv in m.get("investments", []):
        r = dict(inv)
        if unit_op and inv.get("added_bottles_year"):
            yearly = unit_op * inv["added_bottles_year"]
            r["payback_years"] = round(inv["amount"] / yearly, 1) if yearly > 0 else None
        out.append(r)
    return out


def run():
    m = load_master()
    F = K.Findings()
    lf = K.reconcile_localfood(F); ss = K.smartstore(F); bt = K.batches(F, lf); kp = K.kpi(F, lf, ss)
    sold_bottles = sum(int(r["qty"]) for r in lf["lines"] if r["source_file_id"] in lf["unique_file_ids"])
    kl_last = sold_bottles * m["products"]["금배주 25"]["volume_l"] / 1000  # 원장 확인분만(다른 채널 미포함)
    ue = [unit_economics(m, pr, ch, kl_last) for pr in m["products"] for ch in (m["products"][pr].get("price") or {})]
    sc = scenario_100b(m)
    inv = investments(m, next((u.get("operating_profit") for u in ue if "operating_profit" in u), None))
    missing = sorted({x for u in ue for x in u["missing"]} | ({"생산능력(배치당 병·배치 일수·발효조 수·가동일)"} if sc["annual_capacity"] is None else set())
                     | ({"시설투자 후보(금액·늘어나는 연 생산량)"} if not inv else set()))
    unverified = [f"{k}: {v['note']}" for k, v in m["tax"].items() if isinstance(v, dict) and not v.get("verified", True)]
    return {"master": m, "kpi": kp, "batches": bt, "sold_bottles": sold_bottles, "kl_last": kl_last,
            "unit_economics": ue, "scenario": sc, "investments": inv, "missing": missing, "unverified": unverified}


def report(r) -> str:
    sc, kp = r["scenario"], r["kpi"]
    L = [f"이 문서에서 알 수 있는 것: 100억 목표 기준 전사 가치사슬 7단계 상태 · 현재 단가로 100억 = 연 {sc['bottles_year']:,}병({sc['kl_year']}kl) · 입력 필요 {len(r['missing'])}건 · 세율 미확정 {len(r['unverified'])}건\n",
         f"# 킹스 전사 가치사슬 보고서 ({datetime.now(KST):%Y-%m-%d %H:%M} KST)\n",
         "## 1. 7단계 가동 현황\n", "| 단계 | 상태 | 근거 |", "|---|---|---|",
         f"| ① 입고(원료) | ⏳ 배치 '원료입고' 줄로 기록 | 실배치 {r['batches']['real_complete']}건 |",
         f"| ② 생산·공장가동 | {'✅' if sc['annual_capacity'] else '⏳ 생산능력 미입력'} | master.capacity |",
         f"| ③ 재고 | {'✅' if r['batches']['inventory'] else '⏳ 병입·실사 대기'} | 재고 대사 {len(r['batches']['inventory'])}건 |",
         f"| ④ 출고·판매 | ✅ 원장 연결 | 원장 최근12개월 {kp['trailing12']:,}원, 로컬푸드 순판매 {r['sold_bottles']}병 |",
         f"| ⑤ 세금(주세·교육세·부가세) | ⚠️ 계산식 준비, 세율 미확정 | 세무사 확인 필요 {len(r['unverified'])}건 |",
         f"| ⑥ 영업이익 | {'✅' if any('operating_profit' in u for u in r['unit_economics']) else '⏳ 원가·반출가 미입력'} | 병당 손익 표 |",
         f"| ⑦ 시설투자 | {'✅' if r['investments'] else '⏳ 투자 후보 미입력'} | 회수기간 계산기 준비 |",
         "\n## 2. 100억 시나리오 (확인된 단가 기준)\n",
         f"- 기준: {sc['product']} · {sc['channel']} 단가 {sc['unit_price']:,}원 (정산서 확인값)",
         f"- 필요 물량: 연 **{sc['bottles_year']:,}병** · 하루 **{sc['bottles_day']:,}병** · 연 **{sc['kl_year']}kl**",
         f"- 주세 경감 구간(미확정 기준 {sc['tier_limits']}kl): 목표 물량에서 경감률 **{int(sc['reduction_at_target']*100)}%** "
         f"→ 현재(원장 확인분 {r['kl_last']*1000:.0f}L)는 최대 경감 구간. **성장할수록 병당 세금이 오르는 구조** — 가격·채널 전략에 반영 필요",
         f"- 생산능력 대비 부족: {sc['capacity_gap']:,}병" if sc["capacity_gap"] is not None else "- 생산능력: 입력 필요(실배치 1건 입력 시 계산)",
         "\n## 3. 병당 영업이익 (채널별)\n", "| 제품 | 채널 | 판매가 | 부가세 제외 | 수수료 | 원가 | 주세+교육세 | 영업이익 | 빠진 값 |", "|---|---|---:|---:|---:|---:|---:|---:|---|"]
    for u in r["unit_economics"]:
        f = lambda k: f"{u[k]:,}" if k in u else "—"
        tx = f"{u['liquor_tax']+u['education_tax']:,}{'' if u.get('tax_verified') else '(미확정)'}" if "liquor_tax" in u else "—"
        L.append(f"| {u['product']} | {u['channel']} | {f('price')} | {f('net_of_vat')} | {f('fee')} | {f('cogs')} | {tx} | {f('operating_profit')} | {', '.join(u['missing']) or '없음'} |")
    inv_lines = [f"- {i['name']}: {i['amount']:,}원 · 연 +{i.get('added_bottles_year',0):,}병 · 회수 {i.get('payback_years','—')}년" for i in r["investments"]]
    L += ["\n## 4. 시설투자\n", *(inv_lines or ["- 후보 없음 → master.json `investments`에 {name, amount, added_bottles_year} 입력"]),
          "\n## 5. 대표 입력 필요 (추정으로 채우지 않음)\n", *[f"- [ ] {x}" for x in r["missing"]],
          "\n## 6. 세무사 확인 필요\n", *[f"- [ ] {x}" for x in r["unverified"]]]
    return "\n".join(L) + "\n"


def main():
    r = run()
    out = K.REPORTS / f"전사_가치사슬_{datetime.now(KST):%Y%m%d}.md"
    out.parent.mkdir(exist_ok=True)
    out.write_text(report(r), encoding="utf-8")
    sc = r["scenario"]
    print(f"100억 = 연 {sc['bottles_year']:,}병 · {sc['kl_year']}kl · 경감 {int(sc['reduction_at_target']*100)}% · 입력 필요 {len(r['missing'])} · 미확정 {len(r['unverified'])} → {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
