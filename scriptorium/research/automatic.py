"""One-question research: local routing, source collection and existing method execution."""
import re
import sqlalchemy as sa
from . import schema as db
from .service import ResearchError, row, rows
from .workspace import add_message, execute_workspace, run_research, windows
from . import collection


def route(text):
    normalized=re.sub(r'[\s!！。.?？,，~～]+','',text).lower()
    if normalized in {'你好','您好','嗨','hello','hi','hey','早上好','晚上好','谢谢','thanks'}:return 'greeting'
    if normalized in {'帮助','怎么用','如何使用','help','你能做什么','你是谁'}:return 'help'
    if normalized in {'研究','帮我研究','开始研究','research'}:return 'clarify'
    if re.search(r'研究|梳理|比较|对比|分析|文献|综述|证据|构境|批判|视差|搜集|收集|查找|检索|调研|考察|找.{0,80}(?:资料|来源)|research|investigat|literature|compare|study|survey|find.{0,80}(?:sources|papers)',text,re.IGNORECASE):return 'research'
    return 'chat'


def reply(s,job,text,state='completed',**metadata):
    with s.engine.begin() as c:
        s.access(c,job['project_id'],job['payload']['principal'],True);s.locked_job(c,job)
        identifier='auto-'+job['id']+'-'+state
        if not row(c,db.messages,db.messages.c.id==identifier):
            add_message(c,job['project_id'],job['payload']['conversation_id'],'assistant',text,
                metadata={'job_id':job['id'],**metadata},identifier=identifier)
        s.finish(c,job,{'state':state,'text':text,**metadata})


def budget_partial(s,job,reason='CALL_BUDGET_REQUIRED'):
    """AUTO at its ceiling: keep the phase result, finish with an explicit partial answer."""
    try:
        latest=collection.associated(s,job['project_id'],job['id'])
    except Exception:
        latest=[]
    full=sum(1 for x in latest if x.get('association',{}).get('availability')=='fulltext')
    restricted=sum(1 for x in latest if x.get('association',{}).get('availability')=='restricted')
    text=(f'自动模式已达到本轮调用预算上限，先保留阶段成果：已收集 {len(latest)} 个来源，'
          f'其中 {full} 份可读全文、{restricted} 项受限。完整的综合分析与逐条引文没有生成；'
          '来源、阅读记录和已生成的阶段结果都已保留。可以调高预算后重试，'
          '或在「研究选项」切换到「逐步确认」继续。')
    try:
        collection.checkpoint(s,job,'completed',decision='AUTO_BUDGET_PARTIAL')
    except Exception:
        pass
    try:
        from .timeline import activity
        activity(s,job,'auto-budget','预算到顶，返回阶段成果','completed',detail=text,stamp='AUTO',reason=reason)
    except Exception:
        pass
    reply(s,job,text,'partial_completed',reason=reason,partial=True)

def pause(s,job,reason):
    collection.checkpoint(s,job,'awaiting_input',decision=reason)
    reply(s,job,{'NATIVE_SEARCH_UNSUPPORTED':'当前模型尚不支持可追溯的原生联网。可以在模型设置中选择支持的千问模型，或仅使用项目材料。',
        'MODEL_NOT_CONFIGURED':'请先在模型设置中配置当前模型，然后继续这项研究。',
        'NO_NETWORK_SOURCES':'这次没有取得联网来源。可以调整问题后继续寻找，或仅使用已收集的材料。',
        'NO_READABLE_SOURCES':'暂时没有可读取的材料。发现的来源和受限原因已保留，可以上传原文、继续收集或结束。',
        'NATIVE_SEARCH_FAILED_USAGE_UNKNOWN':'联网发现请求未取得完整响应，调用用量可能已产生，预留仍保留。可以检查连接后显式重试，或使用已有材料。',
        'NATIVE_SEARCH_STRUCTURE_INVALID':'供应商返回的来源结构无法识别，调用用量已经保留。可以检查模型配置或使用已有材料。',
        'SOURCE_IMPORT_PENDING':'材料仍在处理，现有来源已保存，可以稍后继续。',
        'SOURCE_FETCH_INTERRUPTED':'有一次获取未完成，用量按预留保留。可以显式重试该来源，或使用已有材料。'}.get(reason,
        '已有进展已保存。当前预算或范围不足以继续，请选择追加额度、使用已有材料，或结束。'),
        'awaiting_input',decision=reason)


