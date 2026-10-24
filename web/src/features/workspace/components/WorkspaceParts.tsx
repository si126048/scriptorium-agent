import {useRef,type ReactNode} from 'react';
import {motion} from 'motion/react';
import type {Job} from '../api/client';
export function DocumentPane({children,width,onResize}:{children:ReactNode;width:number;onResize:(v:number)=>void}){
 const drag=useRef<{x:number;width:number}|null>(null);
 return <motion.aside initial={{opacity:0,x:16}} animate={{opacity:1,x:0}} transition={{duration:.24}} className="uw-document-pane" style={{width}}>
 <div className="uw-resize" role="separator" aria-label="调整文档宽度" aria-orientation="vertical" tabIndex={0}
 onKeyDown={e=>{if(e.key==='ArrowLeft')onResize(width+24);if(e.key==='ArrowRight')onResize(width-24);}}
 onPointerDown={e=>{drag.current={x:e.clientX,width};e.currentTarget.setPointerCapture(e.pointerId);}}
 onPointerMove={e=>{if(drag.current)onResize(drag.current.width+drag.current.x-e.clientX);}} onPointerUp={()=>{drag.current=null;}}/>{children}</motion.aside>;
}
export function ResearchProgress({jobs,usage,onCancel}:{jobs:Job[];usage:{used_tokens:number;unknown_calls:number};onCancel:(id:string)=>void}){
 if(!jobs.length&&!usage.used_tokens&&!usage.unknown_calls)return null;
 return <details className="uw-run-card" open={jobs.length>0}><summary><span className={jobs.length?'uw-status-dot active':'uw-status-dot'}/>{jobs.length?'研究正在推进':'研究用量'}<span>{jobs.length?`${jobs.length} 项处理中`:`${usage.used_tokens.toLocaleString()} token`}</span></summary>
 <div className="uw-run-stages"><span>材料阅读</span><span>解释与检验</span><span>修订与成稿</span></div>
 {jobs.map(j=><div className="uw-progress" key={j.id}><span>{j.kind==='import'?'整理研究材料':j.kind==='ocr'?'识别扫描页面':'处理研究步骤'}</span><small>{j.state==='queued'?'等待执行':'执行中'}</small><button onClick={()=>onCancel(j.id)}>停止</button></div>)}
 <p className="uw-muted">已知用量 {usage.used_tokens.toLocaleString()} token{usage.unknown_calls>0?` · ${usage.unknown_calls} 次调用用量待确认`:''} · 仅显示可审查的研究进度</p></details>;
}
export function ScopeChips({selection,materials,onClear,auto}:{selection?:{exact_quote:string};materials:string[];onClear:()=>void;auto?:boolean}){
 return <div className="uw-scope-banner"><span className="uw-eyebrow">本次研究范围</span>{selection?<button onClick={onClear} title="清除选区并改用所选材料">精确选区 · {Array.from(selection.exact_quote).length} 字 ×</button>:<span>{materials.length?`${materials.length} 份材料 · 提交时固定文本版本`:auto?'未选择材料 · 提问时自动检索':'未选择材料 · 普通对话'}</span>}</div>;
}
