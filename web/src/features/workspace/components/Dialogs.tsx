import {createContext,useContext,useRef,useState,type ReactNode} from 'react';
import {Dialog} from 'radix-ui';
interface Options {title:string;initial?:string;confirmation?:boolean}
const Context=createContext<{ask:(title:string,initial?:string)=>Promise<string|null>;confirm:(title:string)=>Promise<boolean>}>(null!);
export function DialogProvider({children}:{children:ReactNode}){
 const [options,setOptions]=useState<Options>();const [value,setValue]=useState('');
 const resolver=useRef<((v:string|null)=>void)|null>(null);
 const finish=(v:string|null)=>{resolver.current?.(v);resolver.current=null;setOptions(undefined);};
 const open=(option:Options)=>new Promise<string|null>(resolve=>{resolver.current?.(null);resolver.current=resolve;setValue(option.initial||'');setOptions(option);});
 return <Context.Provider value={{ask:(title,initial)=>open({title,initial}),confirm:async title=>(await open({title,confirmation:true}))!==null}}>
 {children}<Dialog.Root open={!!options} onOpenChange={v=>{if(!v)finish(null);}}><Dialog.Portal><Dialog.Overlay className="uw-modal-overlay"/><Dialog.Content className="uw-modal">
 <span className="uw-eyebrow">HERMENEUT / 项目操作</span><Dialog.Title>{options?.title}</Dialog.Title><Dialog.Description>此操作仅用于当前项目。取消可返回研究工作台。</Dialog.Description>
 <form onSubmit={e=>{e.preventDefault();finish(options?.confirmation?'yes':value);}}>{!options?.confirmation&&<input aria-label={options?.title} autoFocus value={value} onChange={e=>setValue(e.target.value)}/>}
 <div className="uw-modal-actions"><button type="button" onClick={()=>finish(null)}>取消</button><button className="uw-primary" type="submit">确认</button></div></form>
 </Dialog.Content></Dialog.Portal></Dialog.Root></Context.Provider>;
}
export const useDialogs=()=>useContext(Context);
