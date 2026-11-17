-- =====================================================================
-- 킹스양조장 통합 운영 시스템 (KBS) — 데이터베이스 기초 설계 v0.1
-- 엔진: SQLite (파일 1개, 오프라인, 무료)
-- 단위: 원료 kg / 액체 L / 도수 % / 온도 ℃ / 당도 °Bx / 병 개 / 금액 원
-- 주의: 레시피 배합 수치·고객 개인정보는 로컬 DB에만 저장 (저장소 업로드 금지)
-- =====================================================================
PRAGMA foreign_keys = ON;

-- ---------------------------------------------------------------------
-- 1. 마스터 (기준 정보)
-- ---------------------------------------------------------------------
CREATE TABLE items (
  item_code     TEXT PRIMARY KEY,                 -- RM-DB-01, PK-BT-375, FG-BS-375
  name          TEXT NOT NULL,
  category      TEXT NOT NULL CHECK (category IN ('원료','부자재','반제품','완제품','농자재')),
  unit          TEXT NOT NULL,                    -- kg, L, 개
  safety_stock  REAL DEFAULT 0,
  std_cost      REAL DEFAULT 0,                   -- 표준 단가 (원/단위)
  active        INTEGER DEFAULT 1,
  note          TEXT
);

CREATE TABLE products (                            -- 판매 SKU
  sku             TEXT PRIMARY KEY,               -- FG-BS-375
  item_code       TEXT NOT NULL REFERENCES items(item_code),
  product_name    TEXT NOT NULL,
  liquor_type     TEXT NOT NULL,                  -- 주종 (세무사 확인 후 확정)
  volume_ml       INTEGER NOT NULL,
  abv             REAL NOT NULL,
  price_retail    INTEGER,
  price_wholesale INTEGER,
  price_export    INTEGER,
  is_limited      INTEGER DEFAULT 0,
  limited_qty     INTEGER,
  active          INTEGER DEFAULT 1
);

CREATE TABLE partners (
  partner_id  TEXT PRIMARY KEY,                   -- P-012
  type        TEXT NOT NULL CHECK (type IN ('공급처','거래처','농가','물류','기관','세무사','기타')),
  name        TEXT NOT NULL,
  biz_no      TEXT,
  contact     TEXT,
  phone       TEXT,
  address     TEXT,
  note        TEXT
);

CREATE TABLE customers (
  customer_id       TEXT PRIMARY KEY,             -- C-00128
  name              TEXT NOT NULL,
  phone             TEXT,
  email             TEXT,
  address           TEXT,
  adult_verified    INTEGER DEFAULT 0,
  consent_marketing INTEGER DEFAULT 0,
  grade             TEXT DEFAULT '신규' CHECK (grade IN ('신규','재구매','단골','VIP')),
  first_channel     TEXT,
  created_at        TEXT DEFAULT (datetime('now','localtime')),
  note              TEXT
);

CREATE TABLE fields (                              -- 필지
  field_id     TEXT PRIMARY KEY,                  -- FD-01
  name         TEXT,
  location     TEXT,
  area_m2      REAL,
  crop         TEXT CHECK (crop IN ('돌배','자색옥수수','기타')),
  tree_count   INTEGER,
  planted_year INTEGER,
  note         TEXT
);

CREATE TABLE vessels (                             -- 설비·용기
  vessel_id   TEXT PRIMARY KEY,                   -- FT-01, ST-01, OK03, OB01
  type        TEXT NOT NULL CHECK (type IN ('발효조','증류기','숙성조','옹기','오크통','저장탱크','기타')),
  capacity_l  REAL,
  material    TEXT,
  location    TEXT,
  active      INTEGER DEFAULT 1,
  note        TEXT
);

CREATE TABLE recipes (                             -- 레시피 (버전 관리, 로컬 전용)
  recipe_id     TEXT PRIMARY KEY,                 -- RC-BS-v3
  product_line  TEXT NOT NULL,                    -- BS, DB, PC, LT
  version       TEXT NOT NULL,
  temp_min      REAL, temp_max REAL,              -- 발효 기준 온도 (이탈 알림용)
  brix_target   REAL,
  valid_from    TEXT,
  note          TEXT
);

