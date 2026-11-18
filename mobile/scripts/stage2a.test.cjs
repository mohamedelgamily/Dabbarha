const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const axios = require('axios');

// Execute real TS services/stores with native storage mocked; no server or .env loading.
function loader(mocks = {}, globals = {}) {
  const cache = new Map();
  function load(file) {
    const absolute = path.resolve(file);
    if (cache.has(absolute)) return cache.get(absolute).exports;
    const module = { exports: {} }; cache.set(absolute, module);
    const js = ts.transpileModule(fs.readFileSync(absolute, 'utf8'), { compilerOptions: {
      module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.React,
      esModuleInterop: true,
    } }).outputText;
    const localRequire = name => {
      if (Object.hasOwn(mocks, name)) return mocks[name];
      if (name.startsWith('@/') || name.startsWith('.')) {
        let target = name.startsWith('@/') ? path.resolve('src', name.slice(2)) : path.resolve(path.dirname(absolute), name);
        target = ['.ts', '.tsx', '.js'].map(ext => target + ext).find(p => fs.existsSync(p)) || path.join(target, 'index.ts');
        return load(target);
      }
      return require(name);
    };
    vm.runInNewContext(js, { module, exports: module.exports, require: localRequire,
      Intl, Date, console, process, setTimeout, clearTimeout, AbortController, ...globals }, { filename: absolute });
    return module.exports;
  }
  return load;
}
const plain = value => JSON.parse(JSON.stringify(value));
const deferred = () => { let resolve, reject; const promise = new Promise((a,b) => { resolve=a; reject=b; }); return { promise, resolve, reject }; };
const tick = () => new Promise(resolve => setImmediate(resolve));

test('retry keys request exactly 32 secure bytes and encode canonical base64url without fallback', async () => {
  let calls = 0; const bytes = Uint8Array.from({ length: 32 }, (_, i) => i * 7);
  const load = loader({ 'expo-crypto': { getRandomBytesAsync: async count => { calls++; assert.equal(count, 32); return bytes; } } });
  const key = await load('src/utils/refreshRetryKey.ts').generateRefreshRetryKey();
  assert.equal(key, Buffer.from(bytes).toString('base64url')); assert.equal(key.length, 43); assert.equal(calls, 1);
  const failed = loader({ 'expo-crypto': { getRandomBytesAsync: async () => { throw new Error('native unavailable'); } } });
  await assert.rejects(failed('src/utils/refreshRetryKey.ts').generateRefreshRetryKey(), /native unavailable/);
  const source = fs.readFileSync('src/utils/refreshRetryKey.ts', 'utf8'); assert.equal(source.includes('Math.random('), false);
});

async function refreshHarness(faults = {}, data = new Map()) {
  const h = harness(data, faults); const disk = h.load('src/utils/sessionStorage.ts'); const scope = scopeV2(h);
  if (!data.has('dabbarha_session_v2')) await disk.saveNewSession(scope, savedV2(), 1000);
  const factory = h.load('src/api/refreshCoordinator.ts').createRefreshCoordinator;
  const response = { access_token: 'new-access', token_type: 'bearer', expires_in: 900, refresh_token: 'B'.repeat(42) + 'A', refresh_expires_at: 2500, session_id: scope.sessionId, session_expires_at: 3000 };
  return { ...h, disk, scope, factory, response };
}

test('single-flight refresh persists before send and publishes only after successor without clearing caches', async () => {
  const h = await refreshHarness(); const gate = deferred(); let calls = 0;
  h.query.setQueryDefaults(['private'], { gcTime: Infinity });
  h.query.setQueryData(['private'], { owner: 1 });
  const refresh = h.factory({ now: () => 1001, refresh: async body => {
    calls++; const record = JSON.parse(h.data.get('dabbarha_session_v2'));
    assert.equal(record.pending.attempts, 1); assert.equal(body.retry_key, record.pending.retryKey);
    assert.equal(body.refresh_token, record.pending.originalRefreshToken);
    assert.equal(h.session.sessionSnapshot().token, null); await gate.promise; return h.response;
  } });
  const a = refresh(h.scope), b = refresh(h.scope); assert.equal(a, b); await tick(); assert.equal(calls, 1);
  gate.resolve(); assert.equal((await a).access_token, 'new-access'); await b;
  assert.equal(JSON.parse(h.data.get('dabbarha_session_v2')).pending, null);
  assert.equal(h.session.sessionSnapshot().token, 'new-access'); assert.equal(h.session.sessionSnapshot().generation, h.scope.generation);
  assert.equal(h.query.getQueryData(['private']).owner, 1); await h.clearSession();
});

test('lost response retries identical operation and honors Retry-After for 429 and 503', async () => {
  for (const status of [0, 429, 503]) {
    const h = await refreshHarness(); let time = 1001; const bodies = []; const waits = [];
    const refresh = h.factory({ now: () => time, wait: async ms => { waits.push(ms); time += ms / 1000; }, refresh: async body => {
      bodies.push(plain(body)); if (bodies.length === 1) throw { statusCode: status, retryAfter: '2' }; return h.response;
    } });
    await refresh(h.scope); assert.deepEqual(bodies[0], bodies[1]); assert.deepEqual(waits, [2000]); await h.clearSession();
  }
});

test('restart recovers saved token and key without generating a replacement; attempt budget survives restart', async () => {
  const h = await refreshHarness(); const pending = await h.disk.prepareRefresh(h.scope, 'A'.repeat(43), 1001);
  await h.disk.reserveRefreshAttempt(h.scope, pending.pending, 1001);
  const restarted = await refreshHarness({}, h.data); let calls = 0;
  const refresh = restarted.factory({ now: () => 1002, retryKey: async () => { throw new Error('must not generate'); }, refresh: async body => {
    calls++; assert.equal(body.retry_key, pending.pending.retryKey); return restarted.response;
  } });
  await refresh(restarted.scope); assert.equal(calls, 1); await restarted.clearSession();
  const exhausted = await refreshHarness(); let time = 1001;
  const fail = exhausted.factory({ now: () => time, wait: async ms => { time += ms / 1000; }, refresh: async () => { throw { statusCode: 0 }; } });
  await assert.rejects(fail(exhausted.scope), e => e.kind === 'temporary');
  assert.equal(JSON.parse(exhausted.data.get('dabbarha_session_v2')).pending.attempts, 3);
  const again = exhausted.factory({ now: () => time, refresh: async () => { throw new Error('must not send'); } });
  await assert.rejects(again(exhausted.scope), e => e.kind === 'reauthenticate'); await exhausted.clearSession();
});

test('storage failure stops sending/publication, while ambiguous writes require durable readback', async () => {
  for (const stage of ['prepare', 'successor', 'ambiguous']) {
    const faults = {}; const h = await refreshHarness(faults); let calls = 0;
    if (stage === 'prepare') faults.writes = true;
    if (stage === 'successor') faults.rejectWrite = (key, value) => key === 'dabbarha_session_v2' && JSON.parse(value).refreshToken === h.response.refresh_token;
    if (stage === 'ambiguous') faults.ambiguous = key => key === 'dabbarha_session_v2';
    const refresh = h.factory({ now: () => 1001, refresh: async () => { calls++; return h.response; } });
    if (stage === 'ambiguous') { await refresh(h.scope); assert.equal(h.session.sessionSnapshot().token, 'new-access'); }
    else { await assert.rejects(refresh(h.scope), e => e.kind === 'storage'); assert.equal(h.session.sessionSnapshot().token, null); }
    assert.equal(calls, stage === 'prepare' ? 0 : 1);
    faults.writes = false; faults.rejectWrite = undefined; faults.ambiguous = undefined; await h.clearSession();
  }
});

test('401, both 409 outcomes and 422 do not retry or publish; temporary deadline failures preserve pending', async () => {
  for (const [status, detail, kind] of [[401, '', 'reauthenticate'], [409, 'refresh_conflict', 'reauthenticate'], [409, 'refresh_recovery_unavailable', 'reauthenticate'], [422, '', 'invalid-request'], [429, '', 'temporary'], [503, '', 'temporary']]) {
    const h = await refreshHarness(); let calls = 0;
    const refresh = h.factory({ now: () => 1001, refresh: async () => { calls++; throw { statusCode: status, detail, retryAfter: '60' }; } });
    await assert.rejects(refresh(h.scope), e => e.kind === kind && e.statusCode === status);
    assert.equal(calls, 1); assert.equal(h.session.sessionSnapshot().token, null);
    assert.ok(JSON.parse(h.data.get('dabbarha_session_v2')).pending); await h.clearSession();
  }
  const h = await refreshHarness(); await h.disk.prepareRefresh(h.scope, 'A'.repeat(43), 1000);
  const refresh = h.factory({ now: () => 1060, refresh: async () => { throw new Error('must not send'); } });
  await assert.rejects(refresh(h.scope), e => e.kind === 'reauthenticate'); await h.clearSession();
});

test('late refresh after logout or account switching cannot persist or publish Account A', async () => {
  for (const switchAccount of [false, true]) {
    const h = await refreshHarness(); const gate = deferred();
    const refresh = h.factory({ now: () => 1001, refresh: () => gate.promise });
    const result = refresh(h.scope).catch(e => e); await tick(); await h.clearSession();
    if (switchAccount) await h.login('B');
    gate.resolve(h.response); assert.equal((await result).code, 'ERR_CANCELED');
    assert.equal(h.data.has('dabbarha_session_v2'), switchAccount);
    if (switchAccount) assert.equal(JSON.parse(h.data.get('dabbarha_session_v2')).userId, 2);
    assert.equal(h.session.sessionSnapshot().token, switchAccount ? 'B' : null); await h.clearSession();
  }
});

test('terminal stop and server cooldown survive coordinator recreation', async () => {
  for (const status of [401, 409, 422, 429, 503]) {
    const h = await refreshHarness(); let calls = 0;
    const first = h.factory({ now: () => 1001, refresh: async () => { calls++; throw { statusCode: status, detail: 'refresh_conflict', retryAfter: '90' }; } });
    await assert.rejects(first(h.scope));
    const restart = await refreshHarness({}, h.data);
    const second = restart.factory({ now: () => 1002, refresh: async () => { calls++; return restart.response; } });
    await assert.rejects(second(restart.scope)); assert.equal(calls, 1); await restart.clearSession();
  }
});

test('logout during backoff prevents another send and malformed responses cannot publish', async () => {
  const h = await refreshHarness(); let calls = 0;
  const refresh = h.factory({ now: () => 1001, wait: async () => { await h.clearSession(); }, refresh: async () => { calls++; throw { statusCode: 503, retryAfter: '1' }; } });
  await assert.rejects(refresh(h.scope), e => e.code === 'ERR_CANCELED'); assert.equal(calls, 1);
  for (const change of [{ session_id: 'other' }, { expires_in: 0 }, { refresh_token: 'invalid' }, { session_expires_at: 4000 }]) {
    const fixture = await refreshHarness(); const invalid = fixture.factory({ now: () => 1001, refresh: async () => ({ ...fixture.response, ...change }) });
    await assert.rejects(invalid(fixture.scope)); assert.equal(fixture.session.sessionSnapshot().token, null);
    assert.ok(JSON.parse(fixture.data.get('dabbarha_session_v2')).pending); await fixture.clearSession();
  }
});

test('real session transport timeout recovers bearer-free with the same persisted request', async () => {
  const h = await refreshHarness(); const requests = []; let time = 1001;
  h.setHandler(async config => {
    assert.equal(config.headers.has('Authorization'), false); requests.push(JSON.parse(config.data));
    if (requests.length === 1) throw new axios.AxiosError('timeout', 'ECONNABORTED', config, {});
    return h.success(config, h.response);
  });
  const refresh = h.factory({ now: () => time, wait: async ms => { time += ms / 1000; } });
  await refresh(h.scope); assert.equal(requests.length, 2); assert.deepEqual(requests[0], requests[1]); await h.clearSession();
});

const savedV2 = () => ({ version: 1, userId: 1, sessionId: '11111111-1111-4111-8111-111111111111', refreshToken: 'A'.repeat(43), refreshExpiresAt: 2000, sessionExpiresAt: 3000, pending: null });
const scopeV2 = (h, record = savedV2()) => ({ generation: h.session.sessionSnapshot().generation, userId: record.userId, sessionId: record.sessionId });

test('V2 serialization, pending crash recovery and durable successor leave legacy credentials unchanged', async () => {
  const data = new Map([['token', 'legacy']]); const h = harness(data);
  const api = h.load('src/utils/sessionStorage.ts'); const scope = scopeV2(h); const record = savedV2();
  await api.saveNewSession(scope, record, 1000);
  assert.deepEqual(JSON.parse(data.get('dabbarha_session_v2')), record);
  assert.equal(data.get('token'), 'legacy'); assert.equal(h.store.getState().isAuthenticated, false);
  const pending = await api.prepareRefresh(scope, 'B'.repeat(42) + 'A', 1001);
  const restarted = harness(data); const disk = restarted.load('src/utils/sessionStorage.ts'); const newScope = scopeV2(restarted);
  const restored = await disk.readSessionRecord(newScope.generation, 1002);
  assert.equal(restored.status, 'pending'); assert.deepEqual(plain(restored.record), plain(pending));
  await assert.rejects(disk.prepareRefresh(newScope, 'C'.repeat(42) + 'A', 1003), /already pending/);
  assert.deepEqual(plain(await disk.prepareRefresh(newScope, pending.pending.retryKey, 1003)), plain(pending));
  const successor = { ...record, refreshToken: 'D'.repeat(42) + 'A', refreshExpiresAt: 2500 };
  await disk.saveRefreshSuccessor(newScope, pending.pending, successor, 1004);
  assert.deepEqual(JSON.parse(data.get('dabbarha_session_v2')), successor);
  assert.equal((await disk.readSessionRecord(newScope.generation, 1005)).status, 'ready');
  assert.equal(data.get('token'), 'legacy'); await restarted.clearSession(); assert.equal(data.size, 0);
});

