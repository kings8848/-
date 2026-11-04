#!/usr/bin/env python3
"""킹스 지시 파이프라인 — 영상 'AI 회사' 구조를 1인 양조장용으로 줄인 것

흐름: 지시 등록(원문 봉인) → [토론: 기본 생략] → 해석 → 분해·배정(1담당·1산출물·검수기준 잠금)
      → 수행·제출 → 일괄 검수(통과/반려/불가, 반려 3회 → 대표 상신) → [독립검토: 권고만]
      → 외부 발송·게시·제출 건은 대표 승인 후 완료

  python3 ops/company/workflow.py new "원문" [--depth 생략|심도차등|전원깊게]
  python3 ops/company/workflow.py interpret D-0001 "해석"
  python3 ops/company/workflow.py task D-0001 --owner 정산원가 --output 경로 --accept "기준1;기준2" [--after T-0001] [--external]
  python3 ops/company/workflow.py submit T-0001
  python3 ops/company/workflow.py review --pass T-0001 T-0002 --reject T-0003="지적"   (일괄)
  python3 ops/company/workflow.py advise T-0001 "권고"      # 상태 불변
  python3 ops/company/workflow.py approve T-0001            # 대표 승인(외부 건)
  python3 ops/company/workflow.py brief T-0001              # 회사의 기억 + 기준 + 지난 지적
  python3 ops/company/workflow.py verify | status
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
STATE = Path(os.environ.get("KINGS_WF_STATE", HERE.parent / "state" / "orders.json"))
KST = timezone(timedelta(hours=9))
FIRST_LINE = "이 문서에서 알 수 있는 것"
MAX_REJECT = 3
MAX_MUST_KNOW = 10
# 발행 큐 하루 상한(영상: 스레드 0/250·인스타 0/25처럼 시스템이 강제)
DAILY_CAP = {"고객안내": 20, "메일": 20, "제출": 3, "상품수정": 10, "SNS": 5}
OUTBOX_STATES = ["대표승인대기", "발송대기", "게시확인필요", "완료", "실패", "반려"]


def now():
    return datetime.now(KST).isoformat(timespec="seconds")


def sha(t: str) -> str:
    return hashlib.sha256(t.encode("utf-8")).hexdigest()


def load():
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {"orders": {}, "tasks": {}}


def save(db):
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(db, ensure_ascii=False, indent=1), encoding="utf-8")


def roster():
    return json.loads((HERE / "roster.json").read_text(encoding="utf-8"))


class WFError(Exception):
    pass


# ───────── 지시 ─────────
def new_order(db, text, depth="생략"):
    oid = f"D-{len(db['orders']) + 1:04d}"
    db["orders"][oid] = {"original": text, "sha256": sha(text), "depth": depth, "created": now(),
                         "interpretation": None, "questions": [], "log": [f"{now()} 지시 등록(원문 봉인)"]}
    return oid


def interpret(db, oid, text):
    o = db["orders"][oid]
    o["interpretation"] = text
    o["log"].append(f"{now()} 해석 작성")


def ask(db, oid, q, options=()):
    """영상: '불명확한 점은 임의로 결정하지 말고 먼저 질문'. 답이 오기 전엔 분해 불가."""
    o = db["orders"][oid]
    o.setdefault("questions", []).append({"q": q, "options": list(options), "answer": None, "asked": now()})
    o["log"].append(f"{now()} 확인 질문: {q}")
    return len(o["questions"])


def answer(db, oid, n, text):
    qs = db["orders"][oid]["questions"]
    qs[n - 1]["answer"] = text
    qs[n - 1]["answered"] = now()
    db["orders"][oid]["log"].append(f"{now()} 답변 {n}: {text}")


def open_questions(db, oid):
    return [q for q in db["orders"][oid].get("questions", []) if q["answer"] is None]


def verify(db):
    bad = [oid for oid, o in db["orders"].items() if sha(o["original"]) != o["sha256"]]
    return bad


# ───────── 태스크 ─────────
def add_task(db, oid, owner, output, accept, after=(), external=False, channel=None):
    if oid not in db["orders"]:
        raise WFError(f"{oid} 없음")
    if db["orders"][oid]["interpretation"] is None:
        raise WFError("해석(방향 정리) 전에는 분해할 수 없음")
    oq = open_questions(db, oid)
    if oq:
        raise WFError(f"대표 답변 대기 질문 {len(oq)}개 — 임의 결정 금지: {oq[0]['q']}")
    if owner not in roster():
        raise WFError(f"담당 '{owner}'은 역할표에 없음")
    if roster()[owner].get("advice_only"):
        raise WFError("독립검토 역할은 태스크 담당이 될 수 없음(권고만)")
    crit = [c.strip() for c in accept if c.strip()]
    if not crit:
        raise WFError("검수 기준 없이 배정 불가")
    if external and channel not in DAILY_CAP:
        raise WFError(f"외부 업무는 발행 채널 지정 필요: {', '.join(DAILY_CAP)}")
    for a in after:
        if a not in db["tasks"]:
            raise WFError(f"선행 {a} 없음")
    tid = f"T-{len(db['tasks']) + 1:04d}"
    db["tasks"][tid] = {"order": oid, "owner": owner, "output": output, "accept": crit, "accept_locked": True,
                        "after": list(after), "external": external, "channel": channel, "status": "배정", "rejects": 0,
                        "history": [], "advice": [], "log": [f"{now()} 배정 → {owner}"]}
    return tid


def add_criteria(db, tid, crit):
    raise WFError("검수 기준은 배정 때 확정됨 — 추가하려면 새 태스크로 재분해")


def submit(db, tid):
    t = db["tasks"][tid]
    pending = [a for a in t["after"] if db["tasks"][a]["status"] not in ("완료", "대표승인대기")]
    if pending:
        raise WFError(f"선행 미완료: {', '.join(pending)}")
    t["status"] = "제출"
    t["log"].append(f"{now()} 제출")


def _auto_findings(t):
    p = REPO / t["output"]
    if not p.exists():
        return [f"산출물 파일 없음: {t['output']}"]
    head = p.read_text(encoding="utf-8").lstrip().splitlines()[:1]
    if not head or FIRST_LINE not in head[0]:
        return [f"첫 줄에 '{FIRST_LINE}' 요약 없음"]
    return []


def review(db, passes=(), rejects=None, impossible=()):
    """일괄 검수: 제출된 태스크를 한 번에 판정."""
    rejects = dict(rejects or {})
    out = {}
    for tid in list(passes) + list(rejects) + list(impossible):
        if db["tasks"][tid]["status"] != "제출":
            raise WFError(f"{tid}는 제출 상태가 아님({db['tasks'][tid]['status']})")
    for tid in passes:
        auto = _auto_findings(db["tasks"][tid])
        if auto:
            rejects[tid] = "; ".join(auto)
            continue
        t = db["tasks"][tid]
        t["status"] = "대표승인대기" if t["external"] else "완료"
        t["log"].append(f"{now()} 검수 통과")
        out[tid] = t["status"]
    for tid, note in rejects.items():
        t = db["tasks"][tid]
        t["rejects"] += 1
        t["history"].append({"round": t["rejects"], "note": note, "at": now()})
        t["status"] = "대표상신" if t["rejects"] >= MAX_REJECT else "재작업"
        t["log"].append(f"{now()} 반려 {t['rejects']}회: {note}")
        out[tid] = t["status"]
    for tid in impossible:
        t = db["tasks"][tid]
        t["status"] = "재분해"
        t["log"].append(f"{now()} 불가 → 재분해")
        out[tid] = "재분해"
    return out


def advise(db, tid, text):
    t = db["tasks"][tid]
    t["advice"].append({"at": now(), "by": "독립검토", "text": text})  # 상태는 바꾸지 않음


def approve(db, tid):
    t = db["tasks"][tid]
    if t["status"] != "대표승인대기":
        raise WFError(f"{tid}는 승인 대기 상태가 아님({t['status']})")
    t["status"] = "발송대기"
    t["log"].append(f"{now()} 대표 승인 → 발행 큐")


def sent(db, tid):
    """실제로 내보냈음(고객 안내·메일 발송·제출). 확인 전까지 완료가 아님."""
    t = db["tasks"][tid]
    if t["status"] != "발송대기":
        raise WFError(f"{tid}는 승인 전이거나 이미 처리됨({t['status']}) — 승인 없이 나가는 경로 없음")
    today = now()[:10]
    used = sum(1 for x in db["tasks"].values() if x.get("channel") == t["channel"] and x.get("sent_at", "")[:10] == today)
    if used >= DAILY_CAP[t["channel"]]:
        raise WFError(f"{t['channel']} 오늘 상한 {DAILY_CAP[t['channel']]}건 초과")
    t["status"] = "게시확인필요"
    t["sent_at"] = now()
    t["log"].append(f"{now()} 발송")


def confirm(db, tid, evidence, ok=True):
    """나간 뒤 실제 반영 확인(예: 17시 주문현황 발송대기 0). 증거 없으면 완료 불가."""
    t = db["tasks"][tid]
    if t["status"] != "게시확인필요":
        raise WFError(f"{tid}는 확인 단계가 아님({t['status']})")
    if len(evidence.strip()) < 10:
        raise WFError("확인 증거를 10자 이상 적어야 함(무엇으로 확인했는지)")
    t["status"] = "완료" if ok else "실패"
    t["evidence"] = evidence
    t["log"].append(f"{now()} 게시 확인 {'성공' if ok else '실패'}: {evidence}")


def outbox_counts(db):
    c = {s: 0 for s in OUTBOX_STATES}
    for t in db["tasks"].values():
        if t["external"] and t["status"] in c:
            c[t["status"]] += 1
    return c


# ───────── 회사의 기억 ─────────
def load_memory():
    text = (HERE / "memory.md").read_text(encoding="utf-8")
    sec, must, pits = None, [], []
    for line in text.splitlines():
        if line.startswith("## "):
            sec = line[3:].strip()
        elif line.startswith("- ") and sec == "반드시 아는 것":
            must.append(line[2:].strip())
        elif line.startswith("- [") and sec == "밟은 함정":
            body = line[2:]
            tag = body[1:body.index("]")]
            rest = body[body.index("]") + 1:]
            resolved = None
            if rest.startswith("[해소:"):
                resolved = rest[len("[해소:"):rest.index("]")].strip()
                rest = rest[rest.index("]") + 1:]
            pits.append({"tag": tag, "resolved": resolved, "text": rest.strip()})
    return must, pits


def check_memory():
    must, pits = load_memory()
    errs = []
    if len(must) > MAX_MUST_KNOW:
        errs.append(f"반드시 아는 것 {len(must)}개 > {MAX_MUST_KNOW}개 — 내릴 것을 고르십시오")
    errs += [f"해소 설명이 10자 미만: [{p['tag']}] {p['text'][:30]}" for p in pits if p["resolved"] is not None and len(p["resolved"]) < 10]
    return errs


def brief(db, tid):
    t = db["tasks"][tid]
    o = db["orders"][t["order"]]
    must, pits = load_memory()
    topics = set(roster()[t["owner"]].get("topics", []))
    mine = [p for p in pits if p["tag"] in topics and p["resolved"] is None]
    lines = ["## 반드시 아는 것"] + [f"- {m}" for m in must]
    if mine:
        lines += [f"## 이 담당 주제({', '.join(sorted(topics))})의 미해소 함정"] + [f"- [{p['tag']}] {p['text']}" for p in mine]
    lines += ["\n---\n", f"## 지시 {t['order']} 원문(불변)\n{o['original']}\n",
             f"## 해석\n{o['interpretation']}\n",
             "## 대표 확인 답변\n" + ("\n".join(f"- {q['q']} → {q['answer']}" for q in o.get("questions", [])) or "- 없음") + "\n", f"## 태스크 {tid} · 담당 {t['owner']}\n- 산출물: {t['output']}",
             f"- 첫 줄 규칙: '{FIRST_LINE}: …'", "- 검수 기준:"] + [f"  - {c}" for c in t["accept"]]
    if t["history"]:
        lines.append("## 지난 회차 지적(같은 지적 반복 금지)")
        lines += [f"- {h['round']}회차: {h['note']}" for h in t["history"]]
    return "\n".join(lines)


DEPT_ORDER = ["경영기획실", "총무부", "연구개발부", "생산부", "품질관리부", "자재부", "시설부", "마케팅부"]
RANK_POWER = {"실장": "사장 직속 · 가격·원가·투자 기획(승인권 없음)", "대표이사": "외부 발송·제출·투자 최종 승인", "사장": "부서 간 조정·전사 검수", "부장": "부서 내 검수·반려", "대리": "실행·계산·초안(승인권 없음)", "자문": "권고만"}


def org_chart(db):
    """부서·직급 조직도 + 담당별 업무 건수(대표 질문: 총무·마케팅·자재·시설 + 사장·부장·대리)."""
    ro = roster()
    cnt = {k: [0, 0] for k in ro}
    for t in db["tasks"].values():
        if t["owner"] in cnt:
            cnt[t["owner"]][1 if t["status"] == "완료" else 0] += 1
    L = ["대표이사 — 김종환 (사람) · " + RANK_POWER["대표이사"],
         "└─ 사장 — 손사장 (총괄 AI) · " + RANK_POWER["사장"] + "        ◀ 감사·자문: 독립검토(권고만)"]
    for i, d in enumerate(DEPT_ORDER):
        br = "└─" if i == len(DEPT_ORDER) - 1 else "├─"
        L.append(f"     {br} {d}")
        mem = sorted([k for k, v in ro.items() if v.get("dept") == d], key=lambda k: 0 if ro[k]["rank"] == "부장" else 1)
        for k in mem:
            v = ro[k]
            L.append(f"     {'   ' if br == '└─' else '│  '}  · {v['rank']} {v['title']} [{v.get('model','')}] 진행 {cnt[k][0]} · 완료 {cnt[k][1]}")
    n = lambda rk: sum(1 for v in ro.values() if v.get("rank") == rk)
    hum = sum(1 for v in ro.values() if v.get("rank") == "부장" and v.get("human"))
    L.append(f"합계: 대표이사 1 · 사장 1 · 실장 {n('실장')} · 부장 {n('부장')}(대표 겸임 {hum}) · 대리 {n('대리')} · 자문 1 · 부서 {len(DEPT_ORDER)}")
    return "\n".join(L)


def route_text(text: str) -> list[tuple[str, int]]:
    """대표가 말한 문장 → 담당 후보(키워드 일치 수 순). 일치 없으면 손사장."""
    ro = roster()
    hits = [(k, sum(1 for kw in v.get("keywords", []) if kw.lower() in text.lower())) for k, v in ro.items()]
    hits = sorted([h for h in hits if h[1] > 0], key=lambda h: -h[1])
    return hits or [("손사장", 0)]


def say(db, text: str) -> dict:
    """'내가 이야기하면 바로 연결': 원문 봉인 → 담당 자동 배정. 담당이 여럿이면 각자 1건씩."""
    oid = new_order(db, text)
    owners = [k for k, _ in route_text(text)][:3]
    interpret(db, oid, f"자동 접수: 키워드로 {', '.join(roster()[o]['title'] for o in owners)}에게 배정. 손사장이 검토해 범위를 고친다.")
    tids = [add_task(db, oid, o, "ops/reports", [f"대표 말씀 처리: {text[:60]}", "처리 결과 또는 대표 확인 질문을 산출물로 남길 것"]) for o in owners]
    return {"order": oid, "owners": owners, "tasks": tids}


def status_table(db):
    rows = ["| 태스크 | 지시 | 담당 | 상태 | 반려 | 외부 | 산출물 |", "|---|---|---|---|---:|:-:|---|"]
    for tid, t in db["tasks"].items():
        rows.append(f"| {tid} | {t['order']} | {t['owner']} | {t['status']} | {t['rejects']} | {'Y' if t['external'] else ''} | {t['output']} |")
    return "\n".join(rows)


def main(argv=None):
    ap = argparse.ArgumentParser()
    sp = ap.add_subparsers(dest="cmd", required=True)
    p = sp.add_parser("new"); p.add_argument("text"); p.add_argument("--depth", default="생략", choices=["생략", "심도차등", "전원깊게"])
    p = sp.add_parser("interpret"); p.add_argument("oid"); p.add_argument("text")
    p = sp.add_parser("task"); p.add_argument("oid"); p.add_argument("--owner", required=True); p.add_argument("--output", required=True)
    p.add_argument("--accept", required=True); p.add_argument("--after", nargs="*", default=[]); p.add_argument("--external", action="store_true")
    p.add_argument("--channel", choices=list(DAILY_CAP))
    p = sp.add_parser("submit"); p.add_argument("tid")
    p = sp.add_parser("review"); p.add_argument("--pass", dest="passes", nargs="*", default=[])
    p.add_argument("--reject", nargs="*", default=[], help='T-0001="지적"'); p.add_argument("--impossible", nargs="*", default=[])
    p = sp.add_parser("advise"); p.add_argument("tid"); p.add_argument("text")
    p = sp.add_parser("approve"); p.add_argument("tid")
    p = sp.add_parser("sent"); p.add_argument("tid")
    p = sp.add_parser("confirm"); p.add_argument("tid"); p.add_argument("evidence"); p.add_argument("--fail", action="store_true")
    p = sp.add_parser("brief"); p.add_argument("tid")
    sp.add_parser("outbox"); sp.add_parser("memcheck")
    p = sp.add_parser("ask"); p.add_argument("oid"); p.add_argument("q"); p.add_argument("--options", nargs="*", default=[])
    p = sp.add_parser("answer"); p.add_argument("oid"); p.add_argument("n", type=int); p.add_argument("text")
    sp.add_parser("verify"); sp.add_parser("status"); sp.add_parser("org")
    p = sp.add_parser("say"); p.add_argument("text")
    a = ap.parse_args(argv)
    db = load()
    try:
        if a.cmd == "new":
            print(new_order(db, a.text, a.depth))
        elif a.cmd == "interpret":
            interpret(db, a.oid, a.text)
        elif a.cmd == "task":
            print(add_task(db, a.oid, a.owner, a.output, a.accept.split(";"), a.after, a.external, a.channel))
        elif a.cmd == "ask":
            print(ask(db, a.oid, a.q, a.options))
        elif a.cmd == "answer":
            answer(db, a.oid, a.n, a.text)
        elif a.cmd == "submit":
            submit(db, a.tid)
        elif a.cmd == "review":
            rj = dict(x.split("=", 1) for x in a.reject)
            print(json.dumps(review(db, a.passes, rj, a.impossible), ensure_ascii=False))
        elif a.cmd == "advise":
            advise(db, a.tid, a.text)
        elif a.cmd == "approve":
            approve(db, a.tid)
        elif a.cmd == "sent":
            sent(db, a.tid)
        elif a.cmd == "confirm":
            confirm(db, a.tid, a.evidence, not a.fail)
        elif a.cmd == "outbox":
            print(" · ".join(f"{k} {v}" for k, v in outbox_counts(db).items())); return 0
        elif a.cmd == "memcheck":
            errs = check_memory(); print("\n".join(errs) or "회사의 기억 규칙 통과"); return 1 if errs else 0
        elif a.cmd == "brief":
            print(brief(db, a.tid)); return 0
        elif a.cmd == "verify":
            bad = verify(db)
            print("원문 무결" if not bad else f"원문 변경 감지: {bad}")
            return 1 if bad else 0
        elif a.cmd == "say":
            r = say(db, a.text)
            print(f"{r['order']} 접수 → " + ", ".join(f"{roster()[o]['title']}({t})" for o, t in zip(r['owners'], r['tasks'])))
        elif a.cmd == "org":
            print(org_chart(db)); return 0
        elif a.cmd == "status":
            print(status_table(db)); return 0
    except WFError as e:
        print(f"거부: {e}", file=sys.stderr)
        return 2
    save(db)
    return 0


if __name__ == "__main__":
    sys.exit(main())
