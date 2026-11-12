#!/usr/bin/env python3
"""
킹스양조장 제어판 캡처 업로더 (Seeker / Termux 용)

MacroDroid가 저장한 GiGAeyes 화면 캡처를 묶어서 Apps Script 웹앱으로 보낸다.
- 몇 초 간격으로 찍힌 캡처(기본 3장)를 한 묶음으로 전송 → AI가 장끼리 비교해 판독
- Pillow가 있으면 JPEG로 줄이고 제어판 부분만 잘라서 전송(정확도↑, 비용↓)
- 전송 성공 파일은 sent/ 로 옮기고 하루 지나면 삭제

실행:  python uploader.py          (계속 감시)
시험:  python uploader.py --once   (한 번만 처리하고 종료)
"""
import base64
import io
import json
import os
import shutil
import sys
import time
import urllib.request
from datetime import datetime, timezone

# ───────── 설정: 이 부분만 고치면 됩니다 ─────────
WATCH_DIR = "/sdcard/KingsPanel"          # MacroDroid 캡처 저장 폴더
ENDPOINT = "https://script.google.com/macros/s/여기에_웹앱_ID/exec"
UPLOAD_TOKEN = "여기에_Apps_Script와_같은_비밀문자열"
GROUP_GAP_SEC = 30        # 이 간격 안에 찍힌 캡처는 한 묶음
SETTLE_SEC = 15           # 마지막 캡처 후 이만큼 기다렸다가 전송(묶음 완성 대기)
MAX_PER_GROUP = 3         # 묶음당 최대 장수
POLL_SEC = 20             # 폴더 확인 주기
# 제어판 부분만 자르기(비율, 0~1): (왼쪽, 위, 오른쪽, 아래). 안 자르려면 None
CROP = None               # 예: (0.20, 0.05, 0.80, 0.95)
MAX_EDGE = 1568           # 긴 변 픽셀(이보다 크면 축소)
# ─────────────────────────────────────────

SENT_DIR = os.path.join(WATCH_DIR, "sent")
EXTS = (".png", ".jpg", ".jpeg")

try:
    from PIL import Image
except ImportError:  # Pillow 없으면 원본 전송
    Image = None


def log(msg):
    print(f"[{datetime.now():%m-%d %H:%M:%S}] {msg}", flush=True)


def list_images():
    if not os.path.isdir(WATCH_DIR):
        return []
    files = []
    for name in os.listdir(WATCH_DIR):
        path = os.path.join(WATCH_DIR, name)
        if os.path.isfile(path) and name.lower().endswith(EXTS):
            files.append((os.path.getmtime(path), path))
    return sorted(files)


def group_files(files, now):
    """mtime 기준으로 묶고, 마지막 캡처 후 SETTLE_SEC 지난 묶음만 돌려준다."""
    groups, cur = [], []
    for mtime, path in files:
        if cur and mtime - cur[-1][0] > GROUP_GAP_SEC:
            groups.append(cur)
            cur = []
        cur.append((mtime, path))
    if cur:
        groups.append(cur)
    return [g for g in groups if now - g[-1][0] >= SETTLE_SEC]


def encode(path):
    if Image is None:
        mime = "image/png" if path.lower().endswith(".png") else "image/jpeg"
        with open(path, "rb") as f:
            data = f.read()
        if len(data) > 3_500_000:
            log(f"경고: {os.path.basename(path)} 용량 큼({len(data)//1024}KB). 'pkg install python-pillow' 권장")
        return {"name": os.path.basename(path), "mime": mime, "data": base64.b64encode(data).decode()}

    img = Image.open(path).convert("RGB")
    if CROP:
        w, h = img.size
        l, t, r, b = CROP
        img = img.crop((int(w * l), int(h * t), int(w * r), int(h * b)))
    img.thumbnail((MAX_EDGE, MAX_EDGE))
    buf = io.BytesIO()
    img.save(buf, "JPEG", quality=90)
    return {"name": os.path.basename(path), "mime": "image/jpeg", "data": base64.b64encode(buf.getvalue()).decode()}


def upload(group):
    picks = group[-MAX_PER_GROUP:]
    captured = datetime.fromtimestamp(picks[0][0], tz=timezone.utc).isoformat()
    body = json.dumps({
        "token": UPLOAD_TOKEN,
        "captured_at": captured,
        "images": [encode(p) for _, p in picks],
    }).encode()
    req = urllib.request.Request(ENDPOINT, data=body, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as res:  # Apps Script는 리다이렉트 후 응답
        result = json.loads(res.read().decode())
    if not result.get("ok"):
        raise RuntimeError(result.get("error"))
    return result


def move_sent(group):
    os.makedirs(SENT_DIR, exist_ok=True)
    for _, path in group:
        shutil.move(path, os.path.join(SENT_DIR, os.path.basename(path)))


def prune_sent(max_age_sec=86400):
    if not os.path.isdir(SENT_DIR):
        return
    cutoff = time.time() - max_age_sec
    for name in os.listdir(SENT_DIR):
        path = os.path.join(SENT_DIR, name)
        if os.path.getmtime(path) < cutoff:
            os.remove(path)


def process_once():
    groups = group_files(list_images(), time.time())
    if len(groups) > 3:  # 오래 끊겼다가 쌓였으면 최신 것만 보내고 나머지는 보관
        log(f"밀린 묶음 {len(groups) - 1}개는 전송 생략(sent/로 이동)")
        for g in groups[:-1]:
            move_sent(g)
        groups = groups[-1:]
    for g in groups:
        try:
            r = upload(g)
            log(f"전송 OK: {len(g)}장 → 기록 {r.get('rows')}줄, 경보 {r.get('alarms')}건")
            move_sent(g)
        except Exception as e:  # 실패 시 파일 그대로 두고 다음 주기에 재시도
            log(f"전송 실패(다음에 재시도): {e}")
            break
    prune_sent()


def main():
    if "여기에" in ENDPOINT or "여기에" in UPLOAD_TOKEN:
        sys.exit("uploader.py 맨 위의 ENDPOINT와 UPLOAD_TOKEN을 먼저 입력하세요.")
    log(f"감시 시작: {WATCH_DIR} (Pillow {'사용' if Image else '없음'})")
    if "--once" in sys.argv:
        process_once()
        return
    while True:
        process_once()
        time.sleep(POLL_SEC)


if __name__ == "__main__":
    main()
