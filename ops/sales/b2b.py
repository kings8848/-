#!/usr/bin/env python3
"""킹스 B2B 리드 → 맞춤 제안 파이프라인 (대표 제공 n8n 시나리오의 킹스·법규 적용판)

단계: ① 리드 수집(leads.csv: 문의 inbound / 공식 API / 수동) → ② 매장 유형 판별·페어링(코드, SOP 기준)
      → ③ 제안서 HTML 생성 → ④ 발송 가능 판정 + 발행 큐 등록(대표 승인, 카카오 알림) → ⑤ 상태·5일 팔로업 경보

법규 게이트(compliance_register):
  - 광고성 메일은 source=inbound 이거나 consent=Y 인 리드만 (정보통신망법 제50조). 나머지는 '방문·전화 제안'
  - 무료 시음 키트 문구는 NTS-TASTING 증빙(세무서 사전승인)이 있을 때만
  - B2B 단가가 없거나, 추천 제품 품목제조보고 미확인이면 제안서는 만들되 발송 불가
  python3 ops/sales/b2b.py
"""
from __future__ import annotations

import csv
import html
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OPS = HERE.parent
KST = timezone(timedelta(hours=9))
LEADS = Path(os.environ.get("KINGS_LEADS", HERE / "leads.csv"))
OUT = Path(os.environ.get("KINGS_PROPOSALS", HERE / "proposals"))
FIELDS = ["lead_id", "name", "segment", "menu", "area", "contact", "email", "source", "consent", "status", "proposal", "sent_at", "last_reply", "note"]
SEGMENTS = [
    ("한우", ["한우", "고기", "숯불", "구이", "육류", "스테이크"], "금배주 25", "산돌배 특유의 산미와 은은한 배 향이 기름진 육류를 산뜻하게 씻어냅니다.", True),
    ("해산물코스", ["해산물", "스시", "코스", "한식 다이닝", "정갈", "파인다이닝"], "봉신설주 17", "깔끔한 여운과 깊은 곡주 향이 정갈한 코스와 어울립니다.", True),
    ("바", ["바", "펍", "칵테일", "고도수", "전통주 바"], "설락소주", "깔끔한 증류 풍미.", False),
]
FOLLOWUP_DAYS = 5


def load(path=LEADS):
    return list(csv.DictReader(path.open(encoding="utf-8"))) if path.exists() else []


def save(rows, path=LEADS):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS); w.writeheader()
        w.writerows([{k: r.get(k, "") for k in FIELDS} for r in rows])


def classify(lead) -> dict:
    text = f"{lead.get('menu','')} {lead.get('name','')} {lead.get('note','')}"
    best = max(SEGMENTS, key=lambda s: sum(1 for kw in s[1] if kw in text))
    if not any(kw in text for kw in best[1]):
        return {"segment": "미분류", "product": None, "reason": None, "reason_ok": False}
    return {"segment": best[0], "product": best[2], "reason": best[3], "reason_ok": best[4]}


def gates(lead, prof, master, register) -> list[str]:
    block = []
    ev = {i["id"]: i for i in register["items"]}
    if lead.get("source") != "inbound" and lead.get("consent", "").upper() != "Y":
        block.append("광고성 메일 사전 동의 없음(정보통신망법 제50조) → 방문·전화 제안으로")
    if not prof["product"]:
        block.append("매장 유형 미분류")
    else:
        p = master["products"].get(prof["product"], {})
        if (p.get("price") or {}).get("B2B") is None:
            block.append(f"{prof['product']} B2B 공급 단가 미입력")
        if not p or p.get("verified") is False:
            block.append(f"{prof['product']} 품목제조보고·라벨 확인 필요")
        if not prof["reason_ok"]:
            block.append("페어링 문구 대표 확인 필요(SOP B2B_페어링)")
    if not ev.get("NTS-DIRECT-SUPPLY", {}).get("evidence"):
        block.append("음식점 직접 공급 범위 세무서 확인 전")
    return block


