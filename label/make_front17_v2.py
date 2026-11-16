#!/usr/bin/env python3
"""금배주 17도 앞면 품질 보강판 (디자이너 PDF 기반, 60×155mm + 사방 2mm 재단 여유).

실행: python3 label/make_front17_v2.py
입력: label/금배주_2027/원본/앞면_17_디자이너_60x155.pdf, 낙관.webp
출력: label/금배주_2027/앞면_17_v2/

원본 대비 바꾸는 것
- 글자 뒤 회색 그림자·흰 테두리 제거 (25도처럼 깨끗한 먹색 글자)
- 위쪽 둥근 배, 오른쪽 산을 따뜻한 노랑·주황으로, 왼쪽 돌을 갈색으로
- 금색 점 추가, 낙관 추가
- "ALC. 17% VOL" 을 지우고 25도처럼 왼쪽 아래 "17%", 오른쪽 아래 "375ml"
"""
import base64
import pathlib
import random
import re
import subprocess
import tempfile

import cv2
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "금배주_2027" / "원본"
OUT = ROOT / "금배주_2027" / "앞면_17_v2"
FONTS = ROOT / "fonts"
PW, PH = 181.417323, 450.708661           # 쪽 크기(pt) = 64×159mm
SCALE = 1512 / PW                         # 배경 렌더링 배율(약 600dpi)
INK = "rgb(13.725281%, 12.156677%, 12.548828%)"
SHADOW = ("rgb(55.685425%, 58.430481%, 61.175537%)", "rgb(100%, 100%, 100%)")
PAPER = "rgb(94.900513%, 92.155457%, 86.273193%)"
TEXT_BOXES = [(75, 345, 108, 368), (33, 383, 148, 401), (106, 412, 162, 418), (128, 423, 162, 432)]
ALC_BOX = TEXT_BOXES[2]


def bbox(tag):
    n = [float(x) for x in re.findall(r"-?\d+\.?\d*", re.search(r' d="([^"]+)"', tag).group(1))]
    return min(n[0::2]), min(n[1::2]), max(n[0::2]), max(n[1::2])


def near(b, t, tol=3.5):
    return all(abs(b[k] - t[k]) < tol for k in range(4))


def split_layers(svg):
    """원본 SVG를 (배경 SVG, 글자 path 목록)으로 나눈다."""
    i = svg.index("</defs>") + 7
    head, body = svg[:i], svg[i:]
    body = re.sub(r'<g\s+mask="[^"]*">.*?</g\s*>', "", body, flags=re.S)   # 부드러운 그림자 층
    ink = []

    def visit(m):
        tag = m.group(0)
        fill = re.search(r'fill="([^"]+)"', tag).group(1)
        if fill == INK:
            if not near(bbox(tag), ALC_BOX):
                ink.append(tag)
            return ""
        if fill in SHADOW:
            return ""
        b = bbox(tag)
        if fill == PAPER and any(near(b, t) for t in TEXT_BOXES):          # 종이색 글자 테두리
            return ""
        if 20 < b[0] < 32 and 148 < b[1] < 158 and b[2] - b[0] < 3:        # 떨어져 있는 잡티 점
            return ""
        return tag

    body = re.sub(r"<path [^>]*?/>", visit, body)
    head = head.replace(f'width="{PW}" height="{PH}"', 'width="1512" height="3756"', 1)
    return head + body, ink


def render(svg_text, png):
    with tempfile.TemporaryDirectory() as d:
        f = pathlib.Path(d) / "bg.svg"
        f.write_text(svg_text)
        js = (f"const {{chromium}}=require('playwright');(async()=>{{const b=await chromium.launch();"
              f"const p=await b.newPage({{viewport:{{width:1512,height:3756}}}});await p.goto('file://{f}');"
              f"await p.screenshot({{path:'{png}'}});await b.close();}})();")
        subprocess.run(["node", "-e", js], check=True)


def soft(mask, sigma):
    return cv2.GaussianBlur(mask.astype(np.float32), (0, 0), sigma)


