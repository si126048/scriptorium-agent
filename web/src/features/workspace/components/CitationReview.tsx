import {useState} from 'react';
export interface CitationDraft {conversation_id?:string;id:string;job_id:string;revision:number;payload:{error:string;result?:{findings?:{citations?:{segment_id:string;exact_quote:string}[]}[];immanent?:{citations?:{segment_id:string;exact_quote:string}[]};parallax?:{citations?:{segment_id:string;exact_quote:string}[]}}}}
export function CitationReview({draft,onBind,onDiscard}:{draft:CitationDraft;onBind:(index:number)=>void;onDiscard:()=>void}){
 const [index,setIndex]=useState(0);const r=draft.payload.result;
 const citations=[...(r?.findings||[]).flatMap(f=>f.citations||[]),...(r?.immanent?.citations||[]),...(r?.parallax?.citations||[])];
 return <section className="uw-decision"><span className="uw-eyebrow">证据核验</span><h3>引文需要确认</h3>
 <p>{draft.payload.error==='CITATION_AMBIGUOUS'?'原文中存在重复摘录，请选中正确位置后重新绑定。':'模型引文未能精确匹配原文。你可以逐项绑定正确选区；全部通过后才继续研究。'}</p>
 {citations.length>0&&<label>核验摘录<select aria-label="核验摘录" value={index} onChange={e=>setIndex(Number(e.target.value))}>{citations.map((q,i)=><option key={i} value={i}>{i+1}. {q.exact_quote}</option>)}</select></label>}
 <div className="uw-inline-actions"><button disabled={!citations.length} onClick={()=>onBind(index)}>用当前选区绑定</button><button onClick={onDiscard}>不采用这项解释</button></div></section>;
}
