#!/usr/bin/env python3
"""1인 통합 대시보드(Cockpit) — 1차·2차·3차·B2B·법정 의무·대표 판단 사항을 한 화면에.
파이프라인 마지막 단계에서 매일 다시 그린다: ops/reports/cockpit.html (휴대폰·PC 브라우저로 열기)
"""
from __future__ import annotations

import csv
import html
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

OPS = Path(__file__).resolve().parent
sys.path.insert(0, str(OPS)); sys.path.insert(0, str(OPS / "marketing"))
import kings_ops as K  # noqa: E402
import six_industry  # noqa: E402

KST = timezone(timedelta(hours=9))
e = html.escape


def gather() -> dict:
    F = K.Findings()
    lf = K.reconcile_localfood(F); ss = K.smartstore(F); bt = K.batches(F, lf); K.compliance(F); kp = K.kpi(F, lf, ss)
    six = six_industry.measure()
    db = json.loads((OPS / "state" / "orders.json").read_text(encoding="utf-8")) if (OPS / "state" / "orders.json").exists() else {"orders": {}, "tasks": {}}
    qs = [(oid, q["q"], q.get("options", [])) for oid, o in db["orders"].items() for q in o.get("questions", []) if q["answer"] is None]
    approvals = [(tid, t["accept"][0]) for tid, t in db["tasks"].items() if t["status"] in ("대표승인대기", "대표상신")]
    leads = list(csv.DictReader((OPS / "sales" / "leads.csv").open(encoding="utf-8"))) if (OPS / "sales" / "leads.csv").exists() else []
    reg = json.loads((OPS / "company" / "compliance_register.json").read_text(encoding="utf-8"))["items"]
    return {"F": F, "lf": lf, "ss": ss, "bt": bt, "kp": kp, "six": six, "qs": qs, "approvals": approvals, "leads": leads, "reg": reg, "tasks": db["tasks"]}


def render(g) -> str:
    F, six = g["F"], g["six"]
    urgent = F.by("긴급"); warn = F.by("경고")
    lead_st = {}
    for L in g["leads"]:
        lead_st[L.get("status") or "수집"] = lead_st.get(L.get("status") or "수집", 0) + 1
    reg_open = [i for i in g["reg"] if not i["evidence"]]
    open_tasks = sum(1 for t in g["tasks"].values() if t["status"] != "완료")
    def axis(name, ok, rows):
        return f"<section class='ax {'ok' if ok else 'no'}'><h3>{name}<span>{'증거 있음' if ok else '증거 0'}</span></h3><ul>" + "".join(f"<li><b>{e(k)}</b>{e(str(v))}</li>" for k, v in rows) + "</ul></section>"
    s1, s2, s3 = six["1차"], six["2차"], six["3차"]
    ceo = "".join(f"<li class='u'>{e(i['msg'])}<small>{e(i['action'])}</small></li>" for i in urgent) + \
          "".join(f"<li>승인 {e(t)}: {e(a)}</li>" for t, a in g["approvals"]) + \
          "".join(f"<li>결정 {e(o)}: {e(q)}{('<small>' + e(' / '.join(op)) + '</small>') if op else ''}</li>" for o, q, op in g["qs"])
    return f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>킹스 콕핏</title><style>
