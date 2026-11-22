// Never log Playwright error details: locator call logs can contain form values.
import { chromium } from 'playwright-core';
import { readFileSync } from 'node:fs';
import { createHmac } from 'node:crypto';
import assert from 'node:assert/strict';

const { origin, admin, ordinary, password, factor } = JSON.parse(readFileSync(0, 'utf8'));
assert.equal(new URL(origin).hostname, '127.0.0.1');
const phase = label => { stage = label; console.log('Checking ' + label); };
let stage = 'Chromium launch', browser;
function code() {
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30000)));
  const digest = createHmac('sha1', Buffer.from(factor, 'base64')).update(counter).digest();
  return String((digest.readUInt32BE(digest[19] & 15) & 0x7fffffff) % 1000000).padStart(6, '0');
}
try {
  browser = await chromium.launch({
    channel: 'chromium', chromiumSandbox: true, headless: true,
    ignoreDefaultArgs: ['--disable-back-forward-cache']
  });
  console.log('Chromium ' + browser.version());
  const context = await browser.newContext({ ignoreHTTPSErrors: false });
  const page = await context.newPage();
  page.setDefaultTimeout(10000);
  const heading = text => { phase('heading: '+text); return page.getByRole('heading', {name: text, exact: true}).waitFor(); };
  page.on('response', response => {
    if (response.request().isNavigationRequest()) console.log('Navigation HTTP '+response.status());
  });
  const protectedText = /Your device sessions|Administrator browser|Revoke this session|View own sessions/;
  let restored = false;
  page.on('console', msg => { if (msg.text() === 'protected-document-restored') restored = true; });
  await page.addInitScript(() => {
    addEventListener('pageshow', e => {
      if (e.persisted && document.querySelector('form[action="/revoke"], form[action="/sessions"]'))
        console.info('protected-document-restored');
    });
  });
  async function login(email) {
    await page.goto(origin);
    await heading('Administrator sign in');
    await page.getByLabel('Email').fill(email);
    await page.getByLabel('Password').fill(password);
    await page.getByRole('button', {name:'Continue'}).click();
    await heading('Administrator verification');
  }
  phase('ordinary account denial');
  await login(ordinary);
  await page.getByLabel('Authenticator code').fill('000000');
  await page.getByRole('button', {name:'Verify'}).click();
  await heading('Authentication failed or session expired');
  const errorHtml = await page.content();
  for (const value of [ordinary, password, factor, '000000']) assert.ok(!errorHtml.includes(value));
  assert.ok(!/Bearer |eyJ[A-Za-z0-9_-]+\.|Traceback|SQLAlchemy/.test(errorHtml));

  phase('admin login and TOTP');
  await login(admin);
  await page.getByLabel('Authenticator code').fill(code());
  await page.getByRole('button', {name:'Verify'}).click();
  await heading('Administrator session');
  phase('protected device list');
  await page.getByRole('button', {name:'View own sessions'}).click();
  await heading('Your device sessions');
  await page.getByText('Administrator browser', {exact:false}).first().waitFor();
  const deviceIds = await page.locator('input[name=sid]').evaluateAll(inputs => inputs.map(i=>i.value));
  assert.ok(deviceIds.length);
  async function privateContentAbsent() {
    const html = await page.content();
    assert.ok(!protectedText.test(html) && deviceIds.every(id => !html.includes(id)) && !restored);
  }
  phase('logout');
  await page.getByRole('button', {name:'Sign out'}).click();
  await heading('Signed out');
  assert.ok(!(await context.cookies(origin)).some(c=>c.name==='__Host-dabbarha-admin'));
  phase('real Back navigation');
  const cdp = await context.newCDPSession(page);
  const before = await cdp.send('Page.getNavigationHistory');
  assert.equal(before.entries[before.currentIndex-1].url,origin+'/sessions');
  // Chromium can show an internal expired-POST page on history traversal.
  try { await page.goBack({waitUntil:'load'}); }
  catch (e) { if (!String(e).includes('ERR_CACHE_MISS')) throw e; }
  const after = await cdp.send('Page.getNavigationHistory');
  assert.equal(after.currentIndex,before.currentIndex-1);
  assert.equal(after.entries[after.currentIndex].url,origin+'/sessions');
  await privateContentAbsent();
  phase('direct entry and reload after logout');
  for (const [path,status,title] of [['/sessions',404,'Unavailable'],['/',200,'Administrator sign in']]) {
    assert.equal((await page.goto(origin+path)).status(),status);
    await heading(title); await privateContentAbsent();
    assert.equal((await page.reload()).status(),status);
    await heading(title); await privateContentAbsent();
  }
  console.log('PASS: all Linux browser acceptance checks');
} catch {
  console.error('FAIL: '+stage+' (sensitive browser diagnostics suppressed)');
  process.exitCode = 1;
} finally {
  await browser?.close();
}
