import {endpoint} from './client';
import type {Schemas} from './generated';
const project=(root:string)=>decodeURIComponent(root.split('/').pop()!);
export const artifactApi={
 chapters:(root:string,id:string)=>endpoint('GET /api/v2/projects/{project_id}/artifacts/{record_id}/chapters',{project_id:project(root),record_id:id}),
 chapter:(root:string,id:string,chapter:string,body:Schemas['ChapterIn'])=>endpoint('PUT /api/v2/projects/{project_id}/artifacts/{record_id}/chapters/{chapter_id}',{project_id:project(root),record_id:id,chapter_id:chapter},body),
 suggest:(root:string,id:string,body:Schemas['ProposalIn'],key:string)=>endpoint('POST /api/v2/projects/{project_id}/artifacts/{rid}/change-proposals',{project_id:project(root),rid:id},body,{headers:{'Idempotency-Key':key}}),
 export:(root:string,id:string,body:Schemas['ExportIn'],key:string)=>endpoint('POST /api/v2/projects/{project_id}/artifacts/{rid}/exports',{project_id:project(root),rid:id},body,{headers:{'Idempotency-Key':key}}),
 proposals:(root:string,id:string)=>endpoint('GET /api/v2/projects/{project_id}/artifacts/{rid}/change-proposals',{project_id:project(root),rid:id}),
};
