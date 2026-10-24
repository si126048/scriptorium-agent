import {useEffect,useRef} from 'react';
import {EditorContent,useEditor} from '@tiptap/react';
import StarterKit from '@tiptap/starter-kit';
import {Node,mergeAttributes,type JSONContent} from '@tiptap/core';
import {useDialogs} from './dialog-context';
import Placeholder from '@tiptap/extension-placeholder';
const Citation=Node.create({name:'citation',group:'inline',inline:true,atom:true,
 addAttributes:()=>({anchorId:{default:''}}),parseHTML:()=>[{tag:'span[data-citation]'}],
 renderHTML:({HTMLAttributes})=>['span',mergeAttributes(HTMLAttributes,{'data-citation':HTMLAttributes.anchorId,'class':'uw-inline-citation',role:'button',tabindex:0}),'原文↗']});
const Footnote=Node.create({name:'footnote',group:'inline',inline:true,atom:true,
 addAttributes:()=>({text:{default:''}}),parseHTML:()=>[{tag:'span[data-footnote]'}],
 renderHTML:({HTMLAttributes})=>['span',mergeAttributes(HTMLAttributes,{'data-footnote':'',class:'uw-footnote-node',title:HTMLAttributes.text,role:'button',tabindex:0,'aria-label':'编辑脚注：'+HTMLAttributes.text}),'[注]']});
const Raw=Node.create({name:'rawBlock',group:'block',atom:true,addAttributes:()=>({source:{default:''}}),
 parseHTML:()=>[{tag:'pre[data-original]'}],renderHTML:({HTMLAttributes})=>['pre',{'data-original':'',class:'uw-original-block'},HTMLAttributes.source]});
function fromSource(source:string):JSONContent{
 return {type:'doc',content:source.split(/\n\s*\n/).filter(Boolean).map(block=>{
 if(/^#{1,6} /.test(block)){const m=block.match(/^(#{1,6}) (.*)$/s)!;return {type:'heading',attrs:{level:m[1].length},content:[{type:'text',text:m[2]}]};}
 if(/(\[|\]|`|\*|<|>)|^[-|>]/m.test(block))return {type:'rawBlock',attrs:{source:block}};
 return {type:'paragraph',content:[{type:'text',text:block}]};})};
}
export function ManuscriptEditor({value,source,onChange,evidenceIds,onLocate,recordId}:{value?:Record<string,unknown>;source:string;recordId:string;evidenceIds:string[];onChange:(v:Record<string,unknown>,text:string)=>void;onLocate:(id:string)=>void}){
 const {ask}=useDialogs();
 const handler=useRef(onChange);
 useEffect(()=>{handler.current=onChange;},[onChange]);
 const editor=useEditor({extensions:[StarterKit,Citation,Footnote,Raw,Placeholder.configure({placeholder:'从材料和论点开始写作…'})],
 content:(value || fromSource(source)) as JSONContent,editorProps:{attributes:{class:'uw-prose-editor','aria-label':'文稿可视化编辑器'},
 handleKeyDown:(view,event)=>{const footnote=(event.target as HTMLElement).closest('[data-footnote]');if(footnote&&(event.key==='Enter'||event.key===' ')){event.preventDefault();const position=view.posAtDOM(footnote,0);const node=view.state.doc.nodeAt(position);if(node?.type.name==='footnote')void ask('编辑脚注',node.attrs.text).then(text=>{if(text!==null)view.dispatch(view.state.tr.setNodeMarkup(position,undefined,{text}));});return true;}const id=(event.target as HTMLElement).closest('[data-citation]')?.getAttribute('data-citation');if(id&&(event.key==='Enter'||event.key===' ')){event.preventDefault();onLocate(id);return true;}return false;},
 handleClick:(view,_pos,event)=>{const footnote=(event.target as HTMLElement).closest('[data-footnote]');if(footnote){const position=view.posAtDOM(footnote,0);const node=view.state.doc.nodeAt(position);if(node?.type.name==='footnote')void ask('编辑脚注',node.attrs.text).then(text=>{if(text!==null)view.dispatch(view.state.tr.setNodeMarkup(position,undefined,{text}));});return true;}const id=(event.target as HTMLElement).closest('[data-citation]')?.getAttribute('data-citation');if(id){onLocate(id);return true;}return false;}},
 onUpdate:({editor})=>handler.current(editor.getJSON(),editor.getText({blockSeparator:'\n\n'}))});
 useEffect(()=>{if(editor&&!editor.isDestroyed&&value&&JSON.stringify(editor.getJSON())!==JSON.stringify(value))editor.commands.setContent(value as JSONContent,{emitUpdate:false});},[editor,value]);
 if(!editor||editor.isDestroyed)return <p>正在准备编辑器…</p>;
 return <div className="uw-writing" data-record={recordId}><div className="uw-editor-toolbar" role="toolbar" aria-label="文稿格式">
 <button type="button" aria-label="粗体" aria-pressed={editor.isActive('bold')} onClick={()=>editor.chain().focus().toggleBold().run()}><b>B</b></button>
 <button type="button" aria-label="斜体" onClick={()=>editor.chain().focus().toggleItalic().run()}><i>I</i></button>
 <button type="button" onClick={()=>editor.chain().focus().toggleHeading({level:2}).run()}>标题</button><button type="button" onClick={()=>editor.chain().focus().toggleBulletList().run()}>列表</button>
 <button type="button" onClick={()=>editor.chain().focus().toggleOrderedList().run()}>编号</button>
 <button type="button" onClick={()=>editor.chain().focus().toggleBlockquote().run()}>引述</button>
 <button type="button" onClick={async()=>{const text=await ask("脚注内容");if(text)editor.chain().focus().insertContent({type:"footnote",attrs:{text}}).run();}}>脚注</button>
 <button type="button" onClick={()=>editor.chain().focus().undo().run()} disabled={!editor.can().undo()}>撤销</button><button type="button" onClick={()=>editor.chain().focus().redo().run()} disabled={!editor.can().redo()}>重做</button>
 {evidenceIds.length>0&&<select aria-label="插入原文引用" value="" onChange={e=>{if(e.target.value)editor.chain().focus().insertContent({type:'citation',attrs:{anchorId:e.target.value}}).run();}}><option value="">插入引用</option>{evidenceIds.map((id,i)=><option key={id} value={id}>原文 {i+1}</option>)}</select>}
 </div><EditorContent editor={editor}/><small className="uw-editor-caption">引用保持与原文版本关联 · Ctrl / ⌘ Z 撤销 · 原 Markdown 特殊块保留原貌</small></div>;
}
