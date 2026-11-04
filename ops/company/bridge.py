#!/usr/bin/env python3
"""자동화 계층 → 총괄 계층 연결 (대표 지시 D-0004: 두 계층 분업)

자동화 계층(kings_ops·connectors)은 **계산과 경보만** 한다 — 판단·승인 없음, 토큰 0.
총괄 계층(workflow·손사장)은 **경보를 업무로 받아 배정·검수·승인**한다 — 계산하지 않음.
둘 사이 계약은 하나: reports/역량평가_YYYYMMDD.json 의 findings.

  python3 ops/company/bridge.py            # 최신 경보 → 상시 지시 D-AUTO 아래 태스크 생성/해소
"""
from __future__ import annotations

import glob
import hashlib
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import workflow as wf  # noqa: E402

REPORTS = Path(os.environ.get("KINGS_OPS_REPORTS", HERE.parent / "reports"))
MAP = Path(os.environ.get("KINGS_BRIDGE_STATE", HERE.parent / "state" / "bridge.json"))
STANDING = "[상시] 자동화 계층 경보 수신 — 긴급·경고·확인 경보를 담당 업무로 받는다"
# 경보 영역 → 담당·외부채널(외부로 나가는 조치만)
ROUTE = [("출고", "출고재고", "고객안내"), ("정산·세무", "컴플라이언스", "메일"), ("정산", "정산원가", None),
         ("배치", "제조기록", None), ("재고", "출고재고", None), ("매출", "정산원가", None),
         ("연결", "손사장", None), ("성과", "손사장", None)]


def key(f: dict) -> str:
    # 숫자(일수·건수)가 바뀌어도 같은 경보로 본다: 영역+조치 기준
    return hashlib.sha256(f"{f['area']}|{f['action']}".encode()).hexdigest()[:12]


def route(area: str):
    for prefix, owner, ch in ROUTE:
        if area.startswith(prefix):
            return owner, ch
    return "손사장", None


def latest_findings() -> tuple[str, list[dict]]:
    files = sorted(glob.glob(str(REPORTS / "역량평가_*.json")))
    if not files:
        return "", []
    data = json.loads(Path(files[-1]).read_text(encoding="utf-8"))
    return files[-1], [f for f in data["findings"] if f["level"] in ("긴급", "경고", "확인") and f["action"]]


def run(db: dict) -> dict:
    src, findings = latest_findings()
    m = json.loads(MAP.read_text(encoding="utf-8")) if MAP.exists() else {"order": None, "tasks": {}}
    if not m["order"] or m["order"] not in db["orders"]:
        oid = wf.new_order(db, STANDING)
        wf.interpret(db, oid, "자동화 계층이 낸 경보마다 태스크 1개. 조치가 끝나 다음 실행에서 경보가 사라지면 해소 기록 후 완료.")
        m["order"] = oid
    oid = m["order"]
    now_keys, created, closed = set(), [], []
    for f in findings:
        k = key(f)
        now_keys.add(k)
        if k in m["tasks"] and m["tasks"][k] in db["tasks"]:
            continue
        owner, ch = route(f["area"])
        external = ch is not None and f["level"] == "긴급"
        tid = wf.add_task(db, oid, owner, os.path.relpath(src, wf.REPO) if src else "ops/reports",
                          [f"[{f['level']}] {f['msg'][:120]}", f"조치: {f['action']}", "다음 실행에서 이 경보가 사라질 것"],
                          external=external, channel=ch if external else None)
        db["tasks"][tid]["finding"] = f
        m["tasks"][k] = tid
        created.append(tid)
    for k, tid in m["tasks"].items():
        t = db["tasks"].get(tid)
        if t and k not in now_keys and t["status"] in ("배정", "재작업"):
            t["status"] = "완료"
            t["evidence"] = f"자동화 계층 최신 실행({Path(src).name})에서 경보 사라짐"
            t["log"].append(f"{wf.now()} 경보 해소 → 완료")
            closed.append(tid)
    MAP.parent.mkdir(parents=True, exist_ok=True)
    MAP.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"order": oid, "created": created, "closed": closed, "open": len(now_keys)}


def main():
    db = wf.load()
    r = run(db)
    wf.save(db)
    print(f"{r['order']}: 신규 {len(r['created'])}건 {r['created']} · 해소 {len(r['closed'])}건 · 현재 경보 {r['open']}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
