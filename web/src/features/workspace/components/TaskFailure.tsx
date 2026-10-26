import {Icon} from './Icon';
export function TaskFailure({error,onRetry,onMaterials,onAuto,onSettings}:{error:string;onRetry:()=>void;onMaterials:()=>void;onAuto:()=>void;onSettings:()=>void}){
 const ownership=/JOB_NO_LONGER_OWNED/.test(error);
 const missing=/NO_MATERIALS_FOR_QUESTION|SELECT_RESEARCH_MATERIALS|NO_RESEARCH_TEXT/.test(error),model=/MODEL_NOT_CONFIGURED|NATIVE_SEARCH_UNSUPPORTED/.test(error),policy=/AUTHORIZ|DISABLED|CONSENT/.test(error);
 return <div className="wb-task-failure" role="status"><Icon name="file"/><div><strong>{ownership?'后台执行中断，进度仍保留':missing?'这项材料研究还缺少原文':model?'需要检查模型配置':policy?'当前范围暂未获得处理授权':'这一步没有完成，已有内容已保存'}</strong><p>{ownership?'可以从检查点恢复，已完成材料和结果将被复用。':missing?'可以添加材料，或使用自动模式寻找公开来源。':model?'请配置当前模型，或选择支持原生联网的千问模型。':policy?'请检查项目政策和材料授权，再继续研究。':'可查看详情，再决定是否重试。'}</p><div>{missing?<><button onClick={onMaterials}>添加材料</button><button onClick={onAuto}>改用自动研究</button></>:model?<button onClick={onSettings}>打开模型设置</button>:!policy&&<button onClick={onRetry}>{ownership?'从检查点继续':'重试这一步'}</button>}</div><details><summary>技术详情</summary>{error}</details></div></div>;
}
