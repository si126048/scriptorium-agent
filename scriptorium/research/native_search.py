"""Qwen-native discovery. Never send keys to guessed or model-selected endpoints."""
from types import SimpleNamespace
import httpx
from . import schema as db
from .service import ResearchError, rows
from .providers import provider_config, key_for
from .calls import reserve

ENDPOINTS = {
    'https://dashscope.aliyuncs.com/compatible-mode/v1': 'https://dashscope.aliyuncs.com/api/v1/services/aigc/text-generation/generation',
    'https://dashscope-intl.aliyuncs.com/compatible-mode/v1': 'https://dashscope-intl.aliyuncs.com/api/v1/services/aigc/text-generation/generation',
}


def capabilities(config=None):
    config = config or provider_config()
    endpoint = ENDPOINTS.get(config['base_url'].rstrip('/'))
    supported = config['id'] == 'qwen' and bool(endpoint) and config['model'].startswith(('qwen-plus', 'qwen-flash'))
    return {'provider': config['id'], 'model': config['model'], 'web_search': supported,
            'structured_sources': supported, 'streaming_sources': False,
            'verified': False, 'protocol': 'dashscope-native' if supported else None,
            'reason': None if supported else '当前模型或端点尚未适配原生联网，请选择受支持的千问模型或仅使用项目材料。'}


def discover(s, job, query):
    from .events import emit
    from .collection import check_owned
    check_owned(s,job)
    config = provider_config()
    if not capabilities(config)['web_search']:
        raise ResearchError('NATIVE_SEARCH_UNSUPPORTED', 422)
    if not config['ready']:
        raise ResearchError('MODEL_NOT_CONFIGURED', 422)
    endpoint = ENDPOINTS[config['base_url'].rstrip('/')]
    # Discovery has no local text or conversation history. Queries are the user-supplied question.
    safe_job = {**job, 'payload': {**job['payload'], 'asset_ids': [], 'segment_ids': [], 'scope_snapshot': []}}
    messages = [{'role':'system','content':'为这个研究问题寻找可核实的公开学术来源与网页。优先原始文献、出版机构及学术机构，不编造链接。'},
                {'role':'user','content':query}]
    active = SimpleNamespace(model=config['model'], base_url=endpoint)
    identifier = reserve(s, safe_job, active, messages, 2000)
    call_id = db.uid()
    with s.engine.begin() as c:
        s.locked_job(c, job)
        c.execute(db.discovery_calls.insert().values(id=call_id, job_id=job['id'], model_call_id=identifier,
            state='reserved', payload={'query':query,'provider':config['id'],'model':config['model']}, created_at=db.now()))
        emit(c, job['project_id'], job['payload']['conversation_id'], 'research.phase', {'job_id':job['id'],'phase':'discovering'})
    try:
        with httpx.Client(trust_env=False, timeout=90) as client:
            response = client.post(endpoint, headers={'Authorization':'Bearer '+key_for(config['id'])},
                json={'model':config['model'],'input':{'messages':messages},'parameters':{
                    'enable_search':True,'search_options':{'enable_source':True,'forced_search':True},
                    'result_format':'message','max_tokens':2000}})
            response.raise_for_status(); data = response.json()
            if not isinstance(data,dict):raise ValueError('NATIVE_SEARCH_STRUCTURE_INVALID')
    except Exception as exc:
        with s.engine.begin() as c:
            c.execute(db.model_calls.update().where(db.model_calls.c.id==identifier).values(
                state='unknown',error=type(exc).__name__[:100],finished_at=db.now()))
            c.execute(db.discovery_calls.update().where(db.discovery_calls.c.id==call_id).values(
                state='unknown',payload={'query':query,'provider':config['id'],'error':type(exc).__name__}))
        raise ResearchError('NATIVE_SEARCH_FAILED_USAGE_UNKNOWN', 502) from None
    reported = data.get('usage') or {}
    if not isinstance(reported,dict) or any(not isinstance(reported.get(k,0),int) or reported.get(k,0)<0 for k in ('input_tokens','output_tokens','total_tokens')):reported={}
    output = data.get('output') if isinstance(data.get('output'),dict) else {}
    info = output.get('search_info') or data.get('search_info') or {}
    found = info.get('search_results',[]) if isinstance(info,dict) else None
    usage = {'input_tokens':reported.get('input_tokens',0),'output_tokens':reported.get('output_tokens',0),
             'total_tokens':reported.get('total_tokens',reported.get('input_tokens',0)+reported.get('output_tokens',0))} if reported else None
    # Settle tokens before validating sources. Empty or malformed results are not free calls.
    with s.engine.begin() as c:
        c.execute(db.model_calls.update().where(db.model_calls.c.id==identifier).values(
            state='returned' if usage else 'unknown',usage=usage,finished_at=db.now()))
        c.execute(db.discovery_calls.update().where(db.discovery_calls.c.id==call_id).values(
            state='returned' if usage else 'unknown',payload={'query':query,'provider':config['id'],
                'usage':reported,'raw_sources':found if isinstance(found,list) else [],'search_count_semantics':'provider reported intent/tool usage, not proof of retrieval'}))
    if not isinstance(found, list):
        raise ResearchError('NATIVE_SEARCH_STRUCTURE_INVALID', 502)
    result = []
    for item in found:
        if not isinstance(item,dict) or not isinstance(item.get('url'),str):
            continue
        result.append({'url':item['url'],'title':str(item.get('title') or item['url'])[:500],
            'snippet':str(item.get('snippet') or item.get('description') or '')[:10000],
            'doi':item.get('doi') if isinstance(item.get('doi'),str) else '',
            'provider_index':str(item.get('index',len(result)+1)), 'provider':config['id'],
            'query':query,'discovered_at':db.now()})
    return result


def spent(s, job_id):
    with s.engine.connect() as c:
        calls = rows(c, db.model_calls, db.model_calls.c.job_id == job_id)
    return sum((x['usage'] or {}).get('total_tokens',0) +
        (x['reserved_tokens'] if x['state'] in {'reserved','unknown'} else 0) for x in calls)