CREATE TABLE recipe_lines (
  recipe_id     TEXT NOT NULL REFERENCES recipes(recipe_id),
  item_code     TEXT NOT NULL REFERENCES items(item_code),
  qty_per_batch REAL NOT NULL,
  unit          TEXT NOT NULL,
  PRIMARY KEY (recipe_id, item_code)
);

CREATE TABLE liquor_tax_rates (                    -- 세무사 확인 후 입력
  liquor_type  TEXT NOT NULL,
  method       TEXT NOT NULL CHECK (method IN ('종가','종량')),
  rate         REAL NOT NULL,                     -- 종가: 비율(%), 종량: 원/kL
  reduction    TEXT,                              -- 경감 조건 메모
  valid_from   TEXT NOT NULL,
  PRIMARY KEY (liquor_type, valid_from)
);

-- ---------------------------------------------------------------------
-- 2. 1차 농업
-- ---------------------------------------------------------------------
CREATE TABLE farm_tasks (
  task_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  task_date     TEXT NOT NULL,
  field_id      TEXT NOT NULL REFERENCES fields(field_id),
  task_type     TEXT NOT NULL CHECK (task_type IN ('전정','시비','방제','관수','제초','파종','적과','수확','건조','기타')),
  material_item TEXT REFERENCES items(item_code),
  material_qty  REAL,
  dilution      TEXT,                             -- 방제 희석배수
  hours         REAL,
  note          TEXT
);

CREATE TABLE harvests (
  harvest_lot  TEXT PRIMARY KEY,                  -- H-26-DB-03
  field_id     TEXT NOT NULL REFERENCES fields(field_id),
  crop         TEXT NOT NULL,
  harvest_date TEXT NOT NULL,
  qty_kg       REAL NOT NULL,
  grade        TEXT,
  note         TEXT
);

-- ---------------------------------------------------------------------
-- 3. 2차 생산·품질
-- ---------------------------------------------------------------------
CREATE TABLE material_lots (                       -- 원료로트
  lot_id        TEXT PRIMARY KEY,                 -- R-261117-01
  item_code     TEXT NOT NULL REFERENCES items(item_code),
  source_type   TEXT NOT NULL CHECK (source_type IN ('자가수확','매입')),
  harvest_lot   TEXT REFERENCES harvests(harvest_lot),
  partner_id    TEXT REFERENCES partners(partner_id),
  received_date TEXT NOT NULL,
  qty           REAL NOT NULL,
  unit          TEXT NOT NULL,
  unit_price    REAL DEFAULT 0,
  inspection    TEXT DEFAULT '대기' CHECK (inspection IN ('대기','합격','불합격','보류')),
  expiry_date   TEXT,
  note          TEXT
);

CREATE TABLE batches (                             -- 담금배치
  batch_id      TEXT PRIMARY KEY,                 -- B-BS-2611-01
  product_line  TEXT NOT NULL,
  recipe_id     TEXT REFERENCES recipes(recipe_id),
  start_date    TEXT NOT NULL,
  vessel_id     TEXT REFERENCES vessels(vessel_id),
  water_l       REAL,
  status        TEXT DEFAULT '담금' CHECK (status IN ('담금','발효','여과','증류','숙성','병입완료','폐기')),
  yield_l       REAL,                             -- 압착·여과 후 원액량
  lees_kg       REAL,                             -- 지게미
  work_hours    REAL DEFAULT 0,
  note          TEXT
);

CREATE TABLE batch_inputs (
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id   TEXT NOT NULL REFERENCES batches(batch_id),
  lot_id     TEXT NOT NULL REFERENCES material_lots(lot_id),
  qty        REAL NOT NULL,
  unit       TEXT NOT NULL,
  cost       REAL                               -- 자동: qty × 로트 단가
);

