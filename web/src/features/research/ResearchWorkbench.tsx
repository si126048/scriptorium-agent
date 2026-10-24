import { useCallback, useEffect, useRef, useState } from 'react';
import type { Anchor, Job, LegacyRecord, Material, Payload, Project, ResearchRecord, Segment } from './client';
import { codepointOffset, download, exportBrowserHistory, persistDesktopConnection, projectPath, request, serviceUrl } from './client';
import './research.css';

const tabs = [
  ['reader', '材料与阅读'], ['contexts', '构境比较'], ['methods', '方法分析'],
  ['arguments', '论证与概念演化'], ['parallax', '视差与研究分支'],
  ['writing', '文稿与导出'], ['legacy', '历史档案'], ['settings', '服务与任务'],
] as const;
type Tab = typeof tabs[number][0];
const kindNames: Record<string, string> = { annotation: '批注', concept: '概念出现', context: '构境档案',
  claim: '论点', position: '立场', criterion: '自身尺度', difficulty: '困难', transition: '概念转化',
  standpoint: '观察位置', appearance: '对象显现', shift: '对象位移', parallax: '视差候选',
  question: '研究问题', branch: '研究分支', objection: '异议', response: '回应', manuscript: '文稿',
  review: '评议', method_report: '方法报告' };

function message(error: unknown) { return error instanceof Error ? error.message : String(error); }

