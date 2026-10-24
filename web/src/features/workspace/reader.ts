import type {Segment} from './api/client';
export interface ReadingPart {segment:Segment;start:number;end:number;text:string}
export type ReadingPage=ReadingPart[];
/** Display windows retain code-point offsets into the immutable source segment. */
export function readingPages(segments:Segment[],limit=6000,maxParts=40):ReadingPage[]{
 const pages:ReadingPage[]=[];let page:ReadingPage=[];let length=0;
 const flush=()=>{if(page.length)pages.push(page);page=[];length=0;};
 for(const segment of segments){
  const chars=Array.from(segment.text);
  if(chars.length>limit){flush();for(let start=0;start<chars.length;start+=limit){const end=Math.min(chars.length,start+limit);pages.push([{segment,start,end,text:chars.slice(start,end).join('')}]);}continue;}
  if(length+chars.length>limit||page.length>=maxParts)flush();
  page.push({segment,start:0,end:chars.length,text:segment.text});length+=chars.length;
 }
 flush();return pages;
}
export function pageForAnchor(pages:ReadingPage[],anchor:{segment_id:string;start_codepoint:number}){
 return pages.findIndex(page=>page.some(p=>p.segment.id===anchor.segment_id&&anchor.start_codepoint>=p.start&&anchor.start_codepoint<p.end));
}
export function expandForAnchor(part:ReadingPart,anchor?:{segment_id:string;start_codepoint:number;end_codepoint:number}):ReadingPart{
 if(!anchor||anchor.segment_id!==part.segment.id||anchor.start_codepoint<part.start||anchor.start_codepoint>=part.end)return part;
 const end=Math.max(part.end,anchor.end_codepoint);
 return end===part.end?part:{...part,end,text:Array.from(part.segment.text).slice(part.start,end).join('')};
}
