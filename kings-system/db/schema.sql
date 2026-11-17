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


-- ---------------------------------------------------------------------
-- 9. AI 운영 조직 (v0.3): 부서·목표·업무·이벤트·권한·상신·예외·현장 지시
-- ---------------------------------------------------------------------
CREATE TABLE departments (
  dept_code  TEXT PRIMARY KEY,                    -- MKT_INT, PRODUCT, BRAND, SALES, CRM, PLAN, FIN, QA, EXT, COO, BOARD
  name       TEXT NOT NULL,
  mission    TEXT
);

CREATE TABLE goals (                               -- 목표 트리: 분기 → 월 → 주
  goal_id    INTEGER PRIMARY KEY AUTOINCREMENT,
  parent_id  INTEGER REFERENCES goals(goal_id),
  level      TEXT NOT NULL CHECK (level IN ('연','분기','월','주')),
  period     TEXT NOT NULL,                       -- 2027-Q1, 2027-02, 2027-W06
  dept_code  TEXT REFERENCES departments(dept_code),
  title      TEXT NOT NULL,
  metric     TEXT,                                -- 측정 지표
  target     REAL,
  actual     REAL,
  status     TEXT DEFAULT '진행' CHECK (status IN ('진행','달성','미달','취소'))
);

CREATE TABLE events (                              -- 자동 실행의 시작점
  event_id    INTEGER PRIMARY KEY AUTOINCREMENT,
  occurred_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  event_type  TEXT NOT NULL,                      -- 주문발생, 재고부족, 문의접수, 마감도래, 실적변화, 배송지연, 저평점, 발효이상, AI노출변화, 플랫폼정책
  ref_type    TEXT, ref_id TEXT,
  payload     TEXT,
  handled     INTEGER DEFAULT 0
);

CREATE TABLE tasks (                               -- 업무 티켓 (AI 총괄이 생성·배정)
  task_id      INTEGER PRIMARY KEY AUTOINCREMENT,
  goal_id      INTEGER REFERENCES goals(goal_id),
  event_id     INTEGER REFERENCES events(event_id),
  dept_code    TEXT NOT NULL REFERENCES departments(dept_code),
  role         TEXT NOT NULL CHECK (role IN ('조사','판단','제작','실행','검수')),
  title        TEXT NOT NULL,
  executor     TEXT NOT NULL CHECK (executor IN ('AI','규칙','대표','외주','단기인력','설비')),
  harness_code TEXT,
  input_ref    TEXT,                              -- 입력 파일·레코드
  output_ref   TEXT,                              -- 산출물
  prev_task_id INTEGER REFERENCES tasks(task_id),  -- 부서 간 인계
  due_at       TEXT,
  status       TEXT DEFAULT '대기' CHECK (status IN ('대기','진행','검수','완료','되돌림','상신','예외','취소')),
  retries      INTEGER DEFAULT 0,
  created_at   TEXT DEFAULT (datetime('now','localtime')),
  done_at      TEXT
);

CREATE TABLE authority_rules (                     -- 권한표 (대표 확정, 변경은 rule_changes)
  rule_id     INTEGER PRIMARY KEY AUTOINCREMENT,
  domain      TEXT NOT NULL CHECK (domain IN ('예산','가격','수량','발신','수정','데이터')),
  action      TEXT NOT NULL,                      -- 부자재발주, 할인적용, 파손재발송 …
  limit_value REAL,                               -- 한도 (금액·수량·비율)
  limit_unit  TEXT,
  condition   TEXT,                               -- 기존 거래처, 승인된 캠페인 등
  version     TEXT NOT NULL,
  active      INTEGER DEFAULT 1
);

CREATE TABLE approvals (                           -- 상신과 결재
  approval_id INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id     INTEGER REFERENCES tasks(task_id),
  dept_code   TEXT REFERENCES departments(dept_code),
  rule_id     INTEGER REFERENCES authority_rules(rule_id),   -- 넘은 권한
  title       TEXT NOT NULL,
  options     TEXT,                               -- 선택지와 추천안
  cost_risk   TEXT,
  due_at      TEXT,
  requested_at TEXT DEFAULT (datetime('now','localtime')),
  decision    TEXT CHECK (decision IN ('승인','반려','수정승인','보류')),
  decided_at  TEXT,
  comment     TEXT
);