CREATE TABLE ferment_logs (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  batch_id     TEXT NOT NULL REFERENCES batches(batch_id),
  measured_at  TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  temp_c       REAL,
  brix         REAL,
  ph           REAL,
  abv          REAL,
  sensory_note TEXT,
  source       TEXT DEFAULT '수기' CHECK (source IN ('수기','센서'))
);

CREATE TABLE distillations (
  dist_id      TEXT PRIMARY KEY,                  -- D-BS-2611-01-1
  batch_id     TEXT NOT NULL REFERENCES batches(batch_id),
  dist_date    TEXT NOT NULL,
  round        INTEGER DEFAULT 1,
  still_id     TEXT REFERENCES vessels(vessel_id),
  input_l      REAL, input_abv REAL,
  head_l       REAL, head_abv  REAL,              -- 초류
  heart_l      REAL, heart_abv REAL,              -- 본류
  tail_l       REAL, tail_abv  REAL,              -- 후류
  hours        REAL,
  energy_kwh   REAL,
  gas_m3       REAL,
  note         TEXT
);

CREATE TABLE aging (
  aging_id     TEXT PRIMARY KEY,                  -- A-OK03-2611
  source_type  TEXT NOT NULL CHECK (source_type IN ('batch','dist','blend')),
  source_id    TEXT NOT NULL,
  vessel_id    TEXT NOT NULL REFERENCES vessels(vessel_id),
  start_date   TEXT NOT NULL,
  target_date  TEXT,
  end_date     TEXT,
  start_l      REAL, start_abv REAL,
  end_l        REAL, end_abv   REAL,
  note         TEXT
);

CREATE TABLE aging_logs (
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  aging_id     TEXT NOT NULL REFERENCES aging(aging_id),
  check_date   TEXT NOT NULL,
  volume_l     REAL,
  abv          REAL,
  temp_c       REAL,
  humidity     REAL,
  sensory_score REAL,
  sensory_note TEXT
);

CREATE TABLE blends (
  blend_id     TEXT PRIMARY KEY,                  -- BL-270301-01
  blend_date   TEXT NOT NULL,
  target_abv   REAL,
  water_l      REAL,
  final_l      REAL,
  final_abv    REAL,
  note         TEXT
);

CREATE TABLE blend_lines (
  blend_id     TEXT NOT NULL REFERENCES blends(blend_id),
  source_type  TEXT NOT NULL CHECK (source_type IN ('batch','dist','aging')),
  source_id    TEXT NOT NULL,
  qty_l        REAL NOT NULL,
  abv          REAL,
  PRIMARY KEY (blend_id, source_type, source_id)
);

CREATE TABLE quality_checks (
  qc_id         TEXT PRIMARY KEY,
  target_type   TEXT NOT NULL CHECK (target_type IN ('원료','배치','증류','숙성','병입','외부검사')),
  target_id     TEXT NOT NULL,
  check_date    TEXT NOT NULL,
  abv           REAL,
  methanol      REAL,
  ph            REAL,
  sensory_score REAL,
  result        TEXT NOT NULL CHECK (result IN ('합격','불합격','보류')),
  lab           TEXT,                             -- 외부 검사기관
  report_path   TEXT,
  next_due      TEXT,                             -- 다음 정기검사 예정일
  note          TEXT
);

CREATE TABLE bottlings (                           -- 병입로트 = 라벨 Batch No.
  bottle_lot   TEXT PRIMARY KEY,                  -- L-BS-270315-01
  sku          TEXT NOT NULL REFERENCES products(sku),
  source_type  TEXT NOT NULL CHECK (source_type IN ('batch','aging','blend')),
  source_id    TEXT NOT NULL,
  bottle_date  TEXT NOT NULL,
  bottles      INTEGER NOT NULL,
  volume_ml    INTEGER NOT NULL,
  abv          REAL NOT NULL,
  qc_id        TEXT REFERENCES quality_checks(qc_id),
  release_ok   INTEGER DEFAULT 0,                 -- 완제품 검사 합격 시 1 → 출고 가능
  unit_cost    REAL,                              -- 자동: 병당 원가
  serial_from  INTEGER, serial_to INTEGER,        -- 한정판 넘버링
  note         TEXT
);

