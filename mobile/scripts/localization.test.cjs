const { test } = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

// Run pure TypeScript logic without adding a test framework or loading native modules.
function loader(mocks = {}) {
  const cache = new Map();
  return function load(file) {
    const absolute = path.resolve(file);
    if (cache.has(absolute)) return cache.get(absolute).exports;
    const module = { exports: {} }; cache.set(absolute, module);
    const js = ts.transpileModule(fs.readFileSync(absolute, 'utf8'), {
      compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
    }).outputText;
    const localRequire = name => {
      if (Object.hasOwn(mocks, name)) return mocks[name];
      if (name.startsWith('@/') || name.startsWith('.')) {
        let target = name.startsWith('@/') ? path.resolve('src', name.slice(2)) : path.resolve(path.dirname(absolute), name);
        target = fs.existsSync(target + '.ts') ? target + '.ts' : path.join(target, 'index.ts');
        return load(target);
      }
      return require(name);
    };
    vm.runInNewContext(js, { module, exports: module.exports, require: localRequire, Intl, Date, console, process, setTimeout });
    return module.exports;
  };
}

test('dictionaries contain Arabic copy and matching interpolation parameters', () => {
  const { ar, en } = loader()('src/i18n/dictionaries.ts');
  assert.deepEqual(Object.keys(ar), Object.keys(en));
  for (const key of Object.keys(en)) {
    assert.match(ar[key], /[\u0600-\u06ff]/, key);
    assert.deepEqual((ar[key].match(/\{\w+\}/g) || []).sort(), (en[key].match(/\{\w+\}/g) || []).sort(), key);
  }
});

test('bundled font cmap tables cover all Arabic translation characters and digits', () => {
  const { ar } = loader()('src/i18n/dictionaries.ts');
  const characters = new Set([...Object.values(ar).join(''), ...'٠١٢٣٤٥٦٧٨٩'].filter(c => /[\u0600-\u06ff]/.test(c)));
  for (const name of ['Regular', 'Bold']) {
    const buffer = fs.readFileSync(`assets/fonts/NotoNaskhArabic-${name}.ttf`);
    let cmap;
    for (let i=0; i<buffer.readUInt16BE(4); i++) {
      const record = 12 + i*16;
      if (buffer.toString('ascii',record,record+4)==='cmap') cmap=buffer.readUInt32BE(record+8);
    }
    assert.ok(cmap, `${name}: missing cmap`);
    let subtable;
    for (let i=0; i<buffer.readUInt16BE(cmap+2); i++) {
      const record = cmap+4+i*8;
      const offset = cmap+buffer.readUInt32BE(record+4);
      if (buffer.readUInt16BE(offset)===4 && [0,3].includes(buffer.readUInt16BE(record))) subtable=offset;
    }
    assert.ok(subtable, `${name}: missing Unicode BMP cmap`);
    const count = buffer.readUInt16BE(subtable+6)/2;
    for (const char of characters) {
      const code=char.codePointAt(0); let glyph=0;
      for(let i=0;i<count;i++) {
        const end=buffer.readUInt16BE(subtable+14+i*2), start=buffer.readUInt16BE(subtable+16+count*2+i*2);
        if(code<start || code>end) continue;
        const delta=buffer.readInt16BE(subtable+16+count*4+i*2);
        const rangePosition=subtable+16+count*6+i*2, range=buffer.readUInt16BE(rangePosition);
        glyph=range ? buffer.readUInt16BE(rangePosition+range+(code-start)*2) : code;
        if(glyph) glyph=(glyph+delta)&0xffff;
        break;
      }
      assert.notEqual(glyph,0, `${name} missing ${char} U+${code.toString(16)}`);
    }
  }
});

test('Arabic and Persian numeric keyboard values normalize without changing financial value', () => {
  const { normalizeNumericInput } = loader()('src/i18n/index.ts');
  assert.equal(normalizeNumericInput('١٬٢٣٤٫٥٠'), '1234.50');
  assert.equal(normalizeNumericInput('۱۲۳۴٫۵۰'), '1234.50');
  assert.equal(normalizeNumericInput('٢٠٢٦-٠٩-١٧'), '2026-09-17');
  assert.equal(normalizeNumericInput('-١٠٫٢٥'), '-10.25');
  assert.equal(normalizeNumericInput('1234.50'), '1234.50');
  assert.equal(normalizeNumericInput('1.2.3'), '1.2.3'); // invalid input must not become valid silently
});

test('currency locale changes digits without conversion, preserving negatives, zero and codes', () => {
  const load = loader(); const i18n = load('src/i18n/index.ts'); const fmt = load('src/utils/format.ts');
  for (const language of ['en', 'ar']) {
    i18n.setTranslationLanguage(language);
    for (const currency of ['EGP','USD','SAR','AED','EUR']) {
      const value = fmt.formatCurrency('-1234.5', currency);
      assert.ok(value.includes(currency));
      const numeric = i18n.normalizeNumericInput(value).replace(/[^\d.\-]/g, '');
      assert.equal(Number(numeric), -1234.5);
      assert.ok(fmt.formatCurrency(null, currency).includes(currency));
    }
    assert.equal(fmt.formatCurrency('invalid', 'EGP'), 'invalid EGP');
    assert.equal(i18n.normalizeNumericInput(fmt.formatPercent(25)).replace(/[^\d]/g, ''), '25');
  }
});

