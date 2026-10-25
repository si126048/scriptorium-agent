import {useQuery} from '@tanstack/react-query';
import {response,serviceUrl} from '../api/client';
export function useCitationLabels(root:string,ids:string[]){
 const unique=[...new Set(ids)].filter(Boolean).sort().slice(0,200);const path=root+'/citation-labels?ids='+encodeURIComponent(unique.join(','));
 const query=useQuery<{anchor_id:string;label:string;version_id:string}[]>({queryKey:['api',serviceUrl(),path],queryFn:async({signal})=>(await response(path,{signal})).json(),enabled:!!root&&!!unique.length,staleTime:60000});
 return Object.fromEntries((query.data||[]).map(item=>[item.anchor_id,item.label]));
}
export function editorCitations(node:unknown):string[]{if(!node||typeof node!=='object')return [];const n=node as{type?:string;attrs?:{anchorId?:string};content?:unknown[]};return [...(n.type==='citation'&&n.attrs?.anchorId?[n.attrs.anchorId]:[]),...(n.content||[]).flatMap(editorCitations)];}