CREATE TABLE exceptions (                          -- 자동 복구 실패 → 대표
  exc_id      INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id     INTEGER REFERENCES tasks(task_id),
  severity    TEXT NOT NULL CHECK (severity IN ('긴급','높음','보통')),
  dept_code   TEXT REFERENCES departments(dept_code),
  summary     TEXT NOT NULL,
  attempts    TEXT,                               -- 시도 내역
  recommend   TEXT,                               -- 추천 조치
  opened_at   TEXT DEFAULT (datetime('now','localtime')),
  closed_at   TEXT,
  resolution  TEXT
);

CREATE TABLE work_orders (                         -- 현장 작업 지시서
  wo_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  task_id      INTEGER REFERENCES tasks(task_id),
  work_type    TEXT NOT NULL CHECK (work_type IN ('담금','발효점검','증류','숙성점검','블렌딩','병입','검사','포장','출고','재발송','조립','설비점검','외주발주','기타')),
  target_ref   TEXT,                              -- 배치·로트·주문
  qty          REAL,
  sop_ref      TEXT,
  assignee     TEXT NOT NULL CHECK (assignee IN ('대표','단기인력','외주','설비','택배')),
  partner_id   TEXT REFERENCES partners(partner_id),
  due_at       TEXT,
  accepted_at  TEXT,                              -- 접수 확인
  done_at      TEXT,
  proof        TEXT,                              -- 완료 증빙 (수량·사진 경로·측정값·납품서)
  status       TEXT DEFAULT '발행' CHECK (status IN ('발행','접수','진행','완료','지연','취소')),
  reminders    INTEGER DEFAULT 0
);

CREATE TABLE contracts (
  contract_id  TEXT PRIMARY KEY,
  partner_id   TEXT REFERENCES partners(partner_id),
  type         TEXT CHECK (type IN ('공급','납품','외주','임대','보험','지원사업','기타')),
  title        TEXT NOT NULL,
  start_date   TEXT, end_date TEXT,
  amount       INTEGER,
  terms        TEXT,
  file_path    TEXT,
  renew_notice INTEGER DEFAULT 30                 -- 만료 며칠 전 알림
);

CREATE TABLE rule_changes (                        -- 중요 규칙 변경 통제
  change_id    INTEGER PRIMARY KEY AUTOINCREMENT,
  target       TEXT NOT NULL,                     -- 권한표, 하한선 공식, 주세 집계, 검수 기준, 위임 단계 …
  importance   TEXT NOT NULL CHECK (importance IN ('일반','중요')),
  before_value TEXT, after_value TEXT,
  reason       TEXT,
  proposed_by  TEXT,
  approval_id  INTEGER REFERENCES approvals(approval_id),
  tested       INTEGER DEFAULT 0,
  rollback_plan TEXT,
  applied_at   TEXT,
  version      TEXT
);

CREATE TABLE metrics_monthly (
  ym          TEXT NOT NULL,
  dept_code   TEXT NOT NULL REFERENCES departments(dept_code),
  metric      TEXT NOT NULL,
  value       REAL,
  target      REAL,
  PRIMARY KEY (ym, dept_code, metric)
);

-- 일일 결재 목록: 상신 대기 + 열린 예외
CREATE VIEW v_board_inbox AS
SELECT '상신' AS kind, approval_id AS id, dept_code, title AS summary, due_at AS due, NULL AS severity
FROM approvals WHERE decision IS NULL
UNION ALL
SELECT '예외', exc_id, dept_code, summary, NULL, severity
FROM exceptions WHERE closed_at IS NULL;

-- 부서별 업무 현황
CREATE VIEW v_dept_workload AS
SELECT dept_code,
       SUM(status IN ('대기','진행','검수')) AS open_tasks,
       SUM(status = '완료') AS done_tasks,
       SUM(status = '되돌림') AS rollbacks,
       SUM(status IN ('상신','예외')) AS escalated,
       SUM(executor = 'AI') AS ai_tasks, SUM(executor = '규칙') AS rule_tasks
FROM tasks GROUP BY dept_code;

-- 열린 현장 작업 지시서 (미접수·지연 포함)
CREATE VIEW v_open_work_orders AS
SELECT wo_id, work_type, target_ref, qty, assignee, due_at, status, reminders,
       CASE WHEN accepted_at IS NULL THEN '미접수'
            WHEN due_at < datetime('now','localtime') THEN '마감초과' END AS alert
