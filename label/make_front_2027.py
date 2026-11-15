#!/usr/bin/env python3
"""금배주 앞면 라벨 2027년판 (60×155mm) 합성기.

실행: python3 label/make_front_2027.py
입력: label/금배주_2027/원본/ 의 앞면 그림(25·40), 낙관
출력: label/금배주_2027/앞면/ 의 PNG(재단 크기)·PDF(사방 2mm 재단 여유 포함)

17도는 원본 그림의 비율이 60×155와 달라서, 25도 그림을 바탕으로
金 글자를 은색으로, 붉은 산을 주황으로 바꿔 만든다.
"""
import base64
import pathlib
import subprocess

import cv2
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parent
SRC = ROOT / "금배주_2027" / "원본"
OUT = ROOT / "금배주_2027" / "앞면"
FONTS = ROOT / "fonts"

W_MM, H_MM, BLEED = 60, 155, 2
PX_W, PX_H = 770, 2000

WARNING = ("알코올은 발암물질로 지나친 음주는 간암·위암 등을 일으킵니다. "
           "임신 중 음주는 기형아 출생 위험을 높입니다. "
           "음주운전은 자신과 다른 사람의 생명을 위태롭게 할 수 있습니다.")

# 배치(mm, 재단선 기준)
BOX_TOP, BOX_BOTTOM, BOX_SIDE = 123.2, 4.6, 3.2   # 경고 상자: 위, 아래 여백, 좌우 여백
SEAL = dict(left=37.2, top=84.6, size=10.5)

METAL = {
    "gold": ("#fbe9a6", "#d9a521", "#8a5a0c"),
    "silver": ("#ffffff", "#b9bcc0", "#6d7176"),
}
PRODUCTS = [
    dict(abv=17, base="앞면_25.webp", metal="silver", variant="17"),
    dict(abv=25, base="앞면_25.webp", metal="gold", variant=None),
    dict(abv=40, base="앞면_40.webp", metal="gold", variant=None),
]


def imread(p):
    return cv2.imdecode(np.frombuffer(p.read_bytes(), np.uint8), cv2.IMREAD_UNCHANGED)


def remove_old_text(img):
    """원본에 박혀 있는 도수·영문·용량 글자를 지운다(경고 상자 위로 드러나는 부분만)."""
    y0, y1, x0, x1 = 1530, 1625, 170, 610
    roi = img[y0:y1, x0:x1]
    bg = cv2.medianBlur(roi, 61)
    diff = cv2.absdiff(roi, bg).max(axis=2)
    mask = (diff > 22).astype(np.uint8) * 255
    mask = cv2.dilate(mask, np.ones((9, 9), np.uint8))
    full = np.zeros(img.shape[:2], np.uint8)
    full[y0:y1, x0:x1] = mask
    return cv2.inpaint(img, full, 7, cv2.INPAINT_TELEA)


def to_17(img):
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    yy, xx = np.mgrid[0:img.shape[0], 0:img.shape[1]]
    # 金 글자: 금 → 은
    gold = (yy > 295) & (yy < 710) & (xx > 105) & (xx < 665) & (h > 8) & (h < 32) & (s > 70)
    g = cv2.GaussianBlur(gold.astype(np.float32), (0, 0), 1.2)
    s2 = s * (1 - g * 0.95)
    v2 = np.clip(v + g * (22 + (v - 128) * 0.35), 0, 255)
    # 아래 산: 붉은색 → 주황
    red = (yy > 1150) & ((h < 10) | (h > 168)) & (s > 35)
    r = cv2.GaussianBlur(red.astype(np.float32), (0, 0), 2.0)
    hh = np.where(h > 168, h - 180, h)
    h2 = (hh + r * 13) % 180
    s2 = np.clip(s2 * (1 + r * 0.25), 0, 255)
    out = np.stack([h2, s2, v2], axis=-1).astype(np.uint8)
    return cv2.cvtColor(out, cv2.COLOR_HSV2BGR)


def data_uri(p, mime):
    return f"data:{mime};base64," + base64.b64encode(p.read_bytes()).decode()


def font_css():
    faces = [
        ("KR", 700, "noto-sans-kr-korean-700-normal.woff2"),
        ("KRL", 700, "noto-sans-kr-latin-700-normal.woff2"),
        ("KR", 900, "noto-sans-kr-korean-900-normal.woff2"),
        ("KRL", 900, "noto-sans-kr-latin-900-normal.woff2"),
        ("Cinzel", 600, "cinzel-latin-600-normal.woff2"),
        ("Cinzel", 700, "cinzel-latin-700-normal.woff2"),
        ("Cormorant", 700, "cormorant-garamond-latin-700-normal.woff2"),
    ]
    return "\n".join(
        f"@font-face{{font-family:'{n}';font-weight:{w};src:url({data_uri(FONTS / f, 'font/woff2')}) format('woff2');}}"
        for n, w, f in faces)


def page_html(p, bg_uri, seal_uri):
    hi, mid, lo = METAL[p["metal"]]
    return f"""<section class="page"><div class="art" style="background-image:url({bg_uri})"></div>
<div class="trim">
  <img class="seal" src="{seal_uri}">
  <div class="haze"></div>
  <svg class="abv" viewBox="-30 0 600 150" xmlns="http://www.w3.org/2000/svg">
    <defs><linearGradient id="m{p['abv']}" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="{hi}"/><stop offset=".45" stop-color="{mid}"/>
      <stop offset="1" stop-color="{lo}"/></linearGradient></defs>
    <g fill="url(#m{p['abv']})" stroke="{lo}" stroke-width=".8">
      <rect x="62" y="71" width="78" height="2.6" stroke="none"/>
      <rect x="400" y="71" width="78" height="2.6" stroke="none"/>
      <text x="{340 if p['abv'] != 17 else 322}" y="112" text-anchor="end" font-family="Cinzel" font-weight="600" font-size="118">{p['abv']}</text>
      <circle cx="{362 if p['abv'] != 17 else 344}" cy="40" r="11" fill="none" stroke="url(#m{p['abv']})" stroke-width="5"/>
    </g></svg>
  <div class="en">GEUMBAEJU</div>
  <div class="vol">375 mL</div>
  <div class="warn"><b>경고 :</b> {WARNING}</div>
</div></section>"""


