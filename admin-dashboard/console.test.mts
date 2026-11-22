import assert from 'node:assert/strict';
import test from 'node:test';
import {consoleView,consoleNav} from './console.mts';
const grant='5cf86054-d79d-4222-91ac-5899519d4749';
const form=(path,fields,label)=>'<form>'+fields+label+'</form>';
function render(input,reply={},role='admin') {
  const calls=[];
  const result=consoleView(role,new URLSearchParams(input),form,async(...args)=>{
    calls.push(args); if(reply instanceof Error) throw reply;return reply;
  });
  return {result,calls};
}
test('role navigation, operations counters, unavailable values and readiness',async()=>{
  assert.doesNotMatch(consoleNav('admin',form),/Support Access/);
  assert.match(consoleNav('superadmin',form),/Support Access/);
  const {result,calls}=render({op:'overview'},{accounts:{total:33}});
  assert.match((await result)[1],/33/);assert.deepEqual(calls,[['GET','/admin/ops/overview?window_days=7']]);
  const [,health]=await consoleView('admin',new URLSearchParams({op:'health'}),form,async(_,path)=>{
    if(path==='/ready') throw Error();return {components:{database:'available',redis:'unavailable'},worker:{state:'stale'}};
  });
  assert.match(health,/readiness: Unavailable/);assert.match(health,/stale/);
  await assert.rejects(render({op:'overview'},Error('outage')).result);
});
test('exact search encodes email and allowlists metadata; invalid query never forwarded',async()=>{
  const {result,calls}=render({op:'lookup',by:'email',query:'operator+qa@example.com'},
    {account_id:13,display_name:'<script>',password_hash:'do-not-render'});
  const [,body]=await result;
  assert.match(calls[0][1],/operator%2Bqa%40example.com/);
  assert.match(body,/&lt;script&gt;/);assert.doesNotMatch(body,/do-not-render/);
  for(const query of ['%','a*','?']) {
    const x=render({op:'lookup',by:'email',query});await assert.rejects(x.result,{status:422});assert.equal(x.calls.length,0);
  }
});
test('bounded session and delivery pagination retain account scope and redact extras',async()=>{
  const s=render({op:'user-sessions',id:'2'},{items:[{device_label:'Phone',devices:[{platform:'ios',token:'private-token'}]}],next_offset:20});
  const [,sessions]=await s.result;assert.match(sessions,/Next sessions/);assert.doesNotMatch(sessions,/private-token/);
  assert.equal(s.calls[0][1],'/admin/users/2/sessions?limit=20&offset=0');
  for(const scoped of [true,false]){
    const d=render({op:'deliveries',...(scoped?{id:'2'}:{}),after:'10',state:'failed'},{items:[{state:'failed',body:'private-body'}],next_cursor:19});
    const [,page]=await d.result;assert.doesNotMatch(page,/private-body/);assert.match(page,/Next deliveries/);
    assert.equal(d.calls[0][1],(scoped?'/admin/users/2/deliveries':'/admin/notifications/deliveries')+'?limit=20&after_id=10&state=failed');
  }
  await assert.rejects(render({op:'deliveries',id:'../2'}).result,{status:422});
  assert.match((await render({op:'deliveries'},{items:[]}).result)[1],/No matching/);
});
const metadata={grant_id:grant,target_user_id:9,support_case_reference:'CASE-123',status:'active',scopes:['obligations'],expires_at:2000000000};
test('superadmin grant create, approve, explicit self-approve, inspect and revoke',async()=>{
  for(const op of ['support','request','approve','self','inspect','revoke-grant','read']){
    const x=render({op,grant});await assert.rejects(x.result,{status:403});assert.equal(x.calls.length,0);
  }
  const r=render({op:'request',id:'9',scope:'obligations',reference:'CASE-123',reason:'security_review'},metadata,'superadmin');
  assert.match((await r.result)[1],/Fresh authenticator/);
  assert.deepEqual(r.calls[0],['POST','/admin/support-grants',{target_user_id:9,support_case_reference:'CASE-123',reason_code:'security_review',scopes:['obligations']}]);
  for(const [op,method,suffix] of [['approve','POST','/approve'],['self','POST','/approve'],['inspect','GET',''],['revoke-grant','POST','/revoke']]){
    const x=render({op,grant,case:'on'},metadata,'superadmin');await x.result;
    assert.equal(x.calls[0][0],method);assert.equal(x.calls[0][1],'/admin/support-grants/'+grant+suffix);
    if(suffix==='/approve') assert.equal(x.calls[0][2].self_approval,op==='self');
  }
  await assert.rejects(render({op:'self',grant},metadata,'superadmin').result,{status:422});
  const expired=await render({op:'inspect',grant},{...metadata,status:'expired'},'superadmin').result;
  assert.doesNotMatch(expired[1],/Fresh authenticator/);
});
test('each financial page binds target, scope and fresh code; no arbitrary paths or extra response fields',async()=>{
  for(const [scope,suffix] of [['financial_profile','financial-profile'],['obligations','obligations'],['installments','obligations/7/installments'],['payment_statuses','payment-statuses']]){
    const fields={op:'read',scope,grant,id:'9',obligation:'7',offset:'20'};
    const absent=render(fields,{},'superadmin');await assert.rejects(absent.result,{status:422});assert.equal(absent.calls.length,0);
    const x=render({...fields,code:'123456'},{items:[{scheduled_amount:'19.45',private_key:'sensitive'}],next_offset:40},'superadmin');
    const [,body]=await x.result;
    assert.deepEqual(x.calls[0],['GET','/admin/support-grants/'+grant+'/users/9/'+suffix+(scope==='financial_profile'?'':'?limit=20&offset=20'),undefined,'123456']);
    assert.doesNotMatch(body,/123456|sensitive/);assert.match(body,/Fresh authenticator/);
  }
  for(const change of [{scope:'../../ops'},{id:'2/3'},{grant:'../x'},{offset:'1001'}]){
    const x=render({op:'read',scope:'obligations',grant,id:'9',code:'123456',...change},{},'superadmin');
    await assert.rejects(x.result,{status:422});assert.equal(x.calls.length,0);
  }
});
