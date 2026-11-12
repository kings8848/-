"""업로더 묶음·인코딩 테스트: python tests/test_uploader.py"""
import base64
import importlib.util
import io
import os
import tempfile

spec = importlib.util.spec_from_file_location("uploader", os.path.join(os.path.dirname(__file__), "..", "seeker", "uploader.py"))
up = importlib.util.module_from_spec(spec)
spec.loader.exec_module(up)

# 묶음: 3장(3초 간격) + 10분 뒤 3장, 마지막 묶음은 아직 진행 중
now = 10_000.0
files = [(1000, "a1"), (1003, "a2"), (1006, "a3"), (1600, "b1"), (1603, "b2"), (now - 5, "c1")]
groups = up.group_files(files, now)
assert [[p for _, p in g] for g in groups] == [["a1", "a2", "a3"], ["b1", "b2"]], groups
print("✓ 캡처 묶음 분리, 진행 중 묶음 대기")

# 인코딩: 큰 PNG → 긴 변 1568 JPEG, 자르기
if up.Image:
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, "s.png")
        up.Image.new("RGB", (2400, 1080), (30, 30, 30)).save(p)
        up.CROP = (0.2, 0.0, 0.8, 1.0)
        enc = up.encode(p)
        img = up.Image.open(io.BytesIO(base64.b64decode(enc["data"])))
        assert enc["mime"] == "image/jpeg" and img.size == (1440, 1080), img.size
        print("✓ 제어판 영역 자르기 + JPEG 변환", img.size)
else:
    print("- Pillow 없음: 인코딩 테스트 생략")
print("\n모든 테스트 통과")
