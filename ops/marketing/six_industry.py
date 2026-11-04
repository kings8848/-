#!/usr/bin/env python3
"""6차 산업 1×2×3 계기판 — 브랜드 주장을 데이터로 증명하는 마케팅 근거 엔진

곱셈 법칙: 한 축이라도 '증거 0'이면 전체가 0으로 표시된다.
  1차(테루아·원료) : data/raw_materials.csv — 자가 재배 원료 비율·로트
  2차(제조·숙성)  : 배치 기록(batches.xlsx/csv) — 실배치·공정 완결
  3차(유통·팬덤)  : 원장 — 채널 매출, 직거래 비중, 중간 수수료
  python3 ops/marketing/six_industry.py
"""
from __future__ import annotations

import csv
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
OPS = HERE.parent
sys.path.insert(0, str(OPS))
import kings_ops as K  # noqa: E402

DIRECT = {"스마트스토어", "와디즈", "B2B", "현장"}  # 킹스가 고객과 직접 만나는 채널
CONSIGN = {"로컬푸드"}  # 위탁(수수료) 채널


def measure() -> dict:
    F = K.Findings()
    lf = K.reconcile_localfood(F); ss = K.smartstore(F); bt = K.batches(F, lf)
    raw = list(csv.DictReader((K.DATA / "raw_materials.csv").open(encoding="utf-8"))) if (K.DATA / "raw_materials.csv").exists() else []
    own = sum(float(r["qty"] or 0) for r in raw if r.get("own_grown", "").upper() == "Y")
    tot = sum(float(r["qty"] or 0) for r in raw)
    lf_sales = lf["totals"].get("sales", 0); lf_fee = lf["totals"].get("fee", 0)
    direct = ss["total"]
    rev = lf_sales + direct
    s1 = {"records": len(raw), "own_ratio": round(own / tot, 3) if tot else None, "score": 1 if raw else 0}
    s2 = {"real_batches": bt["real_complete"], "score": 1 if bt["real_complete"] else 0}
    s3 = {"revenue": rev, "direct": direct, "direct_ratio": round(direct / rev, 3) if rev else None,
          "consign_fee": lf_fee, "consign_fee_rate": round(lf_fee / lf_sales, 3) if lf_sales else None, "score": 1 if rev else 0}
    return {"1차": s1, "2차": s2, "3차": s3, "product": s1["score"] * s2["score"] * s3["score"]}


def report(m) -> str:
    s1, s2, s3 = m["1차"], m["2차"], m["3차"]
    z = lambda s: "✅ 증거 있음" if s["score"] else "❌ 증거 0"
    L = [f"이 문서에서 알 수 있는 것: 6차 산업 1×2×3 = {m['product']} · 1차 {z(s1)} · 2차 {z(s2)} · 3차 {z(s3)} · 직거래 비중 {s3['direct_ratio']:.0%}\n" if s3["direct_ratio"] is not None else "이 문서에서 알 수 있는 것: 6차 산업 계기판\n",
         "# 6차 산업 계기판 (브랜드 주장 ↔ 데이터)\n",
         "| 축 | 측정 | 값 | 상태 |", "|---|---|---|---|",
         f"| 1차 테루아·원료 | 원료 입고 기록 · 자가 재배 비율 | {s1['records']}건 · {s1['own_ratio'] if s1['own_ratio'] is not None else '—'} | {z(s1)} |",
         f"| 2차 제조·숙성 | 실배치(6공정 완결) | {s2['real_batches']}건 | {z(s2)} |",
         f"| 3차 유통·팬덤 | 원장 매출 · 직거래 비중 · 위탁 수수료 | {s3['revenue']:,}원 · {s3['direct_ratio']:.0%} · {s3['consign_fee']:,}원({s3['consign_fee_rate']:.0%}) | {z(s3)} |",
         f"\n**곱셈 결과 = {m['product']}** — 한 축이라도 증거가 0이면 '19년 재배·옹기 숙성' 같은 주장을 광고에 쓸 근거가 약합니다.",
         "\n- 직거래 비중: 스마트스토어 입금 ÷ (로컬푸드 판매 + 스마트스토어 입금). 와디즈·B2B·현장은 원장 미연결이라 실제 직거래 비중은 이보다 높을 수 있음",
         "- 위탁 수수료: 로컬푸드 13%가 실측치. '중간 마진 50~70% 내재화'는 업계 일반론이며 킹스 실측이 아님"]
    return "\n".join(L) + "\n"


if __name__ == "__main__":
    m = measure()
    out = K.REPORTS / "6차산업_계기판.md"
    out.write_text(report(m), encoding="utf-8")
    print(report(m).splitlines()[0])
