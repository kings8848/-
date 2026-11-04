#!/usr/bin/env python3
"""카카오톡 '나에게 보내기' 알림 (대표 결정 D-0011-1: 카카오톡)

용도: 파이프라인 오류 · 대표 승인 요청 · 긴급 경보를 대표 휴대폰으로.
상태: **실서버 미검증** — 대표님이 카카오 개발자 앱을 만들고 토큰을 .env에 넣은 뒤 첫 실행에서 검증.

필요한 값(.env, set_secret.py로 입력):
  KAKAO_REST_API_KEY   카카오 개발자 > 내 애플리케이션 > 앱 키 > REST API 키
  KAKAO_REFRESH_TOKEN  최초 1회 로그인 동의(talk_message 권한)로 받은 리프레시 토큰
흐름: 리프레시 토큰 → 액세스 토큰(POST kauth.kakao.com/oauth/token) → 메시지(POST kapi.kakao.com/v2/api/talk/memo/default/send)

  python3 ops/connectors/kakao_notify.py "테스트 알림"
설정 전에는 보내지 않고 state/notify_outbox.jsonl 에만 적는다(알림 유실 방지).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
OPS = HERE.parent
sys.path.insert(0, str(HERE))
from smartstore_api import load_env  # noqa: E402

KST = timezone(timedelta(hours=9))
QUEUE = Path(os.environ.get("KINGS_NOTIFY_QUEUE", OPS / "state" / "notify_outbox.jsonl"))
TOKEN_URL = "https://kauth.kakao.com/oauth/token"
SEND_URL = "https://kapi.kakao.com/v2/api/talk/memo/default/send"


def _queue(level: str, text: str, status: str) -> None:
    QUEUE.parent.mkdir(parents=True, exist_ok=True)
    with QUEUE.open("a", encoding="utf-8") as f:
        f.write(json.dumps({"at": datetime.now(KST).isoformat(timespec="seconds"), "level": level, "text": text, "status": status}, ensure_ascii=False) + "\n")


def notify(text: str, level: str = "알림", link: str = "https://claude.ai", session=None) -> str:
    """보낸 결과: sent / queued(미설정) / failed. 실패해도 예외를 던지지 않는다(알림이 파이프라인을 멈추면 안 됨)."""
    env = load_env()
    key, refresh = env.get("KAKAO_REST_API_KEY"), env.get("KAKAO_REFRESH_TOKEN")
    msg = f"[킹스 {level}] {text}"[:200]
    if not key or not refresh:
        _queue(level, msg, "queued")
        return "queued"
    try:
        import requests
        s = session or requests
        tok = s.post(TOKEN_URL, data={"grant_type": "refresh_token", "client_id": key, "refresh_token": refresh}, timeout=15)
        tok.raise_for_status()
        access = tok.json()["access_token"]
        tmpl = {"object_type": "text", "text": msg, "link": {"web_url": link, "mobile_web_url": link}}
        r = s.post(SEND_URL, headers={"Authorization": f"Bearer {access}"}, data={"template_object": json.dumps(tmpl, ensure_ascii=False)}, timeout=15)
        r.raise_for_status()
        _queue(level, msg, "sent")
        return "sent"
    except Exception as e:  # noqa: BLE001
        _queue(level, f"{msg} (전송 실패: {type(e).__name__})", "failed")
        return "failed"


if __name__ == "__main__":
    print(notify(" ".join(sys.argv[1:]) or "킹스 알림 시험"))
