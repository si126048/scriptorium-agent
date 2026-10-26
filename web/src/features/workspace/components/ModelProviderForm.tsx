import {ThemedSelect} from './ThemedSelect';
import {useEffect,useState} from 'react';
import {connectionWarningText,request} from '../api/client';

interface Provider {id:string;label:string;base_url:string;model:string;key_optional:boolean;configured:boolean;ready:boolean;source:string;web_search?:boolean}
interface Status {active:string;editable:boolean;storage:string;providers:Provider[]}

const SOURCE:Record<string,string>={ 'credential-store':'系统凭据', 'private-file':'私有文件', environment:'环境变量', unset:'未设置' };

export function ModelProviderForm(){
 const [status,setStatus]=useState<Status>();
 const [id,setId]=useState('');
 const [baseUrl,setBaseUrl]=useState('');
 const [model,setModel]=useState('');
 const [key,setKey]=useState('');
 const [message,setMessage]=useState('');
 const [busy,setBusy]=useState(false);
 const pick=(s:Status,pid:string)=>{const p=s.providers.find(x=>x.id===pid)||s.providers[0];if(!p)return;setId(p.id);setBaseUrl(p.base_url);setModel(p.model);};
 const load=async()=>{const s=await Promise.race([request<Status>('/api/v2/system/model'),new Promise<never>((_,reject)=>setTimeout(()=>reject(new Error('读取模型设置超时；请检查研究服务地址与连接状态。')),8000))]);setStatus(s);pick(s,s.active);return s;};
 // Mount-time fetch: the state is only written after the request resolves.
 // oxlint-disable-next-line react/set-state-in-effect
 useEffect(()=>{void load().catch(e=>setMessage(String(e)));},[]);
 const current=status?.providers.find(p=>p.id===id);
 const save=async()=>{setBusy(true);try{const keeping=!!key;const s=await request<Status>('/api/v2/system/model',{method:'PUT',body:JSON.stringify({provider:id,base_url:baseUrl,model,key:key||undefined})});setStatus(s);setKey('');setMessage(keeping?'密钥已保存，后续调用立即生效。':'模型配置已保存并启用。');}catch(e){setMessage(String(e));}finally{setBusy(false);}};
 const clear=async()=>{setBusy(true);try{const s=await request<Status>('/api/v2/system/model?provider='+encodeURIComponent(id),{method:'DELETE'});setStatus(s);setMessage('已清除该服务商保存的密钥。');}catch(e){setMessage(String(e));}finally{setBusy(false);}};
 const probe=async()=>{setBusy(true);try{const r=await request<{ok:boolean;error?:string}>('/api/v2/system/model/test?provider='+encodeURIComponent(id),{method:'POST'});setMessage(r.ok?'连接成功：可以列出模型。':'连接失败：'+(r.error||'未知错误'));}catch(e){setMessage(String(e));}finally{setBusy(false);}};
 if(!status)return <><h3>研究模型</h3><p className="uw-muted">正在读取模型设置…</p>{message&&<p className="uw-notice">{message}</p>}<div className="uw-inline-actions"><button type="button" disabled={busy} onClick={()=>{setBusy(true);setMessage('');void load().catch(e=>setMessage(String(e))).finally(()=>setBusy(false));}}>重试</button></div>{connectionWarningText()&&<p className="uw-muted">{connectionWarningText()}</p>}</>;
 return <><h3>研究模型</h3>
  {!status.editable&&<p className="uw-muted">服务商与密钥由服务器管理员管理。</p>}<form onSubmit={e=>{e.preventDefault();void save();}}><fieldset disabled={!status.editable} style={{border:0,padding:0,margin:0}}>
   <label>服务商<ThemedSelect aria-label="模型服务商" value={id} onChange={e=>pick(status,e.target.value)}>{status.providers.map(p=><option key={p.id} value={p.id}>{p.label}{p.configured?' · 已配置':p.ready?' · 无需密钥':''}</option>)}</ThemedSelect></label>
   <label>接口地址<input aria-label="模型接口地址" value={baseUrl} onChange={e=>setBaseUrl(e.target.value)} placeholder="https://…/v1"/></label>
   <label>模型<input aria-label="模型名称" value={model} onChange={e=>setModel(e.target.value)} placeholder={current?.key_optional?'例如 qwen2.5:7b':'例如 deepseek-chat'}/></label>
   <label>{current?.key_optional?'API 密钥（本机模型可留空）':'API 密钥'}<input aria-label="模型 API 密钥" type="password" autoComplete="off" value={key} onChange={e=>setKey(e.target.value)} placeholder="只保存到本机；页面不回显"/></label>
   <div className="uw-inline-actions"><button className="uw-primary" disabled={busy}>保存并启用</button><button type="button" disabled={busy} onClick={()=>void clear()}>清除密钥</button><button type="button" disabled={busy} onClick={()=>void probe()}>测试连接</button></div>
  </fieldset></form>
  <p className="wb-source-warning">{current?.web_search?'原生联网已适配：自动研究可获取来源列表，并尝试读取公开正文。':'当前模型尚未适配可追溯的原生联网；可继续聊天和项目材料研究。'}</p>
  {connectionWarningText()&&<p className="uw-muted">{connectionWarningText()}</p>}<p className="uw-muted">当前：{current?.label||'—'} · {current?.configured?'已配置（'+(SOURCE[current.source]||current.source)+'）':current?.ready?'无需密钥':'未配置'} · 密钥存储：{status.storage==='vault'?'系统凭据':'私有文件'}。密钥不会返回浏览器，也不会写入对话或项目记录。</p>
  {message&&<p className="uw-notice">{message}</p>}</>;
}
