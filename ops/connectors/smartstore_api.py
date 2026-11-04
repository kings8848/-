#!/usr/bin/env python3
"""스마트스토어 커머스API 연결기 (대표 결정 D-0003-2: 커머스API 연동)

상태: **실서버 미검증.** 대표님이 커머스API센터에서 애플리케이션을 등록하고 ID/시크릿을
     PC의 ops/.env 에 넣은 뒤 첫 실행에서 검증한다. 시크릿은 저장소에 올리지 않는다(.gitignore).

인증(공식 GitHub 토론·공개 클라이언트로 교차 확인한 구조)
  client_secret_sign = base64( bcrypt.hashpw(f"{client_id}_{timestamp_ms}", salt=client_secret) )
  POST https://api.commerce.naver.com/external/v1/oauth2/token
       client_id, timestamp, client_secret_sign, grant_type=client_credentials, type=SELF
주문
  GET  /external/v1/pay-order/seller/product-orders/last-changed-statuses?lastChangedFrom=…&lastChangedTo=…
  (상태가 서로 다르면 '상품 주문 상세 내역 조회' 값을 우선 — 공식 토론 #2437)

결과는 ops/data/smartstore_orders_api.csv 에 상품주문번호+최종변경일시 기준으로 중복 없이 쌓는다.

  python3 ops/connectors/smartstore_api.py --days 3          # 실호출
  python3 ops/connectors/smartstore_api.py --fixture 파일.json # 저장된 응답으로 시험
"""
from __future__ import annotations

import argparse
import base64
import csv
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OPS = HERE.parent
OUT = Path(os.environ.get("KINGS_OPS_DATA", OPS / "data")) / "smartstore_orders_api.csv"
BASE = "https://api.commerce.naver.com/external"
KST = timezone(timedelta(hours=9))
FIELDS = ["product_order_id", "order_id", "status", "last_changed_type", "last_changed", "pulled_at"]
# 발송 전 상태(결제완료 = 발송대기). 공식 상태 정의로 첫 실행 때 재확인.
AWAITING = {"PAYED"}


def load_env(path: Path = OPS / ".env") -> dict:
    env = dict(os.environ)
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                env.setdefault(k.strip(), v.strip().strip("'\""))
    return env


def sign(client_id: str, client_secret: str, timestamp_ms: int) -> str:
    import bcrypt  # PC: pip install bcrypt
    hashed = bcrypt.hashpw(f"{client_id}_{timestamp_ms}".encode(), client_secret.encode())
    return base64.b64encode(hashed).decode()


def get_token(client_id: str, client_secret: str, session=None) -> str:
    import requests
    s = session or requests
    ts = int(time.time() * 1000) - 3000  # 서버 시각보다 앞서지 않게 3초 여유(공개 예제 관행)
    r = s.post(f"{BASE}/v1/oauth2/token", data={
        "client_id": client_id, "timestamp": ts, "client_secret_sign": sign(client_id, client_secret, ts),
        "grant_type": "client_credentials", "type": "SELF"}, timeout=20)
    r.raise_for_status()
    return r.json()["access_token"]


def fetch_changed(token: str, since: datetime, until: datetime, session=None) -> list[dict]:
    import requests
    s = session or requests
    rows, cur = [], since
    while cur < until:  # 조회 구간은 24시간 단위로 끊어서 요청
        end = min(cur + timedelta(hours=24), until)
        r = s.get(f"{BASE}/v1/pay-order/seller/product-orders/last-changed-statuses",
                  params={"lastChangedFrom": cur.isoformat(timespec="milliseconds"),
                          "lastChangedTo": end.isoformat(timespec="milliseconds")},
                  headers={"Authorization": f"Bearer {token}"}, timeout=20)
        r.raise_for_status()
        rows += (r.json().get("data") or {}).get("lastChangeStatuses", [])
        cur = end
    return rows


def normalize(raw: list[dict]) -> list[dict]:
    now = datetime.now(KST).isoformat(timespec="seconds")
    return [{"product_order_id": str(x.get("productOrderId", "")), "order_id": str(x.get("orderId", "")),
             "status": x.get("productOrderStatus", ""), "last_changed_type": x.get("lastChangedType", ""),
             "last_changed": x.get("lastChangedDate", ""), "pulled_at": now} for x in raw if x.get("productOrderId")]


def upsert(rows: list[dict], path: Path = OUT) -> tuple[int, int]:
    old = list(csv.DictReader(path.open(encoding="utf-8"))) if path.exists() else []
    seen = {(r["product_order_id"], r["last_changed"]) for r in old}
    new = [r for r in rows if (r["product_order_id"], r["last_changed"]) not in seen]
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS)
        w.writeheader()
        w.writerows(old + new)
    return len(new), len(old) + len(new)


def latest_status(path: Path = OUT) -> dict[str, dict]:
    """상품주문별 최신 상태 1건."""
    if not path.exists():
        return {}
    cur: dict[str, dict] = {}
    for r in csv.DictReader(path.open(encoding="utf-8")):
        if r["product_order_id"] not in cur or r["last_changed"] > cur[r["product_order_id"]]["last_changed"]:
            cur[r["product_order_id"]] = r
    return cur


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=3)
    ap.add_argument("--fixture", help="저장된 API 응답 JSON(시험용)")
    a = ap.parse_args(argv)
    if a.fixture:
        raw = json.loads(Path(a.fixture).read_text(encoding="utf-8"))["data"]["lastChangeStatuses"]
    else:
        env = load_env()
        cid, sec = env.get("NAVER_COMMERCE_CLIENT_ID"), env.get("NAVER_COMMERCE_CLIENT_SECRET")
        if not cid or not sec:
            print("거부: ops/.env 에 NAVER_COMMERCE_CLIENT_ID / NAVER_COMMERCE_CLIENT_SECRET 없음 (대표_작업공간_설정안내 5단계)", file=sys.stderr)
            return 2
        tok = get_token(cid, sec)
        until = datetime.now(KST)
        raw = fetch_changed(tok, until - timedelta(days=a.days), until)
    added, total = upsert(normalize(raw))
    print(f"스마트스토어 API: 신규 {added}건 · 누적 {total}건")
    return 0


if __name__ == "__main__":
    sys.exit(main())
