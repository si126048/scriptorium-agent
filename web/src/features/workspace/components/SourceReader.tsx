import {useMemo,useRef,useLayoutEffect,useState,type ReactNode} from 'react';
import type {Anchor,Segment} from '../api/client';
import {readingPages,expandForAnchor} from '../reader';
import {Icon} from './Icon';
export function SourceReader({segments,selection,page,onPage,onCapture,onDismiss,selectionTools}:{segments:Segment[];selection?:Omit<Anchor,'id'>;page:number;onPage:(page:number)=>void;onCapture:()=>void;onDismiss:()=>void;selectionTools:ReactNode}){
 const pages=useMemo(()=>readingPages(segments),[segments]);const current=Math.max(0,Math.min(page,pages.length-1));const source=useRef<HTMLDivElement>(null);
 const [position,setPosition]=useState<{top:number;left:number;width:number}|null>(null);
 useLayoutEffect(()=>{
  let frame=0;
  const measure=()=>{const mark=source.current?.querySelector('mark');const pane=source.current?.closest('.uw-document-pane');if(!mark||!pane){setPosition(null);return;}const rect=mark.getBoundingClientRect();const bounds=pane.getBoundingClientRect();if(rect.bottom<90||rect.top>window.innerHeight-20){setPosition(null);return;}const width=Math.min(420,bounds.width-32);const left=Math.max(bounds.left+16,Math.min(rect.left,bounds.right-width-16));const top=rect.bottom+300<window.innerHeight?rect.bottom+8:Math.max(90,rect.top-300);setPosition(old=>old&&old.top===top&&old.left===left&&old.width===width?old:{top,left,width});};
  const schedule=()=>{cancelAnimationFrame(frame);frame=requestAnimationFrame(measure);};
  const observer=new ResizeObserver(schedule);const pane=source.current?.closest('.uw-document-pane');if(pane)observer.observe(pane);measure();document.addEventListener('scroll',schedule,true);window.addEventListener('resize',schedule);
  return()=>{observer.disconnect();cancelAnimationFrame(frame);document.removeEventListener('scroll',schedule,true);window.removeEventListener('resize',schedule);};
 },[selection,page,segments]);
 const navigate=(value:number)=>{onPage(value);source.current?.scrollIntoView({block:'start'});};
 if(!pages.length)return <div className="wb-reader-empty">暂无可阅读的文本。材料处理完成后可以在这里阅读。</div>;
 const controls=pages.length>1&&<nav className="wb-reader-pages" aria-label="原文阅读分页"><button disabled={current===0} onClick={()=>navigate(current-1)} aria-label="上一阅读页"><Icon name="back" size={14}/></button><label>阅读页<input type="number" aria-label="跳至阅读页" min={1} max={pages.length} value={current+1} onChange={e=>{const next=Number(e.target.value);if(Number.isInteger(next)&&next>=1&&next<=pages.length)navigate(next-1);}}/><span>/ {pages.length}</span></label><button disabled={current===pages.length-1} onClick={()=>navigate(current+1)} aria-label="下一阅读页"><Icon name="chevron" size={14}/></button><small>连续原文分页 · 引用保留原位置</small></nav>;
 return <div ref={source} className="wb-source-reader">{controls}<div className="uw-source" onMouseUp={onCapture}>{pages[current].map(original=>{
 const part=expandForAnchor(original,selection);const active=selection?.segment_id===part.segment.id&&selection.start_codepoint>=part.start&&selection.start_codepoint<part.end;const chars=active?Array.from(part.text):[];
 return <section id={'uw-segment-'+part.segment.id} key={part.segment.id+':'+part.start}><small>原书页 {part.segment.page_label||'—'}{part.start>0?' · 段落续页':''}</small><p data-source={part.segment.id} data-source-offset={part.start}>{active&&selection?<>{chars.slice(0,selection.start_codepoint-part.start).join('')}<mark>{chars.slice(selection.start_codepoint-part.start,selection.end_codepoint-part.start).join('')}</mark>{chars.slice(selection.end_codepoint-part.start).join('')}</>:part.text}</p></section>;
 })}</div>{position&&selection&&<aside className="wb-floating-selection" role="region" aria-label="原文选区操作" style={position}><button className="wb-icon wb-selection-close" aria-label="关闭选区工具" onClick={onDismiss}><Icon name="close" size={14}/></button>{selectionTools}</aside>}{controls}</div>;
}
