import {create} from 'zustand';
import {mergeDocumentTab} from './document-tabs';
export interface DocumentTab{kind:'material'|'artifact';id:string;version?:string;title:string;readerPage?:number}
interface UI{sidebarOpen:boolean;quiet:boolean;documentWidth:number;layout:'chat'|'split'|'focus';tabs:DocumentTab[];toggleSidebar:()=>void;setQuiet:(v:boolean)=>void;setDocumentWidth:(v:number)=>void;setLayout:(v:'chat'|'split'|'focus')=>void;setTabs:(v:DocumentTab[])=>void;openTab:(v:DocumentTab)=>void}
export const useWorkspaceUI=create<UI>(set=>({sidebarOpen:window.innerWidth>=1180,quiet:localStorage.getItem('scriptorium_quiet')==='1',documentWidth:640,layout:'chat',tabs:[],
 toggleSidebar:()=>set(s=>({sidebarOpen:!s.sidebarOpen})),setQuiet:v=>{localStorage.setItem('scriptorium_quiet',v?'1':'0');set({quiet:v});},setDocumentWidth:v=>set({documentWidth:Math.max(400,Math.min(1100,v))}),setLayout:v=>set({layout:v}),setTabs:tabs=>set({tabs}),openTab:tab=>set(s=>({tabs:mergeDocumentTab(s.tabs,tab),layout:s.layout==='focus'?'focus':'split'}))}));