def local_scope(s,job):
    if job['payload'].get('scope_snapshot'):return job['payload']['scope_snapshot']
    result=[]
    materials=s.list_materials(job['project_id'],job['payload']['principal'])
    question=job['payload']['text'].lower()
    materials.sort(key=lambda m:(sum(word in str(m['metadata'].get('title',m['name'])).lower() for word in re.findall(r'[a-z]{3,}|[\u4e00-\u9fff]{2}',question)),m['created_at']),reverse=True)
    for material in materials[:20]:
        if material['status']=='ready':
            result.extend(s.get_segments(job['project_id'],job['payload']['principal'],material['id'])['segments'])
    return windows(result)



def methods_for(question):
    result=['situating.v1']
    if re.search(r'批判|矛盾|内在|critique|contradiction',question,re.IGNORECASE):result.append('immanent_critique.v1')
    if re.search(r'比较|对比|差异|视差|compare|parallax|difference',question,re.IGNORECASE):result.append('parallax.v1')
    return result


def automatic_scope(s,job,scope):
    """Select an explicit, bounded sample; retain every other window as unread."""
    if job['payload'].get('explicit_scope'):return scope
    small=[]
    for w in scope:
        small.extend({**w,'start':start,'end':min(w['end'],start+2000)} for start in range(w['start'],w['end'],2000))
    groups={}
    for w in small:groups.setdefault(w['asset_id'],[]).append(w)
    question=job['payload']['text'][:512].lower()
    terms=set(re.findall(r'[a-z]{3,}',question))|{question[i:i+2] for i in range(len(question)-1) if all('\u4e00'<=ch<='\u9fff' for ch in question[i:i+2])}
    ranked=[]
    with s.engine.connect() as c:
        for group in groups.values():
            for index in range(len(group)):
                if index>=len(group):continue
                w=group[index]
                text=c.execute(sa.select(sa.func.substr(db.segments.c.text,w['start']+1,w['end']-w['start'])).where(db.segments.c.id==w['segment_id'])).scalar() or ''
                ranked.append((sum(text.lower().count(term) for term in terms),w))
    ranked.sort(key=lambda item:item[0],reverse=True)
    first=[];later=[];seen=set()
    for item in ranked:
        if item[1]['asset_id'] not in seen:first.append(item);seen.add(item[1]['asset_id'])
        else:later.append(item)
    selected=[];size=0;cap=min(6000,max(2000,job['payload'].get('token_budget',40000)//6))
    for _,w in first+later:
        if size+w['end']-w['start']<=cap:selected.append(w);size+=w['end']-w['start']
    manifest=[{**w,'state':'selected' if w in selected else 'unread'} for w in small]
    collection.checkpoint(s,job,'reading',coverage_manifest=manifest,available_windows=len(small),selected_windows=len(selected),
        coverage_note='自动选择与问题相关的代表性窗口，非全文阅读；未选窗口明确保留为未读。')
    return selected


def execute(s,job):
    body=job['payload'];intent=route(body['text'])
    if intent in {'greeting','help','clarify'}:
        text={'greeting':'你好！你可以直接告诉我想研究的问题。我可以整理项目材料、寻找公开来源，并把依据和报告呈现在这里。',
            'help':'直接输入一个研究问题即可开始，例如“比较黑格尔与马克思对自由的理解”。也可以上传材料，或选中原文后研究。联网研究使用当前模型的能力；模型尚未配置时可先到设置完成配置。',
            'clarify':'你希望研究哪个主题或问题？可以补充对象、时期或希望比较的立场。'}[intent]
        return reply(s,job,text,local_response=True)
    if intent=='chat' and not body.get('methods'):
        return execute_workspace(s,{**job,'payload':{**body,'tool':'chat'}})
    intake=collection.ensure_intake(s,job); saved=intake['payload']
    if saved.get('stop'):
        collection.checkpoint(s,job,'completed');return reply(s,job,'本次研究已结束，已经发现的来源和已有成果保留在项目中。','stopped')
    try:
        restricted=body.get('explicit_scope') or re.search(r'仅根据|仅使用|只根据|只用这些|只使用|only (these|the provided|project)',body['text'],re.IGNORECASE)
        scope=saved.get('scope') or local_scope(s,job)
        network=body.get('network_mode','auto')!='off' and not restricted and not saved.get('use_project')
        if network and not saved.get('discovered') and not saved.get('use_collected'):
            from .native_search import discover
            with s.engine.connect() as c:
                calls=rows(c,db.discovery_calls,db.discovery_calls.c.job_id==job['id'])
            if any(x['state'] in {'reserved','unknown'} and not x['payload'].get('retry_authorized') for x in calls):return pause(s,job,'NATIVE_SEARCH_FAILED_USAGE_UNKNOWN')
            if len(calls)>=saved['limits']['requests']:return pause(s,job,'COLLECTION_REQUEST_LIMIT')
            # Recover committed discovery results instead of repeating the paid request after a crash.
            returned=next((x for x in reversed(calls) if x['state']=='returned' and not x['payload'].get('consumed')),None)
            if returned:
                items=[{'url':v['url'],'title':v.get('title') or v['url'],'snippet':v.get('snippet') or v.get('description') or '',
                        'provider_index':str(v.get('index','')),'provider':'qwen','query':body['text'],'discovered_at':db.now()}
                       for v in returned['payload'].get('raw_sources',[]) if isinstance(v,dict) and isinstance(v.get('url'),str)]
            elif body.get('provider_mode')=='demo':
                items=[]
            else:
                collection.checkpoint(s,job,'discovering')
                try:
                    items=discover(s,job,body['text'])
                except ResearchError as exc:
                    if exc.code not in {'NATIVE_SEARCH_UNSUPPORTED','NATIVE_SEARCH_FAILED_USAGE_UNKNOWN','NO_NETWORK_SOURCES','MODEL_NOT_CONFIGURED'}:raise
                    items=[]
                    collection.checkpoint(s,job,'discovering',native_warning=exc.code)
            if body.get('provider_mode')!='demo':
                from .open_sources import discover as discover_open
                items=[*items,*discover_open(s,job,body['text'])]
            collection.checkpoint(s,job,'collecting',candidates=items,discovered=True)
            with s.engine.begin() as c:
                for call in rows(c,db.discovery_calls,db.discovery_calls.c.job_id==job['id']):
                    c.execute(db.discovery_calls.update().where(db.discovery_calls.c.id==call['id']).values(payload={**call['payload'],'consumed':True}))
            saved={**saved,'candidates':items,'discovered':True}
        candidates=saved.get('candidates') or []
        unique={}
        from .public_fetch import normalized_url
        for item in candidates:
            try:key=(item.get('doi') or normalized_url(item['url'],canonical=True)).lower()
            except (ValueError,KeyError,ResearchError):continue
            if key in unique:
                old=unique[key];old['locations']=list(dict.fromkeys([*old.get('locations',[]),*item.get('locations',[])]))[:3]
                if not old.get('snippet'):old['snippet']=item.get('snippet','')
            else:unique[key]=dict(item)
        candidates=sorted(unique.values(),key=lambda x:(bool(x.get('metadata_only')),not bool(x.get('locations'))))
        for item in candidates[:saved['limits']['sources']]:collection.register(s,job,item)
        sources=collection.associated(s,job['project_id'],job['id'])
        if network and not sources and not scope and not saved.get('use_collected'):return pause(s,job,'NO_NETWORK_SOURCES')
        if not saved.get('use_collected'):
            for source in sources:
                if source['payload'].get('availability')=='fetching' and source['association'].get('fetch_attempted') and not source['association'].get('import_job_id') and not source['association'].get('original_object_key') and not source['association'].get('fetch_job_id'):
                    return pause(s,job,'SOURCE_FETCH_INTERRUPTED')
                try:
                    collection.schedule_fetch(s,job,source['id'])
                except ResearchError as exc:
                    if exc.code not in {'COLLECTION_SOURCE_LIMIT','COLLECTION_DOWNLOAD_LIMIT'}:raise
                    collection.checkpoint(s,job,'collecting',collection_limit=exc.code)
                    break
                from .timeline import activity
                latest=collection.associated(s,job['project_id'],job['id'])
                activity(s,job,'phase:collecting','获取与整理材料',detail=f"正文 {sum(x['association'].get('availability')=='fulltext' for x in latest)} 份 · 受限 {sum(x['association'].get('availability')=='restricted' for x in latest)} 项 · 候选 {len(sources)} 项")
        for source in collection.associated(s,job['project_id'],job['id']):collection.materialize_excerpt(s,job,source)
        if len(candidates)>saved['limits']['sources'] and not saved.get('use_collected'):
            collection.checkpoint(s,job,'reading',uncovered_sources=len(candidates)-saved['limits']['sources'])
        collection.checkpoint(s,job,'reading')
        for source in collection.associated(s,job['project_id'],job['id']):
            link=source['association']
            if link.get('asset_id') and not link.get('excluded'):
                data=s.get_segments(job['project_id'],body['principal'],link['asset_id'],link.get('version_id'))
                for window in windows(data['segments']):
                    if window not in scope:scope.append(window)
        if not scope:return pause(s,job,'NO_READABLE_SOURCES')
        if not saved.get('scope'):scope=automatic_scope(s,job,scope)
        from .native_search import spent
        total_budget=body.get('_auto_total_budget',body.get('token_budget',40000))
        remaining=total_budget-spent(s,job['id'])
        if remaining<10000:
            if job['payload'].get('review_mode','auto')=='auto':return budget_partial(s,job)
            return pause(s,job,'CALL_BUDGET_REQUIRED')
        collection.checkpoint(s,job,'analyzing',scope=scope,decision=None)
        bound={**body,'scope_snapshot':scope,'asset_ids':list(dict.fromkeys(w['asset_id'] for w in scope)),
            '_auto_total_budget':total_budget,'token_budget':remaining,'methods':body.get('methods') or methods_for(body['text'])}
        with s.engine.begin() as c:
            s.locked_job(c,job)
            c.execute(db.jobs.update().where(db.jobs.c.id==job['id']).values(payload={**bound,'tool':'auto'}))
        run_research(s,{**job,'payload':bound})
    except ResearchError as exc:
        if exc.code=='SOURCE_IMPORT_PENDING':
            with s.engine.begin() as c:
                s.access(c,job['project_id'],body['principal'],True)
                s.defer_job(c,job,delay_seconds=2)
            return
        recoverable={'NATIVE_SEARCH_UNSUPPORTED','MODEL_NOT_CONFIGURED','NATIVE_SEARCH_FAILED_USAGE_UNKNOWN','NATIVE_SEARCH_STRUCTURE_INVALID',
            'COLLECTION_REQUEST_LIMIT','COLLECTION_SOURCE_LIMIT','COLLECTION_DOWNLOAD_LIMIT','SOURCE_IMPORT_PENDING',
            'CALL_BUDGET_REQUIRED','PROJECT_BUDGET_REQUIRED','SOURCE_FETCH_INTERRUPTED','FINAL_ANSWER_NEEDS_REVIEW','FINAL_ANSWER_CITATION_INVALID','MODEL_OUTPUT_TRUNCATED','MODEL_REQUEST_FAILED_USAGE_UNKNOWN'}
        if exc.code in recoverable:
            if exc.code in {'CALL_BUDGET_REQUIRED','PROJECT_BUDGET_REQUIRED'} and job['payload'].get('review_mode','auto')=='auto':
                return budget_partial(s,job,exc.code)
            return pause(s,job,exc.code)
        raise
