import {useEffect,useRef} from 'react';
import {projectPath,response} from '../api/client';
import {queryClient} from '../api/query';
interface Event {type:string;payload:{job_id:string;text:string;state?:string;message?:{metadata?:{job_id?:string}}}}
export function useConversationEvents(pid:string,cid:string,onUpdate:()=>void,onEvent?:(event:Event)=>void){
 const handler=useRef(onUpdate);
 const eventHandler=useRef(onEvent);
 useEffect(()=>{handler.current=onUpdate;},[onUpdate]);
 useEffect(()=>{eventHandler.current=onEvent;},[onEvent]);
 useEffect(()=>{
 if(!pid||!cid)return;
 const controller=new AbortController();let cursor=0;let refresh:ReturnType<typeof setTimeout>|undefined;
 const root=projectPath(pid);
 const notify=()=>{if(refresh)return;refresh=setTimeout(()=>{refresh=undefined;void queryClient.invalidateQueries({predicate:q=>String(q.queryKey[2]||'').includes(root)}).then(()=>{if(!controller.signal.aborted)handler.current();});},180);};
 const run=async()=>{
 try{const snapshot=await response(`${root}/conversations/${cid}/snapshot`,{signal:controller.signal});const state=await snapshot.json();cursor=state.cursor;for(const [job_id,text] of Object.entries(state.drafts||{}))eventHandler.current?.({type:'message.delta',payload:{job_id,text:String(text)}});}catch{if(controller.signal.aborted)return;}
 while(!controller.signal.aborted){
 try{const r=await response(`${root}/conversations/${cid}/events?after=${cursor}`,{signal:controller.signal});const reader=r.body!.getReader();const decoder=new TextDecoder();let buffer='';
 while(!controller.signal.aborted){const chunk=await reader.read();if(controller.signal.aborted)return;if(chunk.done)break;buffer+=decoder.decode(chunk.value,{stream:true});let boundary:number;
 while((boundary=buffer.indexOf('\n\n'))>=0){const frame=buffer.slice(0,boundary);buffer=buffer.slice(boundary+2);const data=frame.split('\n').find(l=>l.startsWith('data: '));if(!data)continue;
 const event=JSON.parse(data.slice(6));if(event.sequence<=cursor)continue;cursor=event.sequence;eventHandler.current?.(event);if(event.type!=='message.delta')notify();}}
 }catch{if(controller.signal.aborted)return;}
 await new Promise<void>(resolve=>{const done=()=>{clearTimeout(timeout);controller.signal.removeEventListener('abort',done);resolve();};const timeout=setTimeout(done,2000);controller.signal.addEventListener('abort',done,{once:true});});
 }};void run();return()=>{controller.abort();if(refresh)clearTimeout(refresh);};
 },[pid,cid]);
}