test('V2 rejects malformed, unknown, extra credential fields and expired records', async () => {
  const h = harness(); const api = h.load('src/utils/sessionStorage.ts'); const scope = scopeV2(h);
  assert.equal((await api.readSessionRecord(scope.generation, 1000)).status, 'missing');
  for (const value of ['{', JSON.stringify({ ...savedV2(), version: 2 }), JSON.stringify({ ...savedV2(), userId: '1' }), JSON.stringify({ ...savedV2(), refreshToken: 'invalid' }), JSON.stringify({ ...savedV2(), access_token: 'must-not-persist' }), JSON.stringify({ ...savedV2(), pending: { originalRefreshToken: 'B'.repeat(43), retryKey: 'A'.repeat(43), preparedAt: 1000 } })]) {
    h.data.set('dabbarha_session_v2', value);
    assert.equal((await api.readSessionRecord(scope.generation, 1000)).status, 'invalid');
  }
  h.data.set('dabbarha_session_v2', JSON.stringify(savedV2()));
  assert.equal((await api.readSessionRecord(scope.generation, 2000)).status, 'expired');
  const pending = { ...savedV2(), pending: { originalRefreshToken: 'A'.repeat(43), retryKey: 'A'.repeat(43), preparedAt: 1990 } };
  h.data.set('dabbarha_session_v2', JSON.stringify(pending));
  assert.equal((await api.readSessionRecord(scope.generation, 2001)).status, 'pending');
  assert.equal((await api.readSessionRecord(scope.generation, 2050)).status, 'recovery-unavailable');
  assert.equal((await api.readSessionRecord(scope.generation, 3000)).status, 'expired');
  await h.clearSession();
});

test('V2 failed preparation/successor writes preserve last durable operation', async () => {
  const faults = {}; const h = harness(new Map(), faults); const api = h.load('src/utils/sessionStorage.ts'); const scope = scopeV2(h);
  await api.saveNewSession(scope, savedV2(), 1000); faults.writes = true;
  await assert.rejects(api.prepareRefresh(scope, 'A'.repeat(43), 1001));
  assert.equal(JSON.parse(h.data.get('dabbarha_session_v2')).pending, null);
  faults.writes = false; const pending = await api.prepareRefresh(scope, 'A'.repeat(43), 1002);
  faults.writes = true;
  await assert.rejects(api.saveRefreshSuccessor(scope, pending.pending, { ...savedV2(), refreshToken: 'B'.repeat(42) + 'A' }, 1003));
  const restart = harness(h.data, faults); const disk = restart.load('src/utils/sessionStorage.ts');
  assert.deepEqual(plain((await disk.readSessionRecord(0, 1004)).record), plain(pending));
  faults.writes = false; await restart.clearSession();
});

test('V2 logout deletion failure blocks restart; recovery and account switching reject stale writes', async () => {
  const faults = {}; const h = harness(new Map(), faults); const api = h.load('src/utils/sessionStorage.ts'); const scope = scopeV2(h);
  await api.saveNewSession(scope, savedV2(), 1000); const pending = await api.prepareRefresh(scope, 'A'.repeat(43), 1001);
  faults.deletes = true; await h.clearSession();
  const restart = harness(h.data, faults); const disk = restart.load('src/utils/sessionStorage.ts');
  assert.equal((await disk.readSessionRecord(0, 1002)).status, 'blocked');
  assert.equal(restart.store.getState().user, null);
  await assert.rejects(api.saveRefreshSuccessor(scope, pending.pending, { ...savedV2(), refreshToken: 'B'.repeat(42) + 'A' }, 1003));
  faults.deletes = false; await h.clearSession();
  const b = { ...savedV2(), userId: 2, sessionId: '22222222-2222-4222-8222-222222222222' };
  await api.saveNewSession(scopeV2(h, b), b, 1004);
  await assert.rejects(api.prepareRefresh({ ...scopeV2(h), userId: 1 }, 'A'.repeat(43), 1005), /identity/);
  await assert.rejects(api.saveNewSession(scope, savedV2(), 1005));
  assert.equal(JSON.parse(h.data.get('dabbarha_session_v2')).userId, 2); await h.clearSession();
});

test('queued V2 write cannot publish after logout or overwrite the next account', async () => {
  const h = harness(); const api = h.load('src/utils/sessionStorage.ts'); const scope = scopeV2(h); const gate = deferred();
  const blocker = h.session.authStorageTask(() => gate.promise);
  const writing = api.saveNewSession(scope, savedV2(), 1000).catch(e => e);
  const logout = h.clearSession(); gate.resolve(); await blocker; await logout;
  assert.equal((await writing).code, 'ERR_CANCELED'); assert.equal(h.data.size, 0);
});

test('V2 native read failure is not treated as missing or valid authentication', async () => {
  const load = loader({ '@/constants/config': { config: { tokenStorageKey: 'token', userStorageKey: 'user' } },
    'expo-secure-store': { getItemAsync: async () => { throw new Error('storage unavailable'); } } });
  await assert.rejects(load('src/utils/sessionStorage.ts').readSessionRecord(0, 1000), /storage unavailable/);
});

test('in-flight V2 native write is followed by logout deletion before the next account writes', async () => {
  const data = new Map(); const gate = deferred(); let started = false;
  const load = loader({ '@/constants/config': { config: { tokenStorageKey: 'token', userStorageKey: 'user' } },
    'expo-secure-store': {
      getItemAsync: async key => data.get(key) || null,
      setItemAsync: async (key, value) => { if (key === 'dabbarha_session_v2' && !started) { started = true; await gate.promise; } data.set(key, value); },
      deleteItemAsync: async key => { data.delete(key); },
    } });
  const session = load('src/api/session.ts'); const disk = load('src/utils/sessionStorage.ts');
  const scope = { generation: 0, userId: 1, sessionId: savedV2().sessionId };
  const writing = disk.saveNewSession(scope, savedV2(), 1000).catch(e => e);
  await tick(); assert.equal(started, true);
  const generation = session.resetPrivateSession();
  const cleanup = session.authStorageTask(load('src/utils/storage.ts').clearAuthStorage);
  const b = { ...savedV2(), userId: 2, sessionId: '22222222-2222-4222-8222-222222222222' };
  const savingB = disk.saveNewSession({ generation, userId: 2, sessionId: b.sessionId }, b, 1001);
  gate.resolve(); assert.equal((await writing).code, 'ERR_CANCELED'); await cleanup; await savingB;
  assert.equal(JSON.parse(data.get('dabbarha_session_v2')).userId, 2);
  await session.authStorageTask(load('src/utils/storage.ts').clearAuthStorage);
});

test('session API contract bodies, responses and explicit authentication modes', async () => {
  const h = harness(); const api = h.load('src/api/sessions.ts').sessionsApi;
  const pair = { access_token: 'synthetic', token_type: 'bearer', expires_in: 900, refresh_token: 'A'.repeat(43), refresh_expires_at: 123, session_id: '11111111-1111-4111-8111-111111111111', session_expires_at: 456 };
  const calls = [];
  h.client.defaults.headers.common.Authorization = 'Bearer inherited-must-be-removed';
  h.setHandler(async config => { calls.push(config); return h.success(config, pair); });
  const login = { email: 'test@example.com', password: 'x', device_label: 'My phone' };
  assert.deepEqual(await api.create(login), pair);
  const refresh = { refresh_token: 'A'.repeat(43), retry_key: 'B'.repeat(42) + 'A' };
  assert.deepEqual(await api.refresh(refresh), pair);
  assert.equal(await api.logoutWithRefresh({ refresh_token: refresh.refresh_token }), undefined);
  assert.deepEqual(calls.map(c => c.url), ['/auth/sessions', '/auth/refresh', '/auth/logout']);
  assert.deepEqual(calls.map(c => JSON.parse(c.data)), [login, refresh, { refresh_token: refresh.refresh_token }]);
  assert.ok(calls.every(c => !c.headers.has('Authorization')));
  await h.clearSession();
  // Protected operations still require an active session and replace stale headers.
  const id = h.session.sessionSnapshot().generation; h.session.setSessionToken(id, 'current');
  const rows = [{ id: pair.session_id, device_label: null, created_at: 1, last_refreshed_at: 2, idle_expires_at: 3, absolute_expires_at: 4, revoked_at: null, current: true }];
  h.setHandler(async config => { calls.push(config); assert.equal(config.headers.Authorization, 'Bearer current'); return h.success(config, rows); });
  assert.deepEqual(await api.list({ offset: 3, limit: 10 }), rows);
  assert.deepEqual(plain(calls.at(-1).params), { offset: 3, limit: 10 });
  await api.revoke(pair.session_id, { password: 'x' });
  assert.equal(calls.at(-1).url, `/auth/sessions/${pair.session_id}/revoke`);
  assert.deepEqual(JSON.parse(calls.at(-1).data), { password: 'x' });
  await api.logoutWithAccess(); assert.equal(calls.at(-1).data, undefined);
  await h.clearSession(); await assert.rejects(api.list());
});

test('session public errors preserve detail and Retry-After without ending an active session', async () => {
  const h = harness(); await h.login('A'); const api = h.load('src/api/sessions.ts').sessionsApi;
  for (const status of [401, 409, 410, 422, 429, 503]) {
    const detail = status === 422 ? [{ loc: ['body', 'retry_key'], msg: 'Invalid credential', type: 'value_error' }] : status === 409 ? 'refresh_conflict' : 'synthetic failure';
    h.setHandler(async config => { const error = h.failure(config, status, detail); error.response.headers = new axios.AxiosHeaders({ 'Retry-After': '17' }); throw error; });
    await assert.rejects(api.refresh({ refresh_token: 'A'.repeat(43), retry_key: 'A'.repeat(43) }), error => {
      assert.equal(error.statusCode, status); assert.deepEqual(error.detail, detail); assert.equal(error.retryAfter, '17'); return true;
    });
    assert.equal(h.store.getState().user.id, 1);
  }
  await h.clearSession();
});

test('session endpoints retain late-response generation protection', async () => {
  const h = harness(); const pending = deferred(); let request;
  h.setHandler(config => { request = config; return pending.promise; });
  const result = h.load('src/api/sessions.ts').sessionsApi.refresh({ refresh_token: 'A'.repeat(43), retry_key: 'A'.repeat(43) }).catch(e => e);
  await tick(); await h.clearSession(); pending.resolve(h.success(request, { access_token: 'old' }));
  assert.equal((await result).code, 'ERR_CANCELED');
});

test('registration uses Unicode code points and preserves legacy login passwords and translations', () => {
  const load = loader(); const { registerSchema, loginSchema } = load('src/schemas/auth.ts');
  const i18n = load('src/i18n/index.ts'); const base = { name: 'Test', email: 'test@example.com' };
  for (const password of ['12345678', 'x'.repeat(128), '😀'.repeat(8), '😀'.repeat(128), '  secret  ']) {
    assert.equal(registerSchema.parse({ ...base, password }).password, password);
  }
  for (const password of ['1234567', 'x'.repeat(129), '😀'.repeat(7), '😀'.repeat(129), ' '.repeat(8), '\u0085'.repeat(8), 'abcdefg\ud800', 'abcdefg\udc00']) {
    const result = registerSchema.safeParse({ ...base, password }); assert.equal(result.success, false);
    for (const issue of result.error.issues) {
      i18n.setTranslationLanguage('ar'); assert.match(i18n.translateMessage(issue.message), /[\u0600-\u06ff]/);
      i18n.setTranslationLanguage('en'); assert.equal(i18n.translateMessage(issue.message), issue.message);
    }
  }
  assert.equal(registerSchema.safeParse({ ...base, name: '😀'.repeat(120), password: '12345678' }).success, true);
  assert.equal(registerSchema.safeParse({ ...base, name: 'x'.repeat(121), password: '12345678' }).success, false);
  assert.equal(registerSchema.safeParse({ ...base, email: 'invalid', password: '12345678' }).success, false);
  for (const password of ['x', '123456', 'x'.repeat(129), '  x  ']) assert.equal(loginSchema.parse({ email: base.email, password }).password, password);
});

test('stable Affordability backend messages preserve English and translate to Arabic', () => {
  const load = loader({ './client': { apiClient: {} } });
  const i18n = load('src/i18n/index.ts');
  const { affordabilityErrorMessage } = load('src/api/affordability.ts');
  const messages = ["The total scheduled payments exceed the supported amount range.","This rate and term do not produce a supported amortizing schedule.","The total plan payments exceed the supported amount range.","This rate and term do not fully repay the financed balance.","A scheduled installment exceeds the supported amount range.","Installment principal and interest do not reconcile with its scheduled amount.","Nominal annual interest rate must be between 0% and 100%.","Nominal annual interest rate supports up to four decimal places.","Installment duration must be between 1 and 1,200 months.","Purchase price must be greater than zero and within the supported amount range.","Down payment must be less than the purchase price.","Enter a valid provider monthly installment amount.","Do not send a manual monthly amount for an automatic calculation.","No-interest plans must use a 0% annual rate.","Enter a monthly amount or a purchase price and payment method.","Installment plan fields require purchase_price.","Choose a payment method for a purchase-price affordability assessment.","A down-payment date or paid status requires a positive amount.","Enter the exact date for the down payment.","Enter the provider's actual monthly installment.","Send the monthly installment in only one field.","Automatic calculations do not accept a manual monthly amount.","The requested period extends beyond the supported calendar (year 9999).","The complete affordability period cannot exceed 1,200 months.","A numeric value is required; true/false is not accepted.","Affordability evaluation does not accept query parameters"];
  for (const message of messages) {
    i18n.setTranslationLanguage('en');
    assert.equal(i18n.translateMessage(affordabilityErrorMessage(message)), message);
    assert.equal(affordabilityErrorMessage(`Value error, ${message}`), message);
    i18n.setTranslationLanguage('ar');
    const translated = i18n.translateMessage(affordabilityErrorMessage(message));
    assert.match(translated, /[\u0600-\u06ff]/); assert.notEqual(translated, message);
  }
  const fallback = affordabilityErrorMessage('internal error with private data');
  assert.match(i18n.translateMessage(fallback), /[\u0600-\u06ff]/);
  assert.equal(i18n.translateMessage('arbitrary user text'), 'arbitrary user text');
  i18n.setTranslationLanguage('en');
  assert.equal(i18n.translateMessage(fallback), 'We could not evaluate this payment plan. Check your entries and try again.');
});

