import {LogoSVG} from '../../components/startup/LogoSVG';
import {useEffect,useRef,useState,type ReactNode} from 'react';
import {resetConnection,setStoredConnection} from '../workspace/api/client';
import './desktop-gate.css';

interface Status {
  installed:boolean; state:string; phase?:string|null; progress?:string|null;
  url?:string|null; error?:string|null; search:boolean; api_port?:number|null;
  root?:string|null; logs?:string|null; online:boolean;
}
type Bridge={invoke:(name:string,args?:Record<string,unknown>)=>Promise<unknown>};
const bridge=()=>(window as unknown as {__TAURI_INTERNALS__?:Bridge}).__TAURI_INTERNALS__;
const isDesktop=()=>!!bridge();

const PHASES:Record<string,string>={
  search_wait:'等待全文检索完成首次启动',postgres_wait:'等待数据库完成启动或恢复',pandoc:'下载文档转换组件',postgres:'下载并解压 PostgreSQL',elasticsearch:'下载并解压 Elasticsearch',
  database:'初始化数据库',schema:'初始化数据表',api:'启动研究工作台服务',done:'连接工作台',
  launching:'启动本机服务',queued:'准备启动',
};

function phaseText(status:Status){
  const key=status.phase||status.progress||'';
  if(status.state==='not_installed')return '尚未安装本机服务';
  if(status.state==='failed')return '启动失败';
  if(status.state==='running')return '服务已就绪';
  if(status.state==='stopped')return '服务未运行';
  return PHASES[key]||'正在启动本机服务';
}

function steps(status:Status){
  const deps=status.installed||status.state==='installing';
  const database=deps&&['starting','running'].includes(status.state);
  const service=database&&(['api','done'].includes(status.phase||'')||status.state==='running');
  const connected=status.state==='running'&&status.online;
  return [
    {label:'准备本机组件',done:status.installed,active:!deps},
    {label:'数据库与检索',done:status.state==='running',active:deps&&!database},
    {label:'研究工作台服务',done:status.state==='running',active:service&&!connected},
    {label:'连接界面',done:connected,active:false},
  ];
}

