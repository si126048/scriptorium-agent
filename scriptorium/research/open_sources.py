"""Small public metadata queries; no credentials, bulk paging or paid fallback."""
import hashlib
import time
import threading
from urllib.parse import urlencode
import httpx
import sqlalchemy as sa
from . import schema as db
from .public_fetch import PublicTransport, normalized_url
from .service import ResearchError, row, rows
from .collection import check_owned

_ENDPOINTS={'crossref':'https://api.crossref.org/works','openalex':'https://api.openalex.org/works','openlibrary':'https://openlibrary.org/search.json'}
_locks={name:threading.Lock() for name in _ENDPOINTS}
_last={name:0.0 for name in _ENDPOINTS}


def request(s,job,channel,query):
    check_owned(s,job)
    key=hashlib.sha256((channel+':'+query).encode()).hexdigest()
    with s.engine.begin() as c:
        s.access(c,job['project_id'],job['payload']['principal'],True);s.locked_job(c,job)
        old=row(c,db.metadata_requests,db.metadata_requests.c.job_id==job['id'],db.metadata_requests.c.request_key==key)
        if old:return old['payload'].get('results',[])
        existing=rows(c,db.metadata_requests,db.metadata_requests.c.job_id==job['id'])
        intake=row(c,db.intakes,db.intakes.c.job_id==job['id'])
        if len(existing)>=(intake['payload']['limits'].get('metadata_requests',12)):return []
        identifier=db.uid()
        c.execute(db.metadata_requests.insert().values(id=identifier,job_id=job['id'],channel=channel,
            request_key=key,state='requested',payload={'query':query},created_at=db.now()))
    params={'crossref':{'query.bibliographic':query,'rows':6},'openalex':{'search':query,'per-page':6},
            'openlibrary':{'q':query,'limit':6,'fields':'key,title,author_name,first_publish_year,isbn,edition_key,language,ia,public_scan_b'}}[channel]
    results=[];error=None;state='returned';http_requests=0
    try:
        for attempt in range(2):
            check_owned(s,job)
            with s.engine.begin() as c:
                s.access(c,job['project_id'],job['payload']['principal'],True);s.locked_job(c,job)
                total=sum(v['payload'].get('http_requests',0) for v in rows(c,db.metadata_requests,db.metadata_requests.c.job_id==job['id']))
                if total>=intake['payload']['limits'].get('metadata_requests',12):
                    state='limited';error='METADATA_REQUEST_LIMIT';break
                http_requests+=1
                c.execute(db.metadata_requests.update().where(db.metadata_requests.c.id==identifier).values(payload={'query':query,'http_requests':http_requests}))
            with _locks[channel]:
                delay=max(0,1-(time.monotonic()-_last[channel]))
                if delay:time.sleep(delay)
                _last[channel]=time.monotonic()
                with httpx.Client(transport=PublicTransport(),trust_env=False,timeout=15,follow_redirects=False) as client, client.stream('GET',_ENDPOINTS[channel]+'?'+urlencode(params),headers={'User-Agent':'Scriptorium/3.5 (personal research metadata)','Accept':'application/json'}) as response:
                    if response.status_code==429 and attempt==0:
                        delay=min(5,max(1,int(response.headers.get('Retry-After','1'))))
                        time.sleep(delay);continue
                    response.raise_for_status()
                    content=bytearray()
                    for chunk in response.iter_bytes(65536):
                        check_owned(s,job);content.extend(chunk)
                        if len(content)>2*1024*1024:raise ResearchError('METADATA_RESPONSE_TOO_LARGE',413)
                    import json
                    results=normalize(channel,json.loads(content));break
    except ResearchError as exc:
        if exc.code in {'JOB_NO_LONGER_OWNED','PROJECT_EXTERNAL_PROCESSING_DISABLED'}:raise
        error=exc.code;state='failed'
    except Exception as exc:
        error=type(exc).__name__;state='unavailable'
    with s.engine.begin() as c:
        s.locked_job(c,job)
        c.execute(db.metadata_requests.update().where(db.metadata_requests.c.id==identifier).values(state=state,
            payload={'query':query,'results':results,'error':error,'http_requests':http_requests}))
    return results


def normalize(channel,data):
    items=(data.get('message') or {}).get('items',[]) if channel=='crossref' else data.get('results',[]) if channel=='openalex' else data.get('docs',[])
    result=[]
    for item in items[:6]:
        if channel=='crossref':
            doi=item.get('DOI','');url=item.get('URL') or ('https://doi.org/'+doi if doi else '')
            title=' '.join(item.get('title') or []);author='; '.join(' '.join(filter(None,[a.get('given'),a.get('family')])) for a in item.get('author',[])[:6])
            links=[v.get('URL') for v in item.get('link',[]) if v.get('content-type')=='application/pdf']
            year=str(((item.get('published') or {}).get('date-parts') or [['']])[0][0])
            extra={'doi':doi,'author':author,'publication_date':year,'locations':links,'document_type':item.get('type'),'version_status':'unconfirmed'}
        elif channel=='openalex':
            doi=(item.get('doi') or '').removeprefix('https://doi.org/');location=item.get('best_oa_location') or item.get('primary_location') or {}
            url=item.get('doi') or location.get('landing_page_url') or item.get('id','')
            title=item.get('title') or '';links=[v for loc in [location,*item.get('locations',[])[:4]] for v in [loc.get('pdf_url'),loc.get('landing_page_url')] if v]
            author='; '.join((a.get('author') or {}).get('display_name','') for a in item.get('authorships',[])[:6])
            extra={'doi':doi,'author':author,'publication_date':str(item.get('publication_year') or ''),'locations':links,'version_status':location.get('version') or 'unconfirmed'}
        else:
            url='https://openlibrary.org'+item.get('key','');title=item.get('title') or ''
            extra={'author':'; '.join(item.get('author_name') or []),'publication_date':str(item.get('first_publish_year') or ''),
                'isbn':next(iter(item.get('isbn') or []),''),'language':','.join(item.get('language') or []),
                'work_key':item.get('key'),'version_status':'work_only','locations':[], 'metadata_only':True}
        try:url=normalized_url(url)
        except (ValueError,ResearchError):continue
        result.append({'url':url,'title':title[:500],'provider':channel,'snippet':'','source_type':'academic',**extra})
    return result


def discover(s,job,query):
    from .timeline import activity
    found=[]
    for channel in _ENDPOINTS:
        activity(s,job,'discovery:'+channel,'检索 '+{'crossref':'Crossref 书目','openalex':'OpenAlex 开放文献','openlibrary':'Open Library 专著'}[channel])
        values=request(s,job,channel,query[:500]);found.extend(values)
        with s.engine.connect() as c:
            status=c.execute(sa.select(db.metadata_requests).where(db.metadata_requests.c.job_id==job['id'],db.metadata_requests.c.channel==channel).order_by(db.metadata_requests.c.created_at.desc())).mappings().first()
        available=bool(status and status['state']=='returned')
        activity(s,job,'discovery:'+channel,'检索 '+channel+('' if available else ' · 渠道暂不可用'),'completed' if available else 'unavailable',detail=f'取得 {len(values)} 项书目。' if available else '没有取得可用响应，已保留状态并继续其他渠道。')
    return found
