import {useEffect,useRef} from 'react';
import {projectPath,response} from '../api/client';
import type {TimelineBlock,TimelineUpdate} from '../timeline';
export interface ConversationEvent{sequence?:number;type:string;payload:{job_id:string;text:string;state?:string;blocks?:TimelineBlock[];block?:TimelineBlock;delta?:TimelineUpdate['delta'];replace?:boolean;message?:{id:string;role:string;content:string;artifact_ids:string[];metadata:{job_id?:string;provider_mode?:string}}}}
export function useConversationEvents(pid:string,cid:string,onUpdate:(event?:ConversationEvent)=>void,onEvent?:(event:ConversationEvent)=>void,onConnection?:(online:boolean)=>void){
 const handler=useRef(onUpdate),eventHandler=useRef(onEvent),connection=useRef(onConnection);
 useEffect(()=>{handler.current=onUpdate;eventHandler.current=onEvent;connection.current=onConnection;});
 useEffect(()=>{
  if(!pid||!cid)return;
  const controller=new AbortController();let cursor=0;let timer:ReturnType<typeof setTimeout>|undefined;let queue:ConversationEvent[]=[];
  const flush=()=>{timer=undefined;if(controller.signal.aborted)return;const pending=queue;queue=[];for(const event of pending){eventHandler.current?.(event);if(!['timeline.block','message.delta'].includes(event.type))handler.current(event);}};
  const deliver=(event:ConversationEvent)=>{queue.push(event);timer??=setTimeout(flush,100);};
  const denied=(error:unknown)=>/^(401|403|404)/.test(String(error).replace(/^Error: /,''));
  const snapshot=async()=>{const r=await response(`${projectPath(pid)}/conversations/${cid}/snapshot`,{signal:controller.signal});const value=await r.json();if(controller.signal.aborted)return;queue=[];cursor=value.cursor;deliver({type:'timeline.snapshot',payload:{job_id:'',text:'',blocks:value.blocks||[]}});for(const[job_id,text]of Object.entries(value.drafts||{}))deliver({type:'message.delta',payload:{job_id,text:String(text),replace:true}});};
  const run=async()=>{
   connection.current?.(false);
   while(!controller.signal.aborted){
    const stream=new AbortController();let watchdog:ReturnType<typeof setTimeout>|undefined;
    const pulse=()=>{if(watchdog)clearTimeout(watchdog);watchdog=setTimeout(()=>stream.abort(),45000);};
    try{
     await snapshot();if(controller.signal.aborted)return;
     const r=await response(`${projectPath(pid)}/conversations/${cid}/events?after=${cursor}`,{signal:AbortSignal.any([controller.signal,stream.signal])},true);
     connection.current?.(true);handler.current();pulse();const reader=r.body!.getReader();const decoder=new TextDecoder();let buffer='';
     while(!controller.signal.aborted){const chunk=await reader.read();if(chunk.done)break;pulse();buffer+=decoder.decode(chunk.value,{stream:true}).replace(/\r\n/g,'\n');let boundary:number;
      while((boundary=buffer.indexOf('\n\n'))>=0){const frame=buffer.slice(0,boundary);buffer=buffer.slice(boundary+2);const data=frame.split('\n').filter(l=>l.startsWith('data:')).map(l=>l.slice(5).trimStart()).join('\n');if(!data)continue;const event=JSON.parse(data) as ConversationEvent;if(!event.sequence||event.sequence<=cursor)continue;if(event.sequence!==cursor+1){await snapshot();if(event.sequence<=cursor)continue;throw new Error('EVENT_GAP');}cursor=event.sequence;deliver(event);}
     }
    }catch(error){if(controller.signal.aborted)return;if(denied(error)){eventHandler.current?.({type:'access.denied',payload:{job_id:'',text:''}});return;}}
    finally{if(watchdog)clearTimeout(watchdog);stream.abort();}
    if(controller.signal.aborted)return;connection.current?.(false);
    await new Promise<void>(resolve=>{const finish=()=>{clearTimeout(retry);controller.signal.removeEventListener('abort',finish);resolve();};const retry=setTimeout(finish,2000);controller.signal.addEventListener('abort',finish,{once:true});});
   }
  };void run();return()=>{controller.abort();if(timer)clearTimeout(timer);};
 },[pid,cid]);
}