-- ---------------------------------------------------------------------
-- 4. 재고: 수불 원장 (모든 입·출의 단일 기록)
-- ---------------------------------------------------------------------
CREATE TABLE inventory_moves (
  move_id    INTEGER PRIMARY KEY AUTOINCREMENT,
  moved_at   TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  move_type  TEXT NOT NULL CHECK (move_type IN ('입고','투입','생산','출고','반품','폐기','시음','샘플','조정')),
  item_code  TEXT NOT NULL REFERENCES items(item_code),
  lot_id     TEXT,                                -- 원료로트 / 병입로트 / 배치
  qty        REAL NOT NULL,                       -- 들어오면 +, 나가면 −
  unit       TEXT NOT NULL,
  ref_type   TEXT,                                -- batch, bottling, order, stocktake …
  ref_id     TEXT,
  note       TEXT
);
CREATE INDEX ix_moves_item ON inventory_moves(item_code, lot_id);

-- ---------------------------------------------------------------------
-- 5. 판매·서비스
-- ---------------------------------------------------------------------
CREATE TABLE orders (
  order_id      TEXT PRIMARY KEY,                 -- O-261117-005
  order_date    TEXT NOT NULL,
  channel       TEXT NOT NULL CHECK (channel IN ('자사몰','스마트스토어','오픈마켓','전화','방문','B2B','한정판예약','체험','수출')),
  channel_order_no TEXT,                          -- 플랫폼 주문번호 (중복 방지)
  customer_id   TEXT REFERENCES customers(customer_id),
  partner_id    TEXT REFERENCES partners(partner_id),
  adult_checked INTEGER DEFAULT 0,
  status        TEXT DEFAULT '접수' CHECK (status IN ('접수','결제완료','출고완료','배송완료','취소','반품')),
  total_amount  INTEGER DEFAULT 0,
  shipping_fee  INTEGER DEFAULT 0,
  discount      INTEGER DEFAULT 0,
  note          TEXT,
  UNIQUE (channel, channel_order_no)
);

CREATE TABLE order_items (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id    TEXT NOT NULL REFERENCES orders(order_id),
  sku         TEXT NOT NULL REFERENCES products(sku),
  bottle_lot  TEXT REFERENCES bottlings(bottle_lot),   -- 선입선출 자동 배정
  qty         INTEGER NOT NULL,
  unit_price  INTEGER NOT NULL,
  amount      INTEGER NOT NULL
);

CREATE TABLE shipments (
  shipment_id    INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id       TEXT NOT NULL REFERENCES orders(order_id),
  ship_date      TEXT NOT NULL,
  courier        TEXT,
  tracking_no    TEXT,
  is_tax_release INTEGER DEFAULT 1,               -- 주세 반출 대상 여부 (기준 세무사 확인)
  hold_reason    TEXT,                            -- 출고 보류 사유 (성인 미인증, 주소 오류 등)
  packed_photo   TEXT,                            -- 포장 사진 경로 (파손 분쟁 대비)
  delivered_at   TEXT,                            -- 배송 완료 시각 → D+3 후기 요청
  delay_flag     INTEGER DEFAULT 0,               -- 3일 이상 미배송
  note           TEXT
);

CREATE TABLE payments (
  payment_id  INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id    TEXT REFERENCES orders(order_id),
  paid_at     TEXT,
  method      TEXT,
  amount      INTEGER NOT NULL,
  fee         INTEGER DEFAULT 0,                  -- 플랫폼·카드 수수료
  settled_at  TEXT,                               -- 실제 입금일
  note        TEXT
);

