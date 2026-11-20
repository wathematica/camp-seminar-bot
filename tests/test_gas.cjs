const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function createHarness(status = 200) {
  const properties = { DISCORD_WEBHOOK_URL: 'https://discord.com/api/webhooks/123/example', DISCORD_USE_CANARY: 'false' };
  const requests = [];
  const context = vm.createContext({
    console: { log() {}, error() {} },
    PropertiesService: { getScriptProperties: () => ({
      getProperty: key => properties[key],
      setProperty: (key, value) => { properties[key] = value; },
    }) },
    LockService: { getScriptLock: () => ({ waitLock() {}, releaseLock() {} }) },
    UrlFetchApp: { fetch: (url, options) => {
      requests.push({ url, payload: JSON.parse(options.payload) });
      return { getResponseCode: () => status, getContentText: () => status === 429 ? '{"retry_after":60}' : '{"id":"456"}', getAllHeaders: () => ({'Retry-After':'60'}) };
    } },
  });
  vm.runInContext(fs.readFileSync(path.join(__dirname, '../gas/onSubmit.gs'), 'utf8'), context);
  function submit(name = '線形代数') {
    context.onSubmit({ response: {
      getId: () => 'response-1',
      getItemResponses: () => [['名称', name], ['形式', ['輪読', '演習']]].map(([title, value]) => ({
        getItem: () => ({ getTitle: () => title }), getResponse: () => value,
      })),
    } });
  }
  return { properties, requests, submit };
}

test('名称は見出しのみ、本文の回答は保持し、同じ回答を重複投稿しない', () => {
  const h = createHarness();
  h.submit(); h.submit();
  assert.equal(h.requests.length, 1);
  const embed = h.requests[0].payload.embeds[0];
  assert.equal(embed.title, '線形代数');
  assert.deepEqual(embed.fields, [{ name: '形式', value: '輪読、演習' }]);
});

test('長すぎる名称は送信前に検出', () => {
  const h = createHarness();
  assert.throws(() => h.submit('a'.repeat(257)), /256/);
  assert.equal(h.requests.length, 0);
});

test('送信失敗を投稿済みとして記録しない', () => {
  const h = createHarness(403);
  assert.throws(() => h.submit(), /HTTP 403/);
  assert.equal(h.properties['CAMP_POSTED_response-1'], undefined);
});

test('429後は指定待機時間中にDiscordへ再送しない', () => {
  const h = createHarness(429);
  assert.throws(() => h.submit(), /HTTP 429/);
  assert.throws(() => h.submit(), /投稿待機中/);
  assert.equal(h.requests.length, 1);
  assert.equal(h.properties['CAMP_POSTED_response-1'], undefined);
});