test('failed credential deletion blocks restoration across restart and login retries cleanup', async () => {
  const data = new Map(); const faults = {};
  const a = harness(data, faults); await a.login('A');
  a.query.setQueryData(['private'], { owner: 'A' }); faults.deletes = true;
  await a.store.getState().logout();
  assert.equal(data.has('token'), false); assert.equal(JSON.parse(data.get('dabbarha_session_v2')).userId, 1);
  assert.equal(data.get('token_logout_pending'), '1');
  assert.equal(a.store.getState().user, null); assert.equal(a.query.getQueryCache().getAll().length, 0);
  assert.match(a.store.getState().error, /Try signing in again/);
  a.store.getState().clearError(); assert.ok(a.store.getState().error);
  const restarted = harness(data, faults); let calls = 0;
  restarted.setHandler(async () => { calls++; throw new Error('must not send old token'); });
  await restarted.store.getState().initializeAuth();
  assert.equal(calls, 0); assert.equal(restarted.store.getState().isAuthenticated, false);
  await assert.rejects(restarted.login('B')); assert.equal(calls, 0);
  faults.deletes = false;
  const recovered = harness(data, faults); await recovered.store.getState().initializeAuth();
  assert.equal(recovered.store.getState().isAuthenticated, false); assert.equal(data.size, 0);
  await recovered.login('B'); assert.equal(recovered.store.getState().user.id, 2);
  assert.equal(recovered.store.getState().error, null);
  const normalRestart = harness(data, faults); const successor = rotatedPair(normalRestart);
  normalRestart.setHandler(async config => normalRestart.success(config, config.url === '/auth/refresh' ? successor : { id: 2 }));
  await normalRestart.store.getState().initializeAuth();
  assert.equal(normalRestart.store.getState().isAuthenticated, true);
  assert.equal(JSON.parse(data.get('dabbarha_session_v2')).userId, 2);
  await normalRestart.clearSession(); assert.equal(data.size, 0);
});

test('complete storage failure reports lack of durable protection without retaining private memory', async () => {
  const data = new Map(); const faults = {}; const h = harness(data, faults);
  await h.login('A'); faults.deletes = true; faults.writes = true;
  await h.clearSession();
  assert.equal(h.store.getState().isAuthenticated, false);
  assert.match(h.store.getState().error, /could not be cleared or blocked from restoration/);
  assert.equal(JSON.parse(data.get('dabbarha_session_v2')).userId, 1); assert.equal(data.has('token_logout_pending'), false);
  // OS-wide write failure cannot leave a durable marker; expose this limitation.
  faults.deletes = false; faults.writes = false;
  await h.login('B'); assert.equal(h.store.getState().user.id, 2); await h.clearSession();
});

test('token replacement prevents restoration when logout marker cannot be written', async () => {
  const data = new Map([['token', 'A']]);
  const load = loader({ '@/constants/config': { config: { tokenStorageKey: 'token', userStorageKey: 'user' } },
    'expo-secure-store': {
      getItemAsync: async key => data.get(key) || null,
      setItemAsync: async (key, value) => { if (!['token', 'dabbarha_session_v2'].includes(key)) throw new Error('marker unavailable'); data.set(key, value); },
      deleteItemAsync: async () => { throw new Error('deletion unavailable'); },
    } });
  await assert.rejects(load('src/utils/storage.ts').clearAuthStorage(), /Try signing in again/);
  assert.equal(data.get('token'), '');
  const restarted = harness(data); let calls = 0;
  restarted.setHandler(async () => { calls++; throw new Error('must not restore'); });
  await restarted.store.getState().initializeAuth();
  assert.equal(calls, 0); assert.equal(restarted.store.getState().isAuthenticated, false);
});

for (const mode of ['success', 'cache-failure', 'api-failure']) test(`financial profile PATCH: ${mode} preserves authoritative state and invalidation`, async () => {
  const faults = {}; const h = harness(new Map(), faults); await h.login('A');
  const id = h.session.sessionSnapshot().generation;
  const before = h.store.getState().user;
  const updated = { ...before, monthly_income: '9000', fixed_expenses: '2000' };
  for (const name of ['dashboard-summary', 'forecast']) {
    h.query.setQueryDefaults([name], { gcTime: Infinity });
    h.query.setQueryData([name, id, before.id], { previous: true });
    h.query.setQueryData([name, id + 1, 2], { otherGeneration: true });
  }
  let calls = 0;
  h.setHandler(async config => {
    assert.equal(config.url, '/auth/me'); assert.equal(config.method, 'patch'); calls++;
    if (mode === 'api-failure') throw h.failure(config, 503, 'Profile temporarily unavailable');
    return h.success(config, updated);
  });
  faults.rejectWrite = key => mode === 'cache-failure' && key === 'user';
  if (mode === 'api-failure') {
    await assert.rejects(h.store.getState().updateProfile({ monthly_income: '9000' }), e => e.statusCode === 503);
    assert.deepEqual(plain(h.store.getState().user), plain(before));
    assert.equal(h.store.getState().error, 'Profile temporarily unavailable');
  } else {
    const result = await h.store.getState().updateProfile({ monthly_income: '9000' });
    assert.deepEqual(plain(result), updated); assert.deepEqual(plain(h.store.getState().user), updated);
    assert.equal(h.store.getState().error, null);
    if (mode === 'success') assert.deepEqual(JSON.parse(h.data.get('user')), updated);
    else assert.equal(h.data.has('user'), false);
  }
  assert.equal(calls, 1); assert.equal(h.store.getState().isLoading, false);
  assert.equal(h.store.getState().isAuthenticated, true);
  for (const name of ['dashboard-summary', 'forecast']) {
    assert.equal(h.query.getQueryState([name, id, before.id]).isInvalidated, mode !== 'api-failure');
    assert.equal(h.query.getQueryState([name, id + 1, 2]).isInvalidated, false);
  }
  await h.clearSession();
});

test('profile publishes before optional cache write; logout and B login cannot receive its late completion', async () => {
  const faults = {}; const h = harness(new Map(), faults); await h.login('A');
  const updated = { ...h.store.getState().user, monthly_income: '9000' };
  const gate = deferred(), entered = deferred();
  faults.beforeWrite = async key => { if (key === 'user') { entered.resolve(); await gate.promise; } };
  h.setHandler(async config => config.method === 'patch' ? h.success(config, updated)
    : config.url === '/auth/sessions' ? h.success(config, loginPair('B'))
    : h.success(config, { ...updated, id: 2, monthly_income: '3000' }));
  const pending = h.store.getState().updateProfile({ monthly_income: '9000' }).catch(e => e);
  await entered.promise;
  assert.equal(h.store.getState().user.monthly_income, '9000');
  const cleanup = h.clearSession(); gate.resolve(); await cleanup;
  assert.equal((await pending).code, 'ERR_CANCELED');
  faults.beforeWrite = undefined; await h.login('B');
  assert.equal(h.store.getState().user.id, 2); assert.equal(h.store.getState().user.monthly_income, '3000');
  assert.equal(h.data.has('user'), false); await h.clearSession();
});

test('late profile PATCH from A cannot publish or invalidate B financial state', async () => {
  const h = harness(); await h.login('A'); const gate = deferred(), entered = deferred();
  const oldUser = h.store.getState().user;
  h.setHandler(async config => {
    if (config.method === 'patch') { entered.resolve(); await gate.promise; return h.success(config, { ...oldUser, monthly_income: '9000' }); }
    if (config.url === '/auth/sessions') return h.success(config, loginPair('B'));
    return h.success(config, { ...oldUser, id: 2, monthly_income: '3000' });
  });
  const pending = h.store.getState().updateProfile({ monthly_income: '9000' }).catch(e => e);
  await entered.promise; await h.clearSession(); await h.login('B');
  const key = ['dashboard-summary', h.session.sessionSnapshot().generation, 2];
  h.query.setQueryDefaults(['dashboard-summary'], { gcTime: Infinity }); h.query.setQueryData(key, { owner: 2 });
  gate.resolve(); assert.equal((await pending).code, 'ERR_CANCELED');
  assert.equal(h.store.getState().user.id, 2); assert.equal(h.query.getQueryState(key).isInvalidated, false);
  await h.clearSession();
});

test('obligation monetary schema rejects non-finite input and preserves ordinary and normalized amounts', () => {
  const load = loader(); const { obligationSchema } = load('src/schemas/obligation.ts');
  const { normalizeNumericInput } = load('src/i18n/index.ts');
  const base = { provider: 'Synthetic', item_name: 'Synthetic', category: 'Electronics', total_amount: '12000',
    monthly_installment_amount: '1000', start_date: '2026-11-01', term_months: '12', due_day_of_month: '1', status: 'active' };
  for (const field of ['total_amount', 'monthly_installment_amount']) {
    for (const value of ['Infinity', '-Infinity', 'NaN', '1e309', '-1e309', '  Infinity  ', 'invalid']) {
      const result = obligationSchema.safeParse({ ...base, [field]: value });
      assert.equal(result.success, false, `${field}: ${value}`);
      assert.ok(result.error.issues.some(issue => issue.path[0] === field));
    }
    for (const value of ['0', '0.01', '12000', '1250.50', ' 250.75 ', '1.234', '1e3']) {
      const parsed = obligationSchema.parse({ ...base, [field]: value });
      assert.ok(Number.isFinite(Number(parsed[field])));
      assert.notEqual(JSON.parse(JSON.stringify({ amount: Number(parsed[field]) })).amount, null);
    }
    for (const input of ['\u0661\u0662\u0663\u0664\u066b\u0665\u0660', '\u06f1\u06f2\u06f3\u06f4\u066b\u06f5\u06f0']) {
      assert.equal(obligationSchema.parse({ ...base, [field]: normalizeNumericInput(input) })[field], '1234.50');
    }
  }
});

test('obligation create/update reject non-finite monetary payloads before transport', async () => {
  const h = harness(); await h.login('A'); const api = h.load('src/api/obligations.ts').obligationsApi;
  let calls = 0; const payloads = [];
  h.setHandler(async config => { calls++; payloads.push(JSON.parse(config.data)); return h.success(config, { id: 1 }); });
  const base = { provider: 'Synthetic', item_name: 'Synthetic', category: 'Electronics', total_amount: 12000,
    monthly_installment_amount: 1000, start_date: '2026-11-01', term_months: 12, due_day_of_month: 1 };
  for (const field of ['total_amount', 'monthly_installment_amount']) {
    for (const value of [Infinity, -Infinity, NaN, 'Infinity', '-Infinity', 'NaN', '1e309', null]) {
      await assert.rejects(api.createObligation({ ...base, [field]: value }));
      await assert.rejects(api.updateObligation(1, { [field]: value }));
    }
  }
  assert.equal(calls, 0);
  await api.createObligation({ ...base, total_amount: 0, monthly_installment_amount: '12.50' });
  await api.updateObligation(1, { total_amount: '1250.75' });
  await api.updateObligation(1, { status: 'completed' });
  assert.equal(calls, 3); assert.equal(payloads[0].total_amount, 0);
  assert.equal(payloads[0].monthly_installment_amount, '12.50'); assert.equal(payloads[1].total_amount, '1250.75');
  assert.deepEqual(payloads[2], { status: 'completed' }); await h.clearSession();
});

function loginPair(name = 'A') {
  const now = Math.floor(Date.now() / 1000);
  return { access_token: name, token_type: 'bearer', expires_in: 900,
    refresh_token: name.repeat(42) + 'A', refresh_expires_at: now + 3600,
    session_id: name === 'A' ? '11111111-1111-4111-8111-111111111111' : '22222222-2222-4222-8222-222222222222',
    session_expires_at: now + 7200 };
}

function harness(data = new Map(), faults = {}) {
  const load = loader({
    'expo-crypto': { getRandomBytesAsync: async count => { if (faults.crypto) throw new Error('must reuse pending key'); return new Uint8Array(require('node:crypto').randomBytes(count)); } },
    '@/constants/config': { API_BASE_URL: 'https://synthetic.invalid', config: { apiTimeoutMs: 100, tokenStorageKey: 'token', userStorageKey: 'user' } },
    'expo-secure-store': {
      getItemAsync: async key => { if (faults.reads) throw new Error('storage unavailable'); return data.get(key) ?? null; },
      setItemAsync: async (key, value) => {
        await faults.beforeWrite?.(key, value);
        if (faults.writes || faults.rejectWrite?.(key, value)) throw new Error('storage unavailable');
        data.set(key, value);
        if (faults.ambiguous?.(key, value)) throw new Error('ambiguous write');
      },
      deleteItemAsync: async key => { if (faults.deletes) throw new Error('storage unavailable'); data.delete(key); },
    },
  }, faults.now ? { Date: class extends Date { static now() { return faults.now() * 1000; } } } : {});
  const { useAuthStore: store, clearSession } = load('src/store/authStore.ts');
  const { apiClient: client } = load('src/api/client.ts');
  const { logoutClient } = load('src/api/logout.ts');
  const { queryClient: query } = load('src/api/queryClient.ts');
  // Keep production freshness/retry behavior, but do not retain GC timers in Node.
  query.setDefaultOptions({ queries: { ...query.getDefaultOptions().queries, gcTime: 0 }, mutations: { ...query.getDefaultOptions().mutations, gcTime: 0 } });
  const session = load('src/api/session.ts');
  const success = (config, body) => ({ data: body, status: 200, statusText: 'OK', headers: {}, config });
  const failure = (config, status, detail) => new axios.AxiosError('synthetic failure', 'ERR_BAD_RESPONSE', config, {}, { data: { detail }, status, headers: {}, config });
  let handler = async config => {
    if (config.url === '/auth/sessions') return success(config, loginPair(JSON.parse(config.data).email));
    if (config.url === '/auth/me') return success(config, { id: config.headers.Authorization.endsWith('A') ? 1 : 2, name: 'Synthetic', monthly_income: '5000', fixed_expenses: '1000', currency: 'EGP' });
    return success(config, { owner: config.headers.Authorization });
  };
  client.defaults.adapter = config => handler(config);
  logoutClient.defaults.adapter = async config => ({ ...success(config, undefined), status: 204 });
  return { data, load, store, clearSession, client, logoutClient, query, session, success, failure,
    setHandler: next => { handler = next; }, login: name => store.getState().login({ email: name, password: 'synthetic-only' }) };
}