CREATE TABLE cs_tickets (
  cs_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  opened_at   TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  customer_id TEXT REFERENCES customers(customer_id),
  order_id    TEXT REFERENCES orders(order_id),
  bottle_lot  TEXT REFERENCES bottlings(bottle_lot),
  type        TEXT CHECK (type IN ('배송','파손','품질','선물·대량','교환·반품','기타')),
  content     TEXT,
  status      TEXT DEFAULT '접수' CHECK (status IN ('접수','처리중','완료')),
  resolution  TEXT
);

CREATE TABLE experiences (
  exp_id      INTEGER PRIMARY KEY AUTOINCREMENT,
  exp_date    TEXT NOT NULL,
  program     TEXT NOT NULL,                      -- 견학, 시음, 담금체험, 수확체험
  customer_id TEXT REFERENCES customers(customer_id),
  headcount   INTEGER NOT NULL,
  price       INTEGER DEFAULT 0,
  status      TEXT DEFAULT '예약' CHECK (status IN ('예약','확정','완료','취소')),
  note        TEXT
);

-- ---------------------------------------------------------------------
-- 6. 사무·세무
-- ---------------------------------------------------------------------
CREATE TABLE grants (                              -- 지원사업
  grant_id    TEXT PRIMARY KEY,                   -- G-26-02
  name        TEXT NOT NULL,
  agency      TEXT,
  start_date  TEXT,
  end_date    TEXT,
  total_amount INTEGER,
  gov_amount  INTEGER,
  self_amount INTEGER,
  status      TEXT CHECK (status IN ('검토','신청','선정','수행','정산','종료','탈락')),
  folder_path TEXT,
  note        TEXT
);

CREATE TABLE expense_rules (                       -- 증빙 자동 분류 규칙
  rule_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  keyword     TEXT NOT NULL,                      -- 거래처명·적요에 포함된 단어
  account     TEXT NOT NULL,                      -- 계정과목
  allocation  TEXT NOT NULL CHECK (allocation IN ('직접','공통','판매비')),
  priority    INTEGER DEFAULT 100
);

CREATE TABLE expenses (
  expense_id    TEXT PRIMARY KEY,                 -- E-2611-034
  expense_date  TEXT NOT NULL,
  partner_id    TEXT REFERENCES partners(partner_id),
  vendor_name   TEXT,                             -- 증빙 원문 거래처명
  description   TEXT,
  account       TEXT,                             -- 비어 있으면 '미분류'
  supply_amount INTEGER NOT NULL,
  vat           INTEGER DEFAULT 0,
  total         INTEGER NOT NULL,
  evidence_type TEXT CHECK (evidence_type IN ('세금계산서','계산서','카드','현금영수증','간이영수증','기타')),
  evidence_path TEXT,
  allocation    TEXT CHECK (allocation IN ('직접','공통','판매비')),
  batch_id      TEXT REFERENCES batches(batch_id),
  grant_id      TEXT REFERENCES grants(grant_id),
  grant_share   TEXT CHECK (grant_share IN ('정부지원금','자부담')),
  source_key    TEXT UNIQUE                       -- 가져오기 중복 방지 키
);

CREATE TABLE tax_calendar (
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  due_date    TEXT NOT NULL,
  tax_type    TEXT NOT NULL,                      -- 주세, 부가세, 원천세, 법인세 …
  description TEXT,
  confirmed   INTEGER DEFAULT 0,                  -- 세무사 확인 여부
  status      TEXT DEFAULT '예정' CHECK (status IN ('예정','자료전달','완료')),
  done_at     TEXT
);

CREATE TABLE documents (                           -- 문서 색인·만료 관리
  doc_id       INTEGER PRIMARY KEY AUTOINCREMENT,
  category     TEXT NOT NULL,                     -- 인허가, 계약, 보험, 인증, 검사성적서 …
  title        TEXT NOT NULL,
  path         TEXT,
  related_type TEXT,
  related_id   TEXT,
  expires_at   TEXT,
  note         TEXT
);

CREATE TABLE schedule (                            -- 통합 일정 (생산·판매·시즌·기타)
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  due_date    TEXT NOT NULL,
  area        TEXT NOT NULL CHECK (area IN ('F','P','Q','I','S','C','O','T')),
  title       TEXT NOT NULL,
  ref_type    TEXT,
  ref_id      TEXT,
  done        INTEGER DEFAULT 0
);

