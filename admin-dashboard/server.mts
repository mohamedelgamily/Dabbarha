import { createServer, type IncomingMessage, type ServerResponse } from 'node:http';
import { randomBytes, timingSafeEqual } from 'node:crypto';
import { isPrimary } from 'node:cluster';
import { pathToFileURL } from 'node:url';

const cookie = '__Host-dabbarha-admin';
const nonce = () => randomBytes(32).toString('base64url');
const uuid = /^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i;
const escaped = (s: string) => s.replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]!));
class Failure extends Error {
  status: number;
  constructor(status: number) { super(); this.status = status; }
}
type Session = { csrf: string; until: number; busy: boolean; access?: string; refresh?: string; admin?: string; sid?: string };
const routes = {
  login: ['POST','/auth/sessions'], mfa: ['POST','/admin/auth/step-up'],
  identity: ['GET','/admin/auth/me'], list: ['GET','/auth/sessions?limit=50'],
  logout: ['POST','/auth/logout'], revoke: ['POST','/auth/sessions/']
} as const;

function origin(value: string, local = false) {
  const u = new URL(value);
  if (u.origin !== value || !(u.protocol === 'https:' || (local && u.protocol === 'http:' && u.hostname === '127.0.0.1'))) throw Error('Invalid service origin');
  return u;
}