test('server logout invalidates immediately, clears caches and sends one bearer-free refresh credential', async () => {
  const h = harness(); await h.login('A'); const original = JSON.parse(h.data.get('dabbarha_session_v2'));
  const old = h.session.sessionSnapshot(); h.session.setSessionToken(old.generation, 'expired-access', 1);
  h.query.setQueryData(['private'], { owner: 1 });
  await h.query.getMutationCache().build(h.query, { mutationFn: async () => ({ owner: 1 }) }).execute({});
  h.logoutClient.defaults.headers.common.Authorization = 'Bearer must-not-send';
  h.logoutClient.defaults.auth = { username: 'must-not-send', password: 'must-not-send' };
  let calls = 0;
  h.logoutClient.defaults.adapter = async config => {
    calls++; assert.equal(config.url, '/auth/logout'); assert.equal(config.method, 'post');
    assert.deepEqual(JSON.parse(config.data), { refresh_token: original.refreshToken });
    assert.equal(config.headers.has('Authorization'), false); assert.equal(config.auth, undefined);
    assert.equal(config.timeout, 10000); assert.notEqual(config.signal, old.signal); assert.equal(config.signal.aborted, false);
    assert.equal(h.store.getState().isAuthenticated, false); assert.equal(h.store.getState().isLoading, false);
    assert.equal(h.data.size, 0); return { ...h.success(config, undefined), status: 204 };
  };
  const result = h.store.getState().logout();
  assert.equal(h.store.getState().isAuthenticated, false); assert.equal(h.store.getState().token, null);
  assert.equal(h.session.sessionSnapshot().token, null); assert.equal(old.signal.aborted, true);
  assert.equal(h.query.getQueryCache().getAll().length, 0); assert.equal(h.query.getMutationCache().getAll().length, 0);
  await result; assert.equal(calls, 1); assert.equal(h.store.getState().logoutRevocation, 'confirmed');
  assert.equal(h.store.getState().error, null);
});

test('duplicate logout calls share one attempt, including after idempotent server confirmation', async () => {
  const h = harness(); await h.login('A'); const gate = deferred(); const entered = deferred(); let calls = 0;
  h.logoutClient.defaults.adapter = async config => { calls++; entered.resolve(); await gate.promise; return { ...h.success(config, undefined), status: 204 }; };
  const a = h.store.getState().logout(), b = h.store.getState().logout(); assert.equal(a, b);
  await entered.promise; assert.equal(h.store.getState().isLoading, false); assert.equal(h.store.getState().logoutRevocation, 'pending');
  gate.resolve(); await a; await b; await h.store.getState().logout(); assert.equal(calls, 1);
  // A 204 is also the backend result for an already-revoked/unknown token.
  assert.equal(h.store.getState().logoutRevocation, 'confirmed');
});

test('offline, timeout, invalid credentials, 429/503 and unexpected success do not claim revocation or leak errors', async () => {
  for (const status of [0, 'timeout', 401, 429, 503, 200]) {
    const h = harness(); await h.login('A'); const secret = JSON.parse(h.data.get('dabbarha_session_v2')).refreshToken; let calls = 0;
    h.logoutClient.defaults.adapter = async config => {
      calls++; if (status === 200) return h.success(config, {});
      if (status === 0 || status === 'timeout') throw new axios.AxiosError(secret, status === 0 ? 'ERR_NETWORK' : 'ECONNABORTED', config, {});
      const error = h.failure(config, status, secret); error.response.headers = new axios.AxiosHeaders({ 'Retry-After': '90' }); throw error;
    };
    await h.store.getState().logout(); assert.equal(calls, 1); assert.equal(h.data.size, 0);
    assert.equal(h.store.getState().isAuthenticated, false); assert.equal(h.store.getState().logoutRevocation, 'unconfirmed');
    const message = h.store.getState().error; assert.match(message, /revocation was not confirmed/); assert.equal(message.includes(secret), false);
    h.store.getState().clearError(); assert.equal(h.store.getState().error, message);
    const i18n = h.load('src/i18n/index.ts'); i18n.setTranslationLanguage('en'); assert.equal(i18n.translateMessage(message), message);
    i18n.setTranslationLanguage('ar'); assert.match(i18n.translateMessage(message), /[\u0600-\u06ff]/);
    assert.equal(h.session.sessionSnapshot().refreshable, false);
  }
});

test('logout deletion failures preserve marker recovery and report storage and revocation independently', async () => {
  for (const serverFails of [false, true]) for (const allWritesFail of [false, true]) {
    const faults = {}; const h = harness(new Map(), faults); await h.login('A'); faults.deletes = true; faults.writes = allWritesFail;
    h.logoutClient.defaults.adapter = async config => {
      if (serverFails) throw h.failure(config, 503, 'sensitive backend detail');
      return { ...h.success(config, undefined), status: 204 };
    };
    await h.store.getState().logout(); assert.equal(h.store.getState().isAuthenticated, false);
    assert.equal(h.store.getState().logoutRevocation, serverFails ? 'unconfirmed' : 'confirmed');
    assert.match(h.store.getState().error, allWritesFail ? /could not be cleared or blocked/ : /Try signing in again/);
    assert.equal(h.store.getState().error.includes('revocation was not confirmed'), serverFails);
    const i18n = h.load('src/i18n/index.ts'); i18n.setTranslationLanguage('ar');
    assert.match(i18n.translateMessage(h.store.getState().error), /[\u0600-\u06ff]/);
    if (!allWritesFail) {
      assert.equal(h.data.get('token_logout_pending'), '1');
      const restarted = harness(h.data, faults); let calls = 0;
      restarted.setHandler(async () => { calls++; throw new Error('must not restore'); });
      await restarted.store.getState().initializeAuth(); assert.equal(calls, 0); assert.equal(restarted.store.getState().isAuthenticated, false);
    }
    faults.deletes = false; faults.writes = false; await h.login('B'); assert.equal(h.store.getState().user.id, 2); await h.clearSession();
  }
});

test('unreadable or mismatched logout credentials are never sent and never block local cleanup', async () => {
  for (const stage of ['read', 'corrupt', 'identity']) {
    const faults = {}; const h = harness(new Map(), faults); await h.login('A');
    if (stage === 'read') faults.reads = true;
    if (stage === 'corrupt') h.data.set('dabbarha_session_v2', '{');
    if (stage === 'identity') h.data.set('dabbarha_session_v2', JSON.stringify({ ...JSON.parse(h.data.get('dabbarha_session_v2')), userId: 2 }));
    let calls = 0; h.logoutClient.defaults.adapter = async () => { calls++; throw new Error('must not send'); };
    await h.store.getState().logout(); assert.equal(calls, 0); assert.equal(h.data.size, 0);
    assert.equal(h.store.getState().logoutRevocation, 'unconfirmed'); assert.equal(h.store.getState().isLoading, false);
  }
});

test('Account A pending server logout cannot revoke or clear Account B or publish a stale failure', async () => {
  const h = harness(); await h.login('A'); const aToken = JSON.parse(h.data.get('dabbarha_session_v2')).refreshToken;
  const entered = deferred(), gate = deferred(); const bodies = [];
  h.logoutClient.defaults.adapter = async config => {
    bodies.push(JSON.parse(config.data));
    if (bodies.length === 1) { entered.resolve(); await gate.promise; throw h.failure(config, 503, 'old logout failure'); }
    return { ...h.success(config, undefined), status: 204 };
  };
  const a = h.store.getState().logout(); await entered.promise; await h.login('B');
  const bToken = JSON.parse(h.data.get('dabbarha_session_v2')).refreshToken;
  assert.equal(h.store.getState().user.id, 2); assert.equal(h.store.getState().error, null);
  assert.deepEqual(bodies, [{ refresh_token: aToken }]);
  gate.resolve(); await a;
  assert.equal(h.store.getState().user.id, 2); assert.equal(h.store.getState().token, 'B');
  assert.equal(JSON.parse(h.data.get('dabbarha_session_v2')).refreshToken, bToken);
  assert.equal(h.store.getState().error, null); assert.equal(h.store.getState().logoutRevocation, 'idle');
  await h.store.getState().logout(); assert.equal(h.store.getState().logoutRevocation, 'confirmed');
  assert.deepEqual(bodies, [{ refresh_token: aToken }, { refresh_token: bToken }]);
  assert.equal(h.store.getState().logoutRevocation, 'confirmed'); assert.equal(h.store.getState().error, null); assert.equal(h.data.size, 0);
});

test('logout during refresh uses the stored consumed-token credential and rejects the late successor', async () => {
  const h = harness(); await h.login('A'); const pair = rotatedPair(h); const gate = deferred(), entered = deferred();
  let original; let refreshes = 0;
  h.setHandler(async config => {
    if (config.url === '/auth/refresh') { refreshes++; original = JSON.parse(config.data).refresh_token; entered.resolve(); await gate.promise; return h.success(config, pair); }
    throw h.failure(config, 401, 'Could not validate credentials');
  });
  let sent;
  h.logoutClient.defaults.adapter = async config => { sent = JSON.parse(config.data); return { ...h.success(config, undefined), status: 204 }; };
  const request = h.client.get('/forecast').catch(e => e); await entered.promise;
  await h.store.getState().logout(); assert.deepEqual(sent, { refresh_token: original });
  gate.resolve(); assert.equal((await request).code, 'ERR_CANCELED'); assert.equal(refreshes, 1);
  assert.equal(h.data.size, 0); assert.equal(h.session.sessionSnapshot().token, null);
});

test('logout during restoration captures the right credential before deletion at every phase', async () => {
  for (const stage of ['refresh', 'identity', 'write']) {
    const faults = {}; const h = harness(coldData(), faults); const pair = rotatedPair(h);
    const original = JSON.parse(h.data.get('dabbarha_session_v2')).refreshToken; const gate = deferred(), entered = deferred();
    faults.beforeWrite = async (key, value) => {
      if (stage === 'write' && key === 'dabbarha_session_v2' && JSON.parse(value).refreshToken === pair.refresh_token) { entered.resolve(); await gate.promise; }
    };
    h.setHandler(async config => {
      if ((stage === 'refresh' && config.url === '/auth/refresh') || (stage === 'identity' && config.url === '/auth/me')) { entered.resolve(); await gate.promise; }
      return h.success(config, config.url === '/auth/refresh' ? pair : { id: 1 });
    });
    let credential;
    h.logoutClient.defaults.adapter = async config => { credential = JSON.parse(config.data).refresh_token; return { ...h.success(config, undefined), status: 204 }; };
    const restoring = h.store.getState().initializeAuth(); await entered.promise;
    const logout = h.store.getState().logout(); assert.equal(h.store.getState().isAuthenticated, false);
    gate.resolve(); await logout; await restoring;
    assert.equal(credential, stage === 'refresh' ? original : pair.refresh_token);
    assert.equal(h.data.size, 0); assert.equal(h.store.getState().logoutRevocation, 'confirmed');
  }
});

test('logout during login never resurrects credentials and reports when no revocation credential was received', async () => {
  for (const stage of ['create', 'identity', 'write']) {
    const faults = {}; const h = harness(new Map(), faults); const gate = deferred(), entered = deferred();
    faults.beforeWrite = async key => { if (stage === 'write' && key === 'dabbarha_session_v2') { entered.resolve(); await gate.promise; } };
    h.setHandler(async config => {
      if ((stage === 'create' && config.url === '/auth/sessions') || (stage === 'identity' && config.url === '/auth/me')) { entered.resolve(); await gate.promise; }
      return h.success(config, config.url === '/auth/sessions' ? loginPair() : { id: 1 });
    });
    let calls = 0; h.logoutClient.defaults.adapter = async config => { calls++; return { ...h.success(config, undefined), status: 204 }; };
    const login = h.login('A').catch(e => e); await entered.promise;
    const logout = h.store.getState().logout(); gate.resolve(); await logout; await login;
    assert.equal(h.store.getState().isAuthenticated, false); assert.equal(h.data.size, 0);
    assert.equal(calls, stage === 'write' ? 1 : 0);
    assert.equal(h.store.getState().logoutRevocation, stage === 'write' ? 'confirmed' : 'unconfirmed');
  }
});

test('legacy logout remains local-only and never sends a bearer to refresh-token logout', async () => {
  const h = harness(new Map([['token', 'A']])); await h.store.getState().initializeAuth(); let calls = 0;
  h.logoutClient.defaults.adapter = async () => { calls++; throw new Error('must not send'); };
  await h.store.getState().logout(); assert.equal(calls, 0); assert.equal(h.data.size, 0);
  assert.equal(h.store.getState().logoutRevocation, 'local-only'); assert.equal(h.store.getState().isAuthenticated, false);
  const source = fs.readFileSync('src/api/logout.ts', 'utf8'); assert.equal(/console\.(log|warn|error)/.test(source), false);
});

function coldData() {
  const pair = loginPair();
  return new Map([['dabbarha_session_v2', JSON.stringify({ version: 1, userId: 1, sessionId: pair.session_id,
    refreshToken: pair.refresh_token, refreshExpiresAt: pair.refresh_expires_at,
    sessionExpiresAt: pair.session_expires_at, pending: null })]]);
}

