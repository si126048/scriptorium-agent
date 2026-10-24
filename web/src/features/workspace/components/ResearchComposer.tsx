import {useState,type ReactNode} from 'react';
import {DropdownMenu,Collapsible} from 'radix-ui';
import {ScopeChips} from './WorkspaceParts';
export type Tool='chat'|'research'|'theory'|'subject'|'persona';
const tools:[Tool,string][]=[['chat','研究对话'],['research','完整研究'],['theory','理论视角比较'],['subject','主体分析'],['persona','风格模拟']];
const methods=[['situating.v1','思想构境'],['immanent_critique.v1','内在批判'],['parallax.v1','视差分析']];
interface Props{
 draft:string;onDraft:(v:string)=>void;onSend:()=>void;onUpload:(f:File)=>void;
 disabled:boolean;busy:boolean;tool:Tool;method:string;onTool:(t:Tool,m:string)=>void;
 mode:'live'|'demo';onMode:(m:'live'|'demo')=>void;onPeople:()=>void;
 selection?:{exact_quote:string};onClearSelection:()=>void;
 materials:{id:string;name:string}[];onRemoveMaterial:(id:string)=>void;
 interview?:ReactNode;answering:boolean;
}
export function ResearchComposer(p:Props){
 const [advanced,setAdvanced]=useState(false);
 const label=methods.find(([id])=>id===p.method)?.[1]||tools.find(([id])=>id===p.tool)?.[1];
 return <div className="uw-composer-area">
 <ScopeChips selection={p.selection} materials={p.materials.map(m=>m.name)} onClear={p.onClearSelection}/>
 <div className="uw-context-chips">{p.materials.map(m=><button key={m.id} onClick={()=>p.onRemoveMaterial(m.id)}>{m.name} ×</button>)}</div>
 {p.interview}
 <Collapsible.Root open={advanced} onOpenChange={setAdvanced}>
 <form className="uw-composer" onSubmit={e=>{e.preventDefault();p.onSend();}}>
 <textarea aria-label="研究问题或访谈回答" value={p.draft} onChange={e=>p.onDraft(e.target.value)} placeholder={p.answering?'回答当前访谈问题…':'提出研究问题，或围绕所选材料继续讨论…'} onKeyDown={e=>{if(e.key==='Enter'&&(e.ctrlKey||e.metaKey)&&!e.nativeEvent.isComposing){e.preventDefault();p.onSend();}}}/>
 <div className="uw-composer-toolbar"><label className="uw-attach">＋ 附件<input type="file" accept=".txt,.md,.pdf,.xml,.tei" disabled={p.disabled} onChange={e=>{const f=e.target.files?.[0];e.target.value='';if(f)p.onUpload(f);}}/></label>
 <DropdownMenu.Root><DropdownMenu.Trigger asChild><button type="button" aria-label="研究工具">{label} ▾</button></DropdownMenu.Trigger>
 <DropdownMenu.Portal><DropdownMenu.Content className="uw-dropdown" side="top" align="start" sideOffset={8}>
 <DropdownMenu.Label>研究工具</DropdownMenu.Label>
 {tools.map(([id,name])=><DropdownMenu.Item key={id} onSelect={()=>p.onTool(id,'')}>{name}</DropdownMenu.Item>)}
 <DropdownMenu.Separator/>{methods.map(([id,name])=><DropdownMenu.Item key={id} onSelect={()=>p.onTool('research',id)}>{name}</DropdownMenu.Item>)}
 <DropdownMenu.Item onSelect={p.onPeople}>研究访谈</DropdownMenu.Item>
 </DropdownMenu.Content></DropdownMenu.Portal></DropdownMenu.Root>
 <Collapsible.Trigger asChild><button type="button">选项</button></Collapsible.Trigger>
 <button className="uw-primary uw-send" disabled={p.disabled||p.busy||!p.draft.trim()}>发送 ↑</button></div>
 <Collapsible.Content className="uw-advanced"><label>运行模式<select value={p.mode} onChange={e=>p.onMode(e.target.value as 'live'|'demo')}><option value="live">真实模型</option><option value="demo">演示（不产生学术结论）</option></select></label><p>仅使用当前选定材料。改题、扩范围或增加预算会先请求决定。Ctrl / ⌘ + Enter 发送。</p></Collapsible.Content>
 </form></Collapsible.Root><p className="uw-footnote">解释保留为候选 · 每条证据可回到具体原文版本</p></div>;
}