export function DesktopGate({children}:{children:ReactNode}){
  const [status,setStatus]=useState<Status>();
  const [ready,setReady]=useState(!isDesktop());
  const [error,setError]=useState('');
  const [choice,setChoice]=useState<string|null>(()=>localStorage.getItem('scriptorium_desktop_install'));
  const [busy,setBusy]=useState(false);
  const [external,setExternal]=useState(false);
  const [url,setUrl]=useState('http://127.0.0.1:8010');
  const [key,setKey]=useState('');
  const started=useRef(false);

  const invoke=async <T,>(name:string,args?:Record<string,unknown>)=>{
    const api=bridge();
    if(!api)throw new Error('NOT_DESKTOP');
    return await api.invoke(name,args) as T;
  };

  const connect=async()=>{
    const value=await invoke<{url:string;api_key:string}>('get_research_connection');
    if(!value?.url)throw new Error('服务没有返回地址');
    const probe=await fetch(value.url.replace(/\/$/,'')+'/health',{signal:AbortSignal.timeout(4000)});
    if(!probe.ok)throw new Error(`服务 ${value.url} 健康检查失败（${probe.status}）`);
    setStoredConnection(value.url,value.api_key||'');
    setReady(true);
  };

  const refresh=async()=>{
    const next=await invoke<Status>('research_status');
    setStatus(next);
    if(next.state==='failed'&&next.error)setError(next.error);
    if(next.state==='running'&&next.online){
      try{await connect();}catch(e){setError(String(e));}
    }
  };

  const start=async(search:boolean)=>{
    started.current=true;
    setBusy(true);setError('');
    try{
      localStorage.setItem('scriptorium_desktop_install',search?'full':'lite');
      setChoice(search?'full':'lite');
      await invoke('research_start',{search});
      await refresh();
    }catch(e){setError(String(e));}finally{setBusy(false);}
  };

  useEffect(()=>{
    if(!isDesktop())return;
    let stopped=false;
    const tick=async()=>{
      try{await refresh();}catch(e){if(!stopped)setError(String(e));}
    };
    void tick();
    const timer=setInterval(()=>{void tick();},1500);
    return()=>{stopped=true;clearInterval(timer);};
  },[ready]);

  useEffect(()=>{
    if(ready||!status||started.current)return;
    if(status.state==='running')return;
    const saved=localStorage.getItem('scriptorium_desktop_install');
    if(!saved||status.state==='failed')return;
    started.current=true;
    // Auto-start is an external-system action; state changes happen after the IPC call.
    // oxlint-disable-next-line react/set-state-in-effect
    void start(saved==='full');
  },[status,ready]);

  if(!isDesktop()||ready)return <>{children}</>;

  const phase=status?phaseText(status):'正在检查本机服务';
  const failed=status?.state==='failed'||!!error;
  const firstRun=!choice&&(!status||status.state==='not_installed');
  const progress=steps(status||{installed:false,state:'not_installed',search:true,online:false});

  return <div className="desktop-gate">
    <div className="dg-card">
      <p className="dg-mark"><LogoSVG size={36}/> SCRIPTORIUM · LOCAL ARCHIVE</p>
      <h1>本机研究工作台</h1>
      <p className="dg-lede">首次启动由应用自己准备数据库与研究服务，之后双击即用；也可以连接已有的研究服务。</p>
      <div className="dg-status" aria-live="polite">
        <span className={`dg-dot ${failed?'is-error':status?.state==='running'&&status.online?'is-ok':''}`}/>
        <strong>{phase}</strong>
        {busy&&<span className="dg-spinner" aria-hidden="true"/>}
      </div>
      <ol className="dg-steps">
        {progress.map(step=><li key={step.label} className={`${step.done?'is-done':''} ${step.active?'is-active':''}`}>
          <span className="dg-step-dot"/>{step.label}
        </li>)}
      </ol>
      {firstRun&&<div className="dg-first">
        <p>第一次启动需要下载本机组件（约 5–15 分钟，取决于网络）：</p>
        <div className="dg-actions">
          <button type="button" className="dg-primary" disabled={busy} onClick={()=>void start(true)}>
            完整安装（含全文检索，约 1.2 GB）
          </button>
          <button type="button" disabled={busy} onClick={()=>void start(false)}>
            精简安装（不含检索，约 400 MB）
          </button>
        </div>
      </div>}
      {failed&&<div className="dg-error">
        <p>{error||status?.error||'本机服务启动失败'}</p>
        <div className="dg-actions">
          <button type="button" className="dg-primary" disabled={busy} onClick={()=>void start(choice!=='lite')}>重试启动</button>
          <button type="button" onClick={()=>void invoke('research_open_logs').catch(()=>{})}>打开日志目录</button>
        </div>
      </div>}
      {!firstRun&&!failed&&<div className="dg-actions">
        <button type="button" onClick={()=>void invoke('research_open_logs').catch(()=>{})}>查看日志</button>
        <button type="button" onClick={()=>{setExternal(v=>!v);}}>{external?'改用本机服务':'连接已有服务'}</button>
      </div>}
      {external&&<form className="dg-external" onSubmit={e=>{e.preventDefault();void (async()=>{
        const value=new URL(url);localStorage.setItem('scriptorium_research_url',value.origin);
        localStorage.setItem('scriptorium_research_key',key);
        try{await invoke('set_research_service',{url:value.origin});resetConnection();await connect();}
        catch(err){setError(String(err));}
      })();}}>
        <label>服务地址<input value={url} onChange={e=>setUrl(e.target.value)} placeholder="http://127.0.0.1:8010"/></label>
        <label>访问密钥（可留空）<input type="password" value={key} onChange={e=>setKey(e.target.value)}/></label>
        <div className="dg-actions">
          <button type="submit" className="dg-primary">连接</button>
          <button type="button" onClick={()=>setExternal(false)}>返回</button>
        </div>
      </form>}
      {status?.root&&<p className="dg-meta">本机服务目录：{status.root}{status.search?'':' · 未启用全文检索'}</p>}
    </div>
  </div>;
}