test('cold restoration rotates durably, validates identity and hides cached data until completion', async () => {
  const h = harness(coldData()); const pair = rotatedPair(h); const gate = deferred(); const entered = deferred(); const calls = [];
  h.query.setQueryData(['private'], { owner: 999 }); h.data.set('user', JSON.stringify({ id: 999 }));
  h.setHandler(async config => {
    calls.push(config.url);
    assert.equal(h.store.getState().isAuthenticated, false); assert.equal(h.store.getState().user, null);
    assert.equal(h.store.getState().isInitialized, false);
    if (config.url === '/auth/refresh') {
      assert.equal(config.headers.has('Authorization'), false);
      assert.ok(JSON.parse(h.data.get('dabbarha_session_v2')).pending); return h.success(config, pair);
    }
    assert.equal(config.url, '/auth/me'); assert.equal(config.headers.Authorization, 'Bearer rotated-access');
    assert.equal(JSON.parse(h.data.get('dabbarha_session_v2')).refreshToken, pair.refresh_token);
    entered.resolve(); await gate.promise; return h.success(config, { id: 1 });
  });
  const restoring = h.store.getState().initializeAuth(); await entered.promise;
  await h.store.getState().initializeAuth(); assert.deepEqual(calls, ['/auth/refresh', '/auth/me']);
  assert.equal(h.query.getQueryCache().getAll().length, 0); assert.equal(h.store.getState().token, null);
  gate.resolve(); await restoring;
  assert.equal(h.store.getState().isAuthenticated, true); assert.equal(h.store.getState().user.id, 1);
  assert.equal(h.session.sessionSnapshot().refreshable, true); assert.equal(h.store.getState().isLoading, false);
  assert.equal(h.data.has('token'), false); assert.equal(h.data.has('user'), false);
  assert.equal(h.data.get('dabbarha_session_v2').includes(pair.access_token), false); await h.clearSession();
});

test('valid V2 takes precedence over another legacy account and removes obsolete legacy credentials', async () => {
  const data = coldData(); data.set('token', 'B'); data.set('user', JSON.stringify({ id: 2 }));
  const h = harness(data); const pair = rotatedPair(h); const calls = [];
  h.setHandler(async config => {
    calls.push(config.url); assert.notEqual(config.headers.Authorization, 'Bearer B');
    return h.success(config, config.url === '/auth/refresh' ? pair : { id: 1 });
  });
  await h.store.getState().initializeAuth();
  assert.deepEqual(calls, ['/auth/refresh', '/auth/me']); assert.equal(h.store.getState().user.id, 1);
  assert.equal(data.has('token'), false); assert.equal(data.has('user'), false); await h.clearSession();
});

test('invalid, empty, expired and unrecoverable V2 records never fall back to legacy identity', async () => {
  const base = JSON.parse(coldData().get('dabbarha_session_v2')); const now = Math.floor(Date.now() / 1000);
  const values = ['', '{', JSON.stringify({ ...base, version: 99 }), JSON.stringify({ ...base, userId: '1' }),
    JSON.stringify({ ...base, sessionId: 'invalid' }), JSON.stringify({ ...base, refreshToken: 'invalid' }),
    JSON.stringify({ ...base, refreshExpiresAt: now - 1 }),
    JSON.stringify({ ...base, refreshExpiresAt: now - 2, sessionExpiresAt: now - 1 }),
    JSON.stringify({ ...base, pending: { originalRefreshToken: base.refreshToken, retryKey: 'B'.repeat(42) + 'A', preparedAt: now - 61 } })];
  for (const value of values) {
    const h = harness(new Map([['dabbarha_session_v2', value], ['token', 'B']])); let calls = 0;
    h.setHandler(async () => { calls++; throw new Error('must not fall back'); });
    await h.store.getState().initializeAuth(); assert.equal(calls, 0);
    assert.equal(h.store.getState().isAuthenticated, false); assert.equal(h.store.getState().isInitialized, true);
    assert.equal(h.store.getState().isLoading, false); assert.equal(h.store.getState().restorationRetryable, false);
    assert.equal(h.data.size, 0);
  }
});

test('missing credentials finish startup without requests and legacy outage preserves the legacy token', async () => {
  const h = harness(); let calls = 0;
  h.setHandler(async () => { calls++; throw new Error('no request expected'); });
  await h.store.getState().initializeAuth(); assert.equal(calls, 0); assert.equal(h.store.getState().isInitialized, true);
  const legacy = harness(new Map([['token', 'A']]));
  legacy.setHandler(async config => { throw new axios.AxiosError('offline', 'ERR_NETWORK', config, {}); });
  await legacy.store.getState().initializeAuth(); assert.equal(legacy.data.get('token'), 'A');
  assert.equal(legacy.store.getState().restorationRetryable, true); assert.equal(legacy.store.getState().isAuthenticated, false);
  await legacy.clearSession();
});

test('restoration identity mismatch and rejected identity cannot publish or fall back', async () => {
  for (const mismatch of [true, false]) {
    const data = coldData(); data.set('token', 'B'); const h = harness(data); const pair = rotatedPair(h);
    h.setHandler(async config => {
      if (config.url === '/auth/refresh') return h.success(config, pair);
      if (!mismatch) throw h.failure(config, 401, 'Could not validate credentials');
      return h.success(config, { id: 2 });
    });
    await h.store.getState().initializeAuth(); await h.session.authStorageTask(async () => {}); await tick();
    assert.equal(h.store.getState().isAuthenticated, false); assert.equal(h.session.sessionSnapshot().token, null);
    assert.equal(h.store.getState().isLoading, false); assert.equal(data.size, 0);
  }
});

test('revoked refresh and terminal recovery conflicts clear restoration credentials', async () => {
  for (const [status, detail] of [[401, 'Could not validate credentials'], [409, 'refresh_conflict'], [409, 'refresh_recovery_unavailable']]) {
    const h = harness(coldData()); let calls = 0;
    h.setHandler(async config => { calls++; assert.equal(config.url, '/auth/refresh'); throw h.failure(config, status, detail); });
    await h.store.getState().initializeAuth(); assert.equal(calls, 1);
    assert.equal(h.data.size, 0); assert.equal(h.store.getState().restorationRetryable, false);
    assert.equal(h.store.getState().isAuthenticated, false);
  }
});

test('restart recovers a pending operation with its original token/key, even after original token expiry', async () => {
  const data = coldData(); const record = JSON.parse(data.get('dabbarha_session_v2')); const now = Math.floor(Date.now() / 1000);
  record.refreshExpiresAt = now - 1;
  record.pending = { originalRefreshToken: record.refreshToken, retryKey: 'B'.repeat(42) + 'A', preparedAt: now - 3, attempts: 1 };
  data.set('dabbarha_session_v2', JSON.stringify(record)); const h = harness(data, { crypto: true });
  const pair = { ...rotatedPair(h), refresh_expires_at: now + 3600 }; let calls = 0;
  h.setHandler(async config => {
    if (config.url === '/auth/refresh') {
      calls++; assert.deepEqual(JSON.parse(config.data), { refresh_token: record.refreshToken, retry_key: record.pending.retryKey });
      assert.equal(JSON.parse(data.get('dabbarha_session_v2')).pending.attempts, 2); return h.success(config, pair);
    }
    return h.success(config, { id: 1 });
  });
  await h.store.getState().initializeAuth(); assert.equal(calls, 1); assert.equal(h.store.getState().isAuthenticated, true);
  assert.equal(JSON.parse(data.get('dabbarha_session_v2')).pending, null); await h.clearSession();
});

test('network failure and server cooldown exit startup without deleting durable restoration state', async () => {
  for (const status of [0, 429, 503]) {
    const h = harness(coldData()); let calls = 0;
    h.setHandler(async config => {
      calls++; assert.equal(config.url, '/auth/refresh');
      if (!status) throw new axios.AxiosError('offline', 'ERR_NETWORK', config, {});
      const error = h.failure(config, status, 'unavailable'); error.response.headers = new axios.AxiosHeaders({ 'Retry-After': '90' }); throw error;
    });
    await h.store.getState().initializeAuth();
    assert.equal(calls, status ? 1 : 3); assert.equal(h.store.getState().restorationRetryable, true);
    assert.equal(h.store.getState().isLoading, false); assert.equal(h.store.getState().isInitialized, true);
    assert.equal(h.store.getState().user, null); assert.equal(h.session.sessionSnapshot().token, null);
    const pending = JSON.parse(h.data.get('dabbarha_session_v2')).pending; assert.ok(pending);
    if (status) { await h.store.getState().initializeAuth(); assert.equal(calls, 1); assert.equal(h.store.getState().restorationRetryable, true); }
    const i18n = h.load('src/i18n/index.ts'); i18n.setTranslationLanguage('ar');
    assert.match(i18n.translateMessage(h.store.getState().error), /[\u0600-\u06ff]/);
    await h.clearSession();
  }
});

test('identity network failure preserves the rotated successor and explicit retry restores securely', async () => {
  const h = harness(coldData()); const first = rotatedPair(h);
  h.setHandler(async config => {
    if (config.url === '/auth/refresh') return h.success(config, first);
    throw new axios.AxiosError('offline', 'ERR_NETWORK', config, {});
  });
  await h.store.getState().initializeAuth(); assert.equal(h.store.getState().restorationRetryable, true);
  assert.equal(JSON.parse(h.data.get('dabbarha_session_v2')).refreshToken, first.refresh_token);
  const next = { ...first, access_token: 'second-access', refresh_token: 'D'.repeat(42) + 'A' };
  h.setHandler(async config => {
    if (config.url === '/auth/refresh') { assert.equal(JSON.parse(config.data).refresh_token, first.refresh_token); return h.success(config, next); }
    return h.success(config, { id: 1 });
  });
  await h.store.getState().initializeAuth(); assert.equal(h.store.getState().isAuthenticated, true);
  assert.equal(h.store.getState().token, next.access_token); assert.equal(h.store.getState().restorationRetryable, false);
  await h.clearSession();
});

test('restoration storage read/preparation/successor failures preserve recoverable records', async () => {
  for (const stage of ['read', 'prepare', 'successor']) {
    const faults = {}; const h = harness(coldData(), faults); const pair = rotatedPair(h); const original = h.data.get('dabbarha_session_v2');
    faults.reads = stage === 'read';
    faults.rejectWrite = (key, value) => key === 'dabbarha_session_v2' &&
      (stage === 'prepare' || (stage === 'successor' && JSON.parse(value).refreshToken === pair.refresh_token));
    h.setHandler(async config => h.success(config, config.url === '/auth/refresh' ? pair : { id: 1 }));
    await h.store.getState().initializeAuth(); assert.equal(h.store.getState().restorationRetryable, true);
    assert.equal(h.store.getState().isAuthenticated, false); assert.equal(h.session.sessionSnapshot().token, null);
    if (stage !== 'successor') assert.equal(h.data.get('dabbarha_session_v2'), original);
    else assert.ok(JSON.parse(h.data.get('dabbarha_session_v2')).pending);
    faults.reads = false; faults.rejectWrite = undefined;
    await h.store.getState().initializeAuth(); assert.equal(h.store.getState().isAuthenticated, true); await h.clearSession();
  }
});

test('logout/new login during restoration network or persistence cannot resurrect the old account', async () => {
  for (const stage of ['refresh', 'identity', 'write']) for (const switchAccount of [false, true]) {
    const faults = {}; const h = harness(coldData(), faults); const pair = rotatedPair(h); const entered = deferred(), gate = deferred();
    faults.beforeWrite = async (key, value) => {
      if (stage === 'write' && key === 'dabbarha_session_v2' && JSON.parse(value).refreshToken === pair.refresh_token) { entered.resolve(); await gate.promise; }
    };
    h.setHandler(async config => {
      if ((stage === 'refresh' && config.url === '/auth/refresh') || (stage === 'identity' && config.url === '/auth/me')) { entered.resolve(); await gate.promise; }
      return h.success(config, config.url === '/auth/refresh' ? pair : { id: 1 });
    });
    const restoring = h.store.getState().initializeAuth(); await entered.promise;
    h.setHandler(async config => h.success(config, config.url === '/auth/sessions' ? loginPair('B') : { id: 2 }));
    const replacement = switchAccount ? h.login('B') : h.clearSession();
    gate.resolve(); await replacement; await restoring;
    assert.equal(h.store.getState().isAuthenticated, switchAccount); assert.equal(h.store.getState().restorationRetryable, false);
    if (switchAccount) { assert.equal(h.store.getState().user.id, 2); assert.equal(JSON.parse(h.data.get('dabbarha_session_v2')).userId, 2); }
    else assert.equal(h.data.size, 0);
    await h.clearSession();
  }
});

test('recovery sign-in action preserves credentials until explicit login and never retries in a loop', async () => {
  const faults = { reads: true }; const h = harness(coldData(), faults);
  await h.store.getState().initializeAuth(); const original = h.data.get('dabbarha_session_v2');
  h.store.getState().dismissRestoration(); assert.equal(h.store.getState().restorationRetryable, false);
  await h.store.getState().initializeAuth(); assert.equal(h.data.get('dabbarha_session_v2'), original);
  faults.reads = false; await h.login('B'); assert.equal(h.store.getState().user.id, 2); await h.clearSession();
});

function rotatedPair(h) {
  const record = JSON.parse(h.data.get('dabbarha_session_v2'));
  return { access_token: 'rotated-access', token_type: 'bearer', expires_in: 900,
    refresh_token: 'C'.repeat(42) + 'A', refresh_expires_at: record.refreshExpiresAt,
    session_id: record.sessionId, session_expires_at: record.sessionExpiresAt };
}