FROM work_orders WHERE status NOT IN ('완료','취소');

-- 처리 안 된 이벤트
CREATE VIEW v_unhandled_events AS
SELECT event_id, occurred_at, event_type, ref_type, ref_id FROM events WHERE handled = 0;

-- 기본 부서
INSERT INTO departments VALUES
 ('BOARD','대표·경영 이사회','비전·자본 배분·제품 철학·중대 예외'),
 ('COO','AI 총괄 운영','목표 분해·배정·일정·인계·성과 확인'),
 ('MKT_INT','시장정보','바깥 변화를 먼저 안다'),
 ('PRODUCT','상품전략','무엇을 얼마에 몇 병 만들지 제안한다'),
 ('BRAND','브랜드','고객과 고객의 AI에게 보인다'),
 ('SALES','영업','매출을 만든다'),
 ('CRM','고객관리','경험을 다음 구매로 잇는다'),
 ('PLAN','생산계획','팔릴 만큼, 제때, 품질대로 만든다'),
 ('FIN','재무관리','돈과 세금을 지킨다'),
 ('QA','품질준법','사고와 위반을 막는다'),
 ('EXT','대외사업','외부 자원을 가져온다');


-- ---------------------------------------------------------------------
-- 10. 판매·관리 시스템 (v0.4): 채널·상품등록·광고·세금계산서·결산·재고실사·수출·수입
-- ---------------------------------------------------------------------
CREATE TABLE channels (
  channel_code      TEXT PRIMARY KEY,             -- SS(스마트스토어), MALL(자사몰), OM1(오픈마켓), KAKAO, OFF, B2B, EXPORT
  name              TEXT NOT NULL,
  type              TEXT CHECK (type IN ('오픈마켓','자사몰','메신저','오프라인','B2B','수출')),
  fee_rate          REAL DEFAULT 0,               -- 수수료율 (%)
  settle_cycle_days INTEGER,                      -- 정산 주기
  adult_verify      TEXT,                         -- 성인 인증 방식
  active            INTEGER DEFAULT 1,
  note              TEXT
);

CREATE TABLE channel_listings (                    -- 채널별 상품 등록
  listing_id         INTEGER PRIMARY KEY AUTOINCREMENT,
  channel_code       TEXT NOT NULL REFERENCES channels(channel_code),
  sku                TEXT NOT NULL REFERENCES products(sku),
  channel_product_no TEXT,
  url                TEXT,
  listed_price       INTEGER,                     -- 채널에 실제 올라간 가격
  approved_price     INTEGER,                     -- 승인된 가격
  listed_stock       INTEGER,
  adult_setting      INTEGER DEFAULT 0,           -- 성인 인증 설정 확인
  compliance_ok      INTEGER DEFAULT 0,           -- 품질준법 검수 통과
  status             TEXT DEFAULT '준비' CHECK (status IN ('준비','검수','판매중','품절','중지')),
  last_synced        TEXT,
  UNIQUE (channel_code, sku)
);

CREATE TABLE ad_campaigns (
  ad_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  platform     TEXT NOT NULL,
  campaign_id  TEXT REFERENCES campaigns(campaign_id),
  sku          TEXT REFERENCES products(sku),
  approval_id  INTEGER REFERENCES approvals(approval_id),   -- 광고비 결재
  start_date   TEXT, end_date TEXT,
  budget       INTEGER NOT NULL,
  target_roas  REAL,                              -- 목표 ROAS (매출/광고비, 배)
  status       TEXT DEFAULT '계획' CHECK (status IN ('계획','검수','집행','중지','종료'))
);

CREATE TABLE ad_daily (                            -- 광고 일일 실적
  ad_id       INTEGER NOT NULL REFERENCES ad_campaigns(ad_id),
  day         TEXT NOT NULL,
  spend       INTEGER DEFAULT 0,
  impressions INTEGER, clicks INTEGER, orders INTEGER,
  revenue     INTEGER DEFAULT 0,
  PRIMARY KEY (ad_id, day)
);

