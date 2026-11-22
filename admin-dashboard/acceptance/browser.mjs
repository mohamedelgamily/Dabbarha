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
  const click = name => page.getByRole('button', {name, exact:true}).click();
  phase('operational overview and health');
  await click('Overview'); await heading('Overview');
  assert.ok(await page.getByText('Accounts · last 7 days',{exact:true}).isVisible());
  await click('System Health'); await heading('System Health');
  assert.ok(await page.getByText('Deployment readiness: Ready',{exact:true}).isVisible());
  await click('Users'); await heading('Users');
  await page.getByLabel('Search by').selectOption('email');
  await page.getByLabel('Exact account ID or email').fill(ordinary);
  await click('Find account'); await heading('Account metadata');
  const target=await page.locator('input[name=id]').first().inputValue();
  assert.match(target,/^[1-9][0-9]*$/);
  await click('Inspect sessions'); await heading('Account sessions');
  await click('Notifications'); await heading('Notifications');
  await click('Show deliveries'); await heading('Notification deliveries');
  phase('case-bound grant lifecycle and per-read MFA');
  await click('Support Access'); await heading('Support Access');
  await page.getByLabel('Target account ID').fill(target);
  await page.getByLabel('Case reference').fill('CI-123');
  await page.getByLabel('financial profile',{exact:true}).check();
  await click('Request grant'); await heading('Case grant');
  await page.getByLabel('I am the requester and confirm exceptional audited access').check();
  await click('Exceptionally self-approve'); await heading('Case grant');
  const priorStep=Math.floor(Date.now()/30000);
  while(Math.floor(Date.now()/30000)===priorStep) await page.waitForTimeout(250);
  await page.getByLabel('Fresh authenticator code').fill(code());
  await click('Read financial profile'); await heading('Case records · financial profile');
  await click('Return to grant'); await heading('Case grant');
  await click('Revoke grant'); await heading('Case grant');
  assert.equal(await page.getByRole('button',{name:'Read financial profile'}).count(),0);
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
  assert.equal(before.entries[before.currentIndex-1].url,origin+'/device-sessions');
  // History traversal can commit Chromium's internal expired-POST document
  // without producing a successful HTTP navigation for Playwright.goBack().
  await page.evaluate(() => history.back());
  phase('Back commits the previous device-list history entry');
  let moved = false;
  for (let i=0; i<100; i++) {
    const history = await cdp.send('Page.getNavigationHistory');
    if (history.currentIndex === before.currentIndex-1 &&
        history.entries[history.currentIndex].id === before.entries[before.currentIndex-1].id) {
      moved = true;
      break;
    }
    await page.waitForTimeout(50);
  }
  assert.ok(moved);
  phase('Back shows no protected content');
  await page.waitForFunction(() => document.readyState === 'complete' &&
    document.querySelector('h1')?.textContent !== 'Signed out');
  await privateContentAbsent();
  phase('direct entry and reload after logout');
  for (const [path,status,title] of [['/device-sessions',401,'Authentication failed or session expired'],['/sessions',404,'Unavailable'],['/',200,'Administrator sign in']]) {
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
