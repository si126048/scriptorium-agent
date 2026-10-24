import { useCallback, useEffect, useRef, useState, lazy, Suspense } from 'react';
import { MarkdownRenderer } from '../../components/ui/MarkdownRenderer';
import { loadConfig, saveConfig } from '../../components/startup/startupConfig';
import { codepointOffset, download, exportBrowserHistory, persistDesktopConnection, projectPath, request, response, sendMessage, serviceUrl } from './api/client';
import type { Anchor, Job, Material, Project, ResearchRecord, Segment } from './api/client';
import './workspace.css';
import './experience.css';
import { useDialogs } from './components/dialog-context';
const ManuscriptEditor=lazy(()=>import('./components/ManuscriptEditor').then(m=>({default:m.ManuscriptEditor})));
const ReportGraph=lazy(()=>import('./components/ReportGraph'));
import { DocumentPane, ResearchProgress } from './components/WorkspaceParts';
import { CitationReview,type CitationDraft } from './components/CitationReview';
import { ResearchComposer,type Tool } from './components/ResearchComposer';
import { ModelProviderForm } from './components/ModelProviderForm';
import { useWorkspaceUI } from './state';
import { useConversationEvents } from './hooks/useConversationEvents';
import { queryClient } from './api/query';

interface Conversation { id: string; title: string; archived: boolean; revision: number; workspace: { selection?:Omit<Anchor,'id'>; draft?: string; asset_ids?: string[]; open_artifact?: string; open_material?: string; scroll?: number; document_scroll?: number; panel?: string; version_id?: string; edit_text?: string; edit_title?: string } }
interface Message { id: string; role: string; content: string; artifact_ids: string[]; metadata: { provider_mode?: string; interview_id?: string; job_id?: string; decision_id?: string } }
interface Participant { id: string; pseudonym: string; permissions: Record<string, boolean>; withdrawn_at: string | null }
interface Persona { id: string; name: string; participant_id: string; status: string }
interface Interview { id: string; participant_id: string; state: string; current_question?: { id: string; text: string } | null; conversation_id?: string }

interface Decision { id: string; run_id: string; kind: string; payload: { question: string; suggested_tokens?: number; premise?: string } }
interface VersionDiffRow { xml_id: string; state: 'same' | 'added' | 'removed' | 'changed'; before?: string; now?: string }
interface VersionDiff { oldLabel: string; newLabel: string; rows: VersionDiffRow[]; counts: Record<string, number> }
type Panel = 'none' | 'material' | 'artifact' | 'settings' | 'people' | 'interview' | 'search';
const err = (e: unknown) => e instanceof Error ? e.message : String(e);

