import {useRef,type ReactNode} from 'react';
import {motion} from 'motion/react';
import {Icon} from './Icon';
import type {Job} from '../api/client';
export function DocumentPane({children,width,onResize}:{children:ReactNode;width:number;onResize:(v:number)=>void}){
 const drag=useRef<{x:number;width:number}|null>(null);
 return <motion.aside initial={{opacity:0,x:12}} animate={{opacity:1,x:0}} transition={{duration:.22}} className="uw-document-pane" style={{width}}>
 <div className="uw-resize" role="separator" aria-label="调整文档宽度" aria-orientation="vertical" aria-valuenow={width} tabIndex={0} onKeyDown={e=>{if(e.key==='ArrowLeft')onResize(width+24);if(e.key==='ArrowRight')onResize(width-24);}} onPointerDown={e=>{drag.current={x:e.clientX,width};e.currentTarget.setPointerCapture(e.pointerId);}} onPointerMove={e=>{if(drag.current)onResize(drag.current.width+drag.current.x-e.clientX);}} onPointerUp={()=>{drag.current=null;}} onPointerCancel={()=>{drag.current=null;}}/>{children}</motion.aside>;
}
export function ResearchProgress({jobs,usage,onCancel}:{jobs:Job[];usage:{used_tokens:number;unknown_calls:number};onCancel:(id:string)=>void}){
 if(!jobs.length&&!usage.unknown_calls)return null;
 return <details className="uw-run-card"><summary><span className={'wb-service-dot '+(jobs.length?'working':'')}/><span>{jobs.length?'研究正在进行':'有调用用量待核对'}<small>{jobs.length?`${jobs.length} 项任务 · 展开查看进展`:'已保留预留额度，不会按零消耗处理'}</small></span><Icon name="chevron" size={14}/></summary><div className="wb-run-detail">{jobs.map(j=><div className="uw-progress" key={j.id}><Icon name={j.kind==='import'?'file':'spark'} size={16}/><span>{j.kind==='import'?'整理材料':j.kind==='ocr'?'识别页面':j.kind==='edit'?'准备修改建议':'阅读与研究'}<small>{j.state==='queued'?'等待执行':'正在处理，已有结果会持续保存'}</small></span><button onClick={()=>onCancel(j.id)} title="停止任务" aria-label="停止任务"><Icon name="stop" size={14}/></button></div>)}<small className="uw-muted">已知用量 {usage.used_tokens.toLocaleString()} token{usage.unknown_calls?` · ${usage.unknown_calls} 次待核对`:''}</small></div></details>;
}
export function ScopeChips({selection,materials,onClear,auto}:{selection?:{exact_quote:string};materials:string[];onClear:()=>void;auto?:boolean}){return <div className="uw-scope-banner">{selection?<button onClick={onClear}>精确选区 ×</button>:materials.length?`${materials.length} 份材料`:auto?'自动检索项目材料':'研究对话'}</div>}