:root{{--bg:#f6f4f8;--card:#fff;--ink:#221a2b;--mut:#6b6276;--line:#ddd5e6;--plum:#5b2c83;--ok:#2f6b5a;--no:#b2462e;--gold:#a8812a}}
@media (prefers-color-scheme:dark){{:root{{--bg:#17131c;--card:#211b28;--ink:#efe9f4;--mut:#a79db3;--line:#3a3144;--plum:#c59be8;--ok:#7fd1b6;--no:#f08c72;--gold:#e0bd6a}}}}
body{{margin:0;background:var(--bg);color:var(--ink);font:15px/1.55 "Apple SD Gothic Neo","Malgun Gothic",sans-serif;padding:20px max(16px,env(safe-area-inset-left))}}
.w{{max-width:1000px;margin:0 auto;display:grid;gap:16px}} h1{{margin:0;font-size:24px}} .sub{{color:var(--mut);font-size:13px}}
.tiles{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px}}
.t{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px}} .t b{{display:block;font-size:22px;font-variant-numeric:tabular-nums}} .t span{{font-size:12px;color:var(--mut)}}
.grid{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}} @media(max-width:760px){{.grid{{grid-template-columns:1fr}}}}
.ax{{background:var(--card);border:1px solid var(--line);border-top:4px solid var(--no);border-radius:10px;padding:12px}} .ax.ok{{border-top-color:var(--ok)}}
.ax h3{{margin:0 0 6px;display:flex;justify-content:space-between;font-size:16px}} .ax h3 span{{font-size:12px;color:var(--mut)}}
ul{{margin:0;padding-left:0;list-style:none;display:grid;gap:6px}} li b{{display:block;font-size:12px;color:var(--mut);font-weight:600}}
.ceo{{background:var(--card);border:2px solid var(--gold);border-radius:10px;padding:14px}} .ceo h2{{margin:0 0 8px;font-size:18px}}
.ceo li{{border-top:1px dashed var(--line);padding-top:6px}} .ceo li.u{{color:var(--no);font-weight:600}} small{{display:block;color:var(--mut);font-weight:400}}
.box{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px}} .box h2{{margin:0 0 8px;font-size:16px}}
</style></head><body><div class="w">
<div><h1>킹스양조장 콕핏</h1><div class="sub">{datetime.now(KST):%Y-%m-%d %H:%M} KST · 파이프라인이 매일 갱신 · 숫자는 원장 기준</div></div>
<div class="tiles">
 <div class="t"><span>6차 산업 1×2×3</span><b>{six['product']}</b><span>1차·2차 증거 필요</span></div>
 <div class="t"><span>원장 매출(최근 12개월)</span><b>{g['kp']['trailing12']:,}</b><span>원 · 100억 대비 {g['kp']['achieved_pct']}%</span></div>
 <div class="t"><span>긴급 / 경고</span><b>{len(urgent)} / {len(warn)}</b><span>경보</span></div>
 <div class="t"><span>진행 중 업무</span><b>{open_tasks}</b><span>담당 배정됨</span></div>
 <div class="t"><span>B2B 리드</span><b>{len(g['leads'])}</b><span>{e(', '.join(f'{k} {v}' for k, v in lead_st.items()) or '아직 없음')}</span></div>
 <div class="t"><span>법정 의무 증빙 미등록</span><b>{len(reg_open)}</b><span>/ {len(g['reg'])}건</span></div>
</div>
<div class="ceo"><h2>대표님 판단이 필요한 것</h2><ul>{ceo or '<li>없음</li>'}</ul></div>
<div class="grid">
{axis('1차 테루아·원료', s1['score'], [('원료 입고 기록', f"{s1['records']}건"), ('자가 재배 비율', s1['own_ratio'] if s1['own_ratio'] is not None else '기록 필요')])}
{axis('2차 제조·숙성', s2['score'], [('실배치(6공정)', f"{s2['real_batches']}건"), ('입력', '배치기록 엑셀')])}
{axis('3차 유통·팬덤', s3['score'], [('직거래 비중', f"{s3['direct_ratio']:.0%}" if s3['direct_ratio'] is not None else '—'), ('위탁 수수료', f"{s3['consign_fee']:,}원 ({s3['consign_fee_rate']:.0%})" if s3['consign_fee_rate'] is not None else '—'), ('최근 주문현황', f"발송대기 {g['ss']['latest']['awaiting_shipment']}건" if g['ss']['latest'] else '—')])}
</div>
<div class="box"><h2>경고</h2><ul>{''.join(f"<li>{e(i['msg'])}<small>{e(i['action'])}</small></li>" for i in warn) or '<li>없음</li>'}</ul></div>
</div></body></html>"""


def main():
    out = K.REPORTS / "cockpit.html"
    out.write_text(render(gather()), encoding="utf-8")
    print(f"콕핏 갱신 → {out.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
