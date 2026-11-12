/**
 * 킹스양조장 복합 양조기 제어판 온도 자동 기록기 (Google Apps Script)
 *
 * 흐름: Seeker(GiGAeyes 화면 캡처) → 이 웹앱(doPost) → Claude 판독
 *       → '기록' 시트 저장 → 기준 벗어나면 텔레그램 알림
 *
 * 스크립트 속성(프로젝트 설정 → 스크립트 속성)에 넣을 값
 *   ANTHROPIC_API_KEY   : Claude API 키 (필수)
 *   UPLOAD_TOKEN        : Seeker 업로더와 똑같이 맞출 비밀 문자열 (필수)
 *   TELEGRAM_BOT_TOKEN  : 텔레그램 봇 토큰 (알림용)
 *   TELEGRAM_CHAT_ID    : 알림 받을 채팅 ID (getTelegramChatId()로 확인)
 *   MODEL               : (선택) 기본 claude-opus-5-5
 *   EFFORT              : (선택) 기본 low
 */

// ───────────────────────── 기본 설정 ─────────────────────────
var DEFAULT_MODEL = 'claude-opus-5-5';
var DEFAULT_EFFORT = 'low';
var ANTHROPIC_VERSION = '2026-10-21';
// 서버측 거절 시 대체 모델(fallbacks)을 지원하는 모델
var FALLBACK_MODELS = ['claude-opus-5-5', 'claude-sonnet-5-5', 'claude-opus-5', 'claude-fable-5-2', 'claude-fable-5-1'];

var SHEET_LOG = '기록';
var SHEET_SETTINGS = '설정';
var SHEET_ALARMS = '경보이력';
var IMAGE_FOLDER_NAME = '킹스_제어판캡처';
var TANK_COUNT = 4;

var LOG_HEADERS = ['시각', '탱크', '공정', '로트', '원주℃', '상부℃', '냉각℃', '교반', '상하차', '신뢰도', '판독메모', '경보', '캡처파일'];
var SETTINGS_HEADERS = ['탱크', '사용(Y/N)', '공정', '로트', '원주_최저℃', '원주_최고℃', '상하차_최대℃', '메모'];

// 판독 지침: 제어판 실물 배치(복합 양조기 컨트롤 박스) 기준
var SYSTEM_PROMPT = [
  '당신은 전통주 양조장 "복합 양조기 컨트롤 박스" 사진에서 계기 값을 읽는 판독기다.',
  '',
  '[제어판 배치]',
  '- 위에서 아래로 1호기, 2호기, 3호기, 4호기 순서의 가로 줄 4개.',
  '- 각 줄 윗부분 표시창(왼쪽→오른쪽): ①원주 온도계(빨간 LED, ℃) ②원주 타이머(파란 LED, 판독하지 않음) ③원주 상부온도계(빨간 LED, ℃) ④원주 냉각온도계(빨간 LED, ℃).',
  '- 각 줄 아랫부분 스위치(왼쪽→오른쪽): 스팀, 빨간 손잡이 스위치, 타이머, 교반모터, SPEED ADJ 다이얼, 원주 냉각 온도.',
  '- 교반모터 스위치는 가동 중이면 초록 램프가 밝게 켜진다.',
  '',
  '[판독 규칙]',
  '- 같은 순간을 몇 초 간격으로 찍은 여러 장이 주어진다. 모든 장을 비교해 일관되게 보이는 값만 채택한다.',
  '- LED 표시기는 깜빡이며 표시되므로 사진에 자릿수 일부만 찍히는 경우가 많다. 자릿수가 빠졌거나 희미하거나 장마다 다르면 그 값은 null로 한다. 절대 추측하지 않는다.',
  '- "t", "-", "---", 빈 화면처럼 숫자가 아닌 표시는 null로 하고 note에 그대로 적는다.',
  '- 소수점 위치를 정확히 읽는다(예: 6.9, 20.0, 19.1, 90.0). 끝에 점만 있으면(예: "15.") 정수로 읽는다.',
  '- 제어판이 보이지 않거나 영상 오류 화면이면 panel_visible=false로 한다.',
  '- confidence: high=모든 장에서 선명하고 일치, medium=대체로 선명하나 일부 불확실, low=대부분 판독 불가.'
].join('\n');

