#!/usr/bin/env python3
"""금배주 라벨 2027년판 시안 생성기.

실행: python3 label/make_label_2027.py
결과: label/금배주_2027/ 아래 HTML·PDF·PNG

표시 문구는 PRODUCTS / COMMON 만 고치면 세 도수 모두 다시 만들어진다.
"""
import base64
import pathlib
import subprocess

ROOT = pathlib.Path(__file__).resolve().parent
OUT = ROOT / "금배주_2027"
FONTS = ROOT / "fonts"

# 라벨 크기(mm) — 실제 병 라벨 칼선에 맞춰 수정
W, H = 75, 115

COMMON = dict(
    maker="농업회사법인킹스(주)",
    addr="강원특별자치도 양양군 서면 구룡령로 1103-22",
    volume="375ml",
    food_type="리큐르",
    tel="033-672-2888",
    storage="직사광선을 피해 서늘한 곳에 보관",
    warn=[
        "지나친 음주는 뇌졸중, 기억력 손상이나 치매를 유발합니다.",
        "임신 중 음주는 기형아 출산 위험을 높입니다.",
        "음주운전은 자신과 다른 사람의 생명을 위태롭게 할 수 있습니다.",
    ],
)

PRODUCTS = [
    dict(
        abv=17, report="202400063753", ean="8809990842032", accent="#5d6b3a",
        ingredients="정제수, 증류원액(정제수, 쌀, 수수, 누룩, 효모, 정제효소제), "
                    "돌배나무열매(국내산) 8.5%, 설탕",
    ),
    dict(
        abv=25, report="202400063754", ean="8809990842049", accent="#a0741a",
        ingredients="정제수, 증류원액(정제수, 쌀, 수수, 누룩, 효모, 정제효소제), "
                    "돌배나무열매(국내산) 12.3%, 설탕",
    ),
    dict(
        abv=40, report="202400063755", ean="8809990842056", accent="#1f2a44",
        ingredients="증류원액(정제수, 쌀, 수수, 누룩, 효모, 정제효소제), "
                    "돌배나무열매(국내산) 18.9%, 정제수, 설탕",
    ),
]

L = ["0001101", "0011001", "0010011", "0111101", "0100011",
     "0110001", "0101111", "0111011", "0110111", "0001011"]
G = ["0100111", "0110011", "0011011", "0100001", "0011101",
     "0111001", "0000101", "0010001", "0001001", "0010111"]
R = ["1110010", "1100110", "1101100", "1000010", "1011100",
     "1001110", "1010000", "1000100", "1001000", "1110100"]
PARITY = ["LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG",
          "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL"]


def ean13_svg(code: str) -> str:
    assert len(code) == 13 and code.isdigit()
    s = sum(int(d) * (3 if i % 2 else 1) for i, d in enumerate(code[:12]))
    assert (10 - s % 10) % 10 == int(code[12]), f"EAN 검증숫자 오류: {code}"
    bits = "101"
    for d, p in zip(code[1:7], PARITY[int(code[0])]):
        bits += (L if p == "L" else G)[int(d)]
    bits += "01010"
    for d in code[7:]:
        bits += R[int(d)]
    bits += "101"
    guard = set(range(0, 3)) | set(range(45, 50)) | set(range(92, 95))
    rects = "".join(
        f'<rect x="{11 + i}" y="0" width="1" height="{66 if i in guard else 60}"/>'
        for i, b in enumerate(bits) if b == "1")
    txt = (f'<text x="4" y="72" text-anchor="middle">{code[0]}</text>'
           f'<text x="35.5" y="72" text-anchor="middle" textLength="40">{code[1:7]}</text>'
           f'<text x="81.5" y="72" text-anchor="middle" textLength="40">{code[7:]}</text>')
    return (f'<svg class="ean" viewBox="0 0 113 74" xmlns="http://www.w3.org/2000/svg">'
            f'<rect width="113" height="74" fill="#fff"/><g fill="#000">{rects}</g>'
            f'<g font-family="LAT,sans-serif" font-size="9" fill="#000">{txt}</g></svg>')


PEAR = """<svg class="pear" viewBox="0 0 100 120" xmlns="http://www.w3.org/2000/svg">
<path d="M50 30 C50 18 54 10 62 5" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/>
<path d="M56 16 C68 6 84 10 88 22 C74 28 62 26 56 16 Z" fill="currentColor" opacity=".55"/>
<path d="M50 30 C38 30 34 42 32 52 C29 64 16 70 16 88 C16 106 32 116 50 116 C68 116 84 106 84 88 C84 70 71 64 68 52 C66 42 62 30 50 30 Z"
 fill="none" stroke="currentColor" stroke-width="2.4"/>
<path d="M30 86 C30 98 38 106 48 108" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" opacity=".6"/>
</svg>"""