test('automatic refresh joins concurrent 401s and waiting requests, persists before publishing, and replaces headers', async () => {
  const gate = deferred(); const entered = deferred(); const writeGate = deferred(); const writing = deferred();
  const faults = {}; const h = harness(new Map(), faults); await h.login('A'); const pair = rotatedPair(h);
  let refreshes = 0; const sent = [];
  h.query.setQueryDefaults(['private'], { gcTime: Infinity });
  h.query.setQueryData(['private'], { owner: 1 });
  faults.beforeWrite = async (key, value) => {
    if (key === 'dabbarha_session_v2' && JSON.parse(value).refreshToken === pair.refresh_token) { writing.resolve(); await writeGate.promise; }
  };
  h.setHandler(async config => {
    if (config.url === '/auth/refresh') {
      refreshes++; assert.equal(config.headers.has('Authorization'), false);
      const pending = JSON.parse(h.data.get('dabbarha_session_v2')).pending;
      assert.deepEqual(JSON.parse(config.data), { refresh_token: pending.originalRefreshToken, retry_key: pending.retryKey });
      assert.equal(pending.attempts, 1); assert.equal(pending.retryKey.length, 43);
      entered.resolve(); await gate.promise; return h.success(config, pair);
    }
    sent.push([config.url, config.headers.Authorization]);
    if (config.headers.Authorization === 'Bearer A') throw h.failure(config, 401, 'Could not validate credentials');
    return h.success(config, { owner: 1 });
  });
  const a = h.client.get('/dashboard/summary'), b = h.client.get('/forecast');
  await entered.promise; const c = h.client.get('/obligations'); await tick();
  assert.equal(sent.length, 2); gate.resolve(); await writing.promise;
  assert.equal(h.store.getState().token, 'A'); assert.equal(h.session.sessionSnapshot().token, 'A');
  assert.equal(sent.length, 2); writeGate.resolve(); await Promise.all([a,b,c]);
  assert.equal(refreshes, 1); assert.equal(sent.length, 5);
  assert.ok(sent.slice(2).every(([, header]) => header === 'Bearer rotated-access'));
  assert.equal(h.store.getState().token, pair.access_token); assert.equal(h.store.getState().isAuthenticated, true);
  const record = JSON.parse(h.data.get('dabbarha_session_v2'));
  assert.equal(record.refreshToken, pair.refresh_token); assert.equal(record.pending, null);
  assert.equal(h.data.has('token'), false); assert.equal(h.data.get('dabbarha_session_v2').includes(pair.access_token), false);
  assert.equal(h.query.getQueryData(['private']).owner, 1); await h.clearSession();
});

test('expired access refreshes before dispatch, including a mutation that has not been sent', async () => {
  for (const method of ['get', 'post']) {
    let now = Math.floor(Date.now() / 1000); const h = harness(new Map(), { now: () => now });
    await h.login('A'); const pair = rotatedPair(h); now += 901; const calls = [];
    h.setHandler(async config => {
      calls.push(config.url);
      if (config.url === '/auth/refresh') return h.success(config, pair);
      assert.equal(config.headers.Authorization, 'Bearer rotated-access'); return h.success(config, {});
    });
    await h.client.request({ method, url: '/obligations', data: method === 'post' ? { amount: 12 } : undefined });
    assert.deepEqual(calls, ['/auth/refresh', '/obligations']); await h.clearSession();
  }
});

test('mutating requests are never replayed after 401, even when refresh succeeds', async () => {
  for (const method of ['post', 'patch', 'put', 'delete']) {
    const h = harness(); await h.login('A'); const pair = rotatedPair(h); let sends = 0, refreshes = 0;
    h.setHandler(async config => {
      if (config.url === '/auth/refresh') { refreshes++; return h.success(config, pair); }
      sends++; throw h.failure(config, 401, 'Could not validate credentials');
    });
    await assert.rejects(h.client.request({ method, url: '/obligations/1/payments', data: { paid: true } }), error => {
      assert.equal(error.statusCode, 401); assert.match(error.message, /Review the action/);
      const i18n = h.load('src/i18n/index.ts'); i18n.setTranslationLanguage('ar');
      assert.match(i18n.translateMessage(error.message), /[\u0600-\u06ff]/); return true;
    });
    assert.equal(sends, 1); assert.equal(refreshes, 1); assert.equal(h.store.getState().isAuthenticated, true);
    await h.clearSession();
  }
});

test('a second GET 401 is terminal with one replay and no recursive refresh loop', async () => {
  const h = harness(); await h.login('A'); const pair = rotatedPair(h); let sends = 0, refreshes = 0;
  h.setHandler(async config => {
    if (config.url === '/auth/refresh') { refreshes++; return h.success(config, pair); }
    sends++; throw h.failure(config, 401, 'Could not validate credentials');
  });
  await assert.rejects(h.client.get('/forecast'), e => e.statusCode === 401);
  await h.session.authStorageTask(async () => {});
  assert.equal(sends, 2); assert.equal(refreshes, 1); assert.equal(h.store.getState().isAuthenticated, false);
  assert.equal(h.data.size, 0);
});

test('invalid/revoked refresh and both conflicts terminate locally without recursion or replay', async () => {
  for (const [status, detail] of [[401, 'Could not validate credentials'], [409, 'refresh_conflict'], [409, 'refresh_recovery_unavailable'], [422, 'Invalid credential']]) {
    const h = harness(); await h.login('A'); let sends = 0, refreshes = 0;
    h.query.setQueryData(['private'], { owner: 1 });
    h.setHandler(async config => {
      if (config.url === '/auth/refresh') { refreshes++; assert.equal(config.headers.has('Authorization'), false); throw h.failure(config, status, detail); }
      sends++; throw h.failure(config, 401, 'Could not validate credentials');
    });
    await assert.rejects(h.client.get('/forecast'), e => e.statusCode === 401);
    await h.session.authStorageTask(async () => {});
    assert.equal(sends, 1); assert.equal(refreshes, 1); assert.equal(h.store.getState().isAuthenticated, false);
    assert.equal(h.query.getQueryCache().getAll().length, 0); assert.equal(h.data.size, 0);
  }
});

test('automatic refresh respects durable 429/503 cooldown and blocks stale sends', async () => {
  for (const status of [429, 503]) {
    const h = harness(); await h.login('A'); let sends = 0, refreshes = 0;
    h.setHandler(async config => {
      if (config.url === '/auth/refresh') {
        refreshes++; const error = h.failure(config, status, 'unavailable');
        error.response.headers = new axios.AxiosHeaders({ 'Retry-After': '90' }); throw error;
      }
      sends++; throw h.failure(config, 401, 'Could not validate credentials');
    });
    await assert.rejects(h.client.get('/forecast'), e => e.statusCode === status && e.retryAfter === '90');
    const pending = JSON.parse(h.data.get('dabbarha_session_v2')).pending;
    assert.ok(pending.retryAfterAt >= pending.preparedAt + 90);
    await assert.rejects(h.client.get('/obligations'), e => e.statusCode === 503);
    assert.equal(sends, 1); assert.equal(refreshes, 1); assert.equal(h.store.getState().isAuthenticated, true);
    await h.clearSession();
  }
});

test('lost refresh response recovers through the existing coordinator with identical credentials', async () => {
  const h = harness(); await h.login('A'); const pair = rotatedPair(h); const bodies = [];
  h.setHandler(async config => {
    if (config.url === '/auth/refresh') {
      bodies.push(JSON.parse(config.data));
      if (bodies.length === 1) throw new axios.AxiosError('offline', 'ERR_NETWORK', config, {});
      return h.success(config, pair);
    }
    if (config.headers.Authorization === 'Bearer A') throw h.failure(config, 401, 'Could not validate credentials');
    return h.success(config, {});
  });
  await h.client.get('/forecast'); assert.equal(bodies.length, 2); assert.deepEqual(bodies[0], bodies[1]);
  assert.equal(h.store.getState().token, pair.access_token); await h.clearSession();
});

test('exhausted network recovery has a durable attempt bound and never sends stale requests', async () => {
  const h = harness(); await h.login('A'); let refreshes = 0, sends = 0;
  h.setHandler(async config => {
    if (config.url === '/auth/refresh') { refreshes++; throw new axios.AxiosError('offline', 'ERR_NETWORK', config, {}); }
    sends++; throw h.failure(config, 401, 'Could not validate credentials');
  });
  await assert.rejects(h.client.get('/forecast'), e => e.statusCode === 0);
  assert.equal(JSON.parse(h.data.get('dabbarha_session_v2')).pending.attempts, 3);
  await assert.rejects(h.client.get('/obligations'), e => e.statusCode === 401);
  assert.equal(refreshes, 3); assert.equal(sends, 1); await h.session.authStorageTask(async () => {});
  assert.equal(h.store.getState().isAuthenticated, false);
});

test('automatic refresh storage failures block stale sends and recover without publishing unsaved tokens', async () => {
  for (const stage of ['read', 'prepare', 'successor']) {
    const faults = {}; const h = harness(new Map(), faults); await h.login('A'); const pair = rotatedPair(h);
    if (stage === 'read') faults.reads = true;
    faults.rejectWrite = (key, value) => key === 'dabbarha_session_v2' &&
      (stage === 'prepare' || (stage === 'successor' && JSON.parse(value).refreshToken === pair.refresh_token));
    let sends = 0, refreshes = 0; const bodies = [];
    h.setHandler(async config => {
      if (config.url === '/auth/refresh') { refreshes++; bodies.push(JSON.parse(config.data)); return h.success(config, pair); }
      sends++; if (config.headers.Authorization === 'Bearer A') throw h.failure(config, 401, 'Could not validate credentials');
      return h.success(config, {});
    });
    await assert.rejects(h.client.get('/forecast'), e => e.statusCode === 503);
    assert.equal(h.store.getState().token, 'A'); assert.equal(h.session.sessionSnapshot().token, 'A');
    await assert.rejects(h.client.get('/obligations'), e => e.statusCode === 503);
    assert.equal(sends, 1); assert.equal(refreshes, stage === 'successor' ? 2 : 0);
    faults.reads = false; faults.rejectWrite = undefined;
    await h.client.get('/forecast'); assert.equal(sends, 2); assert.equal(h.store.getState().token, pair.access_token);
    if (stage === 'successor') assert.deepEqual(bodies, [bodies[0], bodies[0], bodies[0]]);
    await h.clearSession();
  }
});

test('logout and direct account switching cancel refresh and all waiting old-account requests', async () => {
  for (const switchAccount of [false, true]) {
    const h = harness(); await h.login('A'); const pair = rotatedPair(h); const gate = deferred(); const entered = deferred();
    const sends = [];
    h.setHandler(async config => {
      if (config.url === '/auth/refresh') { entered.resolve(); await gate.promise; return h.success(config, pair); }
      sends.push(config.url); throw h.failure(config, 401, 'Could not validate credentials');
    });
    const old = h.client.get('/forecast').catch(e => e); await entered.promise;
    const waiting = h.client.get('/obligations').catch(e => e); await tick();
    if (switchAccount) {
      h.setHandler(async config => h.success(config, config.url === '/auth/sessions' ? loginPair('B') : { id: 2 }));
      await h.login('B'); h.query.setQueryData(['private'], { owner: 2 });
    } else await h.clearSession();
    gate.resolve(); assert.equal((await old).code, 'ERR_CANCELED'); assert.equal((await waiting).code, 'ERR_CANCELED');
    assert.deepEqual(sends, ['/forecast']);
    assert.equal(h.store.getState().token, switchAccount ? 'B' : null);
    if (switchAccount) {
      assert.equal(JSON.parse(h.data.get('dabbarha_session_v2')).userId, 2);
      assert.equal(h.query.getQueryData(['private']).owner, 2);
    } else assert.equal(h.data.size, 0);
    await h.clearSession();
  }
});

test('a request created just before logout never dispatches under the next generation', async () => {
  const h = harness(); await h.login('A'); let sends = 0;
  h.setHandler(async config => { sends++; return h.success(config, {}); });
  const old = h.client.get('/forecast').catch(e => e);
  await h.clearSession(); assert.equal((await old).code, 'ERR_CANCELED'); assert.equal(sends, 0);
});

test('late 401 for a replaced token reuses the successor instead of rotating twice', async () => {
  const h = harness(); await h.login('A'); const pair = rotatedPair(h); const gate = deferred(); const entered = deferred(); let refreshes = 0;
  h.setHandler(async config => {
    if (config.url === '/auth/refresh') { refreshes++; return h.success(config, pair); }
    if (config.headers.Authorization === 'Bearer A') {
      if (config.url === '/slow') { entered.resolve(); await gate.promise; }
      throw h.failure(config, 401, 'Could not validate credentials');
    }
    return h.success(config, {});
  });
  const slow = h.client.get('/slow'); await entered.promise; await h.client.get('/forecast');
  gate.resolve(); await slow; assert.equal(refreshes, 1); await h.clearSession();
});

test('legacy sessions keep existing 401 cleanup without attempting refresh or fallback', async () => {
  const h = harness(new Map([['token', 'A']])); await h.store.getState().initializeAuth(); const calls = [];
  assert.equal(h.session.sessionSnapshot().refreshable, false);
  h.setHandler(async config => { calls.push(config.url); throw h.failure(config, 401, 'Could not validate credentials'); });
  await assert.rejects(h.client.get('/forecast'), e => e.statusCode === 401);
  await h.session.authStorageTask(async () => {});
  assert.deepEqual(calls, ['/forecast']); assert.equal(h.store.getState().isAuthenticated, false); assert.equal(h.data.size, 0);
});

test('session login sends exact bearer-free payload, persists metadata before authentication and keeps access/password memory-only', async () => {
  const gate = deferred(); const entered = deferred(); const writes = []; const faults = {
    beforeWrite: async (key, value) => { writes.push([key, value]); if (key === 'dabbarha_session_v2') { entered.resolve(); await gate.promise; } },
  };
  const h = harness(new Map([['token', 'old-legacy'], ['token_logout_pending', '1']]), faults);
  const pair = loginPair(); const calls = [];
  h.setHandler(async config => {
    calls.push(config.url);
    if (config.url === '/auth/sessions') {
      assert.equal(config.headers.has('Authorization'), false);
      assert.deepEqual(JSON.parse(config.data), { email: 'a@example.com', password: 'legacy-short' });
      return h.success(config, pair);
    }
    assert.equal(config.url, '/auth/me'); assert.equal(config.headers.Authorization, 'Bearer A');
    return h.success(config, { id: 1 });
  });
  const login = h.store.getState().login({ email: 'a@example.com', password: 'legacy-short' });
  await entered.promise;
  assert.equal(h.store.getState().isAuthenticated, false); assert.equal(h.store.getState().token, null);
  assert.equal(h.store.getState().user, null); assert.equal(h.store.getState().isLoading, true);
  gate.resolve(); await login;
  assert.deepEqual(calls, ['/auth/sessions', '/auth/me']);
  assert.deepEqual(JSON.parse(h.data.get('dabbarha_session_v2')), {
    version: 1, userId: 1, sessionId: pair.session_id, refreshToken: pair.refresh_token,
    refreshExpiresAt: pair.refresh_expires_at, sessionExpiresAt: pair.session_expires_at, pending: null,
  });
  assert.deepEqual([...h.data.keys()], ['dabbarha_session_v2']);
  assert.equal(writes.some(([key]) => key === 'token' || key === 'user'), false);
  assert.equal(JSON.stringify(writes).includes('legacy-short'), false);
  assert.equal(h.store.getState().token, 'A'); assert.equal(h.store.getState().isAuthenticated, true);
  const restarted = harness(h.data); let restartCalls = 0; const successor = rotatedPair(restarted);
  restarted.setHandler(async config => { restartCalls++; return restarted.success(config, config.url === '/auth/refresh' ? successor : { id: 1 }); });
  await restarted.store.getState().initializeAuth();
  assert.equal(restartCalls, 2); assert.equal(restarted.store.getState().isAuthenticated, true);
  await h.clearSession();
});