var READING_SCHEMA = {
  type: 'object',
  properties: {
    panel_visible: { type: 'boolean' },
    tanks: {
      type: 'array',
      items: {
        type: 'object',
        properties: {
          tank: { type: 'integer', enum: [1, 2, 3, 4] },
          main_temp: { anyOf: [{ type: 'number' }, { type: 'null' }] },
          top_temp: { anyOf: [{ type: 'number' }, { type: 'null' }] },
          cooling_temp: { anyOf: [{ type: 'number' }, { type: 'null' }] },
          stirrer_on: { anyOf: [{ type: 'boolean' }, { type: 'null' }] },
          confidence: { type: 'string', enum: ['high', 'medium', 'low'] },
          note: { type: 'string' }
        },
        required: ['tank', 'main_temp', 'top_temp', 'cooling_temp', 'stirrer_on', 'confidence', 'note'],
        additionalProperties: false
      }
    },
    issues: { type: 'string' }
  },
  required: ['panel_visible', 'tanks', 'issues'],
  additionalProperties: false
};

// ───────────────────────── 최초 1회 실행 ─────────────────────────
/** 시트·폴더·자동 실행(트리거)을 만든다. 편집기에서 setup 선택 후 ▶ 실행. */
function setup() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();

  var log = ss.getSheetByName(SHEET_LOG) || ss.insertSheet(SHEET_LOG);
  if (log.getLastRow() === 0) {
    log.appendRow(LOG_HEADERS);
    log.setFrozenRows(1);
  }

  var st = ss.getSheetByName(SHEET_SETTINGS) || ss.insertSheet(SHEET_SETTINGS);
  if (st.getLastRow() === 0) {
    st.appendRow(SETTINGS_HEADERS);
    // 예시 기준값: 대표님 공정에 맞게 시트에서 바로 고치면 됩니다.
    st.appendRow([1, 'Y', '숙성/저온', '', 0, 12, 5, '']);
    st.appendRow([2, 'Y', '발효', '', 18, 26, 5, '']);
    st.appendRow([3, 'Y', '가열/증자', '', 0, 100, 30, '가열 공정은 상하차 기준 완화']);
    st.appendRow([4, 'Y', '숙성/저온', '', 0, 12, 5, '']);
    st.appendRow([]);
    st.appendRow(['공통설정', '값', '설명']);
    st.appendRow(['경보간격_분', 60, '같은 경보 재발송 최소 간격']);
    st.appendRow(['판독실패_연속', 3, '이 횟수만큼 연속 판독 실패 시 경보']);
    st.appendRow(['업로드중단_분', 40, '이 시간 동안 기록 없으면 경보']);
    st.appendRow(['캡처보관_일', 7, '드라이브 캡처 이미지 보관 기간']);
    st.setFrozenRows(1);
  }

  var al = ss.getSheetByName(SHEET_ALARMS) || ss.insertSheet(SHEET_ALARMS);
  if (al.getLastRow() === 0) {
    al.appendRow(['시각', '탱크', '종류', '내용']);
    al.setFrozenRows(1);
  }

  getImageFolder_();

  // 트리거: 감시(30분), 아침 브리핑(07시), 캡처 정리(03시)
  ScriptApp.getProjectTriggers().forEach(function (t) { ScriptApp.deleteTrigger(t); });
  ScriptApp.newTrigger('watchdog').timeBased().everyMinutes(30).create();
  ScriptApp.newTrigger('dailyBriefing').timeBased().atHour(7).everyDays(1).inTimezone('Asia/Seoul').create();
  ScriptApp.newTrigger('cleanupImages').timeBased().atHour(3).everyDays(1).inTimezone('Asia/Seoul').create();

  Logger.log('설정 완료. 다음: 배포 → 새 배포 → 웹 앱');
}