def proposal_html(lead, prof, master, register) -> str:
    p = master["products"].get(prof["product"] or "", {})
    price = (p.get("price") or {}).get("B2B")
    tasting = bool({i["id"]: i for i in register["items"]}.get("NTS-TASTING", {}).get("evidence"))
    e = html.escape
    rows = [f"<h1>{e(lead['name'])} 님께 드리는 킹스양조장 페어링 제안</h1>",
            "<p>술을 만들려고 고추밭에 돌배나무부터 심은 양조장, 강원 양양 구룡령 킹스양조장입니다.</p>",
            f"<h2>추천: {e(prof['product'] or '—')}</h2>",
            f"<p>{e(prof['reason'] or '') if prof['reason_ok'] else '[페어링 문구 대표 확인 후 기재]'}</p>",
            "<h2>공급 단가</h2>",
            f"<p>{f'{price:,}원 (부가세 별도 여부 대표 확정)' if price else '[B2B 공급 단가 대표 확정 후 기재]'}</p>"]
    if tasting:
        rows.append("<h2>시음</h2><p>시음 키트 신청을 받습니다(세무서 사전승인 범위 내).</p>")
    rows.append("<p><small>19세 미만 청소년에게 판매하지 않습니다. 지나친 음주는 건강을 해칩니다.</small></p>")
    return "<!doctype html><meta charset='utf-8'><title>킹스양조장 제안서</title>" + "\n".join(rows)


def run(today: date | None = None, create_tasks: bool = True, master: dict | None = None, register: dict | None = None) -> dict:
    today = today or datetime.now(KST).date()
    master = master or json.loads((OPS / "enterprise" / "master.json").read_text(encoding="utf-8"))
    register = register or json.loads((OPS / "company" / "compliance_register.json").read_text(encoding="utf-8"))
    leads = load()
    OUT.mkdir(parents=True, exist_ok=True)
    summary = {"leads": len(leads), "ready": [], "blocked": [], "call_list": [], "followup": []}
    for L in leads:
        if L.get("status") in ("거래", "보류"):
            continue
        if L.get("status") == "제안완료" and L.get("sent_at") and not L.get("last_reply"):
            if (today - date.fromisoformat(L["sent_at"][:10])).days >= FOLLOWUP_DAYS:
                summary["followup"].append(L["lead_id"])
            continue
        if L.get("status") not in ("", "수집", "프로파일", "제안초안"):
            continue
        prof = classify(L)
        L["segment"] = prof["segment"]
        f = OUT / f"{L['lead_id']}.html"
        f.write_text(proposal_html(L, prof, master, register), encoding="utf-8")
        L["proposal"] = os.path.relpath(f, OPS.parent)
        block = gates(L, prof, master, register)
        L["status"] = "제안초안"
        if any("사전 동의" in b for b in block):
            summary["call_list"].append(L["lead_id"])
        if block:
            summary["blocked"].append({"lead": L["lead_id"], "why": block})
        else:
            summary["ready"].append(L["lead_id"])
            if create_tasks:
                sys.path.insert(0, str(OPS / "company")); import workflow as wf
                db = wf.load()
                oid = wf.new_order(db, f"[B2B] {L['name']} 맞춤 제안서 발송")
                wf.interpret(db, oid, "B2B 파이프라인 자동 생성: 법규 게이트 통과. 대표 승인 후 대표 메일로 발송.")
                tid = wf.add_task(db, oid, "B2B영업", L["proposal"], [f"{L['name']} 제안서 확인", "발송 후 회신 확인"], external=True, channel="메일")
                wf.save(db)
                L["status"] = "대표승인대기"; L["note"] = (L.get("note", "") + f" task={tid}").strip()
    save(leads)
    return summary


def main():
    s = run()
    print(f"B2B: 리드 {s['leads']} · 발송 준비 {len(s['ready'])} · 보류 {len(s['blocked'])} · 방문·전화 목록 {len(s['call_list'])} · 팔로업 {len(s['followup'])}")
    for b in s["blocked"][:5]:
        print(f"  - {b['lead']}: {'; '.join(b['why'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
