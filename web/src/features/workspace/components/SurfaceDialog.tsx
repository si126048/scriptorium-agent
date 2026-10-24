import {Dialog} from 'radix-ui';
import {useRef,type ReactNode} from 'react';
import {Icon} from './Icon';
export function SurfaceDialog({open,onClose,title,description,children,wide=false}:{open:boolean;onClose:()=>void;title:string;description?:string;children:ReactNode;wide?:boolean}){
 const returnTo=useRef<HTMLElement|null>(null);
 return <Dialog.Root open={open} onOpenChange={v=>{if(!v)onClose();}}><Dialog.Portal><Dialog.Overlay className="wb-overlay"/><Dialog.Content className={'wb-dialog '+(wide?'wb-dialog-wide':'')} aria-describedby={description?'wb-dialog-description':undefined} onOpenAutoFocus={()=>{returnTo.current=document.activeElement instanceof HTMLElement?document.activeElement:null;}} onCloseAutoFocus={event=>{event.preventDefault();const target=returnTo.current;if(target?.isConnected)target.focus();}}> 
 <header><div><Dialog.Title>{title}</Dialog.Title>{description&&<Dialog.Description id="wb-dialog-description">{description}</Dialog.Description>}</div><Dialog.Close asChild><button className="wb-icon" aria-label="关闭"><Icon name="close"/></button></Dialog.Close></header><div className="wb-dialog-body">{children}</div></Dialog.Content></Dialog.Portal></Dialog.Root>;
}
