import { create } from 'zustand';
interface UI {sidebarOpen:boolean;quiet:boolean;documentWidth:number;toggleSidebar:()=>void;setQuiet:(v:boolean)=>void;setDocumentWidth:(v:number)=>void}
export const useWorkspaceUI=create<UI>(set=>({sidebarOpen:window.innerWidth>850,quiet:localStorage.getItem('hermeneut_quiet')==='1',documentWidth:480,
 toggleSidebar:()=>set(s=>({sidebarOpen:!s.sidebarOpen})),setQuiet:v=>{localStorage.setItem('hermeneut_quiet',v?'1':'0');set({quiet:v});},
 setDocumentWidth:v=>set({documentWidth:Math.max(340,Math.min(900,v))})}));
