import {useQuery,useInfiniteQuery} from '@tanstack/react-query';
import {response,serviceUrl,projectPath} from '../api/client';
import type {Schemas} from '../api/generated';
export type ResearchSource=Schemas['SourceOut'];
export type Intake=Schemas['IntakeOut'];
export function useSources(pid:string,cid:string,online:boolean){
 const root=projectPath(pid),enabled=!!pid;
 const sources=useSourcePages(root,cid,online);
 const path=root+'/intakes'+(cid?'?conversation_id='+encodeURIComponent(cid):'');
 const intakes=useQuery({queryKey:['api',serviceUrl(),path],queryFn:async({signal})=>(await response(path,{signal})).json() as Promise<Intake[]>,enabled:enabled&&!!cid,refetchInterval:online?false:10000});
 return {sources:sources.items,sourceTotal:sources.total,intakes:intakes.data||[]};
}

export function useSourcePages(root:string,cid:string,online:boolean,filters:Record<string,string|boolean|undefined>={}){
 const query=new URLSearchParams();if(cid)query.set('conversation_id',cid);for(const[k,v]of Object.entries(filters))if(v!==undefined&&v!=='')query.set(k,String(v));
 const path=root+'/sources'+(query.size?'?'+query:'');
 const data=useInfiniteQuery({queryKey:['api',serviceUrl(),path],initialPageParam:0,queryFn:async({signal,pageParam})=>(await response(path+(path.includes('?')?'&':'?')+'offset='+pageParam,{signal})).json() as Promise<Schemas['SourcePageOut']>,getNextPageParam:page=>page.next_offset??undefined,enabled:!root.endsWith('/'),refetchInterval:online?false:10000});
 return {items:data.data?.pages.flatMap(p=>p.items)||[],total:data.data?.pages[0]?.total||0,hasMore:data.hasNextPage,loadMore:()=>void data.fetchNextPage(),loading:data.isFetching};
}