CREATE TABLE tax_invoices (                        -- 전자세금계산서 발행·수취
  ti_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  direction    TEXT NOT NULL CHECK (direction IN ('발행','수취')),
  issue_date   TEXT NOT NULL,
  supply_month TEXT,                              -- 공급 월 (월 합계 발행)
  partner_id   TEXT REFERENCES partners(partner_id),
  supply_amount INTEGER NOT NULL,
  vat          INTEGER NOT NULL,
  approval_no  TEXT,                              -- 국세청 승인번호
  order_id     TEXT REFERENCES orders(order_id),
  expense_id   TEXT REFERENCES expenses(expense_id),
  kind         TEXT DEFAULT '정상' CHECK (kind IN ('정상','수정','취소')),
  status       TEXT DEFAULT '발행' CHECK (status IN ('예정','발행','전송','취소'))
);

CREATE TABLE closing_tasks (                       -- 월·연 결산 체크리스트
  ym          TEXT NOT NULL,                      -- 2027-06 또는 2027-Y
  item_no     INTEGER NOT NULL,
  item        TEXT NOT NULL,
  dept_code   TEXT REFERENCES departments(dept_code),
  due_date    TEXT,
  status      TEXT DEFAULT '대기' CHECK (status IN ('대기','진행','완료','상신')),
  done_at     TEXT,
  note        TEXT,
  PRIMARY KEY (ym, item_no)
);

CREATE TABLE inventory_counts (                    -- 재고 점검·실사
  count_id    INTEGER PRIMARY KEY AUTOINCREMENT,
  count_date  TEXT NOT NULL,
  count_type  TEXT CHECK (count_type IN ('주간간이','월실사','분기원액','연말')),
  item_code   TEXT NOT NULL REFERENCES items(item_code),
  lot_id      TEXT,
  book_qty    REAL NOT NULL,
  actual_qty  REAL NOT NULL,
  reason      TEXT,
  adjusted    INTEGER DEFAULT 0,                  -- 조정 기록 반영 여부
  wo_id       INTEGER REFERENCES work_orders(wo_id)
);

CREATE TABLE export_deals (
  deal_id      TEXT PRIMARY KEY,                  -- EX-27-001
  buyer_id     TEXT REFERENCES partners(partner_id),
  country      TEXT NOT NULL,
  incoterm     TEXT,                              -- EXW, FOB, CIF …
  currency     TEXT DEFAULT 'USD',
  amount_fx    REAL,
  fx_rate      REAL,
  amount_krw   INTEGER,
  payment_term TEXT,                              -- 선금, T/T, L/C …
  stage        TEXT DEFAULT '견적' CHECK (stage IN ('발굴','견적','샘플','계약','준비','서류','선적','입금','완료','중단')),
  ship_date    TEXT,
  approval_id  INTEGER REFERENCES approvals(approval_id),
  note         TEXT
);

CREATE TABLE export_docs (
  deal_id   TEXT NOT NULL REFERENCES export_deals(deal_id),
  doc_type  TEXT NOT NULL,                        -- 인보이스, 패킹리스트, 원산지증명, 성적서, 수출신고, B/L, 현지라벨 …
  status    TEXT DEFAULT '필요' CHECK (status IN ('필요','작성','완료','해당없음')),
  path      TEXT,
  PRIMARY KEY (deal_id, doc_type)
);

CREATE TABLE imports (                             -- 해외 구매 (오크통·병·설비)
  import_id     TEXT PRIMARY KEY,                 -- IM-27-001
  partner_id    TEXT REFERENCES partners(partner_id),
  item_code     TEXT REFERENCES items(item_code),
  country       TEXT,
  qty           REAL,
  currency      TEXT, amount_fx REAL, fx_rate REAL,
  freight       INTEGER DEFAULT 0,
  duty          INTEGER DEFAULT 0,
  customs_fee   INTEGER DEFAULT 0,
  import_vat    INTEGER DEFAULT 0,
  food_contact_report INTEGER,                    -- 식품용 기구 수입 신고 필요/완료 (확인 필요)
  stage         TEXT DEFAULT '결정' CHECK (stage IN ('결정','발주','송금','운송','통관','입고','완료')),
  arrival_date  TEXT,
  approval_id   INTEGER REFERENCES approvals(approval_id)
);

-- 채널 가격·검수 불일치
CREATE VIEW v_listing_mismatch AS
SELECT channel_code, sku, listed_price, approved_price, adult_setting, compliance_ok, status
FROM channel_listings
WHERE status IN ('판매중','검수')
  AND (listed_price <> approved_price OR adult_setting = 0 OR compliance_ok = 0);