// ───────────────────────── 업로드 수신 ─────────────────────────
/**
 * Seeker 업로더가 보내는 JSON:
 * { token, captured_at, images: [{ name, mime, data(base64) }] }
 */
function doPost(e) {
  var props = PropertiesService.getScriptProperties();
  try {
    var body = JSON.parse(e.postData.contents);
    if (!body.token || body.token !== props.getProperty('UPLOAD_TOKEN')) {
      return json_({ ok: false, error: 'unauthorized' });
    }
    if (!body.images || !body.images.length) {
      return json_({ ok: false, error: 'no images' });
    }

    var capturedAt = body.captured_at ? new Date(body.captured_at) : new Date();
    var fileNames = saveImages_(body.images, capturedAt);
    var reading = readPanel_(body.images);
    var result = recordReading_(reading, capturedAt, fileNames.join(','));
    return json_({ ok: true, rows: result.rows, alarms: result.alarms });
  } catch (err) {
    logAlarm_(new Date(), '-', '시스템오류', String(err));
    return json_({ ok: false, error: String(err) });
  }
}

/** 업로더 연결 확인용(브라우저로 웹앱 주소 열면 표시) */
function doGet() {
  return json_({ ok: true, service: 'kings-panel-logger' });
}

// ───────────────────────── Claude 판독 ─────────────────────────
function buildClaudeRequest(images, model, effort) {
  var content = images.map(function (img) {
    return { type: 'image', source: { type: 'base64', media_type: img.mime || 'image/jpeg', data: img.data } };
  });
  content.push({
    type: 'text',
    text: '위 ' + images.length + '장은 같은 제어판을 몇 초 간격으로 찍은 것이다. 1~4호기 값을 판독 규칙에 따라 JSON으로 답하라.'
  });

  var payload = {
    model: model,
    max_tokens: 8000,
    system: SYSTEM_PROMPT,
    output_config: { effort: effort, format: { type: 'json_schema', schema: READING_SCHEMA } },
    messages: [{ role: 'user', content: content }]
  };
  var headers = { 'x-api-key': null, 'anthropic-version': ANTHROPIC_VERSION };
  if (FALLBACK_MODELS.indexOf(model) >= 0) {
    // 안전 분류기가 드물게 거절할 때 같은 요청을 대체 모델로 자동 재시도
    payload.fallbacks = 'default';
    headers['anthropic-beta'] = 'server-side-fallback-2026-07-01';
  }
  return { payload: payload, headers: headers };
}

function parseClaudeResponse(resp) {
  if (resp.type === 'error') throw new Error('Claude 오류: ' + JSON.stringify(resp.error));
  if (resp.stop_reason === 'refusal') throw new Error('Claude 판독 거절(refusal)');
  if (resp.stop_reason === 'max_tokens') throw new Error('응답이 잘림(max_tokens)');
  var textBlock = (resp.content || []).filter(function (b) { return b.type === 'text'; })[0];
  if (!textBlock) throw new Error('응답에 텍스트 없음');
  return JSON.parse(textBlock.text);
}

function readPanel_(images) {
  var props = PropertiesService.getScriptProperties();
  var key = props.getProperty('ANTHROPIC_API_KEY');
  if (!key) throw new Error('ANTHROPIC_API_KEY 미설정');
  var req = buildClaudeRequest(images, props.getProperty('MODEL') || DEFAULT_MODEL, props.getProperty('EFFORT') || DEFAULT_EFFORT);
  req.headers['x-api-key'] = key;

  var lastErr;
  for (var attempt = 0; attempt < 3; attempt++) {
    var res = UrlFetchApp.fetch('https://api.anthropic.com/v1/messages', {
      method: 'post',
      contentType: 'application/json',
      headers: req.headers,
      payload: JSON.stringify(req.payload),
      muteHttpExceptions: true
    });
    var code = res.getResponseCode();
    if (code === 200) return parseClaudeResponse(JSON.parse(res.getContentText()));
    lastErr = new Error('Claude HTTP ' + code + ': ' + res.getContentText().slice(0, 300));
    if (code !== 429 && code < 500) break; // 400/401/403 등은 재시도해도 같음
    Utilities.sleep(3000 * (attempt + 1));
  }
  throw lastErr;
}