def font_css() -> str:
    out = []
    for fam, key in (("sans", "S"), ("serif", "M")):
        for w in (400, 700, 900):
            for sub, rng in (("latin", "U+0000-00FF,U+2010-2027,U+20AC"), ("korean", "")):
                b = base64.b64encode((FONTS / f"noto-{fam}-kr-{sub}-{w}-normal.woff2").read_bytes()).decode()
                r = f"unicode-range:{rng};" if rng else ""
                out.append(f"@font-face{{font-family:'{key}';font-weight:{w};{r}"
                           f"src:url(data:font/woff2;base64,{b}) format('woff2');}}")
    return "\n".join(out)


CSS = f"""
@page {{ size: A4 landscape; margin: 0; }}
* {{ box-sizing: border-box; margin: 0; padding: 0; }}
body {{ font-family: 'S', sans-serif; color: #1c1a16; -webkit-print-color-adjust: exact; print-color-adjust: exact; }}
.sheet {{ width: 297mm; height: 210mm; padding: 14mm 16mm; page-break-after: always; position: relative; background: #fff; }}
.sheet h1 {{ font-size: 13pt; font-weight: 700; }}
.sheet .sub {{ font-size: 8.5pt; color: #555; margin-top: 1.5mm; }}
.row {{ display: flex; gap: 14mm; margin-top: 8mm; align-items: flex-start; }}
.cap {{ font-size: 8pt; color: #555; margin-bottom: 2mm; }}
.label {{ width: {W}mm; height: {H}mm; background: #f6f0e2; border: .2mm solid #b9b09a; position: relative; overflow: hidden; }}
.notes {{ flex: 1; font-size: 8.5pt; line-height: 1.6; }}
.notes h2 {{ font-size: 9.5pt; margin-bottom: 1.5mm; }}
.notes li {{ margin-left: 4mm; }}
.notes .chk {{ color: #a33; font-weight: 700; }}

/* ── 앞면 ── */
.front {{ display: flex; flex-direction: column; align-items: center; padding: 5mm 4.5mm 4mm; color: var(--ac); }}
.front .frame {{ position: absolute; inset: 2mm; border: .35mm solid var(--ac); pointer-events: none; }}
.front .brand {{ font-family: 'M'; font-size: 6.5pt; letter-spacing: .32em; font-weight: 700; margin-top: 1mm; }}
.front .rule {{ width: 22mm; height: .25mm; background: var(--ac); margin: 1.6mm 0 2mm; }}
.front .pear {{ width: 11mm; height: 13.2mm; }}
.front .name {{ font-family: 'M'; font-weight: 900; font-size: 33pt; letter-spacing: .06em; line-height: 1.05; margin-top: 1.5mm; color: #1c1a16; }}
.front .en {{ font-family: 'M'; font-size: 7pt; letter-spacing: .5em; margin-top: 1mm; padding-left: .5em; }}
.front .abv {{ font-family: 'M'; font-weight: 900; font-size: 46pt; line-height: 1; margin-top: 2.5mm; }}
.front .abv small {{ font-size: 15pt; font-weight: 700; margin-left: .5mm; }}
.front .meta {{ font-size: 7.5pt; font-weight: 700; letter-spacing: .08em; margin-top: 1.5mm; color: #1c1a16; }}
.front .origin {{ font-family: 'M'; font-size: 7pt; margin-top: 1mm; color: #1c1a16; }}
.front .warn {{ margin-top: auto; width: 100%; border: .4mm solid #000; background: #fff; color: #000;
  font-family: 'S'; font-weight: 700; font-size: 10pt; line-height: 1.22; letter-spacing: -.045em;
  padding: 1.1mm 1.4mm; word-break: keep-all; }}
.front .warn b {{ font-weight: 900; }}

/* ── 뒷면 ── */
.back {{ padding: 4mm 4mm 3.5mm; font-size: 10pt; line-height: 1.2; letter-spacing: -.06em; color: #000; display: flex; flex-direction: column; }}
.back table {{ width: 100%; border-collapse: collapse; }}
.back th, .back td {{ border: .2mm solid #000; padding: .45mm 1mm; vertical-align: top; text-align: left; word-break: keep-all; }}
.back th {{ width: 16.5mm; font-weight: 700; background: #ebe3cf; }}
.back .name td {{ font-weight: 900; }}
.back .small {{ margin-top: 1mm; line-height: 1.2; word-break: keep-all; }}
.back .minor {{ margin-top: 1mm; border: .4mm solid #000; text-align: center; font-weight: 900; padding: .5mm 0; background: #fff; }}
.back .foot {{ margin-top: auto; padding-top: 1.5mm; display: flex; align-items: flex-end; justify-content: space-between; gap: 2mm; }}
.back .ean {{ width: 25mm; height: auto; display: block; }}
.back .date {{ flex: 1; border: .2mm solid #000; height: 11mm; padding: .6mm 1mm; font-weight: 700; background: #fff; font-size: 9pt; }}
.back .r1399 {{ font-weight: 700; margin-top: .8mm; }}
"""


