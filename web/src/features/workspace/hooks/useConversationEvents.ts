import {useEffect,useRef} from 'react';
import {projectPath,response} from '../api/client';
export interface ConversationEvent{sequence?:number;type:string;payload:{job_id:string;text:string;state?:string;message?:{id:string;role:string;content:string;artifact_ids:string[];metadata:{job_id?:string;provider_mode?:string}}}}
export function useConversationEvents(pid:string,cid:string,onUpdate:(event?:ConversationEvent)=>void,onEvent?:(event:ConversationEvent)=>void,onConnection?:(online:boolean)=>void){
 const handler=useRef(onUpdate),eventHandler=useRef(onEvent),connection=useRef(onConnection);
 useEffect(()=>{handler.current=onUpdate;eventHandler.current=onEvent;connection.current=onConnection;});
 useEffect(()=>{
  if(!pid||!cid)return;
  const controller=new AbortController();let cursor=0;let refresh:ReturnType<typeof setTimeout>|undefined;let pending:ConversationEvent|undefined;
  const notify=(event?:ConversationEvent)=>{pending=event;if(refresh)return;refresh=setTimeout(()=>{refresh=undefined;if(!controller.signal.aborted)handler.current(pending);},180);};
  const root=projectPath(pid);connection.current?.(false);
  const run=async()=>{
   try{const r=await response(`${root}/conversations/${cid}/snapshot`,{signal:controller.signal});const snapshot=await r.json();if(controller.signal.aborted)return;cursor=snapshot.cursor;for(const [job_id,text]of Object.entries(snapshot.drafts||{}))eventHandler.current?.({type:'message.delta',payload:{job_id,text:String(text)}});}catch(error){if(controller.signal.aborted)return;if(/^(401|403|404)/.test(String(error).replace(/^Error: /,''))){eventHandler.current?.({type:'access.denied',payload:{job_id:'',text:''}});return;}}
   while(!controller.signal.aborted){
    const stream=new AbortController();let watchdog:ReturnType<typeof setTimeout>|undefined;
    const pulse=()=>{if(watchdog)clearTimeout(watchdog);watchdog=setTimeout(()=>stream.abort(),45000);};
    try{const r=await response(`${root}/conversations/${cid}/events?after=${cursor}`,{signal:AbortSignal.any([controller.signal,stream.signal])},true);if(controller.signal.aborted)return;connection.current?.(true);notify();pulse();const reader=r.body!.getReader();const decoder=new TextDecoder();let buffer='';
     while(!controller.signal.aborted){const chunk=await reader.read();if(controller.signal.aborted)return;if(chunk.done)break;pulse();buffer+=decoder.decode(chunk.value,{stream:true});let boundary:number;
      while((boundary=buffer.indexOf('\n\n'))>=0){const frame=buffer.slice(0,boundary);buffer=buffer.slice(boundary+2);const data=frame.split('\n').find(l=>l.startsWith('data: '));if(!data)continue;const event=JSON.parse(data.slice(6));if(event.sequence<=cursor)continue;cursor=event.sequence;eventHandler.current?.(event);if(event.type!=='message.delta')notify(event);}
     }
    }catch(error){if(controller.signal.aborted)return;if(/^(401|403|404)/.test(String(error).replace(/^Error: /,''))){eventHandler.current?.({type:'access.denied',payload:{job_id:'',text:''}});return;}}finally{if(watchdog)clearTimeout(watchdog);stream.abort();}
    if(controller.signal.aborted)return;connection.current?.(false);
    await new Promise<void>(resolve=>{const finish=()=>{clearTimeout(timer);controller.signal.removeEventListener('abort',finish);resolve();};const timer=setTimeout(finish,2000);controller.signal.addEventListener('abort',finish,{once:true});});
   }
  };void run();return()=>{controller.abort();if(refresh)clearTimeout(refresh);};
 },[pid,cid]);
}