export default function UnifiedWorkspace() {
  const { ask, confirm: confirmDialog } = useDialogs();
  const { sidebarOpen, toggleSidebar, quiet, documentWidth, setDocumentWidth, setQuiet } = useWorkspaceUI();
  const [liveDrafts,setLiveDrafts]=useState<Record<string,string>>({});
  const [newMessages,setNewMessages]=useState(false);
  const documentRequest=useRef(0);
  const documentTrail=useRef<{panel:Panel;assetId:string;versionId:string;artifact?:ResearchRecord;editText:string;editTitle:string;editorJson?:Record<string,unknown>;segments:Segment[];selection?:Omit<Anchor,'id'>;scroll:number}[]>([]);
  const [trailLength,setTrailLength]=useState(0);
  const [graphKind,setGraphKind]=useState<'research'|'concept'>();
  const [editorJson, setEditorJson] = useState<Record<string, unknown>>();
  const [citationDrafts,setCitationDrafts] = useState<CitationDraft[]>([]);
  const [usage,setUsage] = useState({used_tokens:0,unknown_calls:0});
  const [librarySearch,setLibrarySearch] = useState('');
  const sendKey = useRef<{text:string;key:string}|undefined>(undefined);
  const [projects, setProjects] = useState<Project[]>([]);
  const [pid, setPid] = useState(localStorage.getItem('scriptorium_research_project') || '');
  const [conversations, setConversations] = useState<Conversation[]>([]);
  const [cid, setCid] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [materials, setMaterials] = useState<Material[]>([]);
  const [artifacts, setArtifacts] = useState<ResearchRecord[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [people, setPeople] = useState<Participant[]>([]);
  const [personas, setPersonas] = useState<Persona[]>([]);
  const [oldAnalyses, setOldAnalyses] = useState<{id:string;state:string}[]>([]);
  const [workspaceReady,setWorkspaceReady] = useState(false);
  const [interviews, setInterviews] = useState<Interview[]>([]);
  const [scrollPosition, setScrollPosition] = useState(0);
  const [documentScroll, setDocumentScroll] = useState(0);
  const documentPane = useRef<HTMLDivElement>(null);
  const [panel, setPanel] = useState<Panel>('none');
  const [assetId, setAssetId] = useState('');
  const [versionId, setVersionId] = useState('');
  const [segments, setSegments] = useState<Segment[]>([]);
  const [selected, setSelected] = useState<string[]>([]);
  const [selection, setSelection] = useState<Omit<Anchor, 'id'>>();
  const [artifact, setArtifact] = useState<ResearchRecord>();
  const activeArtifact=useRef<string|undefined>(undefined);
 useEffect(()=>{activeArtifact.current=artifact?.id;},[artifact?.id]);
  const [editText, setEditText] = useState('');
  const [editTitle, setEditTitle] = useState('');
  const [editFields, setEditFields] = useState<Record<string, string>>({});
  const [bibliography, setBibliography] = useState<Record<string, string>>({});
  const [searchAuthor, setSearchAuthor] = useState('');
  const [searchYear, setSearchYear] = useState('');
  const [note, setNote] = useState('');
  const [draft, setDraft] = useState('');
  const [tool, setTool] = useState<Tool>('ask');
  const [method, setMethod] = useState('');
  const [mode, setMode] = useState<'live' | 'demo'>('live');
  const [participantId, setParticipantId] = useState('');
  const [personaId, setPersonaId] = useState('');
  const [activeInterview, setActiveInterview] = useState<Interview>();
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [library, setLibrary] = useState(false);
  const [documents, setDocuments] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [hits, setHits] = useState<Segment[]>([]);
  const [serviceAddress, setServiceAddress] = useState(serviceUrl());
  const [apiKey, setApiKey] = useState(localStorage.getItem('scriptorium_research_key') || '');
  const [startup, setStartup] = useState(loadConfig());
  const [compare, setCompare] = useState<ResearchRecord[]>();
  const [versionDiff, setVersionDiff] = useState<VersionDiff>();
  const [originalUrl, setOriginalUrl] = useState('');
  const feed = useRef<HTMLDivElement>(null);
  const active = useRef({ pid, cid });
  const workspaceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const root = projectPath(pid);
  const current = conversations.find(c => c.id === cid);
  const currentMaterial = materials.find(a => a.id === assetId);

  const action = useCallback(async (fn: () => Promise<void>) => {
    setBusy(true); setError('');
    try { await fn(); } catch (e) { setError(err(e)); } finally { setBusy(false); }
  }, []);

  const loadProject = useCallback(async (projectId: string) => {
    if (!projectId) return;
    const p = projectPath(projectId);
    const [cs, ms, rs, js, ds, ps, ss, ivs, oldRuns, citationReviews, calls] = await Promise.all([
      request<Conversation[]>(p + '/conversations'), request<Material[]>(p + '/materials'),
      request<ResearchRecord[]>(p + '/records'), request<Job[]>(p + '/jobs'), request<Decision[]>(p + '/decisions'),
      request<Participant[]>(p + '/participants'), request<Persona[]>(p + '/personas'), request<Interview[]>(p + '/interviews'), request<{id:string;state:string}[]>(p + '/analysis-runs'),request<CitationDraft[]>(p+'/citation-drafts'),request<{totals:{used_tokens:number;unknown_calls:number}}>(p+'/model-calls')]);
    if (active.current.pid !== projectId) return;
    setConversations(cs); setMaterials(ms); setArtifacts(rs); setJobs(js); setDecisions(ds); setPeople(ps); setPersonas(ss); setInterviews(ivs); setOldAnalyses(oldRuns); setCitationDrafts(citationReviews);setUsage(calls.totals);
  }, []);

  const chooseConversation = useCallback(async (projectId: string, conversationId: string, cs: Conversation[]) => {
    setWorkspaceReady(false);
    active.current = { pid: projectId, cid: conversationId };
    if(window.innerWidth<850&&useWorkspaceUI.getState().sidebarOpen)useWorkspaceUI.getState().toggleSidebar();
    setCid(conversationId); setMessages([]); setActiveInterview(undefined); setPanel('none'); setCompare(undefined);
    localStorage.setItem(`scriptorium_last_conversation:${projectId}`, conversationId);
    const c = cs.find(c => c.id === conversationId);
    const local = localStorage.getItem(`scriptorium_draft:${projectId}:${conversationId}`);
    // Unsaved document edits survive a session switch even when the workspace PUT lost a race.
    const localDoc = JSON.parse(localStorage.getItem(`scriptorium_doc:${projectId}:${conversationId}`) || 'null') as
      { record_id?: string; title?: string; text?: string; editor_json?:Record<string,unknown> } | null;
    setDraft(local ?? c?.workspace.draft ?? ''); setSelected(c?.workspace.asset_ids || []);
    if (conversationId) {
      const result = await request<Message[]>(`${projectPath(projectId)}/conversations/${conversationId}/messages`);
      if (active.current.pid !== projectId || active.current.cid !== conversationId) return;
      setMessages(result);
      setScrollPosition(c?.workspace.scroll || 0); setDocumentScroll(c?.workspace.document_scroll || 0);
      setTimeout(() => { if (feed.current) feed.current.scrollTop = c?.workspace.scroll || 0; }, 80);
      const w = c?.workspace;
      if (w?.panel === 'material' && w.open_material) {
        const data = await request<{segments:Segment[]}>(`${projectPath(projectId)}/materials/${w.open_material}/segments${w.version_id ? '?version_id='+w.version_id : ''}`);
        if (active.current.pid !== projectId || active.current.cid !== conversationId) return;
        setAssetId(w.open_material);setVersionId(w.version_id || '');setSegments(data.segments);setSelection(w.selection);setPanel('material');
      } else if (w?.panel === 'artifact' && w.open_artifact) {
        const a = await request<ResearchRecord>(`${projectPath(projectId)}/artifacts/${w.open_artifact}`);
        if (active.current.pid !== projectId || active.current.cid !== conversationId) return;
        const unsaved = localDoc && localDoc.record_id === a.id ? localDoc : null;
        setArtifact(a);setEditorJson(unsaved?.editor_json ?? a.payload.editor_json);
        setEditTitle(unsaved?.title ?? w.edit_title ?? a.payload.title ?? '');
        setEditText(unsaved?.text ?? w.edit_text ?? a.payload.text ?? '');
        setPanel('artifact');
      }
      setWorkspaceReady(true);
      setTimeout(() => {if(documentPane.current) documentPane.current.scrollTop=w?.document_scroll || 0;},80);
    }
  }, []);

  const chooseProject = useCallback(async (projectId: string) => {
    void queryClient.cancelQueries({predicate:q => typeof q.queryKey[2] === 'string' && !q.queryKey[2].includes(projectPath(projectId))});
    active.current = { pid: projectId, cid: '' };
    setPid(projectId); setCid(''); setMessages([]); setConversations([]); setMaterials([]); setArtifacts([]);
    documentTrail.current=[];setTrailLength(0);setLiveDrafts({});setNewMessages(false);setGraphKind(undefined);
    setPanel('none'); setDraft(''); setSelected([]); setParticipantId(''); setPersonaId(''); setSegments([]); setSelection(undefined);
    localStorage.setItem('scriptorium_research_project', projectId);
    if (!projectId) return;
    await loadProject(projectId);
    const cs = await request<Conversation[]>(projectPath(projectId) + '/conversations');
    if (active.current.pid !== projectId) return;
    const saved = localStorage.getItem(`scriptorium_last_conversation:${projectId}`);
    const latest = cs.find(c => c.id === saved && !c.archived) || cs.find(c => !c.archived);
    if (latest) await chooseConversation(projectId, latest.id, cs);
  }, [chooseConversation, loadProject]);

  useEffect(() => {
    void request<Project[]>('/api/v2/projects').then(async ps => {
      setProjects(ps);
      const preferred = localStorage.getItem('scriptorium_research_project');
      await chooseProject(ps.some(p => p.id === preferred) ? preferred! : ps[0]?.id || '');
    }).catch(e => setError(err(e)));
  }, [chooseProject]);

  useEffect(() => {
    if (!pid) return;
    let stopped = false;
    const timer = setInterval(() => {
      void loadProject(pid).catch(e => { if (!stopped) setError(err(e)); });
      if (cid) void request<Message[]>(`${projectPath(pid)}/conversations/${cid}/messages`).then(ms => {
        if (!stopped && active.current.cid === cid) setMessages(old => JSON.stringify(old) === JSON.stringify(ms) ? old : ms);
      }).catch(e => { if (!stopped) setError(err(e)); });
    }, 10000);
    return () => { stopped = true; clearInterval(timer); };
  }, [pid, cid, loadProject]);

  useEffect(() => {
    if (!pid || !cid || !current || !workspaceReady) return;
    localStorage.setItem(`scriptorium_draft:${pid}:${cid}`, draft);
    if (panel === 'artifact' && artifact) {
      const stored = JSON.stringify({ record_id: artifact.id, title: editTitle, text: editText, editor_json:editorJson });
      const saved = JSON.stringify({ record_id: artifact.id, title: artifact.payload.title ?? '', text: artifact.payload.text ?? '' });
      if (stored === saved) localStorage.removeItem(`scriptorium_doc:${pid}:${cid}`);
      else localStorage.setItem(`scriptorium_doc:${pid}:${cid}`, stored);
    }
    const workspace = {...current.workspace,draft,asset_ids:selected,scroll:scrollPosition,document_scroll:documentScroll,
      panel,selection,open_material:assetId,version_id:versionId,open_artifact:artifact?.id,edit_text:editText,edit_title:editTitle};
    if (JSON.stringify(current.workspace) === JSON.stringify(workspace)) return;
    if (workspaceTimer.current) clearTimeout(workspaceTimer.current);
    workspaceTimer.current = setTimeout(() => {
      const save = (revision: number, retried: boolean) => {
        void request<Conversation>(`${projectPath(pid)}/conversations/${cid}`, { method: 'PUT', body: JSON.stringify({
          revision, workspace }) })
          .then(updated => setConversations(cs => cs.map(c => c.id === updated.id ? updated : c)))
          .catch(async e => {
            if (String(e).includes('409')) {
              if (retried) return;
              // Another window wrote first: adopt its revision and try once, keeping local edits.
              const cs = await request<Conversation[]>(`${projectPath(pid)}/conversations`).catch(() => undefined);
              const fresh = cs?.find(c => c.id === cid);
              if (cs) setConversations(cs);
              if (fresh) {setWorkspaceReady(false);setNotice('另一窗口已更新会话，本地草稿已保留。重新进入会话以采用最新版本。');}
              return;
            }
            setError(err(e));
          });
      };
      save(current.revision, false);
    }, 900);
    return () => { if (workspaceTimer.current) clearTimeout(workspaceTimer.current); };
  }, [draft, selected, pid, cid, current, workspaceReady, scrollPosition, documentScroll, panel, assetId, versionId, artifact, editText, editTitle, editorJson, selection]);

  useEffect(()=>{
    if(!pid||!artifact||artifact.kind!=='manuscript'||!editorJson||JSON.stringify(editorJson)===JSON.stringify(artifact.payload.editor_json))return;
    const record=artifact;const project=pid;const timer=setTimeout(()=>{void request<ResearchRecord>(`${projectPath(project)}/records/${record.id}`,{method:'PUT',body:JSON.stringify({kind:record.kind,revision:record.revision,payload:{...record.payload,title:editTitle,editor_json:editorJson,text:editText,status:'researcher_revision'}})}).then(updated=>{if(active.current.pid===project&&activeArtifact.current===record.id){setArtifact(updated);setEditText(updated.payload.text||'');}}).catch(e=>setError('文稿自动保存未完成；草稿已保留。'+err(e)));},1800);
    return()=>clearTimeout(timer);
  },[pid,artifact,editorJson,editTitle,editText]);

  async function newResearch() {
    if (!pid) throw new Error('请先创建或选择项目。');
    const c = await request<Conversation>(root + '/conversations', { method: 'POST', body: JSON.stringify({ title: '新研究' }) });
    const cs = [c, ...conversations]; setConversations(cs); await chooseConversation(pid, c.id, cs);
  }

  function rememberDocument(){
    if(panel==='material'||panel==='artifact'){documentTrail.current.push({panel,assetId,versionId,artifact,editText,editTitle,editorJson,segments,selection,scroll:documentPane.current?.scrollTop||0});if(documentTrail.current.length>12)documentTrail.current.shift();setTrailLength(documentTrail.current.length);}
  }
  function previousDocument(){documentRequest.current++;const old=documentTrail.current.pop();if(!old)return;setTrailLength(documentTrail.current.length);setPanel(old.panel);setAssetId(old.assetId);setVersionId(old.versionId);setArtifact(old.artifact);setEditText(old.editText);setEditTitle(old.editTitle);setEditorJson(old.editorJson);setSegments(old.segments);setSelection(old.selection);setTimeout(()=>{if(documentPane.current)documentPane.current.scrollTop=old.scroll;},50);}
  async function openMaterial(id: string, version = '', anchor?: Anchor) {
    rememberDocument();
    const project=pid;const conversation=cid;const requestId=++documentRequest.current;
    setBibliography(Object.fromEntries(Object.entries(materials.find(m => m.id === id)?.metadata || {}).filter(([k, v]) => ['title', 'author', 'translator', 'language', 'publication_date', 'purpose', 'source_note'].includes(k) && typeof v === 'string')) as Record<string,string>);
    if(window.innerWidth<850&&useWorkspaceUI.getState().sidebarOpen)useWorkspaceUI.getState().toggleSidebar();
    setAssetId(id); setVersionId(version); setPanel('material'); setOriginalUrl(''); setVersionDiff(undefined);
    const data = await request<{ segments: Segment[] }>(`${root}/materials/${id}/segments${version ? '?version_id=' + version : ''}`);
    if(active.current.pid!==project||active.current.cid!==conversation||documentRequest.current!==requestId)return;
    setSegments(data.segments); setSelection(anchor);
    if (anchor) setTimeout(() => document.getElementById(`uw-segment-${anchor.segment_id}`)?.scrollIntoView({ block: 'center', behavior: 'smooth' }), 100);
  }

  async function openArtifact(id: string) {
    if(window.innerWidth<850&&useWorkspaceUI.getState().sidebarOpen)useWorkspaceUI.getState().toggleSidebar();
    rememberDocument();
    const project=pid;const conversation=cid;const requestId=++documentRequest.current;
    const a = await request<ResearchRecord>(root + '/artifacts/' + id);
    if(active.current.pid!==project||active.current.cid!==conversation||documentRequest.current!==requestId)return;
    setEditFields(Object.fromEntries(Object.entries(a.payload).filter(([k, v]) => ['retained', 'negated', 'reason', 'shift', 'excluded_causes', 'rebuttal_conditions', 'difficulty_type'].includes(k) && typeof v === 'string')) as Record<string,string>);
    setArtifact(a);setEditorJson(a.payload.editor_json); setEditTitle(a.payload.title || '研究文档'); setEditText(a.payload.text || '');
    setPanel('artifact'); setCompare(undefined);
  }

  async function locate(id: string) {
    const a = await request<Anchor>(root + '/anchors/' + id);
    await openMaterial(a.segment!.asset_id, a.segment!.version_id, a);
  }

  async function compareVersion() {
    const versions = [...(currentMaterial?.versions || [])].sort((a, b) => a.created_at - b.created_at);
    const index = versionId ? versions.findIndex(v => v.id === versionId) : versions.length - 1;
    if (versions.length < 2) { setNotice('此材料只有一个文本版本；修订或 OCR 之后才可对照。'); return; }
    if (index <= 0) { setNotice('请先在新版本上查看，再与上一版本对照。'); return; }
    const [newer, older] = await Promise.all([
      request<{ segments: Segment[] }>(`${root}/materials/${assetId}/segments?version_id=${versions[index].id}`),
      request<{ segments: Segment[] }>(`${root}/materials/${assetId}/segments?version_id=${versions[index - 1].id}`)]);
    const before = new Map(older.segments.map(s => [s.xml_id, s.text]));
    const rows: VersionDiffRow[] = [];
    for (const segment of newer.segments) {
      const previous = before.get(segment.xml_id);
      before.delete(segment.xml_id);
      rows.push({ xml_id: segment.xml_id, state: previous === undefined ? 'added' : previous === segment.text ? 'same' : 'changed',
        before: previous, now: segment.text });
    }
    for (const [xml_id, text] of before) rows.push({ xml_id, state: 'removed', before: text });
    const counts = rows.reduce((total, row) => ({ ...total, [row.state]: (total[row.state] || 0) + 1 }), {} as Record<string, number>);
    setVersionDiff({ oldLabel: '版本 ' + index, newLabel: '版本 ' + (index + 1), rows, counts });
  }

  function capture() {
    const selection = window.getSelection(); if (!selection || selection.isCollapsed || !selection.rangeCount) return;
    const range = selection.getRangeAt(0);
    const a = range.startContainer.parentElement?.closest<HTMLElement>('[data-source]');
    const b = range.endContainer.parentElement?.closest<HTMLElement>('[data-source]');
    if (!a || a !== b) return;
    const before = document.createRange(); before.selectNodeContents(a); before.setEnd(range.startContainer, range.startOffset);
    const start = codepointOffset(a.textContent || '', before.toString().length);
    setSelection({ segment_id: a.dataset.source!, start_codepoint: start,
      end_codepoint: start + Array.from(range.toString()).length, exact_quote: range.toString() });
  }

  useEffect(() => {
    if (panel !== 'material') return;
    document.addEventListener('selectionchange', capture);
    return () => document.removeEventListener('selectionchange', capture);
  }, [panel]);

  async function saveSelection() {
    if (!selection) return;
    const a = await request<Anchor>(root + '/anchors', { method: 'POST', body: JSON.stringify(selection) });
    const record = await request<ResearchRecord>(root + '/records', { method: 'POST', body: JSON.stringify({
      kind: 'annotation', payload: { title: selection.exact_quote.slice(0, 28), text: note || selection.exact_quote,
        evidence_ids: [a.id], status: 'draft' } }) });
    setNote(''); setNotice('笔记已保存并关联原文。'); await loadProject(pid); await openArtifact(record.id);
  }

  async function send() {
    if (!draft.trim()) return;
    const project=pid;const submittedDraft=draft;
    let conversationId = cid;
    if (!conversationId) {
      const c = await request<Conversation>(root + '/conversations', { method: 'POST', body: JSON.stringify({ title: draft.slice(0, 24) }) });
      if(active.current.pid!==project||active.current.cid!==cid)return;
      conversationId = c.id; setWorkspaceReady(true); setCid(c.id); active.current.cid = c.id; setConversations(cs => [c, ...cs]);
    }
    if (activeInterview?.current_question) {
      await request(`${root}/interviews/${activeInterview.id}/turns`, { method: 'POST', body: JSON.stringify({
        question_id: activeInterview.current_question.id, answer_text: draft }) });
      setActiveInterview(await request(`${root}/interviews/${activeInterview.id}`));
    } else {
      const fingerprint=JSON.stringify([draft,tool,selected,selection,mode,participantId,personaId,method]);
      if(sendKey.current?.text!==fingerprint)sendKey.current={text:fingerprint,key:crypto.randomUUID()};
      await sendMessage(pid,conversationId,{text:draft,tool,
          ...(selection ? {scope:[{asset_id:assetId,version_id:segments.find(s=>s.id===selection.segment_id)?.version_id,...selection}]} : {asset_ids:selected}), provider_mode:mode,
          participant_id:participantId||null,persona_id:personaId||null,
          methods:method ? [method as 'situating.v1'|'immanent_critique.v1'|'parallax.v1'] : []},sendKey.current.key);
    }
    if(active.current.pid!==project||active.current.cid!==conversationId)return;
    sendKey.current=undefined;
    setDraft(value=>value===submittedDraft?'':value); localStorage.removeItem(`scriptorium_draft:${pid}:${conversationId}`);
    const nextMessages=await request<Message[]>(`${root}/conversations/${conversationId}/messages`);
    if(active.current.pid!==project||active.current.cid!==conversationId)return;
    setMessages(nextMessages);
    await loadProject(pid); if(feed.current && feed.current.scrollHeight-feed.current.scrollTop-feed.current.clientHeight<200)setTimeout(()=>feed.current?.scrollTo({top:feed.current.scrollHeight,behavior:'smooth'}),100);
  }

  async function deepen(record: ResearchRecord) {
    if (!pid || !cid) throw new Error('请先选择会话。');
    const question = String(record.payload.question || record.payload.title || draft);
    await sendMessage(pid, cid, { text: question, tool: 'research', scope: record.payload.scope,
      provider_mode: mode, token_budget: 120000 }, crypto.randomUUID());
    setNotice('已按这次阅读范围提交完整研究；进度显示在对话下方。');
    await loadProject(pid);
    setMessages(await request(`${root}/conversations/${cid}/messages`));
    setPanel('none');
  }

  async function upload(file: File) {
    const form = new FormData(); form.append('file', file);
    const job = await request<Job & { payload: { asset_id: string } }>(root + '/imports', {
      method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: form });
    setSelected(xs => [...new Set([...xs, job.payload.asset_id])]); setLibrary(true);
    setNotice('材料已加入项目，正在处理。完成后可阅读和研究。'); await loadProject(pid);
  }

  const busyJobs = jobs.filter(j => ['running', 'queued'].includes(j.state));
  // UI-04: unsaved edits and the saved version must stay distinguishable after a reload.
  const artifactDirty = !!artifact && ((editorJson ? JSON.stringify(editorJson)!==JSON.stringify(artifact.payload.editor_json) : editText !== (artifact.payload.text || ''))
    || editTitle !== (artifact.payload.title || '')
    || Object.entries(editFields).some(([key, value]) =>
      value !== String((artifact.payload as Record<string, unknown>)[key] ?? '')));
  const card = (a: ResearchRecord) => <article className="uw-artifact-content" key={a.id}>
    <h2>{a.payload.title}</h2>{a.payload.provider_mode === 'demo' && <span className="uw-badge">演示 · 非学术结论</span>}
    <MarkdownRenderer content={a.payload.text || ''} />
    {a.payload.dimensions && <dl>{Object.entries(a.payload.dimensions).map(([name, text]) => <div key={name}><dt>{name}</dt><dd>{text}</dd></div>)}</dl>}
    {a.payload.findings?.map((f, i) => <section key={i}><h3>{f.title}</h3><MarkdownRenderer content={f.text} />{f.evidence_ids?.map(id => <button key={id} onClick={() => void action(() => locate(id))}>查看依据</button>)}</section>)}
    {!!a.payload.open_questions?.length && <details><summary>未决问题</summary><ul>{a.payload.open_questions.map((q, i) => <li key={i}>{q}</li>)}</ul></details>}
    {a.payload.plan && <details><summary>检索与覆盖</summary><p>检索方式：{String(a.payload.plan.retrieval)}；命中 {String(a.payload.plan.hits ?? '—')}；阅读 {a.payload.coverage?.filter(c => c.status === 'read').length ?? 0} 段，未覆盖 {a.payload.coverage?.filter(c => c.status === 'unread').length ?? 0} 段。</p>{!!a.payload.followups?.length && <ul>{a.payload.followups.map((q, i) => <li key={i}>{q}</li>)}</ul>}</details>}
    {!!a.payload.evidence_ids?.length && <div className="uw-inline-actions">{a.payload.evidence_ids.map((id, i) => <button key={id} onClick={() => void action(() => locate(id))}>原文 {i + 1}</button>)}</div>}
  </article>;

  useConversationEvents(pid,cid,()=>{void loadProject(pid);if(cid)void request<Message[]>(`${projectPath(pid)}/conversations/${cid}/messages`).then(ms=>{if(active.current.pid===pid&&active.current.cid===cid){setMessages(ms);if(feed.current && feed.current.scrollHeight-feed.current.scrollTop-feed.current.clientHeight>180)setNewMessages(true);}});},event=>{if(event.type==='message.delta')setLiveDrafts(old=>({...old,[event.payload.job_id]:(old[event.payload.job_id]||'')+event.payload.text}));if(event.type==='message.created'||event.type==='job.progress'){const id=event.payload.message?.metadata?.job_id || (['failed','cancelled','running'].includes(event.payload.state||'')?event.payload.job_id:undefined);if(id)setLiveDrafts(old=>{const next={...old};delete next[id];return next;});}});

  return <div className={'unified-workspace ' + (panel !== 'none' ? 'uw-document-open ' : '') + (!sidebarOpen ? 'uw-sidebar-collapsed ' : '') + (quiet ? 'uw-quiet' : '')}>
    <aside className="uw-sidebar" aria-label="项目导航"><button className="uw-mobile-close" aria-label="关闭项目导航" onClick={toggleSidebar}>×</button>
      <div className="uw-brand">H<span> / </span>SCRIPTORIUM<small>RESEARCH ARCHIVE</small></div>
      <select aria-label="研究项目" value={pid} onChange={e => void action(() => chooseProject(e.target.value))}><option value="">选择项目</option>{projects.map(p => <option key={p.id} value={p.id}>{p.name}</option>)}</select>
      <div className="uw-inline-actions"><button onClick={() => void action(async () => { const name = await ask('项目名称'); if (!name) return;
        const p = await request<Project>('/api/v2/projects', { method: 'POST', body: JSON.stringify({ name }) }); setProjects(ps => [...ps, p]); await chooseProject(p.id); })}>＋ 项目</button><button className="uw-primary" disabled={!pid} onClick={() => void action(newResearch)}>＋ 新研究</button></div>
      <button className="uw-sidebar-action" onClick={() => setPanel('search')}>⌕ 搜索项目材料</button>
      <h2>研究会话</h2><div className="uw-session-list">{conversations.filter(c => !c.archived).map(c => <button className={c.id === cid ? 'active' : ''} key={c.id} onClick={() => void action(() => chooseConversation(pid, c.id, conversations))}>{c.title}</button>)}</div>
      <button className="uw-sidebar-action" onClick={() => setLibrary(!library)}>材料 <span>{materials.length} {library ? '−' : '+'}</span></button>
      {library && <div className="uw-library"><label className="uw-upload">＋ 导入材料<input type="file" accept=".txt,.md,.pdf,.xml,.tei" disabled={!pid} onChange={e => { const f = e.target.files?.[0]; e.target.value = ''; if (f) void action(() => upload(f)); }} /></label>
        <input aria-label="筛选材料" placeholder="查找项目材料…" value={librarySearch} onChange={e=>setLibrarySearch(e.target.value)} />{materials.filter(m=>String(m.metadata.title || m.name).toLowerCase().includes(librarySearch.toLowerCase())).map(m => <div className="uw-material" key={m.id}><input aria-label={'选择 ' + m.name} type="checkbox" checked={selected.includes(m.id)} onChange={e => setSelected(xs => e.target.checked ? [...xs, m.id] : xs.filter(id => id !== m.id))} /><button onClick={() => void action(() => openMaterial(m.id))}>{String(m.metadata.title || m.name)}<small>{m.status === 'ready' ? '可阅读' : m.status === 'pending' ? '处理中' : '需处理'}</small></button></div>)}</div>}
      <button className="uw-sidebar-action" onClick={() => setDocuments(!documents)}>项目文档 <span>{documents ? '−' : '+'}</span></button>
      {documents && <div className="uw-library">{oldAnalyses.map(r => <button className="uw-document-item" key={r.id} onClick={() => void action(async () => {const a=await request<ResearchRecord>(`${root}/analysis-runs/${r.id}/artifact`,{method:"POST"});await openArtifact(a.id);})}>历史分析 · {r.state}</button>)}{artifacts.map(a => <button className="uw-document-item" key={a.id} onClick={() => void action(() => openArtifact(a.id))}>{a.payload.title || '研究笔记'}</button>)}</div>}
      <div className="uw-sidebar-bottom"><button onClick={() => setPanel('settings')}>设置与档案</button><span>{busyJobs.length ? `${busyJobs.length} 项处理中` : 'LOCAL ARCHIVE / READY'}</span></div>
    </aside>

    <main className="uw-conversation">
      <header className="uw-conversation-header"><button className="uw-nav-toggle" onClick={toggleSidebar} aria-label="切换项目导航">☰</button><div><small>PROJECT / {projects.find(p => p.id === pid)?.name || '未选择'}</small><h1>{current?.title || '从一个研究问题开始'}</h1></div>
        {current && <details className="uw-header-menu"><summary>•••</summary><button onClick={() => void action(async () => { const title = await ask('会话名称', current.title); if (!title) return; await request(`${root}/conversations/${cid}`, { method: 'PUT', body: JSON.stringify({ revision: current.revision, title }) }); await loadProject(pid); })}>重命名</button><button onClick={() => void action(async () => { await request(`${root}/conversations/${cid}`, { method: 'PUT', body: JSON.stringify({ revision: current.revision, archived: true }) }); await chooseProject(pid); })}>归档会话</button></details>}
      </header>
      {error && <div className="uw-error" role="alert">{error}<button onClick={() => setError('')}>关闭</button></div>}
      {notice && <div className="uw-notice" role="status">{notice}<button onClick={() => setNotice('')}>关闭</button></div>}
      <div className="uw-feed" ref={feed} onScroll={e => setScrollPosition(e.currentTarget.scrollTop)}>
        {!messages.length && <section className="uw-welcome"><div className="uw-crosshair">＋</div><h2>让问题、材料与解释在这里相遇。</h2><p>导入材料或开始访谈，然后提出研究问题。依据与文稿会在右侧打开。</p><div className="uw-welcome-actions"><button disabled={!pid} onClick={() => setLibrary(true)}>导入研究材料</button><button disabled={!pid} onClick={() => setPanel('people')}>开始研究访谈</button></div></section>}
        {messages.map(m => <article key={m.id} className={'uw-message ' + m.role}><small>{m.role === 'user' ? '研究者' : 'SCRIPTORIUM'}{m.metadata.provider_mode === 'demo' ? ' / 演示' : ''}</small><MarkdownRenderer content={m.content} />
          {!!m.artifact_ids.length && <div className="uw-result-actions">{m.artifact_ids.map(id => <button key={id} onClick={() => void action(() => openArtifact(id))}>↗ {artifacts.find(a => a.id === id)?.payload.title || '打开研究文档'}</button>)}</div>}
          {m.metadata.interview_id && <button onClick={() => void action(async () => { setActiveInterview(await request(`${root}/interviews/${m.metadata.interview_id}`)); setPanel('interview'); })}>继续此访谈</button>}
        </article>)}
        {Object.entries(liveDrafts).map(([id,text])=><article className="uw-message assistant" key={id}><small>SCRIPTORIUM / 正在生成的草稿</small><MarkdownRenderer content={text}/></article>)}
        {newMessages&&<button className="uw-new-messages" onClick={()=>{feed.current?.scrollTo({top:feed.current.scrollHeight,behavior:quiet?'auto':'smooth'});setNewMessages(false);}}>查看新进展 ↓</button>}
        {decisions.map(d => <section className="uw-decision" key={d.id}><h3>需要你的决定</h3><p>{d.payload.question}</p><p>{d.payload.premise}</p><div className="uw-inline-actions"><button onClick={() => void action(async () => { await request(`${root}/decisions/${d.id}`, { method: 'POST', body: JSON.stringify({ accept: true, additional_tokens: Math.max(40000, d.payload.suggested_tokens || 0) }) }); await loadProject(pid); })}>同意并继续</button><button onClick={() => void action(async () => { await request(`${root}/decisions/${d.id}`, { method: 'POST', body: JSON.stringify({ accept: false }) }); await loadProject(pid); })}>保留当前结果并结束</button></div></section>)}
        {citationDrafts.map(d=><CitationReview key={d.id} draft={d} onBind={index=>void action(async()=>{if(!selection)throw new Error('请先打开对应原文并选择正确摘录。');const result=await request<{state:string}>(`${root}/citation-drafts/${d.id}/resolve`,{method:'POST',body:JSON.stringify({revision:d.revision,bindings:[{index,...selection,version_id:segments.find(s=>s.id===selection.segment_id)?.version_id}]})});setNotice(result.state==='pending'?'已保存这一处绑定，其余摘录仍需核验。':'引文已通过核验，研究继续。');await loadProject(pid);})} onDiscard={()=>void action(async()=>{await request(`${root}/citation-drafts/${d.id}/resolve`,{method:'POST',body:JSON.stringify({revision:d.revision,discard:true})});await loadProject(pid);})}/>)}
        <ResearchProgress jobs={busyJobs} usage={usage} onCancel={id=>void action(async()=>{await request(`${root}/jobs/${id}/cancel`,{method:'POST'});await loadProject(pid);})}/>
        {jobs.filter(j => j.state === 'failed').slice(0, 3).map(j => <div className="uw-error" key={j.id}>任务未完成：{j.error}<button onClick={() => void action(async () => { await request(`${root}/jobs/${j.id}/retry`, { method: 'POST' }); await loadProject(pid); })}>重试</button></div>)}
      </div>
      <ResearchComposer draft={draft} onDraft={setDraft} onSend={()=>void action(send)} onUpload={f=>void action(()=>upload(f))}
        disabled={!pid} busy={busy} tool={tool} method={method} mode={mode} onMode={setMode}
        onTool={(t,m)=>{setTool(t);setMethod(m);if(t==='persona'||t==='subject')setPanel('people');}} onPeople={()=>setPanel('people')}
        selection={selection} onClearSelection={()=>setSelection(undefined)} materials={selected.map(id=>({id,name:materials.find(m=>m.id===id)?.name||'所选材料'}))}
        onRemoveMaterial={id=>setSelected(xs=>xs.filter(x=>x!==id))} answering={!!activeInterview?.current_question}
        interview={activeInterview&&<div className="uw-interview-banner">访谈：{people.find(p=>p.id===activeInterview.participant_id)?.pseudonym} · {activeInterview.state}<button onClick={()=>setPanel('interview')}>访谈控制</button><button onClick={()=>setActiveInterview(undefined)}>返回研究对话</button></div>}/>

    </main>

    {panel !== 'none' && <DocumentPane width={documentWidth} onResize={setDocumentWidth}><header><button className="uw-nav-toggle" aria-label="打开项目导航" onClick={toggleSidebar}>☰</button>{trailLength>0&&<button onClick={previousDocument} aria-label="返回上一个文档">←</button>}<small>DOCUMENT / {panel === 'material' ? '原文' : panel === 'artifact' ? '研究文档' : panel === 'people' ? '研究对象' : panel === 'interview' ? '访谈' : panel === 'search' ? '检索' : '设置'}</small><button onClick={() => setPanel('none')} aria-label="关闭文档">×</button></header><div className="uw-document-body" ref={documentPane} onScroll={e => setDocumentScroll(e.currentTarget.scrollTop)}>
      {panel === 'material' && <><h2>{String(currentMaterial?.metadata.title || currentMaterial?.name || '研究材料')}</h2><div className="uw-inline-actions"><select aria-label="文本版本" value={versionId} onChange={e => { setVersionDiff(undefined); void action(() => openMaterial(assetId, e.target.value)); }}><option value="">最新文本</option>{[...(currentMaterial?.versions || [])].sort((a, b) => a.created_at - b.created_at).map((v, i) => <option key={v.id} value={v.id}>版本 {i + 1}</option>)}</select><button disabled={(currentMaterial?.versions.length || 0) < 2} onClick={() => void action(compareVersion)}>比较上一版</button><button onClick={() => void action(async () => { const r = await response(`${root}/materials/${assetId}/original`); if (originalUrl) URL.revokeObjectURL(originalUrl); setOriginalUrl(URL.createObjectURL(await r.blob())); })}>原件</button><button onClick={() => void action(() => download(`${root}/materials/${assetId}/tei`, 'source.xml'))}>导出 TEI</button></div>
        {versionDiff && <section className="uw-version-diff"><h3>版本对照 · {versionDiff.oldLabel} → {versionDiff.newLabel}</h3><p className="uw-muted">按 xml:id 对齐逐段比较：未变 {versionDiff.counts.same || 0} · 修改 {versionDiff.counts.changed || 0} · 新增 {versionDiff.counts.added || 0} · 删除 {versionDiff.counts.removed || 0}。旧版引用保持原段落位置，不随修订移动。</p><ol>{versionDiff.rows.filter(row => row.state !== 'same').map(row => <li key={row.xml_id} className={'uw-diff-' + row.state}><small>{({ added: '新增段落', removed: '删除段落', changed: '文本修改' } as Record<string, string>)[row.state]} · {row.xml_id}</small>{row.before && <p className="uw-diff-old">{row.before}</p>}{row.now && <p className="uw-diff-new">{row.now}</p>}</li>)}{!versionDiff.rows.some(row => row.state !== 'same') && <li className="uw-diff-same">两个版本正文没有段落差异。</li>}</ol><button onClick={() => setVersionDiff(undefined)}>关闭对照</button></section>}
        {originalUrl && <><object className="uw-original" data={originalUrl} type="application/pdf"><p>原件无法内嵌预览，请下载查看。</p></object><button onClick={() => setOriginalUrl('')}>返回文本</button></>}
        {!originalUrl && <div className="uw-source" onMouseUp={capture} onKeyUp={capture}>{segments.map(s => <section id={'uw-segment-' + s.id} key={s.id}><small>页序 {s.page_label || '—'}</small><p data-source={s.id}>{selection?.segment_id === s.id ? <>{Array.from(s.text).slice(0, selection.start_codepoint).join('')}<mark>{Array.from(s.text).slice(selection.start_codepoint, selection.end_codepoint).join('')}</mark>{Array.from(s.text).slice(selection.end_codepoint).join('')}</> : s.text}</p></section>)}</div>}
        {selection && <section className="uw-selection"><blockquote>{selection.exact_quote}</blockquote><div className="uw-inline-actions"><button onClick={() => { setDraft('请解释这段材料：\n' + selection.exact_quote); setTool('chat'); setSelected(xs => [...new Set([...xs, assetId])]); }}>解释</button><button onClick={() => { setDraft('请比较这段材料与所选材料：\n' + selection.exact_quote); setTool('research'); }}>比较</button><button onClick={() => { setSelected(xs => [...new Set([...xs, assetId])]); setNotice('当前材料已加入研究范围。'); }}>用于研究</button></div><textarea aria-label="原文笔记" value={note} onChange={e => setNote(e.target.value)} placeholder="记录理解；保存时自动关联原文证据" /><button onClick={() => void action(saveSelection)}>保存笔记与证据</button></section>}
        <details><summary>书目信息与处理状态</summary>{['title', 'author', 'translator', 'publication_date', 'purpose', 'source_note'].map(k => <label key={k}>{({title:'书名',author:'作者',translator:'译者',publication_date:'出版时间',purpose:'用途：theory 或 research',source_note:'来源说明'} as Record<string,string>)[k]}<input value={bibliography[k] || ''} onChange={e => setBibliography({...bibliography,[k]:e.target.value})}/></label>)}<button onClick={() => void action(async () => { await request(`${root}/materials/${assetId}/bibliography`, {method:'PUT',body:JSON.stringify({revision:currentMaterial?.revision,metadata:bibliography})});await loadProject(pid);setNotice('书目信息已保存。');})}>保存书目信息</button>{currentMaterial?.versions.map(v => <p key={v.id}>{String(v.quality.extractor).startsWith('ocr') || v.quality.extractor === 'local-tesseract' ? 'OCR 转录（' + String(v.quality.engine || v.quality.extractor) + '），未经人工校核' : '文本转录'}{Array.isArray(v.quality.empty_pages) && v.quality.empty_pages.length > 0 ? '，存在未识别页面：' + (v.quality.empty_pages as number[]).join('、') : ''}{Array.isArray(v.quality.ocr_unavailable_pages) && v.quality.ocr_unavailable_pages.length > 0 ? '，未识别（缺引擎或语言数据）：' + (v.quality.ocr_unavailable_pages as number[]).join('、') : ''}</p>)}{currentMaterial?.name.toLowerCase().endsWith('.pdf') && <button onClick={() => void action(async () => {await request(`${root}/materials/${assetId}/ocr`,{method:'POST'});await loadProject(pid);setNotice('已提交本地 OCR；结果保存为新版本并标为待校核。');})}>识别扫描页</button>}</details><details><summary>版本修订与材料管理</summary><label>上传修订 TEI<input type="file" accept=".xml,.tei" onChange={e => { const f = e.target.files?.[0]; if (f && currentMaterial) void action(async () => { await request(`${root}/materials/${assetId}/revisions`, { method: 'POST', body: JSON.stringify({ revision: currentMaterial.revision, tei: await f.text() }) }); await loadProject(pid); await openMaterial(assetId); }); }} /></label><button onClick={() => void action(async () => { if (!await confirmDialog('撤回此材料并清理相关派生内容？')) return; await request(`${root}/materials/${assetId}`, { method: 'DELETE' }); setPanel('none'); await loadProject(pid); })}>撤回材料</button></details>
      </>}

      {panel === 'artifact' && artifact && <><div className="uw-inline-actions"><button onClick={() => void action(async () => { const updated = await request<ResearchRecord>(`${root}/records/${artifact.id}`, { method: 'PUT', body: JSON.stringify({ kind: artifact.kind, revision: artifact.revision, payload: { ...artifact.payload, ...editFields, editor_json:editorJson, title: editTitle, text: editText, status: 'researcher_revision' } }) }); setArtifact(updated); setNotice('已保存新版本。'); await loadProject(pid); })}>保存修订</button><button onClick={() => void action(async () => { const r = await request<ResearchRecord>(root + '/records', { method: 'POST', body: JSON.stringify({ kind: 'claim', payload: { title: editTitle, text: editText, source_record_ids: [artifact.id], evidence_ids: artifact.payload.evidence_ids || [] } }) }); await loadProject(pid); await openArtifact(r.id); })}>加入论证</button><button onClick={() => void action(async () => { const r = await request<ResearchRecord>(root + '/records', { method: 'POST', body: JSON.stringify({ kind: 'manuscript', payload: { title: '文稿 · ' + editTitle, text: editText, source_record_ids: [artifact.id], evidence_ids: artifact.payload.evidence_ids || [] } }) }); await loadProject(pid); await openArtifact(r.id); })}>插入文稿</button><button onClick={() => { setDraft('请继续检验这项解释，回到原文寻找反例：\n' + editTitle); setTool('research'); }}>继续检验</button>{artifact.kind === 'research_answer' && <button onClick={() => void action(() => deepen(artifact))}>深入完整研究</button>}</div>
        <label>标题<input value={editTitle} onChange={e => setEditTitle(e.target.value)} /></label><label>正文<Suspense fallback={<p>正在准备文稿编辑器…</p>}><ManuscriptEditor key={artifact.id} recordId={artifact.id} value={editorJson} source={editText} evidenceIds={artifact.payload.evidence_ids || []} onChange={(json,text) => {setEditorJson(json);setEditText(text);}} onLocate={id=>void action(()=>locate(id))} /></Suspense></label>
        <p className={'uw-save-state ' + (artifactDirty ? 'uw-dirty' : 'uw-saved')}>{artifactDirty
          ? '未保存修改：切换会话或刷新后可从本机草稿恢复；尚未写入已保存版本。'
          : '与已保存版本一致（修订 ' + artifact.revision + '）。'}</p>
        {Object.keys(editFields).length > 0 && <section>{Object.entries(editFields).map(([k,v]) => <label key={k}>{({retained:'保留的内容',negated:'否定的内容',reason:'转化依据',shift:'对象位移',excluded_causes:'已排除的可消解差异',rebuttal_conditions:'反驳条件',difficulty_type:'困难性质'} as Record<string,string>)[k]}<textarea value={v} onChange={e => setEditFields({...editFields,[k]:e.target.value})}/></label>)}</section>}<details open><summary>证据与分析详情</summary>{card(artifact)}</details>{artifact.payload.legacy_run_id && <section><h3>历史分析评议</h3>{['approve','revise','reject'].map(decision => <button key={decision} onClick={() => void action(async () => {const reason=await ask('评议说明') || '';await request(`${root}/analysis-runs/${artifact.payload.legacy_run_id}/reviews`,{method:'POST',body:JSON.stringify({decision,reason})});setNotice('评议已保存。');})}>{({approve:'通过',revise:'要求修订',reject:'驳回'} as Record<string,string>)[decision]}</button>)}<button onClick={() => void action(() => download(`${root}/analysis-runs/${artifact.payload.legacy_run_id}/export`,'historical-analysis.json'))}>导出原分析</button></section>}<details><summary>比较其他文档</summary><div className="uw-inline-actions">{artifacts.filter(a => a.id !== artifact.id).map(a => <button key={a.id} onClick={() => setCompare([artifact, a])}>{a.payload.title}</button>)}</div></details>{compare && <div className="uw-comparison">{compare.map(card)}</div>}
        <details><summary>研究图与概念演化</summary><div className="uw-inline-actions"><button onClick={()=>setGraphKind('research')}>研究关系</button><button onClick={()=>setGraphKind('concept')}>概念演化</button></div>{graphKind&&<Suspense fallback={<p>正在整理关系…</p>}><ReportGraph root={root} kind={graphKind} records={artifacts} onOpen={id=>void action(()=>openArtifact(id))}/></Suspense>}</details>
      </>}

      {panel === 'people' && <><h2>访谈与风格模拟</h2><p>参与者与材料属于当前项目，授权用途分别记录。</p><form onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); void action(async () => { const p = await request<Participant>(root + '/participants', { method: 'POST', body: JSON.stringify({ pseudonym: f.get('name'), material_collection: f.get('collection') === 'on', profile_analysis: f.get('profile') === 'on', agent_simulation: f.get('simulation') === 'on' }) }); setParticipantId(p.id); await loadProject(pid); }); }}><label>参与者代称<input name="name" required /></label><label className="uw-check"><input type="checkbox" name="collection" required />已获得材料采集授权</label><label className="uw-check"><input type="checkbox" name="profile" />已获得主体分析授权</label><label className="uw-check"><input type="checkbox" name="simulation" />已获得风格模拟授权</label><button>登记参与者与授权</button></form>
        <label>当前参与者<select value={participantId} onChange={e => setParticipantId(e.target.value)}><option value="">选择参与者</option>{people.filter(p => !p.withdrawn_at).map(p => <option key={p.id} value={p.id}>{p.pseudonym}</option>)}</select></label>
        <div className="uw-inline-actions"><button disabled={!participantId || !cid} onClick={() => void action(async () => { const iv = await request<Interview>(root + '/interviews', { method: 'POST', body: JSON.stringify({ participant_id: participantId, conversation_id: cid, provider_mode: mode }) }); setActiveInterview(iv); setPanel('interview'); await loadProject(pid); setMessages(await request(`${root}/conversations/${cid}/messages`)); })}>开始访谈</button><button disabled={!participantId} onClick={() => void action(async () => { await request(`${root}/participants/${participantId}/materials`, { method: 'POST', body: JSON.stringify({ asset_ids: selected }) }); setNotice('所选材料已关联参与者。'); })}>关联所选材料</button><button disabled={!participantId} onClick={() => { setTool('subject'); setDraft('请基于所选授权材料进行主体分析。'); }}>主体分析</button></div>
        {participantId && <details><summary>更新用途授权</summary>{['material_collection','profile_analysis','agent_simulation'].map(k => <label className="uw-check" key={k}><input type="checkbox" checked={people.find(p => p.id === participantId)?.permissions[k] || false} onChange={e => void action(async () => { const person=people.find(p=>p.id===participantId)!; await request(`${root}/participants/${participantId}`, {method:'PUT',body:JSON.stringify({pseudonym:person.pseudonym,...person.permissions,[k]:e.target.checked})}); await loadProject(pid);})}/>{({material_collection:'材料采集',profile_analysis:'主体分析',agent_simulation:'风格模拟'} as Record<string,string>)[k]}</label>)}<button onClick={() => void action(async () => {if(!await confirmDialog('撤回参与者及其材料和派生数据？'))return;await request(`${root}/participants/${participantId}/withdraw`,{method:'POST'});setParticipantId('');await loadProject(pid);})}>撤回授权与相关数据</button></details>}<h3>风格模拟</h3><button disabled={!participantId} onClick={() => void action(async () => { const name = await ask('风格模拟名称'); if (!name) return; const p = await request<Persona>(root + '/personas', { method: 'POST', body: JSON.stringify({ name, participant_id: participantId }) }); setPersonaId(p.id); await loadProject(pid); })}>新建模拟对象</button>
        {personas.map(p => <section className="uw-object-card" key={p.id}><strong>{p.name}</strong><small>AI 模拟 / {p.status}</small><div className="uw-inline-actions"><button onClick={() => void action(async () => { await request(`${root}/personas/${p.id}/train`, { method: 'POST' }); setNotice('已提交本地训练任务。'); await loadProject(pid); })}>训练</button><button onClick={() => { setPersonaId(p.id); setTool('persona'); setNotice('已选择风格模拟，回复将标注 AI 身份。'); }}>开始对话</button><button onClick={() => void action(async () => { await request(`${root}/personas/${p.id}`, { method: 'DELETE' }); await loadProject(pid); })}>删除模拟</button></div></section>)}
        <h3>已有访谈</h3>{interviews.map(iv => <button className="uw-document-item" key={iv.id} onClick={() => void action(async () => { setActiveInterview(await request(`${root}/interviews/${iv.id}`)); setPanel('interview'); })}>{people.find(p => p.id === iv.participant_id)?.pseudonym || '访谈'} · {iv.state}</button>)}
      </>}

      {panel === 'interview' && activeInterview && <><h2>研究访谈</h2><p>{activeInterview.current_question?.text || '主问题已完成，可以生成研究材料。'}</p><p className="uw-muted">在中间输入框回答。访谈状态和问答将持久保存。</p><div className="uw-inline-actions">{['pause', 'resume', 'complete', 'reset'].map(a => <button key={a} onClick={() => void action(async () => { const r = await request<Interview & { job_id?: string }>(`${root}/interviews/${activeInterview.id}/${a}`, { method: 'POST' }); if (a === 'complete') { setActiveInterview(undefined); setNotice('访谈已完成，正在生成项目材料。'); } else setActiveInterview(r); await loadProject(pid); })}>{({ pause: '暂停', resume: '恢复', complete: '生成材料', reset: '重新开始' } as Record<string, string>)[a]}</button>)}</div></>}

      {panel === 'search' && <><h2>检索材料</h2><form onSubmit={e => { e.preventDefault(); void action(async () => { const result = await request<{ items: Segment[] }>(root + '/search?q=' + encodeURIComponent(searchText) + (searchAuthor ? '&author=' + encodeURIComponent(searchAuthor) : '') + (searchYear ? '&year_from=' + encodeURIComponent(searchYear) : '')); setHits(result.items); }); }}><label>原词或短语<input value={searchText} onChange={e => setSearchText(e.target.value)} /></label><details><summary>书目筛选</summary><label>作者<input value={searchAuthor} onChange={e => setSearchAuthor(e.target.value)} /></label><label>起始年份<input type="number" value={searchYear} onChange={e => setSearchYear(e.target.value)} /></label></details><button>搜索当前项目</button></form>{hits.map(hit => <button className="uw-search-hit" key={hit.id} onClick={() => void action(() => openMaterial(hit.asset_id, hit.version_id))}>{hit.text.slice(0, 200)}</button>)}</>}

      {panel === 'settings' && <><h2>项目与服务设置</h2><form onSubmit={e => { e.preventDefault(); void action(async () => { const url = new URL(serviceAddress); if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.pathname !== '/') throw new Error('请填写不含路径和凭证的服务地址。'); localStorage.setItem('scriptorium_research_url', url.origin); localStorage.setItem('scriptorium_research_key', apiKey); await persistDesktopConnection(url.origin); const ps = await request<Project[]>('/api/v2/projects'); setProjects(ps); await chooseProject(ps[0]?.id || ''); setNotice('连接已保存，所有研究能力使用此服务。'); }); }}><label>统一服务地址<input value={serviceAddress} onChange={e => setServiceAddress(e.target.value)} /></label><label>访问密钥<input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)} /></label><button>保存连接</button></form>
        <ModelProviderForm/>
        <h3>界面与动效</h3><label className="uw-check"><input type="checkbox" checked={quiet} onChange={e=>setQuiet(e.target.checked)}/>安静模式（减少转场与动态效果）</label><h3>品牌与启动</h3>{([['enabled', '启动动画'], ['requireInteraction', '交互式播放'], ['sound', '声音'], ['voice', '语音']] as const).map(([name, label]) => <label className="uw-check" key={name}><input type="checkbox" checked={startup[name]} onChange={e => { const patch = { [name]: e.target.checked }; saveConfig(patch); setStartup({ ...startup, ...patch }); }} />{label}</label>)}
        <h3>项目文稿与导出</h3><div className="uw-inline-actions"><button disabled={!pid} onClick={() => void action(async () => { const r = await request<ResearchRecord>(root + '/records', { method: 'POST', body: JSON.stringify({ kind: 'manuscript', payload: { title: '研究文稿', text: '' } }) }); await loadProject(pid); await openArtifact(r.id); })}>新建文稿</button>{['md', 'json', 'tei'].map(format => <button key={format} disabled={!pid} onClick={() => void action(() => download(`${root}/export?format=${format}`, `research.${format === 'tei' ? 'xml' : format}`))}>导出 {format.toUpperCase()}</button>)}</div>
        <h3>历史迁移</h3><button onClick={exportBrowserHistory}>导出浏览器旧聊天</button><label>导入聊天备份<input type="file" accept=".json" disabled={!pid} onChange={e => { const f = e.target.files?.[0]; if (f) void action(async () => { await request(root + '/history-import', { method: 'POST', body: await f.text() }); await loadProject(pid); setNotice('历史会话已导入当前项目。'); }); }} /></label>
        <h3>归档会话</h3>{conversations.filter(c => c.archived).map(c => <button className="uw-document-item" key={c.id} onClick={() => void action(async () => { await request(`${root}/conversations/${c.id}`, { method: 'PUT', body: JSON.stringify({ revision: c.revision, archived: false }) }); await loadProject(pid); })}>恢复 {c.title}</button>)}
        <h3>任务详情</h3>{jobs.map(j => <div className="uw-task-detail" key={j.id}>{j.kind} / {j.state}{j.error ? ' · ' + j.error : ''}</div>)}
      </>}
    </div></DocumentPane>}
  </div>;
}
