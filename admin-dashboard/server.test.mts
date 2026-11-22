import test from 'node:test';
import assert from 'node:assert/strict';
import {createServer, request as httpRequest} from 'node:http';
import {dashboard} from './server.mts';

async function fixture(t,role='admin') {
  let clock=1700000000000, fail='', calls=[];
  const sid='11111111-1111-4111-a111-111111111111';
  const mock=async(url,opts)=>{
    const path=new URL(url).pathname;
    calls.push([path,opts]);
    if(path===fail) return new Response(null,{status:503});
    const data={
      '/auth/sessions':opts.method==='GET'?[{id:sid,device_label:'<script>',revoked_at:null}]:{access_token:'base-secret',refresh_token:'refresh-secret',session_id:sid,expires_in:900},
      '/admin/auth/step-up':{access_token:'admin-secret',expires_in:300},
      '/admin/auth/me':{admin_role:role,step_up_expires_at:clock/1000+300}
    };
    if(['/auth/logout','/auth/sessions/'+sid+'/revoke'].includes(path)) return new Response(null,{status:204});
    if(path==='/admin/auth/step-up' && role==='user') return new Response(null,{status:401});
    return Response.json(data[path]);
  };
  const app=dashboard('https://localhost:8443','http://127.0.0.1:8000',mock,()=>clock);
  const server=createServer(app.handler); await new Promise(r=>server.listen(0,'127.0.0.1',r));
  t.after(async()=>{await new Promise(r=>server.close(r));await app.close()});
  let cookie='',csrf='';
  async function request(path='/',fields={},headers={}) {
    const post=path!=='/';
    const payload=new URLSearchParams({csrf,...fields}).toString();
    const res=await new Promise((resolve,reject)=>{
      const req=httpRequest({hostname:'127.0.0.1',port:server.address().port,path,method:post?'POST':'GET',
        headers:{host:'localhost:8443',cookie,...(post?{origin:'https://localhost:8443','content-type':'application/x-www-form-urlencoded'}:{}),...headers}},resolve);
      req.on('error',reject);req.end(post?payload:undefined);
    });
    let html='';for await(const chunk of res) html+=chunk;
    assert.doesNotMatch(html,/base-secret|refresh-secret|admin-secret/);
    const set=res.headers['set-cookie']?.[0];
    if(set) {assert.match(set,/HttpOnly; Secure; SameSite=Strict/); cookie=set.split(';')[0];}
    csrf=html.match(/name="csrf" value="([^"]+)"/)?.[1]??csrf;
    return {status:res.statusCode,html,cookie,csrf};
  }
  await request();
  return {request,calls,sid,expire:()=>clock+=310000,fail:path=>fail=path};
}
test('origin, CSRF, fixed routes and host guard precede credential forwarding',async t=>{
  const f=await fixture(t);
  for(const headers of [{origin:'https://evil.invalid'},{host:'evil.invalid'}]) assert.equal((await f.request('/login',{},headers)).status,403);
  assert.equal((await f.request('/login',{csrf:'bad'})).status,403);
  assert.equal((await f.request('/admin/ops/overview')).status,404);
  assert.equal((await f.request('/sessions')).status,403);
  assert.equal(f.calls.length,0);
});
test('rotation invalidates pre-MFA handles, checks role upstream, escapes labels and revokes own session',async t=>{
  const f=await fixture(t);
  const pending=await f.request('/login',{email:'admin@example.invalid',password:'example'});
  assert.equal((await f.request('/sessions')).status,403);
  const active=await f.request('/mfa',{code:'123456'});
  assert.equal(active.status,200);assert.notEqual(pending.cookie,active.cookie);
  assert.equal((await f.request('/sessions',{csrf:pending.csrf},{cookie:pending.cookie})).status,401);
  assert.match((await f.request('/sessions')).html,/&lt;script&gt;/);
  assert.equal(f.calls.at(-2)[1].headers.Authorization,'Bearer admin-secret');
  assert.equal((await f.request('/revoke',{sid:'../bad'})).status,400);
  assert.match((await f.request('/revoke',{sid:f.sid,password:'example'})).html,/Current device session revoked/);
  assert.equal((await f.request('/sessions',{}, {cookie:active.cookie})).status,401);
});
test('ordinary user fails MFA and upstream device is signed out',async t=>{
  const f=await fixture(t,'user');await f.request('/login');
  assert.equal((await f.request('/mfa')).status,401);
  assert.equal(f.calls.at(-1)[0],'/auth/logout');
  assert.equal((await f.request('/sessions')).status,401);
});
test('logout outage destroys browser handle and discloses uncertainty',async t=>{
  const f=await fixture(t);await f.request('/login');const active=await f.request('/mfa');
  f.fail('/auth/logout');assert.match((await f.request('/logout')).html,/could not be confirmed/);
  assert.equal((await f.request('/sessions',{}, {cookie:active.cookie})).status,401);
});
test('MFA alone cannot authorize after identity outage or local expiry',async t=>{
  const f=await fixture(t);await f.request('/login');await f.request('/mfa');
  f.fail('/admin/auth/me');assert.equal((await f.request('/sessions')).status,503);
  assert.ok(!f.calls.some(([p,o])=>p==='/auth/sessions'&&o.method==='GET'));
  f.expire();assert.equal((await f.request('/sessions')).status,401);
});
test('reject insecure public configuration',()=>{
  assert.throws(()=>dashboard('http://localhost','https://api.invalid'));
  assert.throws(()=>dashboard('https://localhost','http://api.invalid'));
});
test('logout confirms upstream retirement and a new process rejects the old cookie',async t=>{
  const f=await fixture(t);await f.request('/login');const active=await f.request('/mfa');
  const replacement=await fixture(t);
  assert.equal((await replacement.request('/sessions',{csrf:active.csrf},{cookie:active.cookie})).status,401);
  assert.match((await f.request('/logout')).html,/Signed out/);
  const [,options]=f.calls.at(-1);
  assert.deepEqual(JSON.parse(options.body),{refresh_token:'refresh-secret'});
  assert.equal(options.headers.Authorization,undefined);
  assert.equal((await f.request('/sessions',{csrf:active.csrf},{cookie:active.cookie})).status,401);
});
test('capacity rejects new anonymous sessions while existing handles remain usable',async t=>{
  const f=await fixture(t);
  for(let i=1;i<128;i++) assert.equal((await f.request('/',{},{cookie:''})).status,200);
  assert.equal((await f.request('/',{},{cookie:''})).status,503);
  assert.equal((await f.request()).status,200);
});
