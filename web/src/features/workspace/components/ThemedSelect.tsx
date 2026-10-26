import {Children,isValidElement,type ReactNode,type SelectHTMLAttributes,type ChangeEvent} from 'react';
import {Select} from 'radix-ui';
import {Icon} from './Icon';
export function ThemedSelect({children,value,onChange,disabled,className,...props}:SelectHTMLAttributes<HTMLSelectElement>){
 const options:{value:string;label:ReactNode;disabled?:boolean}[]=[];
 const collect=(nodes:ReactNode)=>Children.forEach(nodes,node=>{if(!isValidElement<{value?:string;children?:ReactNode;disabled?:boolean}>(node))return;if(node.type==='option')options.push({value:String(node.props.value??''),label:node.props.children,disabled:node.props.disabled});else collect(node.props.children);});collect(children);
 return <Select.Root value={String(value??'')||'__empty__'} onValueChange={v=>onChange?.({target:{value:v==='__empty__'?'':v}} as ChangeEvent<HTMLSelectElement>)} disabled={disabled}><Select.Trigger className={'wb-select-trigger '+(className||'')} aria-label={props['aria-label']} id={props.id}><Select.Value/><Select.Icon><Icon name="down" size={14}/></Select.Icon></Select.Trigger><Select.Portal><Select.Content className="wb-select-content" position="popper" sideOffset={5}><Select.Viewport>{options.map((option,i)=><Select.Item className="wb-select-item" key={option.value+':'+i} value={option.value||'__empty__'} disabled={option.disabled}><Select.ItemText>{option.label}</Select.ItemText><Select.ItemIndicator><Icon name="check" size={14}/></Select.ItemIndicator></Select.Item>)}</Select.Viewport></Select.Content></Select.Portal></Select.Root>;
}
