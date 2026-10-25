# ruff: noqa: F811
from test_research_integration import research, client, imported  # noqa: F401
from scriptorium.research.worker import run_one
from scriptorium.research import schema as db
from scriptorium.research.service import row


def doc(text):
    return {'type':'doc','content':[{'type':'paragraph','content':[{'type':'text','text':text}]}]}


def test_export_freezes_main_chapters_and_idempotency(research, client, monkeypatch):
    pid=research.create_project('tester','稳定写作')['id']; root=f'/api/v2/projects/{pid}'
    record=client.post(root+'/records',json={'kind':'manuscript','payload':{'title':'旧稿','editor_json':doc('提交时的内容')}}).json()
    endpoint=root+f"/artifacts/{record['id']}"
    client.put(endpoint+'/chapters/one',json={'payload':{'title':'旧章节','editor_json':doc('旧章节正文')}})
    body={'format':'html','revision':1};headers={'Idempotency-Key':'snapshot-export'}
    submitted=client.post(endpoint+'/exports',json=body,headers=headers);assert submitted.status_code==202,submitted.text
    client.put(root+f"/records/{record['id']}",json={'kind':'manuscript','revision':1,'payload':{'title':'新稿','editor_json':doc('提交后的内容')}})
    client.put(endpoint+'/chapters/one',json={'revision':1,'payload':{'title':'新章节','editor_json':doc('新章节正文')}})
    retry=client.post(endpoint+'/exports',json=body,headers=headers);assert retry.status_code==202 and retry.json()['id']==submitted.json()['id']
    with research.engine.connect() as c:
        snapshot=row(c,db.jobs,db.jobs.c.id==submitted.json()['id'])['payload']['snapshot']
    assert snapshot['record']['revision']==1 and snapshot['record']['payload']['title']=='旧稿'
    assert snapshot['chapters'][0]['revision']==1 and snapshot['chapters'][0]['payload']['title']=='旧章节'
    assert client.post(endpoint+'/exports',json=body).status_code==409
    from pathlib import Path
    binary=Path('desktop-build/pandoc/3.12.1/pandoc.exe').resolve()
    assert binary.is_file(), 'Prepare the pinned export runtime for this local integration check'
    monkeypatch.setattr('scriptorium.research.exporting.ensure_pandoc',lambda:binary)
    run_one(research,submitted.json()['id'])
    output=client.get(root+'/exports/'+submitted.json()['id']+'/download')
    assert output.status_code==200, output.text
    assert '提交时的内容' in output.text and '旧章节正文' in output.text
    assert '提交后的内容' not in output.text and '新章节正文' not in output.text


def test_chapter_suggestion_accepts_only_its_revision(research, client):
    pid=research.create_project('tester','章节')['id'];root=f'/api/v2/projects/{pid}'
    record=client.post(root+'/records',json={'kind':'manuscript','payload':{'title':'文稿','editor_json':doc('主文不变')}}).json()
    endpoint=root+f"/artifacts/{record['id']}"
    client.put(endpoint+'/chapters/one',json={'payload':{'title':'章节','editor_json':doc('章节原文')}})
    job=client.post(endpoint+'/change-proposals',json={'chapter_id':'one','base_revision':1,'instruction':'改善表述','provider_mode':'demo'}).json()
    run_one(research,job['id'])
    accepted=client.post(root+'/change-proposals/'+job['id'],json={'action':'accept'});assert accepted.status_code==200,accepted.text
    chapters=client.get(endpoint+'/chapters').json();assert chapters[0]['revision']==2 and '演示修改建议' in chapters[0]['payload']['text']
    assert client.get(endpoint).json()['revision']==1


def test_reading_window_unicode_and_cross_boundary(research, client):
    source='甲😀e\u0301'*4000
    pid,aid,segments=imported(research,source);root=f'/api/v2/projects/{pid}'
    page=client.get(root+f'/materials/{aid}/reading?page=1').json()
    assert page['page']==1 and len(page['parts'][0]['text'])==6000
    assert page['parts'][0]['text']==source[6000:12000]
    focus=client.get(root+f"/materials/{aid}/reading",params={'version_id':segments[0]['version_id'],'segment_id':segments[0]['id'],'start':11998,'end':12010}).json()
    assert focus['page']==1 and focus['parts'][0]['end']==12010 and focus['parts'][0]['text']==source[6000:12010]
    assert client.get(root+f'/materials/{aid}/reading?page=99').status_code==404


def test_first_message_names_session_without_changing_custom_names(research, client):
    pid=research.create_project('tester','命名')['id'];root=f'/api/v2/projects/{pid}'
    conversation=client.post(root+'/conversations',json={}).json()
    body={'text':'材料中的自由意味着什么？','tool':'ask','provider_mode':'demo'}
    sent=client.post(root+f"/conversations/{conversation['id']}/messages",json=body,headers={'Idempotency-Key':'name'})
    assert sent.status_code==202
    assert client.get(root+'/conversations').json()[0]['title']==body['text']


def test_summary_endpoints_labels_and_chapter_order(research, client):
    pid,aid,segments=imported(research,'原文依据。');root=f'/api/v2/projects/{pid}'
    with research.engine.begin() as c:
        anchor=research.make_anchor(c,pid,segments[0]['id'],0,2,'原文')
    asset=next(a for a in client.get(root+'/materials').json() if a['id']==aid)
    assert client.put(root+f'/materials/{aid}/bibliography',json={'revision':asset['revision'],'metadata':{'title':'期刊论文','author':'作者','journal':'学刊','csl_type':'article-journal','volume':'2','issue':'1','pages':'1-20','doi':'10.0000/example'}}).status_code==200
    label=client.get(root+'/citation-labels',params={'ids':anchor['id']}).json()[0]
    assert '期刊论文' in label['label'] and label['version_id']==segments[0]['version_id']
    record=client.post(root+'/records',json={'kind':'manuscript','payload':{'title':'文稿','editor_json':doc('正文'), 'pinned':True}}).json()
    endpoint=root+f"/artifacts/{record['id']}"
    for name in ['first','second']:
        assert client.put(endpoint+'/chapters/'+name,json={'payload':{'title':name,'editor_json':doc(name)}}).status_code==200
    order={'chapters':[{'id':'second','revision':1},{'id':'first','revision':1}]}
    ordered=client.post(endpoint+'/chapters/order',json=order);assert ordered.status_code==200,ordered.text
    assert [c['id'] for c in ordered.json()]==['second','first']
    assert client.post(endpoint+'/chapters/order',json=order).status_code==409
    summary=client.get(root+'/records?summary=true').json()
    assert any(r['payload'].get('pinned') is True for r in summary)
    assert all('editor_json' not in r['payload'] and 'text' not in r['payload'] for r in summary)
    assert client.get(root+'/jobs?summary=true').status_code==200
    assert client.get(root+'/model-calls?summary=true').json()['totals']['used_tokens']==0