-- 광고 성과 (ROAS) 와 경고
CREATE VIEW v_ad_roas AS
SELECT a.ad_id, a.platform, a.sku, a.budget, a.target_roas,
       SUM(d.spend) AS spend, SUM(d.revenue) AS revenue,
       ROUND(1.0 * SUM(d.revenue) / NULLIF(SUM(d.spend),0), 2) AS roas,
       CASE WHEN 1.0 * SUM(d.revenue) / NULLIF(SUM(d.spend),0) < a.target_roas * 0.5 THEN '중지 검토' END AS alert
FROM ad_campaigns a LEFT JOIN ad_daily d ON d.ad_id = a.ad_id
GROUP BY a.ad_id;

-- B2B 미수금
CREATE VIEW v_receivables AS
SELECT o.order_id, o.partner_id, o.order_date, o.total_amount,
       IFNULL(SUM(p.amount),0) AS paid,
       o.total_amount - IFNULL(SUM(p.amount),0) AS balance
FROM orders o LEFT JOIN payments p ON p.order_id = o.order_id
WHERE o.channel = 'B2B' AND o.status NOT IN ('취소','반품')
GROUP BY o.order_id
HAVING balance > 0;

-- B2B 출고했는데 세금계산서 없는 건
CREATE VIEW v_missing_tax_invoice AS
SELECT o.order_id, o.partner_id, s.ship_date, o.total_amount
FROM orders o JOIN shipments s ON s.order_id = o.order_id
LEFT JOIN tax_invoices t ON t.order_id = o.order_id AND t.direction = '발행' AND t.status <> '취소'
WHERE o.channel = 'B2B' AND t.ti_id IS NULL;

-- 결산 진행 현황
CREATE VIEW v_closing_status AS
SELECT ym, COUNT(*) AS items, SUM(status = '완료') AS done,
       SUM(status <> '완료') AS remaining
FROM closing_tasks GROUP BY ym;

-- 재고 실사 차이와 처리 구분
CREATE VIEW v_count_diff AS
SELECT count_date, count_type, item_code, lot_id, book_qty, actual_qty,
       actual_qty - book_qty AS diff,
       ROUND(100.0 * ABS(actual_qty - book_qty) / NULLIF(book_qty,0), 2) AS diff_pct,
       CASE WHEN ABS(actual_qty - book_qty) <= book_qty * 0.01 THEN '조정'
            WHEN ABS(actual_qty - book_qty) <= book_qty * 0.03 THEN '사유조사'
            ELSE '예외(대표)' END AS action
FROM inventory_counts WHERE adjusted = 0;

-- 수입 건 입고 단가 (관세·운임 포함)
CREATE VIEW v_import_landed_cost AS
SELECT import_id, item_code, qty,
       ROUND(amount_fx * fx_rate) AS goods_krw,
       ROUND(amount_fx * fx_rate + freight + duty + customs_fee) AS landed_krw,
       ROUND((amount_fx * fx_rate + freight + duty + customs_fee) / NULLIF(qty,0)) AS unit_cost
FROM imports;


-- ---------------------------------------------------------------------
-- 11. 결과 책임 운영 단위·위임장·상태 모형·상품 피드 (v0.5)
-- ---------------------------------------------------------------------
CREATE TABLE units (                               -- 결과 책임 운영 단위
  unit_code   TEXT PRIMARY KEY,                   -- U1_NEW ~ U6_RELIABILITY
  name        TEXT NOT NULL,
  outcome     TEXT NOT NULL                       -- 끝까지 책임질 결과
);

CREATE TABLE unit_mandates (                       -- 업무 위임장 (대표 발행)
  mandate_id   INTEGER PRIMARY KEY AUTOINCREMENT,
  unit_code    TEXT NOT NULL REFERENCES units(unit_code),
  version      TEXT NOT NULL,
  goal         TEXT NOT NULL,                     -- 목표
  discretion   TEXT NOT NULL,                     -- 재량
  evidence     TEXT NOT NULL,                     -- 증거 (원본 자료)
  done_when    TEXT NOT NULL,                     -- 완료 조건
  escalate_if  TEXT NOT NULL,                     -- 예외 조건과 대상
  absence_rule TEXT NOT NULL CHECK (absence_rule IN ('보류','기존조건유지','대행')),
  absence_hours INTEGER DEFAULT 48,               -- 무응답 기준 시간
  approval_id  INTEGER REFERENCES approvals(approval_id),   -- 대표 결재
  valid_from   TEXT, valid_to TEXT,
  active       INTEGER DEFAULT 1
);