CSS = f"""
@page {{ size: {W_MM + 2 * BLEED}mm {H_MM + 2 * BLEED}mm; margin: 0; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
.page {{ width: {W_MM + 2 * BLEED}mm; height: {H_MM + 2 * BLEED}mm; position: relative; overflow: hidden; page-break-after: always; }}
.art {{ position: absolute; inset: 0; background-size: 100% 100%; }}
.trim {{ position: absolute; left: {BLEED}mm; top: {BLEED}mm; width: {W_MM}mm; height: {H_MM}mm; }}
.seal {{ position: absolute; left: {SEAL['left']}mm; top: {SEAL['top']}mm; width: {SEAL['size']}mm; height: {SEAL['size']}mm; mix-blend-mode: multiply; opacity: .93; }}
.haze {{ position: absolute; left: 3mm; right: 3mm; top: 93.5mm; height: 30mm;
  background: radial-gradient(ellipse at 50% 55%, rgba(250,244,232,.95) 0%, rgba(250,244,232,.85) 48%, rgba(250,244,232,0) 74%); }}
.abv {{ position: absolute; left: 6mm; width: 48mm; top: 96.4mm; height: 12mm; }}
.en {{ position: absolute; left: 0; right: 0; top: 110mm; text-align: center; font-family: 'Cinzel'; font-weight: 700;
  font-size: 14.5pt; letter-spacing: .05em; color: #17130f; line-height: 1; }}
.vol {{ position: absolute; left: 0; right: 0; top: 117.3mm; text-align: center; font-family: 'Cormorant'; font-weight: 700;
  font-size: 10pt; letter-spacing: .04em; color: #17130f; line-height: 1; }}
.warn {{ position: absolute; left: {BOX_SIDE}mm; right: {BOX_SIDE}mm; top: {BOX_TOP}mm; bottom: {BOX_BOTTOM}mm;
  background: #fff; border: .45mm solid #000; color: #000; padding: .8mm 1.1mm 0;
  font-family: 'KRL','KR',sans-serif; font-weight: 700; font-size: 10pt; line-height: 1.2; letter-spacing: -.07em; word-break: keep-all; text-wrap: balance; }}
.warn b {{ font-weight: 900; }}
"""


def build():
    OUT.mkdir(parents=True, exist_ok=True)
    seal_uri = data_uri(SRC / "낙관.webp", "image/webp")
    pages = []
    pad = round(BLEED * PX_W / W_MM)
    for p in PRODUCTS:
        img = imread(SRC / p["base"])[..., :3]
        img = remove_old_text(img)
        if p["variant"] == "17":
            img = to_17(img)
        img = cv2.resize(img, None, fx=2, fy=2, interpolation=cv2.INTER_LANCZOS4)
        img = cv2.copyMakeBorder(img, 2 * pad, 2 * pad, 2 * pad, 2 * pad, cv2.BORDER_REFLECT)
        ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 95])
        pages.append(page_html(p, "data:image/jpeg;base64," + base64.b64encode(buf.tobytes()).decode(), seal_uri))
    html = (f"<!doctype html><html lang='ko'><head><meta charset='utf-8'><title>금배주 앞면 2027</title>"
            f"<style>{font_css()}{CSS}</style></head><body>{''.join(pages)}</body></html>")
    tmp = OUT / "_앞면.html"
    tmp.write_text(html, encoding="utf-8")
    js = f"""
const {{chromium}} = require('playwright');
(async () => {{
  const b = await chromium.launch();
  const pg = await b.newPage({{deviceScaleFactor: 4}});
  await pg.goto('file://{tmp}');
  await pg.evaluate(() => document.fonts.ready);
  await pg.pdf({{path: '{OUT}/금배주_앞면_2027_인쇄용_재단여유2mm.pdf', width: '{W_MM + 2 * BLEED}mm', height: '{H_MM + 2 * BLEED}mm', printBackground: true}});
  const abv = [17, 25, 40];
  const trims = await pg.$$('.trim');
  for (let i = 0; i < trims.length; i++)
    await trims[i].screenshot({{path: '{OUT}/금배주' + abv[i] + '_앞면_60x155.png'}});
  const lines = await pg.$$eval('.warn', els => els.map(e => [e.scrollHeight, e.clientHeight]));
  console.log('경고상자 내용높이/상자높이(px):', JSON.stringify(lines));
  await b.close();
}})();"""
    subprocess.run(["node", "-e", js], check=True)
    tmp.unlink()
    ims = [cv2.imdecode(np.frombuffer((OUT / f"금배주{a}_앞면_60x155.png").read_bytes(), np.uint8), 1) for a in (17, 25, 40)]
    gap = np.full((ims[0].shape[0], 40, 3), 255, np.uint8)
    sheet = np.hstack([ims[0], gap, ims[1], gap, ims[2]])
    sheet = cv2.resize(sheet, None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    (OUT / "미리보기_3종.png").write_bytes(cv2.imencode(".png", sheet)[1].tobytes())


if __name__ == "__main__":
    build()