export function dashboard(publicOrigin: string, upstream: string, transport = fetch, now = Date.now) {
  const host = origin(publicOrigin).host;
  origin(upstream, true);
  const sessions = new Map<string, Session>();
  let closing = false;
  async function call(action: keyof typeof routes, token?: string, body?: object, sid?: string) {
    const [method, path] = routes[action];
    if (action === 'revoke' && !uuid.test(sid ?? '')) throw new Failure(400);
    const r = await transport(upstream + path + (action === 'revoke' ? sid + '/revoke' : ''), {
      method, redirect:'error', signal:AbortSignal.timeout(4000),
      headers:{...(token ? {Authorization:'Bearer ' + token} : {}), ...(body ? {'Content-Type':'application/json'} : {})},
      body:body ? JSON.stringify(body) : undefined
    });
    if (!r.ok) { await r.body?.cancel(); throw new Failure([401,403,404,409,422,429].includes(r.status) ? r.status : 503); }
    return r.status === 204 ? undefined : await r.json();
  }
  async function retire(s: Session) {
    if (s.refresh) await call('logout', undefined, {refresh_token:s.refresh});
  }
  function discard(key: string, s: Session) {
    sessions.delete(key);
    return retire(s);
  }
  async function sweep() {
    // Keep an expiring entry counted against capacity until bounded cleanup completes.
    for (const [key,s] of sessions) if (s.until <= now() && !s.busy) {
      s.busy = true;
      try { await retire(s); } catch { console.warn('Admin session cleanup unconfirmed'); }
      finally { sessions.delete(key); }
    }
  }
  const timer = setInterval(() => void sweep(), 10000).unref();
  const handler = async (req: IncomingMessage, res: ServerResponse) => {
    res.setTimeout(10000, () => res.destroy());
    res.setHeader('Cache-Control','no-store');
    res.setHeader('Content-Type','text/html; charset=utf-8');
    res.setHeader('Content-Security-Policy',"default-src 'none'; form-action 'self'; frame-ancestors 'none'; base-uri 'none'");
    res.setHeader('Referrer-Policy','no-referrer');
    res.setHeader('X-Content-Type-Options','nosniff');
    res.setHeader('Strict-Transport-Security','max-age=31536000');
    const setCookie = (key: string, seconds: number) => res.setHeader('Set-Cookie',cookie+'='+key+'; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age='+seconds);
    function page(title: string, content = '', status = 200) {
      res.statusCode = status;
      res.end('<!doctype html><html lang="en"><meta charset="utf-8"><title>Dabbarha Admin</title><main><h1>'+title+'</h1>'+content+'</main></html>');
    }
    let locked: Session | undefined;
    let rejectedKey: string | undefined;
    try {
      if (closing || req.headers.host !== host) throw new Failure(closing ? 503 : 403);
      const path = req.url;
      const post = req.method === 'POST';
      if (!(post ? ['/login','/mfa','/logout','/sessions','/revoke'] : ['/']).includes(path ?? '') || (!post && req.method !== 'GET')) throw new Failure(404);
      if (post && (req.headers.origin !== publicOrigin || req.headers['content-type'] !== 'application/x-www-form-urlencoded')) throw new Failure(403);
      const values = (req.headers.cookie ?? '').split(';').map(x => x.trim()).filter(x => x.startsWith(cookie+'='));
      let key = values.length === 1 ? values[0].slice(cookie.length+1) : '';
      let s = sessions.get(key);
      if (s && s.until <= now()) s = undefined;
      if (!s) {
        if (post) throw new Failure(401);
        if (sessions.size >= 128) throw new Failure(503);
        key = nonce(); s = {csrf:nonce(),until:now()+300000,busy:false};
        sessions.set(key,s); setCookie(key,300);
      }
      if (s.busy) throw new Failure(409);
      locked = s; s.busy = true;
      function rotate() {
        sessions.delete(key); key = nonce(); s!.csrf = nonce(); sessions.set(key,s!);
        setCookie(key,Math.max(1,Math.ceil((s!.until-now())/1000)));
      }
      const form = (action: string, fields: string, label: string) => '<form method="post" action="/'+action+'"><input type="hidden" name="csrf" value="'+s!.csrf+'">'+fields+'<button>'+label+'</button></form>';
      const password = '<label>Password <input type="password" name="password" required></label>';
      const out = () => form('logout','','Sign out');
      let f = new URLSearchParams();
      if (post) {
        let bytes = 0; const chunks = [];
        for await (const chunk of req) {
          bytes += chunk.length; if (bytes > 8192) throw new Failure(413);
          chunks.push(chunk);
        }
        f = new URLSearchParams(Buffer.concat(chunks).toString());
        const csrf = Buffer.from(f.get('csrf') ?? '');
        if (f.getAll('csrf').length !== 1 || csrf.length !== 43 || !timingSafeEqual(csrf,Buffer.from(s.csrf))) throw new Failure(403);
        if (s.until <= now()) throw new Failure(401);
      }
      if (path === '/logout') {
        setCookie('',0);
        try { await discard(key,s); } catch { return page('Browser signed out. Device-session revocation could not be confirmed.', '',503); }
        return page('Signed out','<a href="/">Sign in again</a>');
      }
      if (path === '/login' && !s.access) {
        const pair = await call('login',undefined,{email:f.get('email'),password:f.get('password'),device_label:'Administrator browser'});
        s.refresh = pair.refresh_token; s.access = pair.access_token; s.sid = pair.session_id;
        if (!s.refresh || !s.access || !uuid.test(s.sid ?? '')) throw new Failure(503);
        s.until = Math.min(s.until,now()+pair.expires_in*1000); rotate();
      } else if (path === '/mfa' && s.access && !s.admin) {
        rejectedKey = key;
        const result = await call('mfa',s.access,{code:f.get('code')});
        if (!result.access_token || !(result.expires_in > 0)) throw new Failure(503);
        s.admin = result.access_token; s.until = Math.min(s.until,now()+result.expires_in*1000); rotate();
      } else if (path !== '/' && path !== '/sessions' && path !== '/revoke') throw new Failure(403);
      if (!s.admin) {
        if (path === '/sessions' || path === '/revoke') throw new Failure(403);
        return s.access ? page('Administrator verification',form('mfa','<label>Authenticator code <input name="code" inputmode="numeric" pattern="[0-9]{6}" required></label>','Verify')+out()) :
          page('Administrator sign in',form('login','<label>Email <input type="email" name="email" required></label>'+password,'Continue'));
      }
      rejectedKey = key;
      const identity = await call('identity',s.admin);
      if (!['admin','superadmin'].includes(identity.admin_role) || !(identity.step_up_expires_at*1000 > now()) || s.until <= now()) throw new Failure(403);
      rejectedKey = undefined;
      if (path === '/revoke') {
        const sid = f.get('sid') ?? '';
        await call('revoke',s.access,{password:f.get('password')},sid);
        if (sid === s.sid) { sessions.delete(key); setCookie('',0); return page('Current device session revoked'); }
      }
      if (path === '/sessions') {
        const rows = await call('list',s.access);
        const items = rows.map((r: {id:string;device_label:string|null;revoked_at:number|null}) => uuid.test(r.id) ?
          '<li>'+escaped(r.device_label ?? 'Device')+(r.revoked_at ? ' (revoked)' : form('revoke','<input type="hidden" name="sid" value="'+r.id+'">'+password,'Revoke this session'))+'</li>' : '').join('');
        return page('Your device sessions','<ul>'+items+'</ul>'+out());
      }
      page('Administrator session', '<p>'+escaped(identity.admin_role)+'</p>'+form('sessions','','View own sessions')+out());
    } catch (e) {
      const status = e instanceof Failure ? e.status : 503;
      if (locked && rejectedKey && [401,403].includes(status)) {
        setCookie('',0);
        try { await discard(rejectedKey,locked); } catch { console.warn('Admin session cleanup unconfirmed'); }
      }
      page(({401:'Authentication failed or session expired',403:'Access denied',404:'Unavailable',409:'Request in progress or session conflict',413:'Form too large',422:'Check your input',429:'Too many attempts'} as Record<number,string>)[status] ?? 'Service temporarily unavailable','<a href="/">Return to sign in</a>',status);
    } finally { if (locked) locked.busy = false; }
  };
  return {handler, async close() {
    closing = true; clearInterval(timer);
    await Promise.allSettled([...sessions.values()].map(retire)); sessions.clear();
  }};
}

if (process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href) {
  if (!isPrimary || (process.env.WEB_CONCURRENCY ?? '1') !== '1' || process.env.NODE_UNIQUE_ID) throw Error('Single process required');
  const app = dashboard(process.env.ADMIN_ORIGIN ?? 'https://localhost:8443',process.env.API_ORIGIN ?? 'http://127.0.0.1:8000');
  const server = createServer({requestTimeout:10000,headersTimeout:8000,maxHeaderSize:8192},app.handler);
  server.maxConnections = 160;
  server.listen(8787,'127.0.0.1');
  const stop = () => server.close(() => void app.close());
  process.once('SIGTERM',stop); process.once('SIGINT',stop);
}
