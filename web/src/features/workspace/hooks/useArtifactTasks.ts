import {useQuery} from '@tanstack/react-query';
import {response,serviceUrl} from '../api/client';
export interface ArtifactTask{id:string;record_id?:string|null;kind:string;state:string;error?:string;result?:{record_id?:string;revision?:number;created_at?:number;format?:string;filename?:string};conversation_id?:string|null}
/** Server owns task completion; the view can close and reopen without losing the task. */
export function useArtifactTasks(root:string,online:boolean,cid:string){
 return useQuery({queryKey:['api',serviceUrl(),root+'/tasks'],queryFn:async({signal})=>(await response(root+'/tasks',{signal})).json() as Promise<ArtifactTask[]>,refetchInterval:query=>query.state.data?.some(t=>['queued','running','cancel_requested'].includes(t.state)&&(!online||t.conversation_id!==cid))?2000:false});
}