// ───────────────────────── 기록·경보 ─────────────────────────
function loadSettings_() {
  var rows = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_SETTINGS).getDataRange().getValues();
  var tanks = {};
  var common = { '경보간격_분': 60, '판독실패_연속': 3, '업로드중단_분': 40, '캡처보관_일': 7 };
  rows.slice(1).forEach(function (r) {
    var id = Number(r[0]);
    if (id >= 1 && id <= TANK_COUNT) {
      tanks[id] = {
        enabled: String(r[1]).toUpperCase() !== 'N',
        process: r[2], lot: r[3],
        min: numOrNull_(r[4]), max: numOrNull_(r[5]), diffMax: numOrNull_(r[6])
      };
    } else if (common.hasOwnProperty(r[0]) && numOrNull_(r[1]) !== null) {
      common[r[0]] = Number(r[1]);
    }
  });
  return { tanks: tanks, common: common };
}

/**
 * 판독 결과 → 탱크별 경보 목록 (순수 함수, 테스트 대상)
 * failCounts: { "1": 연속실패횟수, ... } — 호출 후 갱신된 값을 돌려줌
 */
function evaluateAlarms(reading, settings, failCounts) {
  var alarms = [];
  var counts = JSON.parse(JSON.stringify(failCounts || {}));
  var failLimit = settings.common['판독실패_연속'];

  if (!reading.panel_visible) {
    counts.panel = (counts.panel || 0) + 1;
    if (counts.panel === failLimit) {
      alarms.push({ tank: '-', kind: '화면이상', msg: '제어판이 ' + failLimit + '회 연속 보이지 않음. GiGAeyes 화면/카메라 확인 필요. ' + (reading.issues || '') });
    }
    return { alarms: alarms, failCounts: counts };
  }
  counts.panel = 0;

  (reading.tanks || []).forEach(function (t) {
    var cfg = settings.tanks[t.tank];
    if (!cfg || !cfg.enabled) return;
    var label = t.tank + '호기(' + (cfg.process || '') + ')';

    if (t.main_temp === null || t.confidence === 'low') {
      counts[t.tank] = (counts[t.tank] || 0) + 1;
      if (counts[t.tank] === failLimit) {
        alarms.push({ tank: t.tank, kind: '판독실패', msg: label + ' 원주온도 ' + failLimit + '회 연속 판독 실패. 카메라 각도/반사 확인.' });
      }
    } else {
      counts[t.tank] = 0;
      if (cfg.min !== null && t.main_temp < cfg.min) {
        alarms.push({ tank: t.tank, kind: '저온', msg: label + ' 원주 ' + t.main_temp + '℃ < 기준 ' + cfg.min + '℃' });
      }
      if (cfg.max !== null && t.main_temp > cfg.max) {
        alarms.push({ tank: t.tank, kind: '고온', msg: label + ' 원주 ' + t.main_temp + '℃ > 기준 ' + cfg.max + '℃' });
      }
    }

    if (t.main_temp !== null && t.top_temp !== null && cfg.diffMax !== null && t.confidence !== 'low') {
      var diff = Math.abs(t.top_temp - t.main_temp);
      if (diff > cfg.diffMax) {
        alarms.push({ tank: t.tank, kind: '상하편차', msg: label + ' 상하 온도차 ' + round1_(diff) + '℃ (원주 ' + t.main_temp + ' / 상부 ' + t.top_temp + ')' });
      }
    }
  });
  return { alarms: alarms, failCounts: counts };
}

