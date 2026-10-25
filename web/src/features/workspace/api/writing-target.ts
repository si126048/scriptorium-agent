import {request,type ResearchRecord,type Payload} from './client';
export interface WritingTarget{project:string;record:string;chapter?:string}
export async function insertResearch(root:string,target:WritingTarget,source:ResearchRecord){
 const record=await request<ResearchRecord>(`${root}/artifacts/${target.record}`);
 const chapters=target.chapter?await request<{id:string;revision:number;ordinal:number;payload:Payload}[]>(`${root}/artifacts/${target.record}/chapters`):[];
 const chapter=chapters.find(c=>c.id===target.chapter);if(target.chapter&&!chapter)throw new Error('目标章节已不存在，请重新选择写作位置。');
 const payload=chapter?.payload||record.payload;
 const editor=(payload.editor_json||{type:'doc',content:payload.text?[{type:'rawBlock',attrs:{source:payload.text}}]:[]}) as{type:string;content:unknown[]};
 const content=[...(editor.content||[]),{type:'paragraph',content:[{type:'text',text:source.payload.text||source.payload.title||''},...(source.payload.evidence_ids||[]).map(id=>({type:'citation',attrs:{anchorId:id}}))]}];
 const next={...payload,editor_json:{type:'doc',content},evidence_ids:[...new Set([...(payload.evidence_ids||[]),...(source.payload.evidence_ids||[])])],source_record_ids:[...new Set([...(payload.source_record_ids||[]),source.id])]};
 if(chapter)await request(`${root}/artifacts/${target.record}/chapters/${chapter.id}`,{method:'PUT',body:JSON.stringify({revision:chapter.revision,ordinal:chapter.ordinal,payload:next})});
 else await request(`${root}/records/${target.record}`,{method:'PUT',body:JSON.stringify({kind:record.kind,revision:record.revision,payload:next})});
 return record.id;
}
