import type {Schemas,Endpoints} from './generated';
import {queryClient} from './query';
let localKey='';
let localUrl='';
let connection:Promise<void>|undefined;
let connectionWarning='';
const DEFAULT_LOCAL_URL='http://127.0.0.1:8010';
function withTimeout<T>(work:Promise<T>,ms:number,message:string):Promise<T>{
 let timer:ReturnType<typeof setTimeout>|undefined;
 const timeout=new Promise<T>((_,reject)=>{timer=setTimeout(()=>reject(new Error(message)),ms);});
 return Promise.race([work,timeout]).finally(()=>{if(timer)clearTimeout(timer);});
}
function timeoutSignal(init:RequestInit,ms:number){
 const timeout=typeof AbortSignal.timeout==='function'?AbortSignal.timeout(ms):undefined;
 if(!timeout)return init.signal;
 if(!init.signal)return timeout;
 return typeof AbortSignal.any==='function'?AbortSignal.any([init.signal,timeout]):timeout;
}
async function hydrateConnection(){
 const internal=(window as unknown as {__TAURI_INTERNALS__?:{invoke:(name:string)=>Promise<{url:string;api_key:string}>}}).__TAURI_INTERNALS__;
 if(!internal||localUrl)return;
 if(!connection)connection=(async()=>{
  // A slow or broken desktop IPC must never block the whole workbench: probe once, then fall back.
  try{
   const value=await withTimeout(internal.invoke('get_research_connection'),2500,'桌面服务地址读取超时');
   localUrl=value.url;localKey=value.api_key;connectionWarning='';
  }catch(e){
   localUrl=DEFAULT_LOCAL_URL;
   connectionWarning=`未能从桌面进程取得研究服务地址（${e instanceof Error?e.message:String(e)}）；已回退到 ${localUrl}。可在“设置与档案”保存连接地址。`;
  }
 })();
 await connection;
}
export function connectionWarningText(){return connectionWarning;}
export function resetConnection(){connection=undefined;localUrl='';localKey='';connectionWarning='';}
export function setStoredConnection(url:string,key:string){
 localUrl=url;localKey=key;connectionWarning='';connection=Promise.resolve();
}
export interface Project { id: string; name: string; description: string }
export interface Version { id: string; quality: Record<string, unknown>; created_at: number }
export interface Material { id: string; name: string; status: string; revision: number; versions: Version[]; metadata: Record<string, unknown>; sha256?:string }
export interface Segment { id: string; asset_id: string; version_id: string; xml_id: string; text: string; page_label: string | null }
export interface Anchor { id: string; segment_id: string; start_codepoint: number; end_codepoint: number; exact_quote: string; segment?: Segment }
export interface ResearchRecord { id: string; kind: string; revision: number; payload: Payload; created_at: number }
export interface Payload {
  pinned?:boolean;archived?:boolean;research_question?:string;editor_json?: Record<string, unknown>; legacy_run_id?: string; title?: string; text?: string; status?: string; provider_mode?: string; evidence_ids?: string[];
  dimensions?: Record<string, string>; findings?: { title: string; text: string; evidence_ids: string[] }[];
  open_questions?: string[]; alternatives?: string[]; outcome?: string; method_id?: string;
  coverage?: { segment_id: string; status: string }[];
  question?: string; followups?: string[]; insufficient?: boolean;
  scope?: { segment_id: string; asset_id: string; version_id: string; start_codepoint: number; end_codepoint: number }[];
  plan?: { retrieval?: string; source?: string; hits?: number; segment_count?: number; characters?: number; materials?: string[] };
  from_id?: string; to_id?: string; parent_id?: string; difficulty_id?: string;
  difficulty_type?: string; criterion_id?: string; position_id?: string;
  retained?: string; negated?: string; reason?: string; shift?: string; excluded_causes?: string;
  rebuttal_conditions?: string; source_record_ids?: string[]; author_id?: string;
  relation?: string; target_id?: string;
}
export interface Job { payload?:{conversation_id?:string;[key:string]:unknown}; id: string; kind: string; state: string; error: string | null; result?: { record_id?: string } }
export interface LegacyRecord { id: string; table_name: string; legacy_key: string; status: string; payload: unknown }

export function serviceUrl() {
  return (localUrl || localStorage.getItem('scriptorium_research_url') ||
    ('__TAURI_INTERNALS__' in window ? 'http://127.0.0.1:8010' :
      location.protocol.startsWith('http') ? location.origin : 'http://127.0.0.1:8010')).replace(/\/$/, '');
}