test('failed and ambiguous session writes never authenticate and are cleaned before retry', async () => {
  for (const ambiguous of [false, true]) {
    const faults = ambiguous ? { ambiguous: key => key === 'dabbarha_session_v2' }
      : { rejectWrite: key => key === 'dabbarha_session_v2' };
    const h = harness(new Map(), faults);
    await assert.rejects(h.login('A'));
    assert.equal(h.store.getState().isAuthenticated, false); assert.equal(h.session.sessionSnapshot().token, null);
    assert.equal(h.store.getState().user, null); assert.equal(h.data.size, 0);
    assert.equal(h.store.getState().error, 'Could not securely save your sign-in. Please try again.');
    faults.ambiguous = undefined; faults.rejectWrite = undefined;
    await h.login('B'); assert.equal(h.store.getState().user.id, 2); await h.clearSession();
  }
});

test('session login failures are localized safely and never fall back to legacy login', async () => {
  for (const status of [401, 0, 422, 429, 503]) {
    const h = harness(); const calls = [];
    h.setHandler(async config => {
      calls.push(config.url);
      if (!status) throw new axios.AxiosError('offline', 'ERR_NETWORK', config, {});
      throw h.failure(config, status, 'untrusted internal detail');
    });
    await assert.rejects(h.login('A'));
    assert.deepEqual(calls, ['/auth/sessions']); assert.equal(h.data.size, 0);
    assert.equal(h.store.getState().isAuthenticated, false); assert.equal(h.session.sessionSnapshot().token, null);
    const message = h.store.getState().error; assert.ok(message); assert.notEqual(message, 'untrusted internal detail');
    const i18n = h.load('src/i18n/index.ts');
    i18n.setTranslationLanguage('en'); assert.equal(i18n.translateMessage(message), message);
    i18n.setTranslationLanguage('ar'); assert.match(i18n.translateMessage(message), /[\u0600-\u06ff]/);
    assert.match(i18n.translateMessage('Could not securely save your sign-in. Please try again.'), /[\u0600-\u06ff]/);
  }
});

test('identity validation failure clears provisional credentials and displays a login error', async () => {
  for (const status of [401, 0]) {
    const h = harness(); const calls = [];
    h.setHandler(async config => {
      calls.push(config.url);
      if (config.url === '/auth/sessions') return h.success(config, loginPair());
      if (!status) throw new axios.AxiosError('offline', 'ERR_NETWORK', config, {});
      throw h.failure(config, status, 'Could not validate credentials');
    });
    await assert.rejects(h.login('A')); await h.session.authStorageTask(async () => {}); await tick();
    assert.deepEqual(calls, ['/auth/sessions', '/auth/me']); assert.equal(h.data.size, 0);
    assert.equal(h.store.getState().isAuthenticated, false); assert.equal(h.session.sessionSnapshot().token, null);
    assert.equal(h.store.getState().error, status ? 'Could not validate credentials'
      : 'Unable to connect to the Dabbarha server. Please check your network.');
  }
});

test('repeated login submissions send one session request', async () => {
  const h = harness(); const gate = deferred(); let calls = 0;
  h.setHandler(async config => {
    if (config.url === '/auth/sessions') { calls++; await gate.promise; return h.success(config, loginPair()); }
    return h.success(config, { id: 1 });
  });
  const first = h.login('A'); await tick(); await h.login('B'); await h.login('A');
  assert.equal(calls, 1); gate.resolve(); await first;
  assert.equal(h.store.getState().user.id, 1); await h.clearSession();
});

test('late login and identity responses cannot restore A after logout and B login', async () => {
  for (const stage of ['/auth/sessions', '/auth/me']) {
    const h = harness(); const gate = deferred(); const entered = deferred();
    h.setHandler(async config => {
      if (config.url === stage) { entered.resolve(); await gate.promise; }
      return h.success(config, config.url === '/auth/sessions' ? loginPair() : { id: 1 });
    });
    const a = h.login('A').catch(e => e); await entered.promise; await h.clearSession();
    h.setHandler(async config => h.success(config, config.url === '/auth/sessions' ? loginPair('B') : { id: 2 }));
    await h.login('B'); gate.resolve(); assert.equal((await a).code, 'ERR_CANCELED');
    assert.equal(h.store.getState().user.id, 2); assert.equal(h.store.getState().error, null);
    assert.equal(JSON.parse(h.data.get('dabbarha_session_v2')).userId, 2); await h.clearSession();
  }
});

test('logout during login persistence removes late A write before B can persist', async () => {
  const gate = deferred(); const entered = deferred(); const faults = {
    beforeWrite: async (key, value) => {
      if (key === 'dabbarha_session_v2' && JSON.parse(value).userId === 1) { entered.resolve(); await gate.promise; }
    },
  };
  const h = harness(new Map(), faults); const a = h.login('A').catch(e => e);
  await entered.promise; const logout = h.clearSession();
  assert.equal(h.store.getState().isAuthenticated, false); assert.equal(h.session.sessionSnapshot().token, null);
  gate.resolve(); await logout; assert.equal((await a).code, 'ERR_CANCELED'); assert.equal(h.data.size, 0);
  await h.login('B'); assert.equal(JSON.parse(h.data.get('dabbarha_session_v2')).userId, 2);
  assert.equal(h.store.getState().error, null); await h.clearSession();
});

test('old login failure cannot publish errors into a login started as cleanup finishes', async () => {
  const h = harness(); let b;
  h.setHandler(async config => { throw h.failure(config, 401, 'Invalid email or password'); });
  const unsubscribe = h.store.subscribe((state, previous) => {
    if (previous.isLoading && !state.isLoading && !state.isAuthenticated && !b) {
      h.setHandler(async config => h.success(config, config.url === '/auth/sessions' ? loginPair('B') : { id: 2 }));
      b = h.login('B');
    }
  });
  await assert.rejects(h.login('A')); await b; unsubscribe();
  assert.equal(h.store.getState().user.id, 2); assert.equal(h.store.getState().error, null); await h.clearSession();
});

test('malformed session responses fail closed without persisting access tokens or falling back', async () => {
  for (const change of [{ access_token: '' }, { token_type: 'other' }, { expires_in: 0 },
    { refresh_token: 'invalid' }, { session_id: 'invalid' }, { refresh_expires_at: 1 }]) {
    const h = harness(); const calls = [];
    h.setHandler(async config => {
      calls.push(config.url); return h.success(config, config.url === '/auth/sessions' ? { ...loginPair(), ...change } : { id: 1 });
    });
    await assert.rejects(h.login('A')); assert.equal(h.data.size, 0);
    assert.equal(h.store.getState().isAuthenticated, false); assert.equal(h.session.sessionSnapshot().token, null);
    assert.equal(calls.includes('/auth/login'), false);
  }
});

test('legacy restoration remains server-validated and never converts a bearer into a refresh record', async () => {
  const h = harness(new Map([['token', 'A']])); const calls = [];
  h.setHandler(async config => { calls.push(config.url); return h.success(config, { id: 1 }); });
  await h.store.getState().initializeAuth(); assert.deepEqual(calls, ['/auth/me']);
  assert.equal(h.store.getState().isAuthenticated, true); assert.equal(h.data.get('token'), 'A');
  assert.equal(h.data.has('dabbarha_session_v2'), false); await h.clearSession();
});

test('A logout clears queries and mutations; B cannot see A financial data', async () => {
  const h = harness();
  await h.login('A');
  const keyA = ['dashboard-summary', h.store.getState().sessionId, 1];
  await h.query.fetchQuery({ queryKey: keyA, queryFn: () => h.client.get('/dashboard/summary').then(r => r.data) });
  await h.query.getMutationCache().build(h.query, { mutationFn: () => h.client.post('/affordability', {}).then(r => r.data) }).execute({});
  assert.equal(h.query.getQueryData(keyA).owner, 'Bearer A');
  assert.equal(h.query.getMutationCache().getAll().length, 1);
  await h.store.getState().logout();
  assert.equal(h.query.getQueryCache().getAll().length, 0);
  assert.equal(h.query.getMutationCache().getAll().length, 0);
  assert.equal(h.data.size, 0);
  await h.login('B');
  assert.equal(h.query.getQueryData(keyA), undefined);
  const keyB = ['dashboard-summary', h.store.getState().sessionId, 2];
  const result = await h.query.fetchQuery({ queryKey: keyB, queryFn: () => h.client.get('/dashboard/summary').then(r => r.data) });
  assert.equal(result.owner, 'Bearer B');
  await h.clearSession();
});

test('logout aborts pending financial queries/mutations and delayed A responses cannot repopulate B', async () => {
  const h = harness(); await h.login('A');
  const requests = [];
  h.setHandler(config => { const d = deferred(); requests.push({ config, ...d }); return d.promise; });
  const key = ['forecast', h.store.getState().sessionId, 1];
  const pending = h.query.fetchQuery({ queryKey: key, queryFn: () => h.client.get('/forecast').then(r => r.data) }).catch(e => e);
  const mutation = h.query.getMutationCache().build(h.query, { mutationFn: () => h.client.post('/affordability', {}) });
  const pendingMutation = mutation.execute({}).catch(e => e);
  await tick();
  await h.clearSession();
  assert.ok(requests.every(r => r.config.signal.aborted));
  h.setHandler(async config => config.url === '/auth/sessions' ? h.success(config, loginPair('B')) : h.success(config, { id: 2 }));
  await h.login('B');
  requests.forEach(r => r.resolve(h.success(r.config, { owner: 'A' })));
  await pending; await pendingMutation;
  assert.equal(h.query.getQueryData(key), undefined);
  assert.equal(h.query.getMutationCache().getAll().length, 0);
  assert.equal(h.store.getState().user.id, 2);
  await h.clearSession();
});

test('generation check rejects an old response even if a transport ignores cancellation', async () => {
  const h = harness(); await h.login('A');
  const id = h.session.sessionSnapshot().generation;
  await h.clearSession();
  const responseGuard = h.client.interceptors.response.handlers[0].fulfilled;
  assert.throws(() => responseGuard({ config: { sessionGeneration: id }, data: { owner: 'A' } }), /Session ended/);
});

test('a mutation deferred before transport cannot run with the next account credential', async () => {
  const h = harness(); await h.login('A');
  const gate = deferred(); let sent = 0;
  const mutation = h.query.getMutationCache().build(h.query, {
    onMutate: () => gate.promise,
    mutationFn: h.session.inSession(h.store.getState().sessionId, async () => { sent++; return h.client.post('/obligations', {}); }),
  });
  const pending = mutation.execute({}).catch(e => e);
  await tick(); await h.clearSession(); await h.login('B');
  gate.resolve();
  const error = await pending;
  assert.equal(error.code, 'ERR_CANCELED'); assert.equal(sent, 0);
  assert.equal(h.store.getState().user.id, 2);
  await h.clearSession();
});

test('a delayed invalid-session response from A cannot sign B out', async () => {
  const h = harness(); await h.login('A');
  const oldGeneration = h.store.getState().sessionId;
  await h.clearSession(); await h.login('B');
  const errorGuard = h.client.interceptors.response.handlers[0].rejected;
  assert.throws(() => errorGuard(h.failure({ privateRequest: true, sessionGeneration: oldGeneration }, 401, 'Invalid')), /Session ended/);
  assert.equal(h.store.getState().user.id, 2);
  await h.clearSession();
});

test('failed storage deletion waits for the other deletion before settling', async () => {
  const other = deferred(); let settled = false;
  const load = loader({ '@/constants/config': { config: { tokenStorageKey: 'token', userStorageKey: 'user' } },
    'expo-secure-store': { deleteItemAsync: key => key === 'token' ? Promise.reject(new Error('storage unavailable')) : other.promise } });
  const clearing = load('src/utils/storage.ts').clearAuthStorage().catch(e => { settled = true; return e; });
  await tick(); assert.equal(settled, false);
  other.resolve(); assert.match((await clearing).message, /Saved sign-in could not be cleared/);
});

test('invalid protected session clears private data, while login 401 does not recurse', async () => {
  const h = harness(); await h.login('A');
  h.query.setQueryData(['private'], { owner: 'A' });
  h.setHandler(async config => { throw h.failure(config, 401, 'Could not validate credentials'); });
  await assert.rejects(h.client.get('/auth/me'), e => e.statusCode === 401);
  await h.session.authStorageTask(async () => {});
  assert.equal(h.store.getState().isAuthenticated, false);
  assert.equal(h.query.getQueryCache().getAll().length, 0);
  assert.equal(h.data.size, 0);
  await assert.rejects(h.login('B'));
  assert.equal(h.store.getState().isAuthenticated, false);
});

test('network failure cannot prevent local logout; unauthenticated requests never reach transport', async () => {
  const h = harness(); await h.login('A'); let calls = 0;
  h.setHandler(async config => { calls++; throw new axios.AxiosError('offline', 'ERR_NETWORK', config, {}); });
  await assert.rejects(h.client.get('/forecast'), e => e.statusCode === 0);
  await h.clearSession();
  await assert.rejects(h.client.get('/forecast'));
  assert.equal(calls, 1);
  assert.equal(h.store.getState().user, null);
});