CREATE TABLE unit_runs (                           -- 업무 진행 기록부 (AI 밖에 두는 상태)
  run_id        INTEGER PRIMARY KEY AUTOINCREMENT,
  unit_code     TEXT NOT NULL REFERENCES units(unit_code),
  mandate_id    INTEGER REFERENCES unit_mandates(mandate_id),
  event_id      INTEGER REFERENCES events(event_id),
  title         TEXT NOT NULL,
  current_step  TEXT,
  steps_done    INTEGER DEFAULT 0,
  external_results INTEGER DEFAULT 0,             -- 발송·등록·주문·입금 등 외부 결과 수
  internal_docs INTEGER DEFAULT 0,                -- AI 간 중간 문서 수
  state_note    TEXT,                             -- 다음에 이어서 할 일 (재개용)
  outcome_ref   TEXT,                             -- 결과 레코드 (주문·입금 등)
  outcome_value REAL,                             -- 이익·회수액 등
  owner_touches INTEGER DEFAULT 0,                -- 대표 개입 횟수
  total_cost    REAL DEFAULT 0,                   -- AI + 검수 + 재작업 + 외주
  started_at    TEXT DEFAULT (datetime('now','localtime')),
  last_progress TEXT,
  ended_at      TEXT,
  status        TEXT DEFAULT '진행' CHECK (status IN ('진행','대기','완료','실패','예외','보류'))
);

CREATE TABLE value_transfers (                     -- 가치 이전 (할인·환불·적립·무상·무료배송)
  id          INTEGER PRIMARY KEY AUTOINCREMENT,
  occurred_at TEXT NOT NULL DEFAULT (datetime('now','localtime')),
  kind        TEXT NOT NULL CHECK (kind IN ('할인','환불','적립금','무상제공','무료배송')),
  amount      INTEGER NOT NULL,
  order_id    TEXT REFERENCES orders(order_id),
  unit_code   TEXT REFERENCES units(unit_code),
  approved_by TEXT                                -- 위임장 / 대표
);

CREATE TABLE product_bom (                         -- 세트·제품 구성표
  sku        TEXT NOT NULL REFERENCES products(sku),
  item_code  TEXT NOT NULL REFERENCES items(item_code),
  qty        REAL NOT NULL,                       -- 1세트(1병)당 소요량
  unit       TEXT NOT NULL,
  PRIMARY KEY (sku, item_code)
);

CREATE TABLE packing_capacity (                    -- 포장 능력
  sku            TEXT NOT NULL REFERENCES products(sku),
  sets_per_hour  REAL NOT NULL,
  hours_per_week REAL NOT NULL,                   -- 대표 + 대행 파트너 가용 시간
  valid_from     TEXT,
  PRIMARY KEY (sku)
);

CREATE TABLE cash_events (                         -- 현금 흐름 예정
  id         INTEGER PRIMARY KEY AUTOINCREMENT,
  due_date   TEXT NOT NULL,
  direction  TEXT NOT NULL CHECK (direction IN ('입금','지급')),
  amount     INTEGER NOT NULL,
  source     TEXT,                                -- 정산, B2B, 세금, 급여, 발주안 …
  certainty  TEXT DEFAULT '확정' CHECK (certainty IN ('확정','예상','시나리오')),
  ref_id     TEXT
);

CREATE TABLE cash_balance (                        -- 기준일 현금 잔고
  as_of   TEXT PRIMARY KEY,
  amount  INTEGER NOT NULL
);

CREATE TABLE price_rules (                         -- 거래 가능한 가격 조건
  rule_id      INTEGER PRIMARY KEY AUTOINCREMENT,
  sku          TEXT NOT NULL REFERENCES products(sku),
  channel_code TEXT REFERENCES channels(channel_code),
  min_qty      INTEGER DEFAULT 1,
  price        INTEGER NOT NULL,
  condition    TEXT,                              -- B2B, 시즌, 선물 구성 등
  valid_from   TEXT, valid_to TEXT,
  approval_id  INTEGER REFERENCES approvals(approval_id)
);

ALTER TABLE products ADD COLUMN lead_days INTEGER DEFAULT 2;           -- 주문 후 출고까지
ALTER TABLE products ADD COLUMN adult_only INTEGER DEFAULT 1;

