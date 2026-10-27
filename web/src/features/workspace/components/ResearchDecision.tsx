import {useId,useState} from 'react';
import {Icon} from './Icon';
export interface ResearchDecisionData{id:string;run_id:string;conversation_id:string;kind:string;payload:{question:string;suggested_tokens?:number;premise?:string}}
export function ResearchDecision({decision,onAnswer,readOnly}:{decision:ResearchDecisionData;onAnswer:(accept:boolean,tokens:number)=>Promise<void>;readOnly:boolean}){
 const [tokens,setTokens]=useState(decision.payload.suggested_tokens||40000);const [busy,setBusy]=useState(false);
 const [failure,setFailure]=useState('');const titleId=useId();
 const budget=decision.kind==='budget';const reframe=decision.kind==='reframe';const branch=decision.kind==='branch';const known=budget||reframe||branch;
 const title=budget?'研究额度不足':reframe?'调整研究问题':branch?'打开新的研究分支':'待处理的研究决定';
 const accept=budget?`增加 ${tokens.toLocaleString()} token 并继续`:reframe?'采用新问题并继续':branch?'在当前额度内建立分支':'暂不支持此操作';
 const reject=budget?'保留结果并结束研究':reframe?'保留原问题继续':'不建立分支，继续原研究';
 const act=async(yes:boolean)=>{if(busy||readOnly)return;setBusy(true);setFailure('');try{await onAnswer(yes,yes&&budget?tokens:0);}catch(error){setFailure(String(error));}finally{setBusy(false);}};
 return <section className="uw-decision fd-research-decision" aria-labelledby={titleId} aria-busy={busy}><header><span className="fd-decision-label">需要你的确认</span><h3 id={titleId}><Icon name="spark" size={17}/>{title}</h3></header><p>{decision.payload.question}</p>{decision.payload.premise&&<blockquote>{decision.payload.premise}</blockquote>}<p className="wb-decision-impact">{budget?'追加额度仅用于当前研究；已有结果、来源和调用用量会保留。':reframe?'后续步骤采用这个问题，原问题保留在过程记录中；不会自动增加额度。':branch?'新分支沿用已授权材料范围和当前总额度，原研究与已有产物保留。':'当前版本无法确认此决定的影响，请保留已有结果。'}</p>{budget&&<label>追加额度<input type="number" aria-label="追加研究额度" min={1000} max={1000000} step={1000} value={tokens} disabled={busy||readOnly} onChange={e=>setTokens(Number(e.target.value))}/></label>}<div className="uw-inline-actions"><button disabled={busy||readOnly||!known||(budget&&(!Number.isInteger(tokens)||tokens<1000||tokens>1000000))} onClick={()=>void act(true)}>{busy?'正在处理…':accept}</button><button disabled={busy||readOnly||!known} onClick={()=>void act(false)}>{reject}</button></div>{readOnly&&<p className="wb-decision-impact">当前为只读权限，请由有编辑权限的研究者处理。</p>}{failure&&<div role="alert" className="fd-decision-error"><p>决定尚未提交成功，原有结果已保留。可以重试；如果另一窗口已经处理，请刷新本回合。</p><details><summary>错误详情</summary>{failure}</details></div>}</section>;
}
