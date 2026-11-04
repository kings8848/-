#!/usr/bin/env python3
"""컨텍스트 주입(RAG의 킹스판) — SOP·회사의 기억·법정 의무 대장에서 질문과 관련된 단락만 찾아 에이전트에게 넘긴다.

킹스 문서량(수십 쪽)에서는 벡터 DB 없이 키워드 점수로 충분하다(비용 0, 결과 재현 가능).
문서가 수천 쪽이 되면(S2~S3) 같은 함수 자리에 Supabase pgvector 검색을 끼운다.
  python3 ops/company/context.py "봉신설주 품목제조보고"
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

OPS = Path(__file__).resolve().parents[1]
SOURCES = [OPS / "sop", OPS / "company" / "memory.md", OPS / "company" / "주류제조_부서_조사.md"]


def chunks():
    files = []
    for s in SOURCES:
        files += sorted(s.glob("*.md")) if s.is_dir() else [s]
    for f in files:
        if not f.exists():
            continue
        for para in re.split(r"\n(?=#|\|)|\n\s*\n", f.read_text(encoding="utf-8")):
            if para.strip():
                yield str(f.relative_to(OPS)), para.strip()
    reg = OPS / "company" / "compliance_register.json"
    if reg.exists():
        for i in json.loads(reg.read_text(encoding="utf-8"))["items"]:
            yield "company/compliance_register.json", f"[{i['id']}] {i['what']} · 담당 {i['owner']} · 주기 {i['cycle']} · {i['note']}"


def tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[가-힣A-Za-z0-9]{2,}", text.lower())}


def search(query: str, k: int = 5) -> list[dict]:
    q = tokens(query)
    scored = []
    for src, para in chunks():
        t = tokens(para)
        score = len(q & t) + sum(1 for w in q if len(w) >= 3 and w in para.lower()) * 0.5
        if score > 0:
            scored.append({"score": score, "source": src, "text": para[:400]})
    return sorted(scored, key=lambda x: -x["score"])[:k]


if __name__ == "__main__":
    for r in search(" ".join(sys.argv[1:])):
        print(f"[{r['score']:.1f}] {r['source']}\n  {r['text'][:200]}\n")
