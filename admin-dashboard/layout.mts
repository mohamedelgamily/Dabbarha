import { createHash } from 'node:crypto';
import { escapeHtml } from './console.mts';

const styles = `
:root{font:16px/1.55 system-ui,sans-serif;color:#02262D;background:#f3f7f6;color-scheme:light}
*{box-sizing:border-box}body{margin:0}header{background:#02262D;color:white;padding:1rem max(5vw,1rem);font-weight:700}
main{max-width:70rem;margin:2rem auto;padding:0 clamp(1rem,4vw,3rem) 3rem}
h1{font-size:clamp(1.8rem,4vw,2.7rem);line-height:1.15}h2{font-size:1.25rem}
nav{display:flex;flex-wrap:wrap;gap:.4rem;border-bottom:1px solid #9aafac;padding-bottom:1rem}
nav form{margin:0}button{background:#02262D;color:white;border:1px solid #02262D;border-radius:.4rem;padding:.65rem 1rem;font:inherit;cursor:pointer}
nav button{background:white;color:#02262D}form{margin:.8rem 0}label{display:block;margin:.6rem 0}
input:not([type=checkbox]),select{display:block;width:min(100%,28rem);padding:.6rem;border:1px solid #708582;border-radius:.3rem;font:inherit}
:focus-visible{outline:3px solid #b76808;outline-offset:3px}dl{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,13rem),1fr));gap:1px;background:#d5e2de;border:1px solid #d5e2de}
dl div{padding:.75rem;background:white;overflow-wrap:anywhere}dt{text-transform:capitalize;font-size:.87rem}dd{margin:.25rem 0;font-weight:650}
.records{list-style:none;padding:0}fieldset{border:1px solid #9aafac}a{color:#175b64}
`;
export const stylePolicy = "'sha256-"+createHash('sha256').update(styles).digest('base64')+"'";
export function layout(title:string,body:string) {
  return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+escapeHtml(title)+' · Dabbarha Admin</title><style>'+styles+'</style></head><body><header>Dabbarha Admin</header><main><h1>'+escapeHtml(title)+'</h1>'+body+'</main></body></html>';
}