-- ---------------------------------------------------------------------
-- 7. 자동 계산 화면 (뷰)
-- ---------------------------------------------------------------------
-- 품목·로트별 현재고
CREATE VIEW v_stock AS
SELECT m.item_code, i.name, i.category, m.lot_id, ROUND(SUM(m.qty), 3) AS qty, i.unit
FROM inventory_moves m JOIN items i ON i.item_code = m.item_code
GROUP BY m.item_code, m.lot_id
HAVING ROUND(SUM(m.qty), 3) <> 0;

-- 안전재고 미달 품목
CREATE VIEW v_stock_alert AS
SELECT i.item_code, i.name, i.unit, IFNULL(SUM(m.qty), 0) AS qty, i.safety_stock
FROM items i LEFT JOIN inventory_moves m ON m.item_code = i.item_code
WHERE i.active = 1
GROUP BY i.item_code
HAVING IFNULL(SUM(m.qty), 0) < i.safety_stock;

-- 배치별 원료비
CREATE VIEW v_batch_material_cost AS
SELECT b.batch_id, b.product_line, b.start_date,
       ROUND(SUM(bi.qty * IFNULL(ml.unit_price, 0)), 0) AS material_cost
FROM batches b
JOIN batch_inputs bi ON bi.batch_id = b.batch_id
JOIN material_lots ml ON ml.lot_id = bi.lot_id
GROUP BY b.batch_id;

-- 월별 반출 집계 (주세 신고 보조 자료의 기초)
CREATE VIEW v_monthly_release AS
SELECT substr(s.ship_date, 1, 7)                       AS ym,
       p.liquor_type, p.sku, p.volume_ml, p.abv,
       SUM(oi.qty)                                     AS bottles,
       ROUND(SUM(oi.qty) * p.volume_ml / 1000.0, 3)    AS liters,
       ROUND(SUM(oi.qty) * p.volume_ml / 1000.0 * p.abv / 100.0, 3) AS pure_alcohol_l,
       SUM(oi.amount)                                  AS amount
FROM shipments s
JOIN orders o       ON o.order_id = s.order_id
JOIN order_items oi ON oi.order_id = o.order_id
JOIN products p     ON p.sku = oi.sku
WHERE s.is_tax_release = 1 AND o.status NOT IN ('취소')
GROUP BY ym, p.sku;

-- 고객별 구매 요약 (등급·재구매 안내용)
CREATE VIEW v_customer_summary AS
SELECT c.customer_id, c.name, c.grade, c.consent_marketing,
       COUNT(DISTINCT o.order_id)  AS orders,
       IFNULL(SUM(o.total_amount), 0) AS total_amount,
       MAX(o.order_date)           AS last_order
FROM customers c LEFT JOIN orders o
  ON o.customer_id = c.customer_id AND o.status NOT IN ('취소','반품')
GROUP BY c.customer_id;

-- 병입로트 → 원료·필지 역추적 (배치에서 직접 병입한 경우)
CREATE VIEW v_trace_direct AS
SELECT bt.bottle_lot, bt.sku, b.batch_id, bi.lot_id AS material_lot,
       ml.item_code, ml.source_type, ml.harvest_lot, h.field_id, ml.partner_id
FROM bottlings bt
JOIN batches b        ON bt.source_type = 'batch' AND b.batch_id = bt.source_id
JOIN batch_inputs bi  ON bi.batch_id = b.batch_id
JOIN material_lots ml ON ml.lot_id = bi.lot_id
LEFT JOIN harvests h  ON h.harvest_lot = ml.harvest_lot;
-- 증류·숙성·블렌드를 거친 경우의 다단계 추적은 자동화 프로그램(A-23)에서 처리