export default function ResearchWorkbench() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectId, setProjectId] = useState(localStorage.getItem('scriptorium_research_project') || '');
  const [materials, setMaterials] = useState<Material[]>([]);
  const [records, setRecords] = useState<ResearchRecord[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [tab, setTab] = useState<Tab>('reader');
  const [assetId, setAssetId] = useState('');
  const [versionId, setVersionId] = useState('');
  const [segments, setSegments] = useState<Segment[]>([]);
  const [selection, setSelection] = useState<Omit<Anchor, 'id'>>();
  const [evidence, setEvidence] = useState<Anchor[]>([]);
  const [notice, setNotice] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const [query, setQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Segment[]>([]);
  const [draft, setDraft] = useState<Payload>({ title: '', text: '' });
  const [kind, setKind] = useState('annotation');
  const [editing, setEditing] = useState<ResearchRecord>();
  const [method, setMethod] = useState('situating.v1');
  const [mode, setMode] = useState('live');
  const [question, setQuestion] = useState('');
  const [selectedSegments, setSelectedSegments] = useState<string[]>([]);
  const [legacy, setLegacy] = useState<LegacyRecord[]>([]);
  const [url, setUrl] = useState(serviceUrl());
  const [key, setKey] = useState(localStorage.getItem('scriptorium_research_key') || '');
  const [graph, setGraph] = useState<{ nodes: ResearchRecord[]; edges: { from: string; to: string; type: string }[] }>();
  const [compare, setCompare] = useState<string[]>([]);
  const reading = useRef<HTMLDivElement>(null);
  const path = projectId ? projectPath(projectId) : '';
  const activeProject = projects.find(p => p.id === projectId);
  const material = materials.find(m => m.id === assetId);
  const latestVersionId = material?.versions.reduce((latest, v) => v.created_at > (latest?.created_at || 0) ? v : latest, undefined as Material['versions'][number] | undefined)?.id;
  const currentProject = useRef(projectId);

  const act = useCallback(async (fn: () => Promise<void>) => {
    setBusy(true); setError('');
    try { await fn(); } catch (e) { setError(message(e)); } finally { setBusy(false); }
  }, []);

  const chooseProject = useCallback((id: string) => {
    currentProject.current = id;
    localStorage.setItem('scriptorium_research_project', id);
    setProjectId(id); setMaterials([]); setRecords([]); setJobs([]);
    setAssetId(''); setVersionId(''); setSegments([]); setEvidence([]); setSelection(undefined);
    setEditing(undefined); setDraft({ title: '', text: '' }); setSearchResults([]); setSelectedSegments([]);
    setLegacy([]); setGraph(undefined); setCompare([]);
  }, []);

  const applyProjects = useCallback((result: Project[]) => {
    setProjects(result);
    const previous = localStorage.getItem('scriptorium_research_project');
    chooseProject(result.some(p => p.id === previous) ? previous! : result[0]?.id || '');
  }, [chooseProject]);
  const loadProjects = useCallback(async () => {
    applyProjects(await request<Project[]>('/api/v2/projects'));
  }, [applyProjects]);

  const refresh = useCallback(async () => {
    if (!projectId) return;
    const root = projectPath(projectId);
    const [a, r, j] = await Promise.all([request<Material[]>(root + '/materials'),
      request<ResearchRecord[]>(root + '/records'), request<Job[]>(root + '/jobs')]);
    if (currentProject.current !== projectId) return;
    setMaterials(a); setRecords(r); setJobs(j);
  }, [projectId]);

  useEffect(() => { void request<Project[]>('/api/v2/projects').then(applyProjects).catch(e => setError(message(e))); }, [applyProjects]);
  useEffect(() => {
    void refresh().catch(e => setError(message(e)));
  }, [refresh]);
  useEffect(() => {
    if (!projectId) return;
    const timer = setInterval(() => { void refresh().catch(e => setError(message(e))); }, 4000);
    return () => clearInterval(timer);
  }, [projectId, refresh]);
  useEffect(() => {
    if (!assetId || !path) return;
    let ignore = false;
    void request<{ segments: Segment[] }>(`${path}/materials/${assetId}/segments${versionId ? '?version_id=' + versionId : ''}`)
      .then(r => { if (!ignore) setSegments(r.segments); })
      .catch(e => { if (!ignore) setError(message(e)); });
    return () => { ignore = true; };
  }, [assetId, versionId, latestVersionId, path]);

  function changeAsset(id: string, version = '') { setAssetId(id); setVersionId(version); setSegments([]); setSelection(undefined); }

  const captureSelection = useCallback(() => {
    const selected = window.getSelection();
    if (!selected || selected.isCollapsed || selected.rangeCount !== 1) return;
    const range = selected.getRangeAt(0);
    const startElement = range.startContainer.parentElement?.closest<HTMLElement>('[data-segment]');
    const endElement = range.endContainer.parentElement?.closest<HTMLElement>('[data-segment]');
    if (!startElement) return;
    if (startElement !== endElement) { setNotice('请在同一段中选择文字；跨段证据可分次添加。'); return; }
    const prefixRange = document.createRange(); prefixRange.selectNodeContents(startElement);
    prefixRange.setEnd(range.startContainer, range.startOffset);
    const start = codepointOffset(startElement.textContent || '', prefixRange.toString().length);
    const exact = range.toString();
    setSelection(old => old && old.segment_id === startElement.dataset.segment &&
      old.start_codepoint === start && old.exact_quote === exact ? old : {
        segment_id: startElement.dataset.segment!, start_codepoint: start,
        end_codepoint: start + Array.from(exact).length, exact_quote: exact });
  }, []);

  useEffect(() => {
    document.addEventListener('selectionchange', captureSelection);
    return () => document.removeEventListener('selectionchange', captureSelection);
  }, [captureSelection]);

  async function addEvidence() {
    if (!selection) return;
    const a = await request<Anchor>(path + '/anchors', { method: 'POST', body: JSON.stringify(selection) });
    setEvidence(old => [...old, a]); setNotice('已保存证据。填写右侧笔记并保存，即可关联原文。');
  }

  async function locate(id: string) {
    const a = await request<Anchor>(path + '/anchors/' + id);
    setTab('reader'); changeAsset(a.segment!.asset_id, a.segment!.version_id);
    setSelection(a); setNotice(`原文定位：${a.segment!.xml_id}，页序 ${a.segment!.page_label || '未知'}。`);
    setTimeout(() => document.getElementById('segment-' + a.segment_id)?.scrollIntoView({ behavior: 'smooth', block: 'center' }), 250);
  }

  async function saveRecord() {
    const payload = { ...draft, evidence_ids: [...new Set([...(draft.evidence_ids || []), ...evidence.map(a => a.id)])] };
    if (!(payload.text || '').trim() && !(payload.title || '').trim()) throw new Error('请填写标题或内容。');
    await request(path + '/records' + (editing ? '/' + editing.id : ''), {
      method: editing ? 'PUT' : 'POST', body: JSON.stringify({ kind, payload, revision: editing?.revision }) });
    setDraft({ title: '', text: '' }); setEvidence([]); setEditing(undefined);
    setNotice('已保存，原文证据和版本记录将保留。'); await refresh();
  }

  function edit(r: ResearchRecord) { setEditing(r); setKind(r.kind); setDraft(r.payload); setEvidence([]); }

  function renderRecord(r: ResearchRecord) {
    return <article className="rw-card" key={r.id}>
      <div className="rw-row"><span className="rw-label">{kindNames[r.kind] || r.kind} · v{r.revision}</span>
        <span className={r.payload.provider_mode === 'demo' ? 'rw-demo' : 'rw-label'}>{r.payload.provider_mode === 'demo' ? '演示结果' : r.payload.status || '草稿'}</span></div>
      <h3>{r.payload.title || kindNames[r.kind]}</h3><p className="rw-prose">{r.payload.text}</p>
      {r.payload.dimensions && <dl className="rw-dimensions">{Object.entries(r.payload.dimensions).map(([k, v]) => <div key={k}><dt>{k}</dt><dd>{v}</dd></div>)}</dl>}
      {r.payload.findings?.map((f, i) => <section key={i}><h4>{f.title}</h4><p className="rw-prose">{f.text}</p>
        {f.evidence_ids.map(id => <button key={id} onClick={() => void act(() => locate(id))}>查看依据</button>)}</section>)}
      {!!r.payload.open_questions?.length && <details><summary>未决问题</summary><ul>{r.payload.open_questions.map((q, i) => <li key={i}>{q}</li>)}</ul></details>}
      {!!r.payload.coverage?.length && <p className="rw-label">已覆盖 {r.payload.coverage.filter(c => c.status === 'read').length} / {r.payload.coverage.length} 个片段</p>}
      <div className="rw-actions">{r.payload.evidence_ids?.map((id, i) => <button key={id} onClick={() => void act(() => locate(id))}>原文 {i + 1}</button>)}
        <button onClick={() => edit(r)}>编辑</button>
        <button onClick={() => void act(async () => { const history = await request<unknown[]>(`${path}/records/${r.id}/history`); setNotice(`该对象有 ${history.length} 个历史版本，当前版本 v${r.revision}。`); })}>版本信息</button>
      </div>
    </article>;
  }

  const tabKinds: Record<string, string[]> = {
    reader: ['annotation', 'concept'], contexts: ['context'], methods: ['method_report', 'context'],
    arguments: ['question', 'claim', 'position', 'criterion', 'difficulty', 'transition', 'objection', 'response', 'review'],
    parallax: ['standpoint', 'appearance', 'shift', 'parallax', 'branch'], writing: ['manuscript'],
  };
  const shown = records.filter(r => tabKinds[tab]?.includes(r.kind));

  return <div className="research-workbench">
    <header className="rw-header"><div><span className="rw-wordmark">SCRIPTORIUM</span><span className="rw-subtitle">材料 · 构境 · 论证</span></div>
      <select aria-label="研究项目" value={projectId} onChange={e => chooseProject(e.target.value)}><option value="">选择研究项目</option>{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
      <button onClick={() => void act(async () => { const name = prompt('研究项目名称'); if (!name?.trim()) return;
        const p = await request<Project>('/api/v2/projects', { method: 'POST', body: JSON.stringify({ name }) }); await loadProjects(); chooseProject(p.id); })}>新建项目</button>
      <button onClick={() => setTab('settings')}>连接设置</button>
    </header>
    <nav className="rw-tabs">{tabs.map(([value, label]) => <button key={value} aria-current={tab === value ? 'page' : undefined} onClick={() => { setTab(value); setEditing(undefined); setDraft({ title: '', text: '' }); }}>{label}</button>)}</nav>
    {error && <div role="alert" className="rw-error">{error}<button onClick={() => setError('')}>关闭</button></div>}
    {notice && <div role="status" className="rw-notice">{notice}<button onClick={() => setNotice('')}>关闭</button></div>}
    <div className="rw-body">
      <aside className="rw-materials"><h2>{activeProject?.name || '研究材料'}</h2>
        <label className="rw-upload">导入材料<input type="file" accept=".txt,.md,.pdf,.xml,.tei" disabled={!projectId || busy} onChange={e => { const file = e.target.files?.[0]; e.target.value = ''; if (!file) return;
          void act(async () => { const form = new FormData(); form.append('file', file); await request(path + '/imports', { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: form }); setNotice('原件已登记，后台正在处理。请确保 Worker 已启动。'); await refresh(); }); }} /></label>
        <p className="rw-help">支持文本 PDF、TXT、Markdown 与项目 TEI 子集。扫描件保留原件，完整 OCR 尚未接入。</p>
        {materials.map(a => <button className={'rw-material ' + (assetId === a.id ? 'active' : '')} key={a.id} onClick={() => { changeAsset(a.id); setTab('reader'); }}><strong>{a.name}</strong><span>{a.status === 'ready' ? '可阅读' : a.status === 'pending' ? '等待处理' : a.status} · {a.versions.length} 个版本</span></button>)}
        {projectId && !materials.length && <p className="rw-help">导入材料，或使用迁移工具将旧材料加入新版。</p>}
        <form onSubmit={e => { e.preventDefault(); void act(async () => { const r = await request<{ items: Segment[]; pending_index_events: number }>(path + '/search?q=' + encodeURIComponent(query)); setSearchResults(r.items); setNotice(`找到 ${r.items.length} 个片段；待索引 ${r.pending_index_events} 项。`); }); }}>
          <label>原文检索<input value={query} onChange={e => setQuery(e.target.value)} placeholder="词语或短语" /></label><button disabled={!projectId || !query.trim()}>检索</button>
        </form>
        {searchResults.map(s => <button className="rw-search-hit" key={s.id} onClick={() => { changeAsset(s.asset_id, s.version_id); setTab('reader'); setTimeout(() => document.getElementById('segment-' + s.id)?.scrollIntoView({ behavior: 'smooth' }), 250); }}>{s.text.slice(0, 130)}</button>)}
      </aside>

      <main className="rw-main">
        {tab === 'reader' && <>
          <div className="rw-row"><h2>{material?.name || '阅读与批注'}</h2>{material && <div className="rw-actions">
            <select aria-label="文本版本" value={versionId} onChange={e => setVersionId(e.target.value)}><option value="">最新版本</option>{material.versions.map((v, i) => <option key={v.id} value={v.id}>版本 {i + 1} · {v.id.slice(0, 8)}</option>)}</select>
            <button onClick={() => void act(() => download(`${path}/materials/${assetId}/original`, material.name))}>原件</button>
            <button onClick={() => void act(() => download(`${path}/materials/${assetId}/tei${versionId ? '?version_id=' + versionId : ''}`, 'source.xml'))}>TEI</button>
          </div>}</div>
          {!material && <p className="rw-empty">从左侧选择或导入一份材料。选中文字后，可将它保存为证据并关联笔记。</p>}
          <div ref={reading} className="rw-reader" onMouseUp={captureSelection} onKeyUp={captureSelection}>
            {segments.map(s => <section id={'segment-' + s.id} className={selection?.segment_id === s.id ? 'selected' : ''} key={s.id}>
              <div className="rw-segment-meta"><label><input type="checkbox" checked={selectedSegments.includes(s.id)} onChange={e => setSelectedSegments(old => e.target.checked ? [...old, s.id] : old.filter(id => id !== s.id))} />用于分析</label><span>页序 {s.page_label || '—'} · {s.xml_id}</span></div>
              <p data-segment={s.id}>{selection?.segment_id === s.id ? <>{Array.from(s.text).slice(0, selection.start_codepoint).join('')}<mark>{Array.from(s.text).slice(selection.start_codepoint, selection.end_codepoint).join('')}</mark>{Array.from(s.text).slice(selection.end_codepoint).join('')}</> : s.text}</p>
            </section>)}
          </div>
          {material && <details className="rw-card"><summary>书目信息、文本修订与材料管理</summary>
            <form key={material.id + ':' + material.revision} onSubmit={e => { e.preventDefault(); const form = new FormData(e.currentTarget); void act(async () => { await request(`${path}/materials/${assetId}/bibliography`, { method: 'PUT', body: JSON.stringify({ revision: material.revision, metadata: Object.fromEntries(form) }) }); await refresh(); setNotice('书目信息已保存。后续方法任务将记录这份书目信息快照。'); }); }}>
              {[['title', '作品题名'], ['author', '作者'], ['translator', '译者'], ['language', '语言'], ['publication_date', '出版时间'], ['edition_description', '版本说明'], ['source_note', '来源说明']].map(([name, label]) => <label key={name}>{label}<input name={name} defaultValue={String(material.metadata[name] || '')} placeholder="未知可留空" /></label>)}<button>保存书目信息</button>
            </form><p className="rw-help">上传修订后的 TEI 将创建新版本，旧证据仍指向旧版本。</p>
            <input type="file" accept=".xml,.tei" onChange={e => { const f = e.target.files?.[0]; if (!f) return; void act(async () => { await request(`${path}/materials/${assetId}/revisions`, { method: 'POST', body: JSON.stringify({ revision: material.revision, tei: await f.text() }) }); setVersionId(''); await refresh(); const r = await request<{ segments: Segment[] }>(`${path}/materials/${assetId}/segments`); setSegments(r.segments); setNotice('新转录版本已保存。'); }); }} />
            <button className="rw-danger" onClick={() => { if (!confirm('撤回该材料将阻断访问，并清理关联研究对象。继续？')) return; void act(async () => { await request(`${path}/materials/${assetId}`, { method: 'DELETE' }); changeAsset(''); await refresh(); }); }}>撤回材料</button>
          </details>}
          {shown.map(renderRecord)}
        </>}

        {tab === 'contexts' && <><h2>思想构境</h2><p className="rw-help">分别重建文本位置、问题关系、概念配置、话语来源、历史实践与阅读者位置。竞争性档案可以并存。</p>
          <div className="rw-actions"><button onClick={() => { setKind('context'); setDraft({ title: '', text: '', dimensions: { '文本位置': 'unknown', '问题与论敌': 'unknown', '概念配置': 'unknown', '话语来源': 'unknown', '历史实践': 'unknown', '阅读者位置': 'unknown' } }); setEditing(undefined); }}>手动建立构境</button><button onClick={() => { setMethod('situating.v1'); setTab('methods'); }}>使用构境分析</button></div>
          <div className="rw-actions">{shown.map(r => <label key={r.id}><input type="checkbox" checked={compare.includes(r.id)} onChange={e => setCompare(old => e.target.checked ? [...old, r.id] : old.filter(id => id !== r.id))} />{r.payload.title || r.id.slice(0, 8)}</label>)}</div>
          <div className={compare.length > 1 ? 'rw-compare' : ''}>{(compare.length ? shown.filter(r => compare.includes(r.id)) : shown).map(renderRecord)}</div></>}

        {tab === 'methods' && <><h2>方法分析</h2><form className="rw-card" onSubmit={e => { e.preventDefault(); void act(async () => {
          const scope = selectedSegments.length ? selectedSegments : segments.map(s => s.id);
          if (!scope.length) throw new Error('请先在阅读器选择材料或分析片段。');
          await request(path + '/method-runs', { method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: JSON.stringify({ method_id: method, question, segment_ids: scope, provider_mode: mode }) }); setNotice('方法任务已提交，结果将保留范围与证据。'); await refresh();
        }); }}>
          <label>方法<select value={method} onChange={e => setMethod(e.target.value)}><option value="situating.v1">思想构境</option><option value="immanent_critique.v1">黑格尔式内在批判</option><option value="parallax.v1">齐泽克式视差分析</option></select></label>
          <label>研究问题<textarea required value={question} onChange={e => setQuestion(e.target.value)} /></label>
          <label>运行模式<select value={mode} onChange={e => setMode(e.target.value)}><option value="live">真实模型</option><option value="demo">演示流程（不产生学术结论）</option></select></label>
          <p className="rw-help">范围：{selectedSegments.length ? `跨材料选中的 ${selectedSegments.length} 个片段` : `${material?.name || '未选择材料'}，${segments.length} 个片段`}。默认输入上限 30,000 字符、输出上限 4,000 token。超出范围会记为未覆盖。</p>
          <div className="rw-actions"><button type="button" onClick={() => setSelectedSegments(old => [...new Set([...old, ...segments.map(s => s.id)])])}>加入当前材料全部片段</button><button type="button" onClick={() => setSelectedSegments([])}>清空跨材料选择</button></div>
          <button disabled={busy || !projectId}>开始分析</button><p className="rw-help">真实模型将向已配置服务商发送选定文本。方法结论均为可评议候选。</p>
        </form>{shown.map(renderRecord)}</>}

        {(tab === 'arguments' || tab === 'parallax') && <><h2>{tab === 'arguments' ? '论证与概念演化' : '视差与研究分支'}</h2>
          <p className="rw-help">{tab === 'arguments' ? '按立场自身尺度检验困难；经验反例不会自动成为内部矛盾。每条转化应说明依据、保留与否定。' : '先记录观察位置和对象位移，再检查差异是否可以消解；裂隙作为假说保留。'}</p>
          <div className="rw-actions">{(tabKinds[tab] || []).map(k => <button key={k} onClick={() => { setKind(k); setEditing(undefined); setDraft({ title: '', text: '', ...(k === 'parallax' ? { status: 'undetermined' } : {}) }); }}>{kindNames[k]}</button>)}</div>
          <button onClick={() => void act(async () => setGraph(await request(`${path}/graph/${tab === 'arguments' ? 'concept' : 'research'}`)))}>查看{tab === 'arguments' ? '概念演化' : '研究'}关系</button>
          {graph && <div className="rw-card"><h3>关系路径</h3>{graph.edges.length ? graph.edges.map((edge, i) => <p key={i}>{records.find(r => r.id === edge.from)?.payload.title || edge.from} → {records.find(r => r.id === edge.to)?.payload.title || edge.to} <span className="rw-label">{edge.type}</span></p>) : <p>尚未建立关系。创建对象并选择前后立场或父问题。</p>}</div>}
          {shown.map(renderRecord)}</>}

        {tab === 'writing' && <><h2>文稿与研究档案</h2><div className="rw-actions"><button onClick={() => { setKind('manuscript'); setEditing(undefined); setDraft({ title: '研究大纲', text: '', source_record_ids: [] }); }}>新建文稿</button>
          <button disabled={!projectId} onClick={() => void act(() => download(path + '/export?format=md', 'research.md'))}>导出 Markdown</button>
          <button disabled={!projectId} onClick={() => void act(() => download(path + '/export?format=json', 'research.json'))}>导出结构化档案</button>
          <button disabled={!projectId} onClick={() => void act(() => download(path + '/export?format=tei', 'annotations.xml'))}>导出 TEI 标注</button></div>
          <p className="rw-help">文稿可关联论点和原文证据。导出保留材料版本、运行模式、覆盖范围及未决问题。</p>{shown.map(renderRecord)}</>}

        {tab === 'legacy' && <><h2>旧版研究档案</h2><div className="rw-actions"><button onClick={exportBrowserHistory}>导出当前浏览器旧聊天</button>
          <label>导入聊天备份<input type="file" accept=".json" disabled={!projectId} onChange={e => { const f = e.target.files?.[0]; if (!f) return; void act(async () => { const result = await request<{ imported: number }>(path + '/history-import', { method: 'POST', body: await f.text() }); setNotice(`已导入 ${result.imported} 项，原历史保持不变。`); setLegacy(await request(path + '/legacy')); }); }} /></label>
          <button disabled={!projectId} onClick={() => void act(async () => setLegacy(await request(path + '/legacy')))}>读取迁移档案</button></div>
          <p className="rw-help">SQLite 迁移通过独立命令执行，先生成预览报告。这里按原结构保留访谈、分析、Persona 和历史对话；不会重新生成历史结果。</p>
          {legacy.map(r => <details className="rw-card" key={r.id}><summary>{r.table_name} · {r.legacy_key} · {r.status}</summary><pre>{JSON.stringify(r.payload, null, 2)}</pre></details>)}</>}

        {tab === 'settings' && <><h2>研究服务连接</h2><form className="rw-card" onSubmit={e => { e.preventDefault(); void act(async () => { const parsed = new URL(url); if (!['http:', 'https:'].includes(parsed.protocol) || parsed.username || parsed.password || parsed.pathname !== '/') throw new Error('请填写不包含凭证和路径的 HTTP 服务地址。'); localStorage.setItem('scriptorium_research_url', parsed.origin); localStorage.setItem('scriptorium_research_key', key); await loadProjects(); await persistDesktopConnection(parsed.origin); setNotice('已连接研究服务。桌面端重启后将使用外部服务模式。'); }); }}>
          <label>服务地址<input value={url} onChange={e => setUrl(e.target.value)} placeholder="http://127.0.0.1:8010" /></label><label>访问密钥<input type="password" value={key} onChange={e => setKey(e.target.value)} autoComplete="off" /></label><button>保存并连接</button>
          <p className="rw-help">新版需要独立启动研究服务与 Worker；旧版功能可以通过顶栏返回。单人身份由服务端配置，不能通过界面切换为其他成员。</p></form>
          <button onClick={() => void act(async () => { await persistDesktopConnection(''); setNotice('桌面端下次启动时恢复旧版后端自动启动。'); })}>恢复桌面旧版启动方式</button>
          <h2>后台任务</h2>{jobs.map(j => <div className="rw-card rw-row" key={j.id}><div><strong>{j.kind}</strong><p>{j.state}{j.error ? ' · ' + j.error : ''}</p></div><div className="rw-actions">
            {['queued', 'running'].includes(j.state) && <button onClick={() => void act(async () => { await request(`${path}/jobs/${j.id}/cancel`, { method: 'POST' }); await refresh(); })}>取消</button>}
            {j.state === 'failed' && <button onClick={() => void act(async () => { await request(`${path}/jobs/${j.id}/retry`, { method: 'POST' }); await refresh(); })}>重试</button>}
          </div></div>)}</>}
      </main>

      {projectId && !['settings', 'legacy'].includes(tab) && <aside className="rw-editor"><h2>{editing ? '编辑研究对象' : '研究笔记'}</h2>
        {selection && <div className="rw-selection"><blockquote>{selection.exact_quote}</blockquote><button disabled={busy} onClick={() => void act(addEvidence)}>保存为证据</button></div>}
        <p className="rw-label">已关联 {new Set([...(draft.evidence_ids || []), ...evidence.map(a => a.id)]).size} 条证据</p>
        <label>类型<select value={kind} disabled={!!editing} onChange={e => setKind(e.target.value)}>{Object.entries(kindNames).map(([v, label]) => <option key={v} value={v}>{label}</option>)}</select></label>
        <label>标题<input value={draft.title || ''} onChange={e => setDraft({ ...draft, title: e.target.value })} /></label>
        <label>内容<textarea rows={12} value={draft.text || ''} onChange={e => setDraft({ ...draft, text: e.target.value })} /></label>
        {kind === 'context' && Object.entries(draft.dimensions || {}).map(([dimension, value]) => <label key={dimension}>{dimension}<textarea value={value} onChange={e => setDraft({ ...draft, dimensions: { ...draft.dimensions, [dimension]: e.target.value } })} /></label>)}
        {['difficulty', 'transition', 'shift', 'parallax', 'branch', 'review', 'response'].includes(kind) && <>
          {(['transition', 'shift', 'parallax'].includes(kind) ? ['from_id', 'to_id'] : kind === 'branch' ? ['parent_id'] : kind === 'difficulty' ? ['position_id', 'criterion_id'] : ['target_id']).map(field => <label key={field}>{({ from_id: '起始立场／位置', to_id: '后续立场／位置', parent_id: '父问题／分支', position_id: '被检验立场', criterion_id: '检验尺度', target_id: '回应或评议对象' } as Record<string, string>)[field]}
            <select value={String(draft[field as keyof Payload] || '')} onChange={e => setDraft({ ...draft, [field]: e.target.value || undefined })}><option value="">请选择</option>{records.map(r => <option key={r.id} value={r.id}>{kindNames[r.kind]}：{r.payload.title || r.id.slice(0, 8)}</option>)}</select></label>)}
          {kind === 'difficulty' && <label>困难类型<select value={draft.difficulty_type || 'undetermined'} onChange={e => setDraft({ ...draft, difficulty_type: e.target.value })}>{[['undetermined', '未定'], ['fact_error', '事实错误'], ['terminology', '术语混用'], ['counterexample', '经验反例'], ['external', '外部批评'], ['internal', '内在困难']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>}
          {kind === 'transition' && <><label>所依据的困难<select value={draft.difficulty_id || ''} onChange={e => setDraft({ ...draft, difficulty_id: e.target.value })}><option value="">选择内部困难</option>{records.filter(r => r.kind === 'difficulty' && r.payload.difficulty_type === 'internal').map(r => <option key={r.id} value={r.id}>{r.payload.title}</option>)}</select></label>{[['retained', '保留什么'], ['negated', '什么规定失效'], ['reason', '为什么需要这一步转化']].map(([f, label]) => <label key={f}>{label}<textarea value={String(draft[f as keyof Payload] || '')} onChange={e => setDraft({ ...draft, [f]: e.target.value })} /></label>)}</>}
          {kind === 'parallax' && <><label>当前判断<select value={draft.status || 'undetermined'} onChange={e => setDraft({ ...draft, status: e.target.value })}>{[['difference_only', '仅有差异'], ['resolvable', '可消解'], ['candidate_gap', '裂隙候选'], ['reviewed_gap_hypothesis', '经评议的裂隙假说'], ['undetermined', '未定']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select></label>{[['shift', '对象如何位移'], ['excluded_causes', '已检查的可消解原因'], ['rebuttal_conditions', '什么材料可以反驳此判断']].map(([f, label]) => <label key={f}>{label}<textarea value={String(draft[f as keyof Payload] || '')} onChange={e => setDraft({ ...draft, [f]: e.target.value })} /></label>)}</>}
        </>}
        {kind === 'manuscript' && <label>关联论点<select multiple value={draft.source_record_ids || []} onChange={e => setDraft({ ...draft, source_record_ids: [...e.target.selectedOptions].map(o => o.value) })}>{records.filter(r => r.kind === 'claim').map(r => <option key={r.id} value={r.id}>{r.payload.title}</option>)}</select></label>}
        <div className="rw-actions"><button disabled={busy} onClick={() => void act(saveRecord)}>保存{editing ? '新版本' : ''}</button><button onClick={() => { setEditing(undefined); setDraft({ title: '', text: '' }); setEvidence([]); }}>清空编辑</button></div>
      </aside>}
    </div>
    <footer className="rw-footer">{busy ? '正在处理…' : '研究对象与原文分开保存'} · {jobs.filter(j => ['running', 'queued'].includes(j.state)).length} 项后台任务 · 未评议结果保留为候选</footer>
  </div>;
}
