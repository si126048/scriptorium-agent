export interface TimelineBlock {id:string;job_id:string;project_id:string;conversation_id:string;block_key:string;kind:string;state:string;generation:number;revision:number;payload:{text?:string;title?:string;detail?:string;items?:string[];current_index?:number;artifact_ids?:string[];evidence_ids?:string[];result?:{state?:string;run_id?:string};reason?:string;offset?:number};created_at:number;updated_at:number}
export interface TimelineUpdate {block:TimelineBlock;delta?:{offset:number;text:string}}
export function mergeBlock(blocks:TimelineBlock[],update:TimelineUpdate):TimelineBlock[]{
 const incoming=update.block;const generation=blocks.find(b=>b.job_id===incoming.job_id&&b.kind==='turn')?.generation||0;if(incoming.generation<generation)return blocks;const old=blocks.find(b=>b.id===incoming.id);
 if(old&&(incoming.generation<old.generation||(incoming.generation===old.generation&&incoming.revision<=old.revision)))return blocks;
 let next=incoming;
 if(update.delta){const text=old?.payload.text||'';if(Array.from(text).length!==update.delta.offset)throw new Error('TIMELINE_GAP');next={...incoming,payload:{...incoming.payload,text:text+update.delta.text}};}
 return old?blocks.map(b=>b.id===next.id?next:b):[...blocks,next];
}

export function markdownBlocks(text:string):string[]{
 if(text.includes('[^'))return [text];
 const blocks:string[]=[];let current:string[]=[];let fence='';let math=false;
 for(const line of text.split('\n')){
  const marker=line.match(/^\s*(`{3,}|~{3,})/);
  if(marker){if(!fence)fence=marker[1];else if(marker[1][0]===fence[0]&&marker[1].length>=fence.length)fence='';}
  if(line.trim()==='$$')math=!math;
  if(!line.trim()&&!fence&&!math){if(current.length){blocks.push(current.join('\n'));current=[];}}else current.push(line);
 }
 if(current.length)blocks.push(current.join('\n'));
 return blocks;
}