test('restoration never exposes cached identity; logout during restore cannot resurrect it', async () => {
  const h = harness(); h.data.set('token', 'A'); h.data.set('user', JSON.stringify({ id: 999 }));
  h.query.setQueryData(['private'], { owner: 'previous' });
  const d = deferred(); let request;
  h.setHandler(config => { request = config; return d.promise; });
  const restoring = h.store.getState().initializeAuth(); await tick();
  assert.equal(h.store.getState().user, null);
  assert.equal(h.store.getState().isAuthenticated, false);
  assert.equal(h.query.getQueryCache().getAll().length, 0);
  await h.clearSession(); d.resolve(h.success(request, { id: 1 })); await restoring;
  assert.equal(h.store.getState().user, null); assert.equal(h.data.size, 0);
});

test('credential storage writes are ordered before logout deletion', async () => {
  const h = harness(); const d = deferred();
  const writing = h.session.authStorageTask(async () => { await d.promise; h.data.set('token', 'A'); });
  const logout = h.clearSession(); d.resolve(); await writing; await logout;
  assert.equal(h.data.size, 0); assert.equal(h.store.getState().isAuthenticated, false);
});

const form = { purchase_price: '12000', payment_method: 'automatic', interest_method: 'none',
  nominal_annual_interest_rate: '', monthly_installment_amount: '', start_date: '2026-11-01', term_months: '12',
  due_day_of_month: '1', down_payment_amount: '', down_payment_date: '', down_payment_paid: false };

test('12000/12 uses purchase-plan semantics, never legacy monthly amount', async () => {
  const h = harness(); await h.login('A');
  const { purchasePlanRequest } = h.load('src/schemas/affordability.ts');
  const request = purchasePlanRequest(form);
  assert.deepEqual(plain(request), { purchase_price: '12000', payment_method: 'automatic', interest_method: 'none', start_date: '2026-11-01', term_months: 12, due_day_of_month: 1, down_payment_amount: '0', down_payment_paid: false });
  const fixture = { classification: 'Comfortable', worst_projected_buffer: '3000.00', worst_buffer_percentage: '60.00', worst_month: '2026-11-01', explanation: 'Synthetic backend fixture', monthly_results: [{ month: '2026-11-01', proposed_installment_amount: '1000.00', proposed_down_payment_amount: '0.00' }] };
  h.setHandler(async config => { assert.deepEqual(JSON.parse(config.data), plain(request)); return h.success(config, fixture); });
  const result = await h.load('src/api/affordability.ts').affordabilityApi.evaluateAffordability(request);
  assert.deepEqual(result, fixture); await h.clearSession();
});

test('down payment and manual/automatic interest modes keep separate backend meanings', () => {
  const { purchasePlanRequest } = loader()('src/schemas/affordability.ts');
  const down = purchasePlanRequest({ ...form, down_payment_amount: '2400', down_payment_date: '2026-10-25' });
  assert.equal(down.purchase_price, '12000'); assert.equal(down.down_payment_amount, '2400'); assert.equal(down.down_payment_paid, false);
  const manual = purchasePlanRequest({ ...form, payment_method: 'manual', monthly_installment_amount: '1100.50', interest_method: 'flat', nominal_annual_interest_rate: '20' });
  assert.equal(manual.monthly_installment_amount, '1100.50'); assert.equal(manual.interest_method, 'none'); assert.equal(manual.amount, undefined);
  for (const method of ['flat', 'reducing_balance']) {
    const automatic = purchasePlanRequest({ ...form, interest_method: method, nominal_annual_interest_rate: '12.3456', monthly_installment_amount: '999' });
    assert.equal(automatic.nominal_annual_interest_rate, '12.3456'); assert.equal(automatic.monthly_installment_amount, undefined);
  }
});

test('rejects zero/negative/oversized money, precision, invalid dates, terms and options', () => {
  const { affordabilitySchema } = loader()('src/schemas/affordability.ts');
  const invalid = [
    { purchase_price: '0' }, { purchase_price: '-1' }, { purchase_price: 'Infinity' }, { purchase_price: '1.001' }, { purchase_price: '10000000000' },
    { start_date: '2026-02-30' }, { start_date: '2025-02-29' }, { start_date: '0000-01-01' },
    { term_months: '0' }, { term_months: '-1' }, { term_months: '1.5' }, { term_months: '1201' },
    { due_day_of_month: '32' }, { payment_method: 'unsupported' }, { interest_method: 'unsupported' },
    { down_payment_amount: '12000' }, { down_payment_amount: '1.001' }, { down_payment_amount: '-1' }, { down_payment_amount: '1' },
    { payment_method: 'manual', monthly_installment_amount: '0' },
    { interest_method: 'flat', nominal_annual_interest_rate: '100.1' }, { interest_method: 'flat', nominal_annual_interest_rate: '1.12345' },
    { start_date: '9999-12-01' }, { down_payment_amount: '1', down_payment_date: '1900-01-01' },
  ];
  for (const change of invalid) assert.equal(affordabilitySchema.safeParse({ ...form, ...change }).success, false, JSON.stringify(change));
  assert.equal(affordabilitySchema.safeParse({ ...form, start_date: '2028-02-29' }).success, true);
});

test('Arabic numerals are normalized without changing purchase/payment meanings', () => {
  const { purchasePlanRequest } = loader()('src/schemas/affordability.ts');
  const payload = purchasePlanRequest({ ...form, purchase_price: '١٢٬٠٠٠٫٠٠', term_months: '١٢', start_date: '٢٠٢٦-١١-٠١' });
  assert.equal(payload.purchase_price, '12000.00'); assert.equal(payload.term_months, 12); assert.equal(payload.start_date, '2026-11-01');
});

test('old results disappear after input changes, while pending, or after failure', () => {
  const { affordabilitySchema, currentAffordabilityResult } = loader()('src/schemas/affordability.ts');
  const submitted = affordabilitySchema.parse(form); const result = { classification: 'Risky' };
  assert.equal(currentAffordabilityResult(result, submitted, form, false, false), result);
  for (const change of [{ purchase_price: '13000' }, { term_months: '6' }, { payment_method: 'manual' }, { start_date: 'invalid' }]) {
    assert.equal(currentAffordabilityResult(result, submitted, { ...form, ...change }, false, false), undefined);
  }
  assert.equal(currentAffordabilityResult(result, submitted, form, true, false), undefined);
  assert.equal(currentAffordabilityResult(result, submitted, form, false, true), undefined);
});

test('422 field errors and unavailable backend remain actionable, without losing valid session', async () => {
  const h = harness(); await h.login('A');
  const request = h.load('src/schemas/affordability.ts').purchasePlanRequest(form);
  const api = h.load('src/api/affordability.ts').affordabilityApi;
  h.setHandler(async config => { throw h.failure(config, 422, [{ loc: ['body', 'purchase_price'], msg: 'Invalid purchase price' }]); });
  await assert.rejects(api.evaluateAffordability(request), e => e.statusCode === 422 && e.detail[0].loc[1] === 'purchase_price');
  h.setHandler(async config => { throw h.failure(config, 503, 'Temporarily unavailable'); });
  await assert.rejects(api.evaluateAffordability(request), e => e.statusCode === 503 && e.message === 'We could not evaluate this payment plan. Check your entries and try again.');
  assert.equal(h.store.getState().isAuthenticated, true); await h.clearSession();
});

test('actual root layout gates startup/recovery and excludes chat through installed Router protected-screen filtering', () => {
  const React = require('react');
  const react = { ...React, useEffect() {}, useMemo: fn => fn() };
  const Stack = Object.assign(() => null, { Screen: () => null, Protected: () => null });
  const identity = ({ children }) => children;
  let authenticated = true;
  let initialized = true, retryable = false; let retries = 0, dismissals = 0;
  const LoadingIndicator = () => null, ScreenWrapper = () => null, Button = () => null, ErrorBanner = () => null;
  const load = loader({ react, 'expo-router': { Stack },
    '@/providers/QueryProvider': { QueryProvider: identity }, '@/providers/LocalizationProvider': { LocalizationProvider: identity },
    '@/components/common/LoadingIndicator': { LoadingIndicator }, '@/constants/theme': { colors: {} },
    '@/components/common/ScreenWrapper': { ScreenWrapper }, '@/components/common/Button': { Button },
    '@/components/common/ErrorBanner': { ErrorBanner },
    '@/store/authStore': { useAuthStore: () => ({ isAuthenticated: authenticated, isInitialized: initialized,
      restorationRetryable: retryable, error: 'Recovery', initializeAuth() { retries++; }, dismissRestoration() { dismissals++; }, sessionId: 7 }) },
  });
  const filterLoad = loader({ react, '../Route': {}, '../useScreens': {}, './IsWithinLayoutContext': {},
    '../native-tabs/NativeTabTrigger': { isNativeTabTrigger: () => false },
    '../views/Protected': { isProtectedReactElement: child => child?.type === Stack.Protected },
    '../views/Screen': { isScreen: child => child?.type === Stack.Screen },
  });
  const { useFilterScreenChildren } = filterLoad('node_modules/expo-router/build/layouts/withLayoutContext.js');
  const Root = load('app/_layout.tsx').default;
  function navigation() { const root = Root(); return root.props.children.props.children.type(); }
  initialized = false; authenticated = false;
  assert.equal(navigation().type, LoadingIndicator); // Neither login nor private routes mount.
  initialized = true; retryable = true;
  const recovery = navigation(); assert.equal(recovery.type, ScreenWrapper);
  const buttons = recovery.props.children.filter(child => child.type === Button);
  assert.deepEqual(buttons.map(child => child.props.title), ['Retry', 'Sign In']);
  buttons[0].props.onPress(); buttons[1].props.onPress(); assert.equal(retries, 1); assert.equal(dismissals, 1);
  retryable = false;
  function layout() { let element = Root(); while (element.type !== Stack) element = element.type(element.props); return element; }
  for (const auth of [true, false]) {
    authenticated = auth;
    const element = layout(); const filtered = useFilterScreenChildren(element.props.children, { contextKey: '/' });
    assert.ok(filtered.protectedScreens.has('chat'));
    assert.equal(filtered.screens.some(s => s.name === 'chat'), false);
    assert.equal(filtered.screens.some(s => s.name === '(tabs)'), auth);
    assert.equal(filtered.screens.some(s => s.name === '(auth)'), !auth);
    assert.equal(element.key, auth ? '7' : 'signed-out');
    // Exercise the installed native stack's action and restored-state handling
    // with the route set produced by the actual application layout.
    const { StackRouter } = load('node_modules/expo-router/build/react-navigation/routers/StackRouter.js');
    const router = StackRouter({});
    const options = { routeNames: filtered.screens.map(s => s.name), routeParamList: {}, routeGetIdList: {}, routeKeyChanges: [] };
    const initial = router.getInitialState(options);
    for (const type of ['NAVIGATE', 'PUSH', 'REPLACE']) {
      assert.equal(router.getStateForAction(initial, { type, payload: { name: 'chat' } }, options), null);
    }
    const restored = router.getRehydratedState({ stale: true, routes: [{ name: 'chat' }], preloadedRoutes: [{ name: 'chat' }] }, options);
    assert.ok(restored.routes.every(r => r.name !== 'chat'));
    const changed = router.getStateForRouteNamesChange({ ...initial, routes: [{ name: 'chat', key: 'old-chat' }], preloadedRoutes: [{ name: 'chat' }] }, options);
    assert.ok(changed.routes.every(r => r.name !== 'chat'));
    assert.equal(changed.preloadedRoutes.length, 0);
    if (auth) assert.equal(restored.routes[0].name, '(tabs)');
  }
  const home = fs.readFileSync('app/(tabs)/index.tsx', 'utf8');
  assert.equal(home.includes("route: '/chat'"), false);
  assert.equal(home.includes('Ask\\nDabbarha'), false);
  assert.ok(home.includes("route: '/(tabs)/obligations'"));
  for (const file of ['app/chat.tsx', 'src/api/chat.ts', 'src/types/chat.ts']) assert.ok(fs.statSync(file).size > 0);
});

test('Affordability screen locks duplicate submissions and maps backend field errors', async () => {
  const React = require('react'); let options, calls = 0; const fields = [];
  const mutation = { isPending: false, isError: false, data: undefined, variables: undefined,
    mutate: () => { calls++; }, reset() {} };
  const identity = ({ children }) => children;
  const Button = () => null;
  const components = Object.fromEntries(['ScreenWrapper', 'Typography', 'Input', 'Icon', 'ErrorBanner', 'Segmented'].map(name => [`@/components/common/${name}`, { [name]: identity }]));
  const load = loader({ ...components,
    react: { ...React, useState: initial => [initial, () => {}], useRef: initial => ({ current: initial }), useEffect() {} },
    'react-native': { View: 'View', ScrollView: 'ScrollView', TouchableOpacity: 'TouchableOpacity', StyleSheet: { create: x => x } },
    'expo-router': { useRouter: () => ({ back() {}, push() {} }) },
    'react-hook-form': { Controller: identity, useForm: () => ({ control: {}, handleSubmit: fn => () => fn(form), setValue() {}, watch: () => form, setError: (...args) => fields.push(args), formState: { errors: {} } }) },
    '@tanstack/react-query': { useMutation: value => { options = value; return mutation; } },
    '@/api/affordability': { affordabilityApi: {} },
    '@/api/session': { inSession: (_id, action) => action },
    '@/store/authStore': { useAuthStore: () => ({ user: { monthly_income: '5000', fixed_expenses: '1000' }, isAuthenticated: true }) },
    '@/constants/theme': { colors: {}, spacing: {}, borderRadius: {} },
    '@/components/common/Button': { Button },
  });
  const screen = load('app/affordability.tsx').default();
  function find(element) {
    if (!element || typeof element !== 'object') return;
    if (element.type === Button && element.props.title === 'Evaluate Affordability') return element;
    for (const child of React.Children.toArray(element.props?.children)) { const match = find(child); if (match) return match; }
  }
  const submit = find(screen); assert.ok(submit);
  submit.props.onPress(); submit.props.onPress(); assert.equal(calls, 1);
  options.onError({ statusCode: 422, message: 'Invalid value', detail: [{ loc: ['body', 'purchase_price'], msg: 'Invalid value' }] });
  assert.equal(fields[0][0], 'purchase_price');
  options.onSettled(); submit.props.onPress(); assert.equal(calls, 2);
});