export async function response(path: string, init: RequestInit = {}, stream=false) {
  await hydrateConnection();
  const headers = new Headers(init.headers);
  const key = localKey || localStorage.getItem('scriptorium_research_key');
  if (key) headers.set('Authorization', `Bearer ${key}`);
  if (typeof init.body === 'string') headers.set('Content-Type', 'application/json');
  const r = await fetch(`${serviceUrl()}${path}`, { ...init, credentials:'include', headers, signal: stream?init.signal:timeoutSignal(init, 30000) });
  if (!r.ok) throw new Error(`${r.status}：${await r.text()}`);
  return r;
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  if (!init.method || init.method === 'GET') return queryClient.fetchQuery<T>({queryKey:['api',serviceUrl(),path],queryFn:async ({signal})=>(await response(path,{...init,signal:init.signal ? AbortSignal.any([signal,init.signal]) : signal})).json()});
  const value = await (await response(path, init)).json();
  const clean=path.split('?')[0];const parts=clean.split('/');const root=parts.slice(0,5).join('/');
  const resource=parts[5];const affected=resource==='records'?['records','artifacts']:resource==='artifacts'||resource==='change-proposals'?['records','artifacts','tasks','jobs']:resource==='imports'?['materials','jobs','tasks']:resource==='materials'?['materials','citation-labels']:resource==='conversations'?(parts[7]==='workspace'?[]:['conversations','jobs','tasks']):resource==='jobs'||resource==='research-runs'||resource==='decisions'?['jobs','tasks','decisions','records','model-calls']:[resource];
  await queryClient.invalidateQueries({predicate:q=>q.queryKey[0]==='api'&&q.queryKey[1]===serviceUrl()&&typeof q.queryKey[2]==='string'&&(clean.startsWith('/api/v2/projects/')?affected.some(name=>name&&String(q.queryKey[2]).startsWith(root+'/'+name)):String(q.queryKey[2]).split('?')[0]===clean)});
  return value;
}

export function projectPath(projectId: string) { return `/api/v2/projects/${encodeURIComponent(projectId)}`; }

export async function download(path: string, filename: string) {
  const r = await response(path);
  saveBlob(await r.blob(), filename);
}

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function exportBrowserHistory() {
  const raw = localStorage.getItem('scriptorium_tasks');
  const content = { format: 'scriptorium-browser-history.v1', tasks: raw ? JSON.parse(raw) : [],
    exported_at: new Date().toISOString(), current_task: localStorage.getItem('scriptorium_current_task'),
    note: '仅包含当前浏览器仍保存的历史；不包含密钥，未删除原记录。' };
  saveBlob(new Blob([JSON.stringify(content, null, 2)], { type: 'application/json' }), 'scriptorium-history.json');
}

export function codepointOffset(text: string, utf16: number) { return Array.from(text.slice(0, utf16)).length; }

export async function persistDesktopConnection(url: string) {
  const internal = (window as unknown as { __TAURI_INTERNALS__?: { invoke: (cmd: string, args: Record<string, unknown>) => Promise<unknown> } }).__TAURI_INTERNALS__;
  if (internal) await internal.invoke('set_research_service', { url });
}

export function sendMessage(pid:string,cid:string,body:Schemas['SendIn'],idempotencyKey:string){
 return request<Job>(`${projectPath(pid)}/conversations/${encodeURIComponent(cid)}/messages`,{
 method:'POST',headers:{'Idempotency-Key':idempotencyKey},body:JSON.stringify(body)});
}

export async function configureConnection(url:string,key:string){
 resetConnection();localUrl=url;localKey=key;localStorage.setItem('scriptorium_research_url',url);
 localStorage.removeItem('scriptorium_research_key');
 await queryClient.cancelQueries();queryClient.clear();await persistDesktopConnection(url);
}

/** Route contracts come from the same OpenAPI document as the service. */
export function endpoint<K extends keyof Endpoints>(route:K,params:Record<string,string>,body?:Endpoints[K]['request'],options:RequestInit&{query?:Record<string,string|number|boolean|undefined>}={}):Promise<Endpoints[K]['response']>{
 const split=route.indexOf(' ');const method=route.slice(0,split);let path=route.slice(split+1).replace(/\{([^}]+)\}/g,(_,name:string)=>{if(!(name in params))throw new Error('Missing path parameter: '+name);return encodeURIComponent(params[name]);});
 const {query,...init}=options;if(query){const values=new URLSearchParams();for(const [key,value]of Object.entries(query))if(value!==undefined)values.set(key,String(value));if(values.size)path+='?'+values;}
 return request<Endpoints[K]['response']>(path,{...init,method,...(body===undefined?{}:{body:JSON.stringify(body)})});
}
