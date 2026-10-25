import {endpoint,type Anchor,type Segment,type Version} from './client';
import type {ReadingPart} from '../reader';
export interface ReadingView{version:Version;page:number;total:number;parts:ReadingPart[];total_segments:number;total_codepoints:number}
export function readWindow(root:string,aid:string,version:string,page:number,signal:AbortSignal,anchor?:Pick<Anchor,'segment_id'|'start_codepoint'|'end_codepoint'>){
 const query=new URLSearchParams({page:String(page)});if(version)query.set('version_id',version);if(anchor){query.set('segment_id',anchor.segment_id);query.set('start',String(anchor.start_codepoint));query.set('end',String(anchor.end_codepoint));}
 return endpoint('GET /api/v2/projects/{project_id}/materials/{aid}/reading',{project_id:decodeURIComponent(root.split('/').pop()!),aid},undefined,{signal,query:Object.fromEntries(query)}) as Promise<ReadingView>;
}
export function windowSegments(view:ReadingView):Segment[]{return view.parts.map(p=>p.segment);}
