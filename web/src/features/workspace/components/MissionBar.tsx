import type {ReactNode} from 'react';
import {Icon} from './Icon';

export interface MissionUsage{used_tokens?:number;reserved_tokens?:number;unknown_calls?:number}

export function MissionBar({project,title,runId,usage,sources,jobs,connected,theme,onTheme,onMenu,onSearch,menu,halo,onHalo}:{
  project:string;title:string;runId:string;usage?:MissionUsage;sources:number;jobs:number;
  connected:boolean;theme:'light'|'dark';onTheme:()=>void;onMenu:()=>void;onSearch:()=>void;menu?:ReactNode;halo?:boolean;onHalo?:()=>void;
}){
  const used=usage?.used_tokens||0;const reserved=usage?.reserved_tokens||0;const total=used+reserved;
  const budget=40000;const ratio=Math.min(1,total/budget);
  return <header className="uw-conversation-header fd-bar">
    <button className="wb-icon fd-icon" onClick={onMenu} aria-label="切换项目导航"><Icon name="panel" size={16}/></button>
    <div className="fd-status" title={connected?'本地服务已连接':'实时连接恢复中'}>
      <span className={`fd-led ${connected?'is-on':'is-warn'}`}/><span>LOCAL</span>
      <b>{connected?'LINK OK':'RECONNECT'}</b>
    </div>
    <div className="fd-crumb">
      <span className="fd-project">{project||'研究工作台'}</span>
      <span className="fd-sep">/</span>
      <h1>{title||'开始一项研究'}</h1>
      <span className="fd-run">RUN {runId||'----'}</span>
    </div>
    <div className="fd-gauges">
      <div className="fd-gauge" title={`已用 ${used.toLocaleString()} · 预留 ${reserved.toLocaleString()} token`}>
        <svg viewBox="0 0 32 32" aria-hidden="true"><circle cx="16" cy="16" r="12" fill="none" stroke="var(--fd-seam)" strokeWidth="2"/><circle cx="16" cy="16" r="12" fill="none" stroke="var(--fd-orange-graphic)" strokeWidth="2" strokeDasharray={`${ratio*75.4} 75.4`} transform="rotate(-90 16 16)"/></svg>
        <div><b>{total>=1000?(total/1000).toFixed(1)+'k':total}</b><span>TOKENS</span></div>
      </div>
      <div className="fd-gauge" title="项目来源数量"><div><b>{sources}</b><span>SOURCES</span></div></div>
      <div className="fd-gauge" title="进行中的任务"><div><b>{jobs}</b><span>JOBS</span></div></div>
    </div>
    {onHalo&&<button className="fd-toggle fd-halo-toggle" onClick={onHalo} aria-label="切换 HALOFLUX 环境光"
      aria-pressed={!!halo} title="HALOFLUX 环境光"><span className="fd-switch"/><span>HALO</span></button>}
    <button className="fd-toggle" onClick={onTheme} aria-label="切换白班 / 夜班" aria-pressed={theme==='dark'}>
      <span className="fd-switch"/><span>{theme==='dark'?'NIGHT':'DAY'}</span>
    </button>
    <button className="wb-icon fd-icon" aria-label="搜索与操作" onClick={onSearch}><Icon name="search" size={16}/></button>
    {menu}
  </header>;
}