def front(p):
    warn = " ".join(COMMON["warn"])
    return f"""<div class="label front" style="--ac:{p['accent']}">
  <div class="frame"></div>
  <div class="brand">KINGS BREWERY</div><div class="rule"></div>
  {PEAR}
  <div class="name">금배주</div>
  <div class="en">GEUMBAEJU</div>
  <div class="abv">{p['abv']}<small>%</small></div>
  <div class="meta">{COMMON['food_type']} · {COMMON['volume']}</div>
  <div class="origin">강원 양양 구룡령 돌배</div>
  <div class="warn"><b>경고:</b> {warn}</div>
</div>"""


def back(p):
    c = COMMON
    return f"""<div class="label back">
  <table>
    <tr class="name"><th>제품명</th><td>금배주 {p['abv']}</td></tr>
    <tr><th>식품유형</th><td>{c['food_type']}</td></tr>
    <tr><th>내용량</th><td>{c['volume']} · 에탄올함량 {p['abv']}%</td></tr>
    <tr><th>원재료명</th><td>{p['ingredients']}</td></tr>
    <tr><th>제조원</th><td>{c['maker']}<br>{c['addr']}</td></tr>
    <tr><th>품목보고</th><td>{p['report']}</td></tr>
    <tr><th>보관방법</th><td>{c['storage']}</td></tr>
    <tr><th>상담실</th><td>{c['tel']}</td></tr>
  </table>
  <div class="small">※ 이 제품은 복숭아를 사용한 제품과 같은 제조시설에서 제조하고 있습니다.<br>
  ※ 원료 성분에 의해 침전물이 생길 수 있으나 안심하고 드십시오.</div>
  <div class="r1399">부정·불량식품 신고는 국번없이 1399</div>
  <div class="minor">19세 미만 청소년에게 판매 금지</div>
  <div class="foot">{ean13_svg(p['ean'])}<div class="date">병입년월일</div></div>
</div>"""


NOTES = """<div class="notes"><h2>2027년판 반영 사항</h2><ul>
<li>경고문구를 <b>앞면 상표 아래</b>로 이동, 사각 테두리·고딕체·10pt (375ml 기준)</li>
<li>음주운전 경고문구 추가 (건강·임신·음주운전 3종 모두 표시)</li>
<li>소재지 "강원도" → "강원특별자치도" (품목제조보고서와 일치)</li>
<li>원재료명을 품목제조보고서 배합비율 순으로 정리</li>
<li>뒷면 표시사항 10pt로 확대</li>
</ul>
<h2 style="margin-top:4mm">인쇄 전 확인</h2><ul>
<li class="chk">라벨 크기는 가정값(75×115mm) — 실제 칼선으로 교체</li>
<li class="chk">경고문구 3종 문안을 고시 원문과 대조</li>
<li>바코드는 번호로 새로 그린 것 — 인쇄소에서 판독 시험</li>
</ul></div>"""


def build():
    OUT.mkdir(exist_ok=True)
    sheets = []
    for p in PRODUCTS:
        sheets.append(f"""<section class="sheet">
<h1>금배주 {p['abv']} · 375ml — 2027년판 라벨 시안</h1>
<div class="sub">실제 크기 100% (라벨 {W}×{H}mm 가정) · 2026-11-09 시행 주류 경고표시 기준 반영</div>
<div class="row">
  <div><div class="cap">앞면 (주상표)</div>{front(p)}</div>
  <div><div class="cap">뒷면 (표시사항)</div>{back(p)}</div>
  {NOTES}
</div></section>""")
    html = (f"<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
            f"<title>금배주 라벨 2027</title><style>{font_css()}{CSS}</style></head>"
            f"<body>{''.join(sheets)}</body></html>")
    src = OUT / "금배주_라벨_2027_시안.html"
    src.write_text(html, encoding="utf-8")
    js = f"""
const {{chromium}} = require('playwright');
(async () => {{
  const b = await chromium.launch();
  const pg = await b.newPage({{viewport: {{width: 1123, height: 794}}, deviceScaleFactor: 2}});
  await pg.goto('file://{src}');
  await pg.evaluate(() => document.fonts.ready);
  await pg.pdf({{path: '{OUT}/금배주_라벨_2027_시안.pdf', format: 'A4', landscape: true, printBackground: true}});
  const abv = [17, 25, 40];
  const sheets = await pg.$$('.sheet');
  for (let i = 0; i < sheets.length; i++)
    await sheets[i].screenshot({{path: '{OUT}/미리보기_금배주' + abv[i] + '.png'}});
  await b.close();
}})();"""
    subprocess.run(["node", "-e", js], check=True)


if __name__ == "__main__":
    build()