def warm_up(img):
    """회색 물감을 따뜻한 색으로 바꾼다. 파란 붓자국과 종이는 그대로 둔다."""
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    H, W = img.shape[:2]
    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    paper = np.abs(img.astype(np.float32) - np.array([220, 235, 242])).max(axis=2) < 9
    grey = (s < 46) & ~paper
    dark = 255 - v

    def paint(region, hue, s_base, s_gain, v_keep, sigma=14):
        a = soft(region & grey, 1.2) * soft(region, sigma)
        a = np.clip(a, 0, 1)
        nonlocal h, s, v
        h = np.where(a > 0.5, hue, h)
        s = s * (1 - a) + np.clip(s_base + dark * s_gain, 0, 235) * a
        v = v * (1 - a) + (255 - dark * v_keep) * a

    # 위쪽 둥근 배 → 옅은 금빛 복숭아색
    paint(np.hypot(xx - 905, yy - 390) < 300, 15, 28, 1.25, 0.22)
    # 오른쪽 아래 산 → 노랑·주황 (17도 포인트 색)
    paint((xx > 800) & (yy > 2520), 16, 70, 1.55, 0.30, sigma=30)
    # 왼쪽 돌 → 갈색
    rock = (xx < 240) & (yy > 2480) & (yy < 2960) & (v < 125) & ~paper
    a = soft(rock, 2.0)
    h = np.where(a > 0.5, 9, h)
    s = s * (1 - a) + 150 * a
    v = v * (1 - a) + np.clip(v * 1.25 + 18, 0, 255) * a
    out = np.stack([h, s, v], axis=-1)
    return cv2.cvtColor(np.clip(out, 0, 255).astype(np.uint8), cv2.COLOR_HSV2BGR)


def gold_flecks():
    rnd = random.Random(17)
    dots = []
    while len(dots) < 95:
        x, y = rnd.uniform(12, 170), rnd.uniform(18, 330)
        if 60 < x < 125 and 95 < y < 300 and rnd.random() < 0.55:      # 글자 줄은 조금 비워 둔다
            continue
        r = rnd.choice([0.35, 0.45, 0.55, 0.7, 0.9, 1.15])
        dots.append(f'<ellipse cx="{x:.1f}" cy="{y:.1f}" rx="{r}" ry="{r * rnd.uniform(.85, 1.25):.2f}" '
                    f'fill="{rnd.choice(["#d9a21c", "#e2b033", "#c98f12", "#ecc04a"])}" opacity="{rnd.uniform(.75, 1):.2f}"/>')
    return "".join(dots)


def uri(p, mime):
    return f"data:{mime};base64," + base64.b64encode(pathlib.Path(p).read_bytes()).decode()


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as d:
        raw = pathlib.Path(d) / "a.svg"
        subprocess.run(["pdftocairo", "-svg", str(SRC / "앞면_17_디자이너_60x155.pdf"), str(raw)], check=True)
        bg_svg, ink = split_layers(raw.read_text())
        png = pathlib.Path(d) / "bg.png"
        render(bg_svg, png)
        bg = warm_up(cv2.imread(str(png)))
        jpg = pathlib.Path(d) / "bg.jpg"
        cv2.imwrite(str(jpg), bg, [cv2.IMWRITE_JPEG_QUALITY, 96])
        bg_uri = uri(jpg, "image/jpeg")
    ink_svg = "".join(t.replace(INK, "#17130f") for t in ink)
    font = uri(FONTS / "noto-serif-kr-latin-900-normal.woff2", "font/woff2")
    html = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8"><title>금배주 17 앞면 v2</title><style>
@font-face{{font-family:'SerifL';font-weight:900;src:url({font}) format('woff2');}}
@page{{size:64mm 159mm;margin:0}} *{{margin:0;padding:0}} body{{-webkit-print-color-adjust:exact;print-color-adjust:exact}}
svg{{display:block;width:64mm;height:159mm}}</style></head><body>
<svg id="label" viewBox="0 0 {PW} {PH}" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink">
<image href="{bg_uri}" x="0" y="0" width="{PW}" height="{PH}" preserveAspectRatio="none"/>
{gold_flecks()}
{ink_svg}
<image href="{uri(SRC / '낙관.webp', 'image/webp')}" x="111.5" y="264" width="26" height="26" style="mix-blend-mode:multiply"/>
<text x="19" y="432.4" font-family="SerifL" font-weight="900" font-size="12.4" fill="#17130f">17%</text>
</svg></body></html>"""
    tmp = OUT / "_17.html"
    tmp.write_text(html, encoding="utf-8")
    js = f"""
const {{chromium}} = require('playwright');
(async () => {{
  const b = await chromium.launch();
  const pg = await b.newPage({{deviceScaleFactor: 4}});
  await pg.goto('file://{tmp}');
  await pg.evaluate(() => document.fonts.ready);
  await pg.pdf({{path: '{OUT}/금배주17_앞면_v2_인쇄용_재단여유2mm.pdf', width: '64mm', height: '159mm', printBackground: true}});
  const r = await (await pg.$('#label')).boundingBox();
  const mm = r.width / 64;
  await pg.screenshot({{path: '{OUT}/금배주17_앞면_v2_60x155.png',
    clip: {{x: r.x + 2 * mm, y: r.y + 2 * mm, width: 60 * mm, height: 155 * mm}}}});
  await b.close();
}})();"""
    subprocess.run(["node", "-e", js], check=True)
    tmp.unlink()


if __name__ == "__main__":
    build()