-- ---------------------------------------------------------------------
-- 8. 마케팅·서비스·매출·출고 확장 + 하네스 (v0.2)
-- ---------------------------------------------------------------------
CREATE TABLE campaigns (
  campaign_id  TEXT PRIMARY KEY,                  -- CP-27-SEOL
  name         TEXT NOT NULL,
  season       TEXT,                              -- 설, 추석, 연말, 한정판, 상시
  start_date   TEXT, end_date TEXT,
  target_sku   TEXT REFERENCES products(sku),
  channels     TEXT,
  budget       INTEGER DEFAULT 0,
  goal_amount  INTEGER,
  limited_qty  INTEGER,
  status       TEXT DEFAULT '기획' CHECK (status IN ('기획','준비','진행','종료','취소')),
  note         TEXT
);

CREATE TABLE contents (
  content_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  channel        TEXT NOT NULL,                   -- 인스타, 쇼츠, 블로그, 스마트스토어, 카톡채널
  planned_date   TEXT,
  published_date TEXT,
  title          TEXT,
  campaign_id    TEXT REFERENCES campaigns(campaign_id),
  loop_q_id      INTEGER,                         -- 답하는 루프 질문
  harness_run_id INTEGER,
  real_photo     INTEGER DEFAULT 1,               -- 실사진 사용 여부
  status         TEXT DEFAULT '기획' CHECK (status IN ('기획','초안','승인','게시','보류')),
  url            TEXT,
  views INTEGER, clicks INTEGER, orders INTEGER,
  note           TEXT
);

CREATE TABLE loop_questions (                      -- 고객(과 고객의 AI)이 물을 상황별 질문
  q_id          INTEGER PRIMARY KEY AUTOINCREMENT,
  situation     TEXT NOT NULL,                    -- 명절선물, 페어링, 원료, 지역, 한정, 기업선물
  question      TEXT NOT NULL,
  target_sku    TEXT REFERENCES products(sku),
  answer_path   TEXT,                             -- 공식 답이 있는 문서·페이지
  last_checked  TEXT
);

CREATE TABLE ai_visibility_checks (                -- AI 간택 진단 (H06)
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  check_date    TEXT NOT NULL,
  ai_service    TEXT NOT NULL,
  q_id          INTEGER REFERENCES loop_questions(q_id),
  question      TEXT,
  appeared      INTEGER NOT NULL,                 -- 킹스양조장이 나왔나 (0/1)
  correct       INTEGER,                          -- 정보가 맞았나 (0/1, 안 나오면 NULL)
  wrong_detail  TEXT,
  competitors   TEXT,                             -- 대신 나온 곳
  action        TEXT                              -- 정정, 보강, 확대
);

CREATE TABLE reviews (
  review_id    INTEGER PRIMARY KEY AUTOINCREMENT,
  channel      TEXT NOT NULL,
  order_id     TEXT REFERENCES orders(order_id),
  customer_id  TEXT REFERENCES customers(customer_id),
  rating       INTEGER CHECK (rating BETWEEN 1 AND 5),
  content      TEXT,
  posted_at    TEXT,
  reply        TEXT,
  replied_at   TEXT,
  issue_flag   INTEGER DEFAULT 0,                 -- 평점 3 이하 → CS 연결
  cs_id        INTEGER REFERENCES cs_tickets(cs_id)
);

CREATE TABLE review_requests (                     -- D+3 후기 요청 대기열
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id     TEXT NOT NULL REFERENCES orders(order_id),
  due_date     TEXT NOT NULL,
  sent_at      TEXT,
  status       TEXT DEFAULT '대기' CHECK (status IN ('대기','발송','제외'))
);

CREATE TABLE settlements (                         -- 플랫폼 정산
  id           INTEGER PRIMARY KEY AUTOINCREMENT,
  channel      TEXT NOT NULL,
  period_start TEXT, period_end TEXT,
  gross        INTEGER NOT NULL,                  -- 주문 금액 합계
  fee          INTEGER DEFAULT 0,
  shipping     INTEGER DEFAULT 0,
  expected_net INTEGER,                           -- 계산된 정산 예정액
  paid_amount  INTEGER,                           -- 실제 입금액
  paid_at      TEXT,
  matched      INTEGER DEFAULT 0,                 -- 대사 일치 여부
  note         TEXT
);

