# 킹스 운영 검증 엔진 (45점 → 90점 실증 패키지)

> 2026-11-03 밤 손사장 야간 작업분. "문서·규칙"이 아니라 **실거래 자료로 돌아가는지**를 증명하기 위한 모듈입니다.

## 대표님 내일 아침 10시 전 할 일 (총 약 25분)

| 순서 | 할 일 | 시간 | 점수 영향 |
|:-:|---|:-:|:-:|
| ① | **스마트스토어 발송대기 1건 처리** (11/2부터 미발송) — 발송 또는 구매자 안내 | 5분 | 손실 방지 |
| ② | 최근 1배치를 `templates/batch_record_template.csv` 양식대로 6줄 작성 → `data/batches.csv`로 저장 (제조일지·병입일지 보면서) | 15분 | +10 |
| ③ | ②의 병입 줄 `counted_on_hand`에 **오늘 실제로 센 남은 병 수** 기입 | 3분 | +5 |
| ④ | 다음 정산서 1건을 손으로 맞춰볼 때 걸린 분을 `data/time_log.csv`에 기록 (`templates/time_log_guide.md`) | 2분+α | +10 |

- ①은 점수와 관계없이 오늘 처리해야 합니다.
- ②~④는 종이·카톡 사진으로 주셔도 됩니다. 손사장이 옮겨 적고, 엔진이 검증합니다.

## 실행

```bash
python3 ops/kings_ops.py run            # 대사·경보·점수 → reports/ 보고서
python3 -m unittest ops/tests/test_ops.py   # 회귀 시험 8개
```

## 들어 있는 실거래 자료 (전부 원본 ID 보존)

| 파일 | 원천 | 건수 |
|---|---|---|
| `data/localfood_settlements.csv` | Google Drive 정산서 머리(합계) | 14부 (중복 1부 포함) |
| `data/localfood_lines.csv` | 정산서 상세행 | 118행 |
| `data/smartstore_deposits.csv` | Gmail '정산금액 입금 완료' | 15건 |
| `data/smartstore_daily_status.csv` | Gmail '주문현황' 메일 자동 추출 | 76일 |
| `data/localfood_gmail_threads.txt` | Gmail 양양 신활력 추진단 정산 메일 | 27통 |

정산서 숫자는 원문 텍스트를 옮겨 적은 것이며, 엔진이 **정산서 머리 합계와 1원 단위로 대조**합니다. 옮겨 적다 틀리면 바로 '불일치'로 드러납니다(시험 `test_tampered_amount_is_caught`).

## 점수 규칙 (증거 없으면 0점)

| 영역 | 항목 | 배점 |
|---|---|---:|
| 운영체계 | 원본 추적 / 검증 규칙 코드화 / 예외→조치 자동 생성 / 반복 실행 무중복 / 예약 실행 실증 | 10×5 |
| 업무자동화 | 실거래 정산 대사 10 · 채널 2곳 연결 5 · 누락 탐지 5 · 출고 경보 5 · 실배치 추적 10 · 재고 대사 5 · 전후 실측 10 | 50 |

`is_sample=Y`인 예시 배치와 `is_estimate=Y`인 짐작 시간은 점수에서 뺍니다.

## 지시 파이프라인 (2026-11-04 추가 · `ops/company/`)

영상 'AI 회사' 구조를 1인 양조장용으로 줄여 적용했습니다. 판단 근거는 `ops/company/운영도면.md`에 있습니다.

| 규칙 | 명령 |
|---|---|
| 원문 봉인 | `workflow.py new "지시 원문"` → `verify` |
| 해석 없이는 분해 불가 | `workflow.py interpret D-0001 "해석"` |
| 1담당·1산출물·검수기준 잠금 | `workflow.py task D-0001 --owner 제조기록 --output ... --accept "기준1;기준2"` |
| 첫 줄 요약 없으면 자동 반려 · 반려 3회는 대표 상신 | `workflow.py review --pass T-..` |
| 독립검토는 권고만 | `workflow.py advise T-.. "권고"` |
| 외부 발송·게시·제출은 대표 승인 | `workflow.py approve T-..` |
| 회사의 기억 + 지난 지적 탑재 | `workflow.py brief T-..` |
| 현황 | `workflow.py status` |

## 대표 결정 반영 (2026-11-04, D-0003)

| 결정 | 구현 |
|---|---|
| 월 예산 10만원 | 회사의 기억 '반드시 아는 것' |
| 스마트스토어 커머스API 연동 | `ops/connectors/smartstore_api.py` (bcrypt 서명·토큰·변경주문 조회·중복 없는 적재) → 엔진이 결제 후 24시간 미발송을 긴급 경보. **실서버 미검증** — 대표님 .env 입력 후 첫 실행에서 검증 |
| 배치 기록 엑셀 | `ops/templates/배치기록_양식.xlsx`(공정·제품 목록 선택) → `ops/data/batches.xlsx`로 저장하면 엔진이 csv보다 우선해 읽음 |
| 누락 정산 대표 직접 | `ops/reports/누락정산_처리목록_대표용.md` (11구간 + 메일 7통 Gmail 링크) |

## 전사 가치사슬 (2026-11-04 · `ops/enterprise/`)

```bash
python3 ops/enterprise/value_chain.py     # 입고→생산→재고→판매→세금→영업이익→시설투자 + 100억 시나리오
```
`master.json`의 null은 계산하지 않고 '입력 필요'로, verified=false 세율은 '미확정'으로 보고합니다. 비밀값은 `python ops/scripts/set_secret.py 이름` (화면에 안 보임).

## 한 줄 전체 실행 (3층 파이프라인)

```bash
python3 ops/pipeline.py
```
수집·대사 → 전사 가치사슬 → 경보→담당 업무 → `reports/아침보고_YYYYMMDD.md`(대표 확인 필요 건수·지능 레버리지). PC 작업 스케줄러에 이 한 줄을 매일 걸면 24시간 자동화가 됩니다.

## 통합 대시보드(콕핏)
`ops/reports/cockpit.html` — 파이프라인 마지막 단계가 매일 다시 그립니다. 1·2·3차 증거, 원장 매출, 경보, B2B 리드, 법정 의무, **대표님 판단이 필요한 것**을 한 화면에. 전체 지도는 `ops/킹스_1인AI법인_시스템_총정리.md`.