test('Gregorian calendar dates do not shift when displayed west of UTC', () => {
  const previous = process.env.TZ; process.env.TZ = 'America/Los_Angeles';
  try {
    const load = loader(); const i18n = load('src/i18n/index.ts'); const fmt = load('src/utils/format.ts');
    for (const language of ['en','ar']) {
      i18n.setTranslationLanguage(language);
      const expected = new Intl.DateTimeFormat(i18n.getLocale(), { calendar: 'gregory', year: 'numeric', month: 'short', day: 'numeric' }).format(new Date(2026,8,1));
      assert.equal(fmt.formatDate('2026-09-01'), expected);
      assert.equal(fmt.formatDate('2026-02-31'), '2026-02-31');
      assert.equal(fmt.formatMonthLabel('2026-13'), '2026-13');
      assert.equal(fmt.formatMonthLabel('2026-09', true), new Intl.DateTimeFormat(i18n.getLocale(), { calendar: 'gregory', month: 'short' }).format(new Date(2026,8,1)));
    }
  } finally { if (previous === undefined) delete process.env.TZ; else process.env.TZ = previous; }
});

test('enum labels, unknown data, and Arabic plurals remain separate from payload values', () => {
  const i18n = loader()('src/i18n/index.ts'); i18n.setTranslationLanguage('ar');
  for (const value of ['active','completed','late','defaulted']) assert.notEqual(i18n.statusLabel(value), value);
  for (const value of ['Comfortable','Manageable','Risky','Not Affordable']) assert.notEqual(i18n.classificationLabel(value), value);
  assert.equal(i18n.categoryLabel('My personal category'), 'My personal category');
  assert.equal(i18n.statusLabel('future_status'), 'future_status');
  for (const label of [i18n.statusLabel, i18n.classificationLabel, i18n.categoryLabel, i18n.sourceLabel]) {
    assert.equal(label('constructor'), 'constructor');
    assert.equal(label('__proto__'), '__proto__');
  }
  assert.notEqual(i18n.sourceLabel('chatbot_entry'), 'chatbot_entry');
  assert.equal(i18n.translateMessage('Unrecognized server detail'), 'Unrecognized server detail');
  assert.equal(i18n.monthCount(1), 'شهر واحد'); assert.equal(i18n.monthCount(2), 'شهران');
  assert.equal(i18n.monthCount(3), '٣ أشهر'); assert.equal(i18n.monthCount(12), '١٢ شهرًا');
  assert.equal(i18n.t('Are you sure you want to remove "{name}"? This action cannot be undone.', {name:'My Laptop'}).includes('My Laptop'), true);
});

function nativeHarness({ data = new Map(), rtl = false, expoGo = false, failSave = false, failLoad = false, failReload = false } = {}) {
  const calls = [];
  const secure = {
    getItemAsync: async key => { if (failLoad) throw Error('read failed'); return data.get(key) || null; },
    setItemAsync: async (key, value) => { if (failSave) throw Error('write failed'); data.set(key,value); calls.push(['save',key,value]); },
    deleteItemAsync: async key => { data.delete(key); },
  };
  const load = loader({
    'expo-secure-store': secure,
    'react-native': { I18nManager: { isRTL: rtl, allowRTL: v=>calls.push(['allow',v]), forceRTL: v=>calls.push(['force',v]), swapLeftAndRightInRTL: v=>calls.push(['swap',v]) }, Platform: { OS: 'android' } },
    'expo-constants': { appOwnership: expoGo ? 'expo' : null },
    'expo': { reloadAppAsync: async ()=>{ calls.push(['reload']); if (failReload) throw Error('cannot reload'); } },
  });
  const { useLanguageStore: store, LANGUAGE_KEY } = load('src/store/languageStore.ts');
  return { data, calls, load, store, LANGUAGE_KEY };
}

test('language saves before restart and survives auth logout and cold start', async () => {
  const h = nativeHarness(); await h.store.getState().initialize();
  assert.equal(h.store.getState().ready, true);
  await h.store.getState().select('ar');
  assert.equal(h.data.get(h.LANGUAGE_KEY), 'ar');
  const save = h.calls.findIndex(c=>c[0]==='save' && c[1]===h.LANGUAGE_KEY);
  assert.ok(save < h.calls.findIndex(c=>c[0]==='reload'));
  const storage = h.load('src/utils/storage.ts');
  await storage.saveToken('test-token'); await storage.saveUser({ name: 'Example' });
  await storage.clearAuthStorage();
  assert.equal(h.data.get(h.LANGUAGE_KEY), 'ar');
  assert.equal(await storage.getToken(), null);
  const cold = nativeHarness({ data:h.data, rtl:true }); await cold.store.getState().initialize();
  assert.equal(cold.store.getState().language, 'ar'); assert.equal(cold.store.getState().ready, true);
  assert.equal(cold.calls.filter(c=>c[0]==='reload').length, 0);
  await cold.store.getState().select('en'); assert.equal(cold.data.get(cold.LANGUAGE_KEY), 'en');
  assert.ok(cold.calls.some(c=>c[0]==='force' && c[1]===false));
});

