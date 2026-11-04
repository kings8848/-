이 문서에서 알 수 있는 것: 킹스 업무별 SOP(표준작업절차) 목록 — 있는 것 9개, 대표 입력이 필요한 것 4개. 에이전트는 작업 전에 해당 SOP를 '뇌(Context)'로 읽는다.

# 킹스 SOP 목록

| 업무 | 담당 | SOP 위치 | 상태 |
|---|---|---|---|
| 정산 대사 | 정산·회계 대리 | `kings_ops.reconcile_localfood` 규칙 + 회사의 기억 | ✅ 코드화 |
| 출고 지연 경보 | 입출고·재고 대리 | `kings_ops.smartstore` | ✅ 코드화 |
| 배치 기록 | 제조기록 대리 | `templates/배치기록_양식.xlsx` | ✅ |
| 법정 의무 | 주세·식품안전 대리 | `company/compliance_register.json` | ✅ (주기 4건 미확인) |
| 지시 처리 | 사장 | `company/workflow.py` (원문 봉인·질문·검수) | ✅ |
| CEO 보고서 | 전원 | `.claude/skills/kings-ceo-report` | ✅ |
| 비밀값 입력 | 대표 | `scripts/set_secret.py` | ✅ |
| 지시 정제 | 대표 | `templates/지시_정제_프롬프트.md` | ✅ |
| 자동/승인 경계 | 전원 | `company/자동화_정책.json` | ✅ |
| **브랜드 지침** | 마케팅·영업·CS | `sop/브랜드_지침.md` | ⏳ 대표 확인 |
| **CS 응대** | CS 응대 대리 | `sop/CS_응대.md` | ⏳ 대표 확인 |
| **B2B 제안** | B2B 영업 대리 | `sop/B2B_페어링.md` + `sales/b2b.py` | ⏳ B2B 단가·페어링 문구 2건 대표 확인 |
| **공장도가격 책정** | 경영기획실장 | (작성 예정) | ⏳ 원가 필요 |