CREATE TABLE returns (
  return_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  order_id      TEXT NOT NULL REFERENCES orders(order_id),
  type          TEXT CHECK (type IN ('반품','교환','파손재발송')),
  reason        TEXT,
  approved      INTEGER DEFAULT 0,                -- 대표 승인
  received_at   TEXT,
  restock       INTEGER DEFAULT 0,                -- 재입고(1) / 폐기(0)
  refund_amount INTEGER DEFAULT 0,
  note          TEXT
);

CREATE TABLE harness_runs (                        -- 하네스 실행 기록
  run_id         INTEGER PRIMARY KEY AUTOINCREMENT,
  harness_code   TEXT NOT NULL,                   -- H01 ~ H10
  version        TEXT,
  started_at     TEXT DEFAULT (datetime('now','localtime')),
  finished_at    TEXT,
  provider       TEXT CHECK (provider IN ('cloud','local','off')),
  data_grade     TEXT CHECK (data_grade IN ('공개','내부','기밀','개인정보')),
  input_ref      TEXT,                            -- SKU, 지원사업 코드, 기간 등
  output_path    TEXT,
  fatal_count    INTEGER DEFAULT 0,
  warn_count     INTEGER DEFAULT 0,
  rollback_count INTEGER DEFAULT 0,
  result         TEXT CHECK (result IN ('통과','되돌림','반려','진행중')),
  owner_approved INTEGER DEFAULT 0,
  cost_won       REAL DEFAULT 0,
  note           TEXT
);

-- 일별·채널별 매출
CREATE VIEW v_sales_daily AS
SELECT order_date, channel, COUNT(*) AS orders, SUM(total_amount) AS amount,
       ROUND(AVG(total_amount)) AS avg_order
FROM orders WHERE status NOT IN ('취소','반품')
GROUP BY order_date, channel;

-- 오늘 출고 대상과 보류
CREATE VIEW v_ship_queue AS
SELECT o.order_id, o.order_date, o.channel, o.customer_id, o.adult_checked,
       CASE WHEN o.adult_checked = 0 THEN '성인 미인증' END AS hold_reason
FROM orders o
LEFT JOIN shipments s ON s.order_id = o.order_id
WHERE o.status IN ('접수','결제완료') AND s.shipment_id IS NULL;

-- 재구매 안내 대상 (마케팅 동의 + 120일 이상 미구매)
CREATE VIEW v_reorder_targets AS
SELECT customer_id, name, grade, orders, total_amount, last_order
FROM v_customer_summary
WHERE consent_marketing = 1 AND orders >= 1
  AND julianday('now') - julianday(last_order) >= 120;

-- 미정산·불일치
CREATE VIEW v_settlement_gap AS
SELECT channel, period_start, period_end, expected_net, paid_amount,
       IFNULL(paid_amount,0) - IFNULL(expected_net,0) AS gap
FROM settlements WHERE matched = 0;

-- AI 간택 진단 최신 결과
CREATE VIEW v_ai_visibility_latest AS
SELECT a.ai_service, COALESCE(a.question, q.question) AS question, q.situation,
       a.appeared, a.correct, a.wrong_detail, a.competitors, a.check_date
FROM ai_visibility_checks a LEFT JOIN loop_questions q ON q.q_id = a.q_id
WHERE a.check_date = (SELECT MAX(check_date) FROM ai_visibility_checks);

-- 하네스별 월간 품질·비용
CREATE VIEW v_harness_monthly AS
SELECT substr(started_at,1,7) AS ym, harness_code, COUNT(*) AS runs,
       SUM(result = '통과') AS passed, SUM(rollback_count) AS rollbacks,
       SUM(fatal_count) AS fatals, ROUND(SUM(cost_won)) AS cost_won,
       SUM(provider = 'local') AS local_runs
FROM harness_runs GROUP BY ym, harness_code;
