import {useQuery} from '@tanstack/react-query';
import {request,type ResearchRecord} from '../api/client';
export default function ReportGraph({root,kind,records,onOpen}:{root:string;kind:'research'|'concept';records:ResearchRecord[];onOpen:(id:string)=>void}){
 const query=useQuery({queryKey:['graph',root,kind],queryFn:()=>request<{edges:{from:string;to:string;type:string}[]}>(`${root}/graph/${kind}`)});
 if(query.isPending)return <p>正在整理关系…</p>;
 if(query.isError)return <p role="alert">关系暂时无法读取。</p>;
 const edges=query.data.edges;const ids=[...new Set(edges.flatMap(e=>[e.from,e.to]))];
 if(!ids.length)return <p className="uw-muted">尚未形成有材料依据的{kind==='research'?'研究':'概念演化'}关系。</p>;
 const visible=ids.slice(0,60);const width=640;const height=Math.max(260,Math.ceil(visible.length/3)*110);
 const position=(id:string)=>{const i=visible.indexOf(id);return {x:110+(i%3)*205,y:50+Math.floor(i/3)*110};};
 return <div className="uw-report-graph"><small>{kind==='research'?'研究论点与回应':'概念转化'} · {ids.length} 个对象</small><svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={kind==='research'?'研究关系图':'概念演化图'}>
 <defs><marker id={'arrow-'+kind} markerWidth="7" markerHeight="7" refX="6" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6" fill="#a9845c"/></marker></defs>
 {edges.filter(e=>visible.includes(e.from)&&visible.includes(e.to)).map((e,i)=>{const a=position(e.from),b=position(e.to);return <line key={i} x1={a.x} y1={a.y+16} x2={b.x} y2={b.y-16} stroke="#b7a184" markerEnd={`url(#arrow-${kind})`}/>;})}
 {visible.map(id=>{const p=position(id);const title=records.find(r=>r.id===id)?.payload.title || '研究对象';return <g key={id} tabIndex={0} role="button" aria-label={title} onClick={()=>onOpen(id)} onKeyDown={e=>{if(e.key==='Enter')onOpen(id);}}><title>{title}</title><rect x={p.x-88} y={p.y-17} width="176" height="35" rx="6" fill="#fbf5e8" stroke="#cab99d"/><text x={p.x} y={p.y+5} textAnchor="middle" fill="#4b493d" fontSize="12">{title.slice(0,13)}</text></g>;})}</svg>{ids.length>60&&<p>当前展示前 60 个对象；完整关系保留在项目档案中。</p>}</div>;
}
