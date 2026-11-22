// Browser actions are POST forms. Only this module constructs administrative upstream paths.
export const escapeHtml = (value: unknown) => String(value ?? 'Unavailable').replace(/[&<>"']/g,
  c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
export class ConsoleError extends Error {
  status: number;
  constructor(status: number) { super(); this.status = status; }
}
type Fields = Record<string,string|number>;
type Form = (action:string, fields:string, label:string)=>string;
type Read = (method:'GET'|'POST', path:string, body?:object, code?:string)=>Promise<any>;
const hidden = (values:Fields) => Object.entries(values).map(([k,v]) =>
  '<input type="hidden" name="'+escapeHtml(k)+'" value="'+escapeHtml(v)+'">').join('');
const entry = (name:string,label:string,extra='required') =>
  '<label>'+label+' <input name="'+name+'" '+extra+'></label>';
const select = (name:string,label:string,choices:string[]) => '<label>'+label+' <select name="'+name+'">'+
  choices.map(c=>'<option value="'+c+'">'+escapeHtml(c.replaceAll('_',' '))+'</option>').join('')+'</select></label>';
const numeric = (v:string|null,max=2147483647,min=1) => {
  if (!v || !/^\d{1,10}$/.test(v) || Number(v)<min || Number(v)>max) throw new ConsoleError(422);
  return Number(v);
};
const scopes = ['financial_profile','obligations','installments','payment_statuses'];
const reasons = ['account_support','payment_question','security_review','data_accuracy'];
const states = ['queued','sending','accepted','platform_accepted','failed','cancelled'];
const mfa = entry('code','Fresh authenticator code','required type="password" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" autocomplete="off"');
const label = (s:string) => s.replaceAll('_',' ');
function facts(record:any, fields:string[]) {
  return '<dl>'+fields.map(k=>'<div><dt>'+label(k)+'</dt><dd>'+escapeHtml(record?.[k])+'</dd></div>').join('')+'</dl>';
}
function list(rows:any[], fields:string[]) {
  if (!Array.isArray(rows)) throw new ConsoleError(503);
  return rows.length ? '<ul class="records">'+rows.map(row=>'<li>'+facts(row,fields)+'</li>').join('')+'</ul>' : '<p>No matching records.</p>';
}
export function consoleNav(role:string,form:Form) {
  const actions=[['overview','Overview'],['users','Users'],['notifications','Notifications'],['health','System Health']];
  if(role==='superadmin') actions.push(['support','Support Access']);
  return '<nav aria-label="Administrator sections">'+actions.map(([op,name])=>form('console',hidden({op}),name)).join('')+
    form('sessions','','View own sessions')+form('console',hidden({op:'settings'}),'Settings / Logout')+'</nav>';
}
export async function consoleView(role:string,f:URLSearchParams,form:Form,read:Read):Promise<[string,string]> {
  if (!['admin','superadmin'].includes(role)) throw new ConsoleError(403);
  const op=f.get('op');
  const action=(op:string,name:string,values:Fields={},inputs='') => form('console',hidden({op,...values})+inputs,name);
  if(op==='settings') return ['Settings',facts({role},['role'])+'<p>Session access ends within five minutes of opening the sign-in form. Use account sessions to revoke your own devices.</p>'+form('logout','','Sign out')];
  if(op==='overview') {
    const r=await read('GET','/admin/ops/overview?window_days=7');
    return ['Overview','<h2>Accounts · last 7 days</h2>'+facts(r.accounts,['total','registered_in_window','recently_refreshed_v2_session_accounts'])+
      '<p>Refreshed sessions indicate activity. Account deletions are unmeasured.</p><h2>Notification delivery</h2>'+
      facts(r.notifications,['queue_size','accepted','failed','cancelled','oldest_pending_age_seconds','stale_sending_count'])+
      '<h2>Obligations</h2>'+facts(r,['obligations_total'])+'<h2>Worker</h2>'+facts(r.worker,['state','last_seen_at','last_error_category'])];
  }
  if(op==='health') {
    const r=await read('GET','/admin/ops/health');
    let readiness='Unavailable';
    try { const probe=await read('GET','/ready'); if(probe.status==='ready') readiness='Ready'; }
    catch { /* An unavailable readiness probe must not erase component diagnostics. */ }
    return ['System Health','<p>Deployment readiness: '+readiness+'</p>'+facts(r,['status','migration_revision'])+'<h2>Components</h2>'+
      facts(r.components,['api','database','redis','migration','notification_worker'])+'<h2>Configuration</h2>'+
      facts(r.configuration_readiness,['rate_limit_backend','redis_endpoint_configured','durable_sessions_enabled','notification_delivery_enabled'])+
      '<h2>Worker heartbeat</h2>'+facts(r.worker,['state','last_seen_at','last_success_at','last_error_category','cycles'])+
      '<p>Database and limiter status reflect the configured services. Use /ready for combined database, migration-head and mandatory Redis readiness.</p>'];
  }
  if(op==='users') return ['Users',action('lookup','Find account',{},select('by','Search by',['user_id','email'])+entry('query','Exact account ID or email'))];
  if(op==='lookup') {
    const by=f.get('by'), query=f.get('query')?.trim() ?? '';
    if(by!=='user_id' && by!=='email') throw new ConsoleError(422);
    if(!query || query.length>254 || /[*?%]/.test(query)) throw new ConsoleError(422);
    const value=by==='user_id'?String(numeric(query)):query;
    const r=await read('GET','/admin/users/lookup?'+new URLSearchParams({[by]:value}));
    const id=numeric(String(r.account_id));
    return ['Account metadata',facts(r,['account_id','display_name','email','registered_at','admin_role','account_state'])+
      action('user-sessions','Inspect sessions',{id})+action('deliveries','Inspect deliveries',{id})];
  }
  if(op==='user-sessions'){
    const id=numeric(f.get('id')), offset=numeric(f.get('offset')??'0',10000,0);
    const r=await read('GET','/admin/users/'+id+'/sessions?limit=20&offset='+offset);
    const rows=r.items.map((s:any)=>'<section>'+facts(s,['device_label','active','created_at','last_refreshed_at','idle_expires_at','revoked_at'])+
      list(s.devices,['platform','active','last_registered_at'])+'</section>').join('');
    const next = r.next_offset!=null && r.next_offset<=10000 ? action('user-sessions','Next sessions',{id,offset:r.next_offset}) : '';
    return ['Account sessions',(rows||'<p>No sessions.</p>')+next];
  }
  if(op==='notifications') return ['Notifications',action('deliveries','Show deliveries',{},select('state','Delivery state',['all',...states]))];
  if(op==='deliveries'){
    const id=f.has('id')?numeric(f.get('id')):null,state=f.get('state')??'all';
    if(state!=='all'&&!states.includes(state)) throw new ConsoleError(422);
    const cursor=numeric(f.get('after')??'0',2147483647,0);
    const path=id?'/admin/users/'+id+'/deliveries':'/admin/notifications/deliveries';
    const r=await read('GET',path+'?limit=20&after_id='+cursor+(state==='all'?'':'&state='+state));
    const next=r.next_cursor==null?'':action('deliveries','Next deliveries',{...(id?{id}:{}),state,after:r.next_cursor});
    return ['Notification deliveries',list(r.items,['delivery_id','user_id','notification_type','state','platform','attempt_count','receipt_attempt_count','error_category','updated_at'])+next];
  }
  if (role!=='superadmin') throw new ConsoleError(403);
  const grantEntry=entry('grant','Grant ID');
  if(op==='support') return ['Support Access','<p>Use an opaque case reference. Access is limited to one account and expires 15 minutes after request. Prefer independent approval.</p>'+
    action('request','Request grant',{},entry('id','Target account ID')+entry('reference','Case reference')+
      select('reason','Reason',reasons)+'<fieldset><legend>Read scopes</legend>'+scopes.map(s=>'<label><input type="checkbox" name="scope" value="'+s+'"> '+label(s)+'</label>').join('')+'</fieldset>')+
    action('inspect','Inspect my grant',{},grantEntry)+action('approve','Independently approve case grant',{},grantEntry+entry('case','Confirm case reviewed','type="checkbox" required'))+
    '<p>Verify the grant ID, target, scopes and reason in the authorized case channel before independent approval. Audit history is reviewed through the security operator.</p>'];
  const grant=f.get('grant')??'';
  if(op!=='request' && !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(grant)) throw new ConsoleError(422);
  const base='/admin/support-grants',path=base+'/'+grant;
  if(op==='read'){
    const scope=f.get('scope')??'',code=f.get('code')??'',id=numeric(f.get('id'));
    if(!scopes.includes(scope)||!/^\d{6}$/.test(code)) throw new ConsoleError(422);
    const offset=numeric(f.get('offset')??'0',1000,0);
    const obligation=scope==='installments'?numeric(f.get('obligation')):null;
    const tail=obligation?'obligations/'+obligation+'/installments':scope.replaceAll('_','-');
    const r=await read('GET',path+'/users/'+id+'/'+tail+(scope==='financial_profile'?'':'?limit=20&offset='+offset),undefined,code);
    const fields:Record<string,string[]>={obligations:['id','item_name','provider','total_amount','purchase_price','monthly_installment_amount','status'],
      installments:['installment_number','due_date','scheduled_amount','principal_amount','interest_amount'],
      payment_statuses:['occurrence_id','payment_kind','due_date','scheduled_amount','state','paid_at']};
    const next=r.next_offset==null||r.next_offset>1000?'':action('read','Read next page',{grant,id,scope,offset:r.next_offset,...(obligation?{obligation}:{})},mfa);
    return ['Case records · '+label(scope),(scope==='financial_profile'?facts(r,['target_user_id','monthly_income','fixed_expenses','currency']):list(r.items,fields[scope]))+next+action('inspect','Return to grant',{grant})];
  }
  let r;
  if(op==='request'){
    const reason=f.get('reason'),reference=f.get('reference')??'',requested=f.getAll('scope');
    if(!reasons.includes(reason??'')||!requested.length||requested.some(x=>!scopes.includes(x))||!/^[A-Za-z0-9][A-Za-z0-9._/-]{2,63}$/.test(reference)) throw new ConsoleError(422);
    r=await read('POST',base,{target_user_id:numeric(f.get('id')),support_case_reference:reference,reason_code:reason,scopes:requested});
  }else if(op==='inspect') r=await read('GET',path);
  else if(op==='revoke-grant') r=await read('POST',path+'/revoke');
  else if(op==='approve'||op==='self'){
    if(f.get('case')!=='on') throw new ConsoleError(422);
    r=await read('POST',path+'/approve',{self_approval:op==='self'});
  }else throw new ConsoleError(404);
  const values={grant:r.grant_id,id:r.target_user_id};
  let controls='';
  if(r.status==='pending') controls+=action('self','Exceptionally self-approve',values,entry('case','I am the requester and confirm exceptional audited access','type="checkbox" required'));
  if(r.status==='active') for(const scope of r.scopes.filter((v:string)=>scopes.includes(v))) controls+=action('read','Read '+label(scope),{...values,scope},(scope==='installments'?entry('obligation','Obligation ID'):'')+mfa);
  if(['pending','active'].includes(r.status)) controls+=action('revoke-grant','Revoke grant',values);
  return ['Case grant',facts({...r,expires_at:new Date(r.expires_at*1000).toISOString(),scopes:r.scopes.join(', ')},['grant_id','target_user_id','support_case_reference','reason_code','scopes','status','self_approved','expires_at'])+controls];
}
