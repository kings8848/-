#!/usr/bin/env python3
"""비밀값(.env) 입력기 — 영상 'set-secret' 방식. 입력한 글자는 화면에 보이지 않고, AI·채팅을 거치지 않는다.

대표님 PC 코드 탭/터미널에서:
  python ops/scripts/set_secret.py NAVER_COMMERCE_CLIENT_SECRET
"""
import getpass, sys
from pathlib import Path

ENV = Path(__file__).resolve().parents[1] / ".env"
ALLOWED = {"NAVER_COMMERCE_CLIENT_ID", "NAVER_COMMERCE_CLIENT_SECRET", "THREADS_APP_ID", "THREADS_APP_SECRET", "KAKAO_REST_API_KEY", "KAKAO_REFRESH_TOKEN"}


def set_secret(name: str, value: str, env: Path = ENV) -> None:
    if name not in ALLOWED:
        raise SystemExit(f"거부: 허용된 이름만 저장합니다 {sorted(ALLOWED)}")
    if not value.strip():
        raise SystemExit("거부: 빈 값")
    lines = [l for l in (env.read_text(encoding="utf-8").splitlines() if env.exists() else []) if not l.startswith(name + "=")]
    lines.append(f"{name}='{value.strip()}'")
    env.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("사용법: python ops/scripts/set_secret.py 이름")
    v = getpass.getpass(f"{sys.argv[1]} 값을 붙여넣고 Enter (화면에 안 보이는 게 정상): ")
    set_secret(sys.argv[1], v)
    print(f"저장됨: ops/.env 의 {sys.argv[1]} (값은 표시하지 않음)")
