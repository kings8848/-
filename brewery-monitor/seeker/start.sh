#!/data/data/com.termux/files/usr/bin/bash
# Termux에서 업로더를 화면 꺼져도 계속 돌게 실행
# Termux:Boot 앱을 쓰면 ~/.termux/boot/ 에 이 파일을 복사해 재부팅 후 자동 시작
termux-wake-lock
cd "$(dirname "$0")"
while true; do
  python uploader.py >> uploader.log 2>&1
  echo "[$(date '+%m-%d %H:%M:%S')] 업로더 종료됨, 10초 후 재시작" >> uploader.log
  sleep 10
done