function recordReading_(reading, capturedAt, fileNames) {
  var props = PropertiesService.getScriptProperties();
  var settings = loadSettings_();
  var failCounts = JSON.parse(props.getProperty('FAIL_COUNTS') || '{}');
  var evald = evaluateAlarms(reading, settings, failCounts);
  props.setProperty('FAIL_COUNTS', JSON.stringify(evald.failCounts));

  var alarmByTank = {};
  evald.alarms.forEach(function (a) { (alarmByTank[a.tank] = alarmByTank[a.tank] || []).push(a.kind); });

  var rows = [];
  if (!reading.panel_visible) {
    rows.push([capturedAt, '-', '', '', '', '', '', '', '', 'low', '제어판 안 보임: ' + (reading.issues || ''), (alarmByTank['-'] || []).join(','), fileNames]);
  } else {
    (reading.tanks || []).forEach(function (t) {
      var cfg = settings.tanks[t.tank] || {};
      var diff = (t.main_temp !== null && t.top_temp !== null) ? round1_(t.top_temp - t.main_temp) : '';
      rows.push([
        capturedAt, t.tank, cfg.process || '', cfg.lot || '',
        nz_(t.main_temp), nz_(t.top_temp), nz_(t.cooling_temp),
        t.stirrer_on === null ? '' : (t.stirrer_on ? 'ON' : 'OFF'),
        diff, t.confidence, t.note, (alarmByTank[t.tank] || []).join(','), fileNames
      ]);
    });
  }
  if (rows.length) {
    var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_LOG);
    sh.getRange(sh.getLastRow() + 1, 1, rows.length, rows[0].length).setValues(rows);
  }
  props.setProperty('LAST_RECORD_AT', String(new Date().getTime()));

  evald.alarms.forEach(function (a) { sendAlarm_(a, settings.common['경보간격_분']); });
  return { rows: rows.length, alarms: evald.alarms.length };
}

/** 같은 탱크·같은 종류 경보는 경보간격_분 안에 한 번만 발송 */
function sendAlarm_(a, cooldownMin) {
  var props = PropertiesService.getScriptProperties();
  var sent = JSON.parse(props.getProperty('ALARM_SENT') || '{}');
  var key = a.tank + '|' + a.kind;
  var now = new Date().getTime();
  logAlarm_(new Date(), a.tank, a.kind, a.msg);
  if (sent[key] && now - sent[key] < cooldownMin * 60000) return;
  sent[key] = now;
  props.setProperty('ALARM_SENT', JSON.stringify(sent));
  telegram_('⚠️ [킹스양조장 경보] ' + a.kind + '\n' + a.msg + '\n' + fmt_(new Date()));
}

function logAlarm_(when, tank, kind, msg) {
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_ALARMS);
  if (sh) sh.appendRow([when, tank, kind, msg]);
}

// ───────────────────────── 자동 실행 작업 ─────────────────────────
/** 30분마다: 기록이 끊기면 알림 (Seeker 꺼짐·앱 종료·와이파이 끊김) */
function watchdog() {
  var props = PropertiesService.getScriptProperties();
  var last = Number(props.getProperty('LAST_RECORD_AT') || 0);
  if (!last) return;
  var limit = loadSettings_().common['업로드중단_분'];
  var mins = Math.round((new Date().getTime() - last) / 60000);
  if (mins >= limit) {
    sendAlarm_({ tank: '-', kind: '업로드중단', msg: mins + '분째 기록 없음. Seeker 전원·와이파이·GiGAeyes 화면·Termux 확인.' }, 180);
  }
}

