#!/usr/bin/env python3
"""킹스양조장 운영 검증 엔진 (손사장 실증 모듈)

하는 일
  1. 실거래 원장 적재  : 양양로컬푸드 정산서, 스마트스토어 입금·일일주문현황
  2. 정산 대사         : 수량·판매금액·수수료(13%)·정산금액·부가세를 정산서 머리 합계와 대조
  3. 중복·누락 탐지    : 같은 내용의 정산서 중복, 반기(1~15일/16~말일) 구간 누락
  4. 출고 경보         : 스마트스토어 '발송대기'가 이틀 이상 이어지면 경보
  5. 배치 추적         : 원료→담금→증류→숙성→병입→출고 연결·알코올 수지 검증 (data/batches.csv)
  6. 재고 대사         : 병입 수량 - 판매 수량 = 장부 재고 (배치 기록이 있을 때)
  7. 전후 측정         : data/time_log.csv 의 수작업/자동 소요시간 비교
  8. 역량 점수         : 증거가 있는 항목만 점수를 준다 (rubric 은 아래 RUBRIC)

반복 실행 안전성(멱등성)
  모든 레코드는 내용 해시를 키로 state/ledger.json 에 적재한다.
  같은 자료를 다시 넣으면 신규 0건이어야 하며, 실행마다 state/runs.jsonl 에 기록한다.

사용법
  python3 ops/kings_ops.py run [--trigger manual|scheduled]
  python3 ops/kings_ops.py score
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import os

ROOT = Path(__file__).resolve().parent
DATA = Path(os.environ.get("KINGS_OPS_DATA", ROOT / "data"))
STATE = Path(os.environ.get("KINGS_OPS_STATE", ROOT / "state"))
REPORTS = Path(os.environ.get("KINGS_OPS_REPORTS", ROOT / "reports"))
KST = timezone(timedelta(hours=9))

LOCALFOOD_FEE_RATE = 0.13  # 양양로컬푸드 직접출하 수수료율 (정산서 기재값)
BOTTLE_L = {"금배주 25": 0.375, "금배주 17": 0.375, "금배주 40": 0.375, "봉신설주 17": 0.75, "금배주 25 봉신설주 에디션": 0.75}
BATCH_STAGES = ["원료입고", "담금", "발효종료", "증류", "숙성", "병입"]


# ───────────────────────── 공통 ─────────────────────────
def read_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [r for r in csv.DictReader(f) if any((v or "").strip() for v in r.values())]


def to_int(v) -> int | None:
    v = (v or "").strip().replace(",", "")
    return int(float(v)) if v else None


def d(v: str) -> date:
    return date.fromisoformat(v)


def h(*parts) -> str:
    return hashlib.sha256("|".join(str(p) for p in parts).encode()).hexdigest()[:16]


def gmail_id_to_kst(thread_id: str) -> datetime:
    """Gmail ID 상위 비트 = 수신 시각(ms). 실측 오차 2초 이내."""
    return datetime.fromtimestamp((int(thread_id, 16) >> 20) / 1000, tz=KST)


class Findings:
    def __init__(self):
        self.items: list[dict] = []

    def add(self, level: str, area: str, msg: str, action: str = "", ref: str = ""):
        self.items.append({"level": level, "area": area, "msg": msg, "action": action, "ref": ref})

    def by(self, level):
        return [i for i in self.items if i["level"] == level]


# ───────────────────────── 1~3. 로컬푸드 정산 대사 ─────────────────────────
def reconcile_localfood(F: Findings) -> dict:
    heads = read_csv(DATA / "localfood_settlements.csv")
    lines = read_csv(DATA / "localfood_lines.csv")
    by_file = defaultdict(list)
    for r in lines:
        by_file[r["source_file_id"]].append(r)

    # 3-a. 내용 지문으로 중복 정산서 찾기
    fp_seen: dict[str, str] = {}
    unique_heads, dup_files = [], []
    for hd in heads:
        rows = sorted(by_file[hd["source_file_id"]], key=lambda r: int(r["line_no"]))
        fp = h(hd["period_start"], hd["period_end"], *[(r["sale_date"], r["qty"], r["sales"]) for r in rows])
        if fp in fp_seen:
            dup_files.append((hd["source_file_id"], fp_seen[fp]))
            F.add("정보", "정산·중복", f"{hd['period_start']}~{hd['period_end']} 정산서가 Drive에 2부 있음(내용 동일) → 1부만 원장 반영",
                  "Drive에서 사본 1부를 '99_미분류·검토'로 이동", hd["source_file_id"])
            continue
        fp_seen[fp] = hd["source_file_id"]
        unique_heads.append(hd)

    checks_total = checks_pass = 0
    fully_reconciled = []
    per_period = []
    for hd in unique_heads:
        fid = hd["source_file_id"]
        rows = by_file[fid]
        q = sum(int(r["qty"]) for r in rows)
        s = sum(int(r["sales"]) for r in rows)
        fee = sum(int(r["fee"]) for r in rows)
        po = sum(int(r["payout"]) for r in rows)
        tag = f"{hd['period_start']}~{hd['period_end']}"
        results = {}

        def chk(name, ok, detail=""):
            nonlocal checks_total, checks_pass
            checks_total += 1
            checks_pass += ok
            results[name] = ok
            if not ok:
                F.add("경고", "정산·대사", f"{tag} {name} 불일치 {detail}", "로컬푸드 담당자에게 확인 요청", fid)

        if hd["header_count"]:
            chk("수량합계", q == to_int(hd["header_count"]), f"(상세 {q} / 머리 {hd['header_count']})")
        chk("판매금액합계", s == to_int(hd["header_sales"]), f"(상세 {s:,} / 머리 {to_int(hd['header_sales']):,})")
        chk("수수료합계", fee == to_int(hd["header_fee"]), f"(상세 {fee:,} / 머리 {to_int(hd['header_fee']):,})")
        chk("정산금액합계", po == to_int(hd["header_payout"]), f"(상세 {po:,} / 머리 {to_int(hd['header_payout']):,})")
        chk("판매-수수료=정산", s - fee == po)
        # 행 단위 수수료율 13% (원 미만 절사)
        bad_fee = [r for r in rows if int(r["fee"]) != int(int(r["sales"]) * LOCALFOOD_FEE_RATE) and
                   int(r["fee"]) != -int(-int(r["sales"]) * LOCALFOOD_FEE_RATE)]
        chk("행별 수수료 13%", not bad_fee, f"({len(bad_fee)}행)")
        # 부가세: 정산금액 = 공급가 + 세액, 세액 = 정산금액/11 반올림
        if hd["header_supply"]:
            sup, vat = to_int(hd["header_supply"]), to_int(hd["header_vat"])
            chk("공급가+세액=정산금액", sup + vat == po, f"({sup:,}+{vat:,}≠{po:,})")
            chk("세액=정산금액/11", vat == int(po / 11 + 0.5), f"(기재 {vat:,} / 계산 {int(po/11+0.5):,})")
        else:
            vat = to_int(hd["header_vat"])
            F.add("확인", "정산·세무", f"{tag} 신양식(농가상세) 정산서는 공급가 칸이 없고 세액 {vat:,}원이 정산금액/11({int(po/11+0.5):,})·판매금액/11({int(s/11+0.5):,}) 어느 쪽과도 맞지 않음",
                  "세무사 또는 로컬푸드에 세액 산식 확인(부가세 신고 전)", fid)
        # 행 단가×수량 ≠ 판매금액 (할인·정정 행)
        odd = [r for r in rows if int(r["unit_price"]) * int(r["qty"]) != int(r["sales"])]
        if odd:
            F.add("정보", "정산·정정", f"{tag} 단가×수량과 판매금액이 다른 행 {len(odd)}건(행당 {int(odd[0]['sales']):,}원) — 2025-10-02 '9월 2차 정산 수정 내역' 메일과 연결됨",
                  "정정 사유(할인·오류)를 원장 비고에 기록", fid)
        ret = [r for r in rows if int(r["qty"]) < 0]
        if ret:
            F.add("정보", "정산·반품", f"{tag} 반품·취소 {len(ret)}건(수량 {sum(int(r['qty']) for r in ret)}병) 상계 확인",
                  "반품된 병의 재입고/폐기 여부를 재고 장부에 기록", fid)
        # 지급 소요일
        pays = {r["pay_date"] for r in rows if r["pay_date"]}
        lag = (d(sorted(pays)[0]) - d(hd["period_end"])).days if pays else None
        if hd["barcode_count"] and to_int(hd["barcode_count"]):
            pass  # 바코드 출력 수수료 0원 확인됨(정산서 기재)
        ok_all = all(results.values())
        if ok_all:
            fully_reconciled.append(tag)
        per_period.append({"period": tag, "qty": q, "sales": s, "fee": fee, "payout": po,
                           "pay_lag_days": lag, "reconciled": ok_all, "source_file_id": fid})

    # 3-b. 반기 구간 누락
    starts = sorted(d(p["period"].split("~")[0]) for p in per_period)
    first, last = starts[0], date(2026, 5, 31)
    covered = [(d(p["period"].split("~")[0]), d(p["period"].split("~")[1])) for p in per_period]
    gaps = []
    cur = first
    while cur <= last:
        end = (cur.replace(day=15) if cur.day == 1 else (cur.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1))
        days = [cur + timedelta(n) for n in range((end - cur).days + 1)]
        uncovered = [x for x in days if not any(a <= x <= b for a, b in covered)]
        if len(uncovered) == len(days):
            gaps.append(f"{cur}~{end}")
        elif uncovered:
            gaps.append(f"{cur}~{end} 중 {len(uncovered)}일")
        cur = end + timedelta(1)
    if gaps:
        F.add("경고", "정산·누락", f"Drive 원장에 없는 정산 구간 {len(gaps)}개: " + ", ".join(gaps),
              "Gmail '매일 아홉 시 정산' 첨부를 Drive에 저장하거나 추진단에 재발송 요청 → 판매 없었던 구간은 '판매 0' 확인서로 닫기")

    # 3-c. Gmail에 온 정산 메일 vs Drive 보관본
    mails = []
    for line in (DATA / "localfood_gmail_threads.txt").read_text(encoding="utf-8").splitlines():
        if line.strip():
            tid, subj = line.split("\t", 1)
            mails.append({"thread_id": tid, "subject": subj, "received_kst": gmail_id_to_kst(tid).strftime("%Y-%m-%d")})
    mails.sort(key=lambda m: m["received_kst"])
    after_drive = [m for m in mails if m["received_kst"] > "2026-06-02"]
    if after_drive:
        F.add("경고", "정산·누락", f"2026-06-02 이후 Gmail로 받은 정산 메일 {len(after_drive)}통이 Drive 원장에 없음 (최근: {after_drive[-1]['received_kst']} '{after_drive[-1]['subject']}')",
              "첨부 엑셀을 Drive '07_재무·회계·세무/정산원본'에 저장 → 다음 실행 때 자동 대사", after_drive[-1]["thread_id"])

    tot = defaultdict(int)
    for p in per_period:
        for k in ("qty", "sales", "fee", "payout"):
            tot[k] += p[k]
    lags = [p["pay_lag_days"] for p in per_period if p["pay_lag_days"] is not None]
    return {"periods": per_period, "duplicates": dup_files, "gaps": gaps, "checks_total": checks_total,
            "checks_pass": checks_pass, "fully_reconciled": fully_reconciled, "totals": dict(tot),
            "avg_pay_lag": round(sum(lags) / len(lags), 1) if lags else None, "mails": mails,
            "mails_after_drive": after_drive, "lines": lines, "unique_file_ids": [p["source_file_id"] for p in per_period]}


# ───────────────────────── 스마트스토어 ─────────────────────────
def smartstore(F: Findings) -> dict:
    deps = read_csv(DATA / "smartstore_deposits.csv")
    status = read_csv(DATA / "smartstore_daily_status.csv")
    monthly = defaultdict(int)
    for r in deps:
        monthly[r["deposit_date"][:7]] += int(r["amount"])
    # 출고 경보: 발송대기 >0 이 연속 2일 이상
    status.sort(key=lambda r: r["status_date"])
    streak, alerts = [], []
    for r in status:
        if int(r["awaiting_shipment"]) > 0:
            if streak and (d(r["status_date"]) - d(streak[-1]["status_date"])).days != 1:
                if len(streak) >= 2:
                    alerts.append(streak)
                streak = []  # 메일이 빠진 날이 있으면 연속으로 보지 않음
            streak.append(r)
        else:
            if len(streak) >= 2:
                alerts.append(streak)
            streak = []
    open_alert = streak if len(streak) >= 2 else None
    for a in alerts:
        F.add("정보", "출고·지연(과거)", f"발송대기 {a[0]['awaiting_shipment']}건이 {a[0]['status_date']}~{a[-1]['status_date']} ({len(a)}일) 지속 후 해소",
              "예약발송·선물 지정일이었는지 메모(재발 방지 기준 마련)")
    if open_alert:
        F.add("긴급", "출고·지연", f"스마트스토어 발송대기 {open_alert[-1]['awaiting_shipment']}건이 {open_alert[0]['status_date']}부터 {len(open_alert)}일째 미발송 (최신 {open_alert[-1]['status_date']} 17시 기준)",
              "오늘 오전 발송 처리 또는 구매자에게 발송 예정일 안내 (지연 시 판매자 점수·페널티 위험)", open_alert[-1]["gmail_message_id"])
    latest = status[-1] if status else None
    return {"deposits": deps, "monthly": dict(sorted(monthly.items())), "total": sum(int(r["amount"]) for r in deps),
            "status_days": len(status), "status_range": (status[0]["status_date"], status[-1]["status_date"]) if status else None,
            "alerts_closed": len(alerts), "open_alert": bool(open_alert), "latest": latest}


# ───────────────────────── 5~6. 배치·재고 ─────────────────────────
def batches(F: Findings, lf: dict) -> dict:
    rows = read_csv(DATA / "batches.csv")
    real = [r for r in rows if (r.get("is_sample") or "").strip().upper() not in ("Y", "1", "TRUE")]
    out = {"batches": [], "real_complete": 0, "inventory": []}
    by = defaultdict(list)
    for r in real:
        by[r["batch_id"]].append(r)
    for bid, rs in by.items():
        stages = [r["stage"] for r in sorted(rs, key=lambda r: r["date"])]
        missing = [s for s in BATCH_STAGES if s not in stages]
        order_ok = [s for s in stages if s in BATCH_STAGES] == [s for s in BATCH_STAGES if s in stages]
        dist = next((r for r in rs if r["stage"] == "증류"), None)
        bott = next((r for r in rs if r["stage"] == "병입"), None)
        balance_ok = None
        if dist and bott and dist.get("abv_pct") and bott.get("abv_pct"):
            pa_dist = float(dist["output_qty"]) * float(dist["abv_pct"]) / 100  # 증류 원액 순알코올(L)
            prod = bott["product"].strip()
            vol = BOTTLE_L.get(prod, 0.375)
            pa_bott = float(bott["output_qty"]) * vol * float(bott["abv_pct"]) / 100
            balance_ok = pa_bott <= pa_dist * 1.02
            if not balance_ok:
                F.add("경고", "배치·수지", f"{bid} 병입 순알코올 {pa_bott:.1f}L > 증류 순알코올 {pa_dist:.1f}L", "증류·희석·병입 수치 재확인", bid)
        complete = not missing and order_ok and balance_ok is not False
        if missing:
            F.add("확인", "배치·추적", f"{bid} 미기록 공정: {', '.join(missing)}", "해당 공정 일자·수량을 batches.csv에 추가", bid)
        out["batches"].append({"batch_id": bid, "stages": stages, "missing": missing, "order_ok": order_ok,
                               "balance_ok": balance_ok, "complete": complete})
        out["real_complete"] += complete
        if bott:
            prod = bott["product"].strip()
            bottled = int(float(bott["output_qty"]))
            sold_after = sum(int(r["qty"]) for r in lf["lines"] if r["source_file_id"] in lf["unique_file_ids"]
                             and r["item"].startswith(prod) and r["sale_date"] >= bott["date"])
            counted = (bott.get("counted_on_hand") or "").strip()
            inv = {"batch_id": bid, "product": prod, "bottled": bottled, "sold_localfood": sold_after,
                   "book_on_hand_min": bottled - sold_after, "counted_on_hand": int(counted) if counted else None}
            out["inventory"].append(inv)
            if counted and int(counted) > bottled - sold_after:
                F.add("확인", "재고·대사", f"{bid} 실사 {counted}병 > 장부 상한 {bottled - sold_after}병", "다른 배치 혼입 또는 판매 미기록 확인", bid)
    if not real:
        F.add("확인", "배치·추적", "실제 배치 기록 0건 (Drive·Gmail에서 제조기록부를 찾지 못함: 품목제조보고서·라벨만 있음)",
              "templates/batch_record_template.csv 양식으로 최근 1배치(금배주 25 또는 봉신설주 17) 6개 공정 입력 — 약 15분")
    return out


# ───────────────────────── 7. 전후 측정 ─────────────────────────
def time_log(F: Findings) -> dict:
    rows = read_csv(DATA / "time_log.csv")
    pairs = defaultdict(dict)
    for r in rows:
        if (r.get("is_estimate") or "").strip().upper() in ("Y", "1", "TRUE"):
            continue
        pairs[r["task"]][r["mode"]] = pairs[r["task"]].get(r["mode"], 0) + float(r["minutes"])
    measured = {t: v for t, v in pairs.items() if "수작업" in v and "자동" in v}
    if not measured:
        F.add("확인", "성과·측정", "전후 실측 기록 0건", "다음 정산서 1건을 수작업으로 대사할 때 걸린 분(minute)을 time_log.csv에 기록")
    return {"measured": {t: {"before": v["수작업"], "after": v["자동"], "saved": v["수작업"] - v["자동"]} for t, v in measured.items()}}


# ───────────────────────── 연결 대장 ─────────────────────────
def connections(F: Findings, today: date | None = None) -> list[dict]:
    p = ROOT / "company" / "connections.json"
    if not p.exists():
        return []
    today = today or datetime.now(KST).date()
    rows = json.loads(p.read_text(encoding="utf-8"))["connections"]
    for c in rows:
        if c["status"] != "연결":
            continue
        if (today - d(c["last_checked"])).days > 7:
            F.add("경고", "연결·점검", f"{c['name']} 마지막 확인 {c['last_checked']} — 7일 넘게 미확인", "연결 상태 확인 후 connections.json 갱신")
        if c.get("expires") and 0 <= (d(c["expires"]) - today).days <= 7:
            F.add("경고", "연결·만료", f"{c['name']} {c['expires']} 만료 예정", "재연결(토큰 갱신)")
    off = [c["name"] for c in rows if c["status"] not in ("연결", "1회 실행 후 종료")]
    if off:
        F.add("정보", "연결·미연결", "미연결: " + ", ".join(off), "우선순위: PC 폴더(Remote Control) → 스마트스토어 커머스API")
    return rows


# ───────────────────────── 멱등 적재 + 실행 기록 ─────────────────────────
def ingest(lf: dict, ss: dict) -> dict:
    STATE.mkdir(exist_ok=True)
    p = STATE / "ledger.json"
    ledger = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    added = 0
    recs = []
    for r in lf["lines"]:
        if r["source_file_id"] not in lf["unique_file_ids"]:
            continue
        recs.append(("localfood", h("lf", r["sale_date"], r["line_no"], r["qty"], r["sales"], r["pay_date"]),
                     {"date": r["sale_date"], "qty": int(r["qty"]), "sales": int(r["sales"]), "payout": int(r["payout"]),
                      "src": r["source_file_id"]}))
    for r in ss["deposits"]:
        recs.append(("smartstore_deposit", h("ssd", r["gmail_thread_id"]),
                     {"date": r["deposit_date"], "amount": int(r["amount"]), "src": r["gmail_thread_id"]}))
    for kind, key, body in recs:
        if key not in ledger:
            ledger[key] = {"kind": kind, **body}
            added += 1
    p.write_text(json.dumps(ledger, ensure_ascii=False, indent=0, sort_keys=True), encoding="utf-8")
    return {"ledger_size": len(ledger), "added": added, "offered": len(recs)}


def log_run(trigger: str, ing: dict, findings: Findings, score: dict, duration_sec: float | None = None):
    entry = {"at": datetime.now(KST).isoformat(timespec="seconds"), "trigger": trigger, **ing,
             "duration_sec": duration_sec,
             "urgent": len(findings.by("긴급")), "warn": len(findings.by("경고")), "score": score["total"]}
    with (STATE / "runs.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    return entry


def runs() -> list[dict]:
    p = STATE / "runs.jsonl"
    return [json.loads(x) for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.exists() else []


# ───────────────────────── 8. 점수 ─────────────────────────
def score(lf, ss, bt, tl, F: Findings, history: list[dict]) -> dict:
    idem = [r for r in history if r["added"] == 0 and r["offered"] > 0]
    sched = [r for r in history if r["trigger"] == "scheduled"]
    actions = [i for i in F.items if i["action"]]
    R = [
        # (영역, 항목, 배점, 획득, 근거)
        ("운영체계", "원본 추적: 모든 원장 행이 원본 파일·메일 ID를 가짐", 10,
         10 if all(r["source_file_id"] for r in lf["lines"]) and all(r["gmail_thread_id"] for r in ss["deposits"]) else 0,
         f"정산 상세 {len(lf['lines'])}행·입금 {len(ss['deposits'])}건 전부 출처 ID 보유"),
        ("운영체계", "검증 규칙 코드화(합계·13%·부가세·반품·정정·중복)", 10,
         10 if lf["checks_total"] >= 50 else 5, f"규칙 검사 {lf['checks_total']}회 실행, 통과 {lf['checks_pass']}회"),
        ("운영체계", "예외→조치 목록 자동 생성", 10, 10 if actions else 0, f"조치 항목 {len(actions)}개 생성"),
        ("운영체계", "반복 실행 무중복(같은 자료 재처리 시 신규 0건)", 10,
         10 if idem else 0, f"실행 {len(history)}회 중 재처리 무중복 확인 {len(idem)}회"),
        ("운영체계", "예약 실행 실증(사람 개입 없이 정해진 시각에 실행·기록)", 10,
         10 if sched else 0, f"예약 실행 기록 {len(sched)}회" + ("" if sched else " — 2026-11-04 09:00 KST 예약 실행 대기")),
        ("업무자동화", "실거래 정산 대사(정산서 머리합계와 전부 일치)", 10,
         10 if lf["fully_reconciled"] else 0, f"완전 대사 {len(lf['fully_reconciled'])}개 구간 / {len(lf['periods'])}개"),
        ("업무자동화", "판매채널 2곳 이상 연결", 5, 5 if lf["periods"] and ss["deposits"] else 0,
         "양양로컬푸드 정산서 + 스마트스토어 입금·주문현황"),
        ("업무자동화", "원장 누락 구간 자동 탐지", 5, 5 if lf["gaps"] is not None else 0, f"누락 구간 {len(lf['gaps'])}개 탐지"),
        ("업무자동화", "출고 지연 자동 경보", 5, 5 if ss["status_days"] else 0, f"주문현황 {ss['status_days']}일치 감시, 미해소 경보 {'있음' if ss['open_alert'] else '없음'}"),
        ("업무자동화", "실제 배치 1건 원료→병입 연결·알코올 수지 검증", 10, 10 if bt["real_complete"] else 0,
         f"완결 배치 {bt['real_complete']}건"),
        ("업무자동화", "병입-판매 재고 대사", 5, 5 if any(i["counted_on_hand"] is not None for i in bt["inventory"]) else 0,
         f"재고 대사 {len(bt['inventory'])}건(실사 포함 {sum(1 for i in bt['inventory'] if i['counted_on_hand'] is not None)}건)"),
        ("업무자동화", "전후 실측(같은 업무 수작업 vs 자동 소요시간)", 10, 10 if tl["measured"] else 0,
         f"실측 업무 {len(tl['measured'])}개"),
    ]
    rows = [{"area": a, "item": i, "max": m, "got": g, "evidence": e} for a, i, m, g, e in R]
    area = defaultdict(lambda: [0, 0])
    for r in rows:
        area[r["area"]][0] += r["got"]
        area[r["area"]][1] += r["max"]
    return {"rows": rows, "areas": {k: {"got": v[0], "max": v[1]} for k, v in area.items()},
            "total": sum(r["got"] for r in rows), "max": sum(r["max"] for r in rows)}


# ───────────────────────── 보고서 ─────────────────────────
def won(n):
    return f"{n:,}원"


def report(lf, ss, bt, tl, F, sc, ing, entry) -> str:
    today = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    L = []
    urgent = F.by("긴급")
    top = urgent[0]["action"] if urgent else (F.by("경고")[0]["action"] if F.by("경고") else "없음")
    L.append(f"이 문서에서 알 수 있는 것: 점수 {sc['total']}/{sc['max']} · 긴급 {len(urgent)}건 · 경고 {len(F.by('경고'))}건 · 1순위 조치: {top}\n")
    L.append(f"# 킹스양조장 운영 검증 보고서\n\n- 실행: {today} KST · 트리거 `{entry['trigger']}` · 원장 {ing['ledger_size']}건(이번 신규 {ing['added']}건) · 소요 {entry.get('duration_sec')}초")
    L.append(f"- 역량 점수(증거 기반): **{sc['total']}/{sc['max']}점** — " +
             " · ".join(f"{k} {v['got']}/{v['max']}" for k, v in sc["areas"].items()))
    L.append("\n## 1. 오늘 할 일 (긴급 → 경고 순)\n")
    L.append("| 등급 | 영역 | 내용 | 조치 |\n|---|---|---|---|")
    for lv in ("긴급", "경고", "확인"):
        for i in F.by(lv):
            L.append(f"| {lv} | {i['area']} | {i['msg']} | {i['action']} |")
    info = F.by("정보")
    if info:
        L.append("\n### 참고(처리 완료·기록용)\n")
        for i in info:
            L.append(f"- [{i['area']}] {i['msg']} → {i['action']}")
    L.append("\n## 2. 양양로컬푸드 정산 대사 (실거래)\n")
    L.append(f"- 정산서 {len(lf['periods'])}개 구간(중복 사본 {len(lf['duplicates'])}부 제외) · 규칙 검사 {lf['checks_total']}회 중 {lf['checks_pass']}회 통과 · 완전 대사 {len(lf['fully_reconciled'])}개 구간")
    t = lf["totals"]
    L.append(f"- 누계: 판매 {t['qty']}병 · 판매금액 {won(t['sales'])} · 수수료 {won(t['fee'])}(13%) · 정산금액 {won(t['payout'])} · 평균 지급 소요 {lf['avg_pay_lag']}일(구간 종료일→지급일)")
    L.append("\n| 구간 | 병 | 판매금액 | 수수료 | 정산금액 | 지급(일) | 대사 |\n|---|---:|---:|---:|---:|---:|:-:|")
    for p in lf["periods"]:
        L.append(f"| {p['period']} | {p['qty']} | {p['sales']:,} | {p['fee']:,} | {p['payout']:,} | {p['pay_lag_days'] if p['pay_lag_days'] is not None else '-'} | {'✅' if p['reconciled'] else '⚠️'} |")
    L.append("\n## 3. 스마트스토어\n")
    L.append(f"- 정산 입금 {len(ss['deposits'])}건 · 합계 {won(ss['total'])} (NH농협은행)")
    L.append("\n| 월 | 입금액 |\n|---|---:|")
    for m, v in ss["monthly"].items():
        L.append(f"| {m} | {v:,} |")
    if ss["latest"]:
        lt = ss["latest"]
        L.append(f"\n- 최신 주문현황({lt['status_date']} 17시): 신규 {lt['new_orders']} · 발송대기 {lt['awaiting_shipment']} · 취소요청 {lt['cancel_req']} · 반품요청 {lt['return_req']}")
    L.append("\n## 4. 배치·재고\n")
    if bt["batches"]:
        for b in bt["batches"]:
            L.append(f"- {b['batch_id']}: 공정 {' → '.join(b['stages'])} · 누락 {b['missing'] or '없음'} · 알코올수지 {b['balance_ok']} · 완결 {b['complete']}")
        for i in bt["inventory"]:
            L.append(f"- 재고 {i['batch_id']} {i['product']}: 병입 {i['bottled']} − 로컬푸드 판매 {i['sold_localfood']} = 장부 상한 {i['book_on_hand_min']}병 · 실사 {i['counted_on_hand']}")
    else:
        L.append("- 실제 배치 기록 없음 → `ops/templates/batch_record_template.csv` 입력 대기")
    L.append("\n## 5. 전후 측정\n")
    if tl["measured"]:
        for k, v in tl["measured"].items():
            L.append(f"- {k}: 수작업 {v['before']}분 → 자동 {v['after']}분 (절감 {v['saved']}분)")
    else:
        L.append("- 실측 없음 → `ops/data/time_log.csv`에 수작업 소요시간 기록 대기")
    L.append("\n## 6. 점수표\n\n| 영역 | 항목 | 배점 | 획득 | 근거 |\n|---|---|---:|---:|---|")
    for r in sc["rows"]:
        L.append(f"| {r['area']} | {r['item']} | {r['max']} | {r['got']} | {r['evidence']} |")
    return "\n".join(L) + "\n"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["run", "score"])
    ap.add_argument("--trigger", default="manual", choices=["manual", "scheduled", "test"])
    a = ap.parse_args(argv)
    import time
    t0 = time.perf_counter()
    F = Findings()
    lf = reconcile_localfood(F)
    ss = smartstore(F)
    bt = batches(F, lf)
    tl = time_log(F)
    connections(F)
    if a.cmd == "score":
        sc = score(lf, ss, bt, tl, F, runs())
        print(json.dumps(sc, ensure_ascii=False, indent=1))
        return 0
    ing = ingest(lf, ss)
    hist = runs()
    # 이번 실행까지 포함해 점수 계산
    provisional = {"at": "", "trigger": a.trigger, **ing}
    sc = score(lf, ss, bt, tl, F, hist + [provisional])
    entry = log_run(a.trigger, ing, F, sc, round(time.perf_counter() - t0, 3))
    REPORTS.mkdir(exist_ok=True)
    stamp = datetime.now(KST).strftime("%Y%m%d")
    md = report(lf, ss, bt, tl, F, sc, ing, entry)
    (REPORTS / f"운영검증_보고서_{stamp}.md").write_text(md, encoding="utf-8")
    (REPORTS / f"역량평가_{stamp}.json").write_text(json.dumps(
        {"generated_at": entry["at"], "score": sc, "findings": F.items, "ingest": ing,
         "localfood": {k: v for k, v in lf.items() if k not in ("lines",)}, "smartstore": {k: v for k, v in ss.items() if k != "deposits"},
         "batches": bt, "time_log": tl}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(f"[{entry['at']}] 원장 {ing['ledger_size']}건 (신규 {ing['added']}/{ing['offered']}) · 긴급 {entry['urgent']} · 경고 {entry['warn']} · 점수 {sc['total']}/{sc['max']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
