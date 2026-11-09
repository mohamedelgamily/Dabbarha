const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const axios = require('axios');

// Execute real TS services/stores with native storage mocked; no server or .env loading.
function loader(mocks = {}) {
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
      Intl, Date, console, process, setTimeout, clearTimeout, AbortController }, { filename: absolute });
    return module.exports;
  }
  return load;
}
const plain = value => JSON.parse(JSON.stringify(value));
const deferred = () => { let resolve, reject; const promise = new Promise((a,b) => { resolve=a; reject=b; }); return { promise, resolve, reject }; };
const tick = () => new Promise(resolve => setImmediate(resolve));

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
  assert.equal(data.get('token'), 'A'); assert.equal(data.get('token_logout_pending'), '1');
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
  const normalRestart = harness(data, faults); await normalRestart.store.getState().initializeAuth();
  assert.equal(normalRestart.store.getState().user.id, 2);
  await normalRestart.clearSession(); assert.equal(data.size, 0);
});

test('complete storage failure reports lack of durable protection without retaining private memory', async () => {
  const data = new Map(); const faults = {}; const h = harness(data, faults);
  await h.login('A'); faults.deletes = true; faults.writes = true;
  await h.clearSession();
  assert.equal(h.store.getState().isAuthenticated, false);
  assert.match(h.store.getState().error, /could not be cleared or blocked from restoration/);
  assert.equal(data.get('token'), 'A'); assert.equal(data.has('token_logout_pending'), false);
  // OS-wide write failure cannot leave a durable marker; expose this limitation.
  faults.deletes = false; faults.writes = false;
  await h.login('B'); assert.equal(h.store.getState().user.id, 2); await h.clearSession();
});

test('token replacement prevents restoration when logout marker cannot be written', async () => {
  const data = new Map([['token', 'A']]);
  const load = loader({ '@/constants/config': { config: { tokenStorageKey: 'token', userStorageKey: 'user' } },
    'expo-secure-store': {
      getItemAsync: async key => data.get(key) || null,
      setItemAsync: async (key, value) => { if (key !== 'token') throw new Error('marker unavailable'); data.set(key, value); },
      deleteItemAsync: async () => { throw new Error('deletion unavailable'); },
    } });
  await assert.rejects(load('src/utils/storage.ts').clearAuthStorage(), /Try signing in again/);
  assert.equal(data.get('token'), '');
  const restarted = harness(data); let calls = 0;
  restarted.setHandler(async () => { calls++; throw new Error('must not restore'); });
  await restarted.store.getState().initializeAuth();
  assert.equal(calls, 0); assert.equal(restarted.store.getState().isAuthenticated, false);
});

function harness(data = new Map(), faults = {}) {
  const load = loader({
    '@/constants/config': { API_BASE_URL: 'https://synthetic.invalid', config: { apiTimeoutMs: 100, tokenStorageKey: 'token', userStorageKey: 'user' } },
    'expo-secure-store': {
      getItemAsync: async key => data.get(key) || null,
      setItemAsync: async (key, value) => { if (faults.writes) throw new Error('storage unavailable'); data.set(key, value); },
      deleteItemAsync: async key => { if (faults.deletes) throw new Error('storage unavailable'); data.delete(key); },
    },
  });
  const { useAuthStore: store, clearSession } = load('src/store/authStore.ts');
  const { apiClient: client } = load('src/api/client.ts');
  const { queryClient: query } = load('src/api/queryClient.ts');
  // Keep production freshness/retry behavior, but do not retain GC timers in Node.
  query.setDefaultOptions({ queries: { ...query.getDefaultOptions().queries, gcTime: 0 }, mutations: { ...query.getDefaultOptions().mutations, gcTime: 0 } });
  const session = load('src/api/session.ts');
  const success = (config, body) => ({ data: body, status: 200, statusText: 'OK', headers: {}, config });
  const failure = (config, status, detail) => new axios.AxiosError('synthetic failure', 'ERR_BAD_RESPONSE', config, {}, { data: { detail }, status, headers: {}, config });
  let handler = async config => {
    if (config.url === '/auth/login') return success(config, { access_token: JSON.parse(config.data).email, token_type: 'bearer' });
    if (config.url === '/auth/me') return success(config, { id: config.headers.Authorization.endsWith('A') ? 1 : 2, name: 'Synthetic', monthly_income: '5000', fixed_expenses: '1000', currency: 'EGP' });
    return success(config, { owner: config.headers.Authorization });
  };
  client.defaults.adapter = config => handler(config);
  return { data, load, store, clearSession, client, query, session, success, failure,
    setHandler: next => { handler = next; }, login: name => store.getState().login({ email: name, password: 'synthetic-only' }) };
}

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
  h.setHandler(async config => config.url === '/auth/login' ? h.success(config, { access_token: 'B' }) : h.success(config, { id: 2 }));
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

test('actual root layout excludes chat through installed Router protected-screen filtering', () => {
  const React = require('react');
  const react = { ...React, useEffect() {}, useMemo: fn => fn() };
  const Stack = Object.assign(() => null, { Screen: () => null, Protected: () => null });
  const identity = ({ children }) => children;
  let authenticated = true;
  const load = loader({ react, 'expo-router': { Stack },
    '@/providers/QueryProvider': { QueryProvider: identity }, '@/providers/LocalizationProvider': { LocalizationProvider: identity },
    '@/components/common/LoadingIndicator': { LoadingIndicator: () => null }, '@/constants/theme': { colors: {} },
    '@/store/authStore': { useAuthStore: () => ({ isAuthenticated: authenticated, isInitialized: true, initializeAuth() {}, sessionId: 7 }) },
  });
  const filterLoad = loader({ react, '../Route': {}, '../useScreens': {}, './IsWithinLayoutContext': {},
    '../native-tabs/NativeTabTrigger': { isNativeTabTrigger: () => false },
    '../views/Protected': { isProtectedReactElement: child => child?.type === Stack.Protected },
    '../views/Screen': { isScreen: child => child?.type === Stack.Screen },
  });
  const { useFilterScreenChildren } = filterLoad('node_modules/expo-router/build/layouts/withLayoutContext.js');
  const Root = load('app/_layout.tsx').default;
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