test('failed storage writes do not change language, native direction, or discard the mounted app', async () => {
  const h = nativeHarness({ failSave: true }); await h.store.getState().initialize(); h.calls.length=0;
  await h.store.getState().select('ar');
  assert.equal(h.store.getState().ready,true); assert.equal(h.store.getState().language,'en');
  assert.equal(h.store.getState().error,'save'); assert.equal(h.calls.length,0);
});

test('mismatched native direction reloads once, then reports manual restart without looping', async () => {
  const data = new Map([['dabbarha.language','ar']]);
  const first = nativeHarness({ data }); await first.store.getState().initialize();
  assert.equal(first.calls.filter(c=>c[0]==='reload').length,1);
  const second = nativeHarness({ data }); await second.store.getState().initialize();
  assert.equal(second.calls.filter(c=>c[0]==='reload').length,0);
  assert.equal(second.store.getState().ready,false); assert.equal(second.store.getState().error,'restart');
});

test('Expo Go rejects unsupported direction changes without overwriting the preference', async () => {
  const h = nativeHarness({ expoGo:true }); await h.store.getState().initialize(); h.calls.length=0;
  await h.store.getState().select('ar'); assert.equal(h.store.getState().error,'expoGo');
  assert.equal(h.data.has(h.LANGUAGE_KEY),false); assert.equal(h.calls.length,0); assert.equal(h.store.getState().ready,true);
});

test('storage read and reload failures leave an actionable recovery state', async () => {
  const read = nativeHarness({ failLoad:true }); await read.store.getState().initialize();
  assert.equal(read.store.getState().error,'load'); assert.equal(read.store.getState().busy,false);
  const reload = nativeHarness({ failReload:true }); await reload.store.getState().initialize(); await reload.store.getState().select('ar');
  assert.equal(reload.store.getState().error,'restart'); assert.equal(reload.store.getState().busy,false);
  assert.equal(reload.data.get(reload.LANGUAGE_KEY),'ar');
  const startup = nativeHarness({ data: new Map([['dabbarha.language', 'ar']]), failReload: true });
  await startup.store.getState().initialize();
  assert.equal(startup.store.getState().error, 'restart');
  assert.equal(startup.store.getState().busy, false);
});

test('pending chat actions prevent language persistence and reload until resolved', async () => {
  const h = nativeHarness(); await h.store.getState().initialize(); h.calls.length = 0;
  h.store.getState().setChatProtected(true);
  await h.store.getState().select('ar');
  assert.equal(h.store.getState().language, 'en');
  assert.equal(h.store.getState().ready, true);
  assert.equal(h.calls.length, 0);
  h.store.getState().setChatProtected(false);
  await h.store.getState().select('ar');
  assert.equal(h.data.get(h.LANGUAGE_KEY), 'ar');
});

test('dirty forms remain registered when a different mounted auth screen is clean', () => {
  const h = nativeHarness();
  h.store.getState().setFormDirty('login', true);
  h.store.getState().setFormDirty('register', false);
  assert.equal(Object.keys(h.store.getState().dirtyForms).length, 1);
  h.store.getState().setFormDirty('register', true);
  h.store.getState().setFormDirty('login', false);
  assert.equal(h.store.getState().dirtyForms.register, true);
  h.store.getState().setFormDirty('register', false);
  assert.equal(Object.keys(h.store.getState().dirtyForms).length, 0);
});

test('schema validation messages have Arabic translations and enums still accept original values', () => {
  const load = loader(); const i18n = load('src/i18n/index.ts'); i18n.setTranslationLanguage('ar');
  const { obligationSchema } = load('src/schemas/obligation.ts');
  const { registerSchema, loginSchema } = load('src/schemas/auth.ts');
  for (const schema of [obligationSchema, registerSchema, loginSchema]) {
    const input = {provider:'',item_name:'',category:'',total_amount:'',monthly_installment_amount:'',start_date:'',term_months:'',due_day_of_month:'',status:'invalid',name:'',email:'',password:''};
    const result = schema.safeParse(input); assert.equal(result.success,false);
    for (const issue of result.error.issues) assert.notEqual(i18n.translateMessage(issue.message), issue.message, issue.message);
  }
  for (const status of ['active','completed','late','defaulted']) {
    const payload = {provider:'NBE',item_name:'Laptop',category:'Electronics',total_amount:'1200',monthly_installment_amount:'100',start_date:'2026-09-17',term_months:'12',due_day_of_month:'1',status};
    const result = obligationSchema.parse(payload);
    assert.equal(result.status,status); assert.equal(result.category,'Electronics'); assert.equal(result.total_amount,'1200');
  }
});
