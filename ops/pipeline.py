#!/usr/bin/env python3
"""킹스 3층 파이프라인 — 한 번 실행으로 전 과정: 수집·대사(kings_ops) → 가치사슬(value_chain) → 경보→업무(bridge) → 아침 보고

PC 작업 스케줄러(매일 07:30)나 메일 도착 트리거에 이 한 줄만 걸면 '24시간 데이터 흐름'이 된다(n8n·Make 없이 비용 0).
  python3 ops/pipeline.py [--trigger scheduled|manual]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

OPS = Path(__file__).resolve().parent
KST = timezone(timedelta(hours=9))
STEPS_OVERRIDE = None  # 시험용
STEPS = [("수집·대사·경보", ["kings_ops.py", "run"]), ("전사 가치사슬", ["enterprise/value_chain.py"]), ("B2B 영업", ["sales/b2b.py"]), ("6차 산업 계기판", ["marketing/six_industry.py"]), ("경보→담당 업무", ["company/bridge.py"]), ("통합 대시보드", ["cockpit.py"])]


STEP_TIMEOUT = int(os.environ.get("KINGS_STEP_TIMEOUT", "300"))


def error_workflow(step: str, code: int, detail: str, trigger: str) -> Path:
    """에러 워크플로우: 실패 단계·원인을 긴급 보고서로 남기고 실행 기록에 실패를 적는다.
    대표 휴대폰 알림 채널은 대표 결정 대기(D-0011) — 정해지면 여기에 연결."""
    rep = OPS / "reports"; rep.mkdir(exist_ok=True)
    p = rep / f"오류_{datetime.now(KST):%Y%m%d_%H%M%S}.md"
    p.write_text(f"이 문서에서 알 수 있는 것: 파이프라인 '{step}' 단계 실패(코드 {code}) — 이후 단계 중단, 대표 확인 필요\n\n"
                 f"# 파이프라인 오류\n\n- 시각: {datetime.now(KST):%Y-%m-%d %H:%M} · 트리거 {trigger}\n- 단계: {step}\n- 코드: {code}\n\n```\n{(detail or '')[-2000:]}\n```\n"
                 "\n## 손사장 조치\n- 원인 확인 → 수정 → 재실행. 데이터는 멱등 적재라 재실행해도 중복 없음\n", encoding="utf-8")
    (OPS / "state").mkdir(exist_ok=True)
    with (OPS / "state" / "pipeline_errors.jsonl").open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": datetime.now(KST).isoformat(timespec="seconds"), "step": step, "code": code, "report": p.name}, ensure_ascii=False) + "\n")
    try:
        sys.path.insert(0, str(OPS / "connectors")); from kakao_notify import notify
        notify(f"파이프라인 '{step}' 단계 실패(코드 {code}). 보고서 {p.name}", level="오류")
    except Exception:
        pass
    return p


def first_line(p: Path) -> str:
    return p.read_text(encoding="utf-8").splitlines()[0] if p.exists() else "(보고서 없음)"


def leverage(orders_path: Path) -> dict:
    """지능 레버리지: 자동으로 처리된 업무 비율, 대표 손이 필요한 건수."""
    if not orders_path.exists():
        return {}
    db = json.loads(orders_path.read_text(encoding="utf-8"))
    tasks = db["tasks"].values()
    done = [t for t in tasks if t["status"] == "완료"]
    auto_closed = [t for t in done if "경보 사라짐" in t.get("evidence", "")]
    ceo = [t for t in tasks if t["status"] in ("대표승인대기", "대표상신")]
    ceo_q = sum(1 for o in db["orders"].values() for q in o.get("questions", []) if q["answer"] is None)
    return {"tasks": len(list(db["tasks"])), "done": len(done), "auto_closed": len(auto_closed),
            "ceo_pending": len(ceo) + ceo_q, "ceo_questions": ceo_q}


def main(argv=None):
    ap = argparse.ArgumentParser(); ap.add_argument("--trigger", default="manual", choices=["manual", "scheduled"])
    a = ap.parse_args(argv)
    t0 = time.perf_counter(); log = []
    for name, cmd in STEPS_OVERRIDE or STEPS:
        args = [sys.executable, str(OPS / cmd[0]), *cmd[1:]] + (["--trigger", a.trigger] if cmd[0] == "kings_ops.py" else [])
        try:
            r = subprocess.run(args, capture_output=True, text=True, timeout=STEP_TIMEOUT)
            code, out = r.returncode, (r.stdout or r.stderr).strip().splitlines()[-1:] or [""]
        except subprocess.TimeoutExpired:
            code, out = 124, [f"{STEP_TIMEOUT}초 시간 초과"]
        log.append((name, code, out))
        if code != 0:
            error_workflow(name, code, (r.stderr if code != 124 else out[0]) if code != 124 else out[0], a.trigger)
            break
    day = datetime.now(KST).strftime("%Y%m%d")
    rep = OPS / "reports"
    lv = leverage(OPS / "state" / "orders.json")
    ok = all(c == 0 for _, c, _ in log)
    L = [f"이 문서에서 알 수 있는 것: 오늘 아침 킹스 파이프라인 {'정상' if ok else '중단'} · 대표 확인 필요 {lv.get('ceo_pending','?')}건 · 소요 {time.perf_counter()-t0:.1f}초\n",
         f"# 킹스 아침 보고 ({datetime.now(KST):%Y-%m-%d %H:%M} KST · {a.trigger})\n",
         "## 단계별 실행", *[f"- {'✅' if c == 0 else '❌'} {n}: {o[0]}" for n, c, o in log],
         "\n## 보고서 첫 줄",
         f"- 운영검증: {first_line(rep / f'운영검증_보고서_{day}.md')}",
         f"- 전사 가치사슬: {first_line(rep / f'전사_가치사슬_{day}.md')}",
         f"- 6차 산업: {first_line(rep / '6차산업_계기판.md')}",
         "\n## 지능 레버리지 (사람 1명이 시스템으로 처리한 양)",
         f"- 전체 업무 {lv.get('tasks',0)}건 · 완료 {lv.get('done',0)}건 · 경보 해소로 자동 완료 {lv.get('auto_closed',0)}건",
         f"- 대표 손이 필요한 것: 승인·상신 {lv.get('ceo_pending',0)-lv.get('ceo_questions',0)}건 + 답변 대기 질문 {lv.get('ceo_questions',0)}건"]
    (rep / f"아침보고_{day}.md").write_text("\n".join(L) + "\n", encoding="utf-8")
    if ok and lv.get("ceo_pending"):
        try:
            sys.path.insert(0, str(OPS / "connectors")); from kakao_notify import notify
            notify(f"아침 보고: 대표 확인 필요 {lv['ceo_pending']}건. 아침보고_{day}.md", level="승인요청")
        except Exception:
            pass
    print(L[0])
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