/** 매일 07시: 최근 24시간 탱크별 요약 */
function dailyBriefing() {
  var data = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(SHEET_LOG).getDataRange().getValues().slice(1);
  var since = new Date().getTime() - 24 * 3600 * 1000;
  var lines = ['☀️ 킹스양조장 발효 브리핑 (' + fmt_(new Date()) + ')'];
  for (var tank = 1; tank <= TANK_COUNT; tank++) {
    var recent = data.filter(function (r) { return Number(r[1]) === tank && new Date(r[0]).getTime() >= since; });
    var temps = recent.map(function (r) { return r[4]; }).filter(function (v) { return v !== '' && v !== null; }).map(Number);
    var alarmCount = recent.filter(function (r) { return r[11]; }).length;
    if (!temps.length) { lines.push(tank + '호기: 판독값 없음'); continue; }
    var last = recent[recent.length - 1];
    var avg = temps.reduce(function (s, v) { return s + v; }, 0) / temps.length;
    lines.push(tank + '호기(' + (last[2] || '-') + '): 현재 ' + last[4] + '℃ / 최저 ' + Math.min.apply(null, temps) + ' / 최고 ' + Math.max.apply(null, temps) + ' / 평균 ' + round1_(avg) + '℃' + (alarmCount ? ' / 경보 ' + alarmCount + '회' : ''));
  }
  telegram_(lines.join('\n'));
}

/** 매일 03시: 오래된 캡처 이미지 삭제 */
function cleanupImages() {
  var days = loadSettings_().common['캡처보관_일'];
  var cutoff = new Date().getTime() - days * 86400000;
  var files = getImageFolder_().getFiles();
  while (files.hasNext()) {
    var f = files.next();
    if (f.getDateCreated().getTime() < cutoff) f.setTrashed(true);
  }
}

// ───────────────────────── 텔레그램 ─────────────────────────
function telegram_(text) {
  var props = PropertiesService.getScriptProperties();
  var token = props.getProperty('TELEGRAM_BOT_TOKEN');
  var chat = props.getProperty('TELEGRAM_CHAT_ID');
  if (!token || !chat) return;
  UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/sendMessage', {
    method: 'post', contentType: 'application/json',
    payload: JSON.stringify({ chat_id: chat, text: text }),
    muteHttpExceptions: true
  });
}

/** 봇에게 아무 메시지나 보낸 뒤 실행 → 로그에 채팅 ID 표시 */
function getTelegramChatId() {
  var token = PropertiesService.getScriptProperties().getProperty('TELEGRAM_BOT_TOKEN');
  var res = JSON.parse(UrlFetchApp.fetch('https://api.telegram.org/bot' + token + '/getUpdates').getContentText());
  (res.result || []).forEach(function (u) {
    var m = u.message || u.channel_post;
    if (m) Logger.log('채팅 ID: ' + m.chat.id + ' (' + (m.chat.title || m.chat.first_name || '') + ')');
  });
}

/** 연결 시험: 텔레그램으로 테스트 메시지 */
function testTelegram() {
  telegram_('✅ 킹스양조장 온도 기록기 텔레그램 연결 성공 ' + fmt_(new Date()));
}

// ───────────────────────── 보조 함수 ─────────────────────────
function saveImages_(images, capturedAt) {
  var folder = getImageFolder_();
  var stamp = Utilities.formatDate(capturedAt, 'Asia/Seoul', 'yyyyMMdd_HHmmss');
  return images.map(function (img, i) {
    var ext = (img.mime === 'image/png') ? 'png' : 'jpg';
    var blob = Utilities.newBlob(Utilities.base64Decode(img.data), img.mime || 'image/jpeg', stamp + '_' + (i + 1) + '.' + ext);
    return folder.createFile(blob).getName();
  });
}

function getImageFolder_() {
  var it = DriveApp.getFoldersByName(IMAGE_FOLDER_NAME);
  return it.hasNext() ? it.next() : DriveApp.createFolder(IMAGE_FOLDER_NAME);
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
function numOrNull_(v) { return (v === '' || v === null || isNaN(Number(v))) ? null : Number(v); }
function nz_(v) { return v === null || v === undefined ? '' : v; }
function round1_(v) { return Math.round(v * 10) / 10; }
function fmt_(d) { return Utilities.formatDate(d, 'Asia/Seoul', 'MM-dd HH:mm'); }
