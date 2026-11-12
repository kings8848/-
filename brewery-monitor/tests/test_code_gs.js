// Apps Script 순수 로직 테스트: node tests/test_code_gs.js
const fs = require('fs');
const vm = require('vm');
const assert = require('assert');

const ctx = {};
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(__dirname + '/../apps_script/Code.gs', 'utf8'), ctx);

const settings = {
  tanks: {
    1: { enabled: true, process: '숙성', min: 0, max: 12, diffMax: 5 },
    2: { enabled: true, process: '발효', min: 18, max: 26, diffMax: 5 },
    3: { enabled: true, process: '가열', min: 0, max: 100, diffMax: 30 },
    4: { enabled: true, process: '숙성', min: 0, max: 12, diffMax: 5 },
  },
  common: { '경보간격_분': 60, '판독실패_연속': 3 },
};

// 실제 제어판 사진(11-13 00시대) 판독값 재현
const reading = {
  panel_visible: true,
  issues: '',
  tanks: [
    { tank: 1, main_temp: 6.9, top_temp: null, cooling_temp: null, stirrer_on: false, confidence: 'medium', note: '상부 자릿수 일부만 보임' },
    { tank: 2, main_temp: 20.0, top_temp: 15, cooling_temp: null, stirrer_on: false, confidence: 'high', note: '' },
    { tank: 3, main_temp: 90.0, top_temp: null, cooling_temp: null, stirrer_on: true, confidence: 'medium', note: '' },
    { tank: 4, main_temp: 6.0, top_temp: 19.1, cooling_temp: null, stirrer_on: false, confidence: 'high', note: '냉각 t 표시' },
  ],
};

let r = JSON.parse(JSON.stringify(ctx.evaluateAlarms(reading, settings, {})));
const kinds = Array.from(r.alarms).map(a => a.tank + ':' + a.kind).sort();
assert.deepStrictEqual(JSON.parse(JSON.stringify(kinds)), ['4:상하편차'], '4호기 상하편차만 경보여야 함: ' + kinds);
assert.ok(r.alarms[0].msg.includes('13.1'), r.alarms[0].msg);
console.log('✓ 실제 사진 판독값 → 4호기 상하편차 13.1℃ 경보');

// 2호기 고온
const hot = JSON.parse(JSON.stringify(reading));
hot.tanks[1].main_temp = 28.4;
r = ctx.evaluateAlarms(hot, settings, {});
assert.ok(r.alarms.some(a => a.tank === 2 && a.kind === '고온'));
console.log('✓ 발효 탱크 고온 경보');

// 판독 실패 3회 연속 → 3번째에만 1회 경보, 성공 시 리셋
const fail = JSON.parse(JSON.stringify(reading));
fail.tanks[1].main_temp = null;
let counts = {};
const fired = [];
for (let i = 0; i < 4; i++) {
  r = ctx.evaluateAlarms(fail, settings, counts);
  counts = r.failCounts;
  fired.push(r.alarms.filter(a => a.kind === '판독실패').length);
}
assert.deepStrictEqual(JSON.parse(JSON.stringify(fired)), [0, 0, 1, 0]);
r = ctx.evaluateAlarms(reading, settings, counts);
assert.strictEqual(r.failCounts[2], 0);
console.log('✓ 판독 실패 연속 3회째 1번만 경보, 성공 시 초기화');

// 화면 안 보임
counts = {};
const hidden = { panel_visible: false, tanks: [], issues: '영상 재생 오류' };
const hf = [];
for (let i = 0; i < 3; i++) { r = ctx.evaluateAlarms(hidden, settings, counts); counts = r.failCounts; hf.push(r.alarms.length); }
assert.deepStrictEqual(JSON.parse(JSON.stringify(hf)), [0, 0, 1]);
console.log('✓ 제어판 안 보임 3회 연속 → 화면이상 경보');

// 비활성 탱크는 무시
const s2 = JSON.parse(JSON.stringify(settings)); s2.tanks[4].enabled = false;
assert.strictEqual(ctx.evaluateAlarms(reading, s2, {}).alarms.length, 0);
console.log('✓ 사용 N 탱크 경보 제외');

// Claude 요청 형태
let req = ctx.buildClaudeRequest([{ mime: 'image/jpeg', data: 'AAA' }, { mime: 'image/jpeg', data: 'BBB' }], 'claude-opus-5-5', 'low');
assert.strictEqual(req.payload.model, 'claude-opus-5-5');
assert.strictEqual(req.payload.output_config.format.type, 'json_schema');
assert.strictEqual(req.payload.output_config.effort, 'low');
assert.strictEqual(req.payload.fallbacks, 'default');
assert.strictEqual(req.headers['anthropic-beta'], 'server-side-fallback-2026-07-01');
assert.strictEqual(req.payload.messages[0].content.length, 3);
assert.ok(!('thinking' in req.payload) && !('temperature' in req.payload));
req = ctx.buildClaudeRequest([{ data: 'A' }], 'claude-haiku-5-5', 'low');
assert.ok(!('fallbacks' in req.payload) && !req.headers['anthropic-beta']);
console.log('✓ Claude 요청: 구조화 출력·fallback 설정');

// 응답 파싱
const ok = ctx.parseClaudeResponse({ stop_reason: 'end_turn', content: [{ type: 'thinking', thinking: '' }, { type: 'text', text: JSON.stringify(reading) }] });
assert.strictEqual(ok.tanks[3].top_temp, 19.1);
assert.throws(() => ctx.parseClaudeResponse({ stop_reason: 'refusal', content: [] }), /거절/);
assert.throws(() => ctx.parseClaudeResponse({ type: 'error', error: { message: 'x' } }), /오류/);
console.log('✓ Claude 응답 파싱·거절 처리');

console.log('\n모든 테스트 통과');
