export interface TabIdentity {kind:'material'|'artifact';id:string;version?:string}
export function sameDocument(a:TabIdentity,b:TabIdentity){return a.kind===b.kind&&a.id===b.id&&(a.kind==='artifact'||(a.version||'')===(b.version||''));}
export function documentKey(tab:TabIdentity){return JSON.stringify([tab.kind,tab.id,tab.kind==='material'?(tab.version||''):'']);}
export function mergeDocumentTab<T extends TabIdentity>(tabs:T[],tab:T){const index=tabs.findIndex(t=>sameDocument(t,tab));return index<0?[...tabs,tab]:tabs.map((t,i)=>i===index?{...t,...tab}:t);}