-- 세트별 생산·포장 가능 수량 (재료 최솟값 vs 포장 능력)
CREATE VIEW v_set_capacity AS
WITH stock AS (
  SELECT item_code, SUM(qty) AS qty FROM inventory_moves GROUP BY item_code
), by_item AS (
  SELECT b.sku, b.item_code, IFNULL(s.qty,0) AS on_hand, b.qty AS per_set,
         CAST(IFNULL(s.qty,0) / b.qty AS INTEGER) AS sets_possible
  FROM product_bom b LEFT JOIN stock s ON s.item_code = b.item_code
)
SELECT bi.sku,
       MIN(bi.sets_possible) AS material_limit,
       (SELECT item_code FROM by_item x WHERE x.sku = bi.sku ORDER BY sets_possible LIMIT 1) AS bottleneck_item,
       CAST(pc.sets_per_hour * pc.hours_per_week AS INTEGER) AS weekly_packing_limit
FROM by_item bi LEFT JOIN packing_capacity pc ON pc.sku = bi.sku
GROUP BY bi.sku;

-- 주별 현금 곡선 (기준 잔고 + 예정 입출금 누적)
CREATE VIEW v_cash_projection AS
WITH base AS (SELECT amount AS base_amount, as_of FROM cash_balance ORDER BY as_of DESC LIMIT 1),
wk AS (
  SELECT strftime('%Y-W%W', e.due_date) AS week,
         SUM(CASE WHEN e.direction = '입금' THEN e.amount ELSE -e.amount END) AS net
  FROM cash_events e, base b WHERE e.due_date >= b.as_of
  GROUP BY week
)
SELECT week, net,
       (SELECT base_amount FROM base) + SUM(net) OVER (ORDER BY week) AS projected_balance
FROM wk;

-- 월별 가치 이전 총액
CREATE VIEW v_value_transfer_monthly AS
SELECT substr(occurred_at,1,7) AS ym, SUM(amount) AS total,
       SUM(kind='할인') AS discounts, SUM(kind='환불') AS refunds,
       SUM(kind IN ('적립금','무상제공','무료배송')) AS others
FROM value_transfers GROUP BY ym;

-- 무진전 감지: 5단계 이상인데 외부 결과 0, 또는 중간 문서 3개 초과
CREATE VIEW v_stalled_runs AS
SELECT run_id, unit_code, title, steps_done, external_results, internal_docs, last_progress
FROM unit_runs
WHERE status = '진행' AND ((steps_done >= 5 AND external_results = 0) OR internal_docs > 3);

-- 단위별 핵심 지표
CREATE VIEW v_unit_kpi AS
SELECT unit_code,
       COUNT(*) AS runs,
       SUM(status = '완료') AS completed,
       ROUND(100.0 * SUM(status = '완료' AND owner_touches = 0) / NULLIF(SUM(status = '완료'),0), 1) AS no_owner_rate_pct,
       ROUND(SUM(total_cost) / NULLIF(SUM(status = '완료'),0)) AS cost_per_done,
       ROUND(SUM(outcome_value)) AS outcome_total
FROM unit_runs GROUP BY unit_code;

-- 상품 피드 (거래 가능한 상품 정보의 공통 원본)
CREATE VIEW v_product_feed AS
SELECT p.sku, p.product_name, p.liquor_type, p.volume_ml, p.abv,
       p.price_retail, p.lead_days, p.adult_only,
       IFNULL((SELECT SUM(qty) FROM inventory_moves m WHERE m.item_code = p.item_code),0) AS stock_on_hand,
       (SELECT COUNT(*) FROM price_rules r WHERE r.sku = p.sku) AS price_rule_count,
       (SELECT GROUP_CONCAT(channel_code) FROM channel_listings l WHERE l.sku = p.sku AND l.status = '판매중') AS live_channels
FROM products p WHERE p.active = 1;

INSERT INTO units VALUES
 ('U1_NEW','신규 매출 확보','이익이 남는 신규 주문'),
 ('U2_ACCOUNT','거래처 운영','거래 성사와 대금 회수'),
 ('U3_RETAIN','고객 유지','재구매와 고객 유지'),
 ('U4_SUPPLY','수요·공급 조정','판매 가능한 재고와 납기 준수'),
 ('U5_CASH','현금·수익 관리','현금 상태와 주문별 수익 파악'),
 ('U6_RELIABILITY','운영 신뢰성 관리','업무 중단과 누락 최소화');
