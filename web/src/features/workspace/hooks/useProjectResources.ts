import {useState,useMemo,useCallback,type SetStateAction} from 'react';
import {useQuery} from '@tanstack/react-query';
import {queryClient} from '../api/query';
import {response,serviceUrl,projectPath,type Material,type ResearchRecord,type Job} from '../api/client';
import type {Conversation,Participant,Persona,Interview} from '../workspace-types';
import type {CitationDraft} from '../components/CitationReview';
import type {ResearchDecisionData} from '../components/ResearchDecision';
function useResource<T>(path:string,enabled:boolean,initial:T,personal=false){
 const [empty]=useState(()=>initial);const url=serviceUrl();const key=useMemo(()=>['api',url,path],[url,path]);
 const query=useQuery<T>({queryKey:key,queryFn:async({signal})=>{const data=await(await response(path,{signal})).json();if(personal){const previous=queryClient.getQueryData<Conversation[]>(key)||[];return data.map((c:Conversation)=>({...c,workspace:previous.find(x=>x.id===c.id)?.workspace||c.workspace}));}return data;},enabled});
 const set=useCallback((value:SetStateAction<T>)=>queryClient.setQueryData<T>(key,old=>typeof value==='function'?(value as(current:T)=>T)(old??empty):value),[key,empty]);
 return {data:query.data??empty,set};
}
export async function refreshProject(pid:string){const prefix=['api',serviceUrl()];await queryClient.invalidateQueries({predicate:q=>q.queryKey[0]===prefix[0]&&q.queryKey[1]===prefix[1]&&String(q.queryKey[2]).startsWith(projectPath(pid)+'/')});}
export function useProjectResources(pid:string,authenticated:boolean){
 const root=projectPath(pid),enabled=!!pid&&authenticated;
 const conversations=useResource<Conversation[]>(root+'/conversations',enabled,[],true);
 const materials=useResource<Material[]>(root+'/materials',enabled,[]);
 const records=useResource<ResearchRecord[]>(root+'/records?summary=true',enabled,[]);
 const jobs=useResource<Job[]>(root+'/jobs?summary=true',enabled,[]);
 const decisions=useResource<ResearchDecisionData[]>(root+'/decisions',enabled,[]);
 const people=useResource<Participant[]>(root+'/participants',enabled,[]);
 const personas=useResource<Persona[]>(root+'/personas',enabled,[]);
 const interviews=useResource<Interview[]>(root+'/interviews',enabled,[]);
 const analyses=useResource<{id:string;state:string}[]>(root+'/analysis-runs',enabled,[]);
 const citations=useResource<CitationDraft[]>(root+'/citation-drafts',enabled,[]);
 const calls=useResource<{totals:{used_tokens:number;unknown_calls:number}}>(root+'/model-calls?summary=true',enabled,{totals:{used_tokens:0,unknown_calls:0}});
 return {conversations:conversations.data,setConversations:conversations.set,materials:materials.data,setMaterials:materials.set,artifacts:records.data,setArtifacts:records.set,jobs:jobs.data,setJobs:jobs.set,decisions:decisions.data,setDecisions:decisions.set,people:people.data,personas:personas.data,interviews:interviews.data,oldAnalyses:analyses.data,citationDrafts:citations.data,setCitationDrafts:citations.set,usage:calls.data.totals,setUsage:(totals:typeof calls.data.totals)=>calls.set({totals})};
}
