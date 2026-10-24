import {useRef,useState} from 'react';
import {SurfaceDialog} from './SurfaceDialog';
import {Icon} from './Icon';
export interface Command {id:string;title:string;group:string;icon?:string;run:()=>void}
export function CommandPalette({open,onClose,commands}:{open:boolean;onClose:()=>void;commands:Command[]}){
 const [query,setQuery]=useState('');const [selected,setSelected]=useState(0);const list=useRef<HTMLDivElement>(null);
 const filtered=commands.filter(c=>c.title.toLocaleLowerCase().includes(query.toLocaleLowerCase())).slice(0,35);
 return <SurfaceDialog open={open} onClose={onClose} title="搜索与操作"><div className="wb-command-search"><Icon name="search"/><input autoFocus aria-label="搜索会话、材料、文稿和操作" placeholder="搜索会话、材料、文稿或操作…" value={query} onChange={e=>{setQuery(e.target.value);setSelected(0);}} onKeyDown={e=>{if(e.key==='ArrowDown'||e.key==='ArrowUp'){e.preventDefault();setSelected(i=>Math.max(0,Math.min(filtered.length-1,i+(e.key==='ArrowDown'?1:-1))));}if(e.key==='Enter'&&filtered[selected]){filtered[selected].run();onClose();}}}/><kbd>ESC</kbd></div>
 <div ref={list} className="wb-command-results" role="listbox" aria-label="搜索结果">{filtered.map((c,i)=><button key={c.id} role="option" aria-selected={i===selected} onClick={()=>{c.run();onClose();}} onMouseEnter={()=>setSelected(i)}><Icon name={c.icon||'file'}/><span>{c.title}<small>{c.group}</small></span><Icon name="back" size={14}/></button>)}{!filtered.length&&<p className="wb-empty-small">没有找到匹配项，换个关键词试试。</p>}</div></SurfaceDialog>;
}
