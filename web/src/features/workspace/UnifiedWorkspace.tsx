import {ResearchTimeline} from './components/ResearchTimeline';
import {mergeBlock,type TimelineBlock} from './timeline';
import {insertResearch} from './api/writing-target';
import { useCallback, useEffect, useRef, useState, lazy, Suspense } from 'react';
import { MarkdownRenderer } from '../../components/ui/MarkdownRenderer';
import { loadConfig, saveConfig } from '../../components/startup/startupConfig';
import { codepointOffset, download, exportBrowserHistory, configureConnection, projectPath, request, response, sendMessage, serviceUrl } from './api/client';
import type { Anchor, Job, Material, Project, ResearchRecord, Segment } from './api/client';
import './workbench.css';
import { useDialogs } from './components/dialog-context';
const ReportGraph=lazy(()=>import('./components/ReportGraph'));
import { DocumentPane, ResearchProgress } from './components/WorkspaceParts';
import { CitationReview,type CitationDraft } from './components/CitationReview';
import { ResearchComposer,type Tool } from './components/ResearchComposer';
import { Icon } from './components/Icon';
import { ProjectSidebar, ConversationMenu } from './components/ProjectSidebar';
import { MissionBar } from './components/MissionBar';
import { HaloLayer } from './components/HaloLayer';
import { getTheme, setTheme, type Theme } from '../theme/theme';
import { SurfaceDialog } from './components/SurfaceDialog';
import { CommandPalette,type Command } from './components/CommandPalette';
import { SectionBoundary } from './components/SectionBoundary';
import {BibliographyForm} from './components/BibliographyForm';
import {SourceReader} from './components/SourceReader';
import {ResearchDecision,type ResearchDecisionData} from './components/ResearchDecision';
import {sameDocument,documentKey} from './document-tabs';
import {readWindow,windowSegments,type ReadingView} from './api/reading';
const ArtifactWorkspace=lazy(()=>import('./components/ArtifactWorkspace').then(m=>({default:m.ArtifactWorkspace})));
const ProjectGovernance=lazy(()=>import('./components/ProjectGovernance').then(m=>({default:m.ProjectGovernance})));
import { ModelProviderForm } from './components/ModelProviderForm';
import type {DocumentTab} from './state';
import { useWorkspaceUI } from './state';
import { useConversationEvents } from './hooks/useConversationEvents';
import {useProjectResources,refreshProject} from './hooks/useProjectResources';
import type {Conversation,Message,Participant,Persona,Interview} from './workspace-types';
import {useSources} from './hooks/useSources';
import type {ResearchSource} from './hooks/useSources';
import {SourceLibrary,IntakeProgress} from './components/SourceLibrary';
import {TaskFailure} from './components/TaskFailure';
import './sources.css';
import './flight-deck.css';
import { queryClient } from './api/query';

function safeJson(value:string|null):unknown{try{return JSON.parse(value||'null');}catch{return null;}}

type Decision=ResearchDecisionData;
interface VersionDiffRow { xml_id: string; state: 'same' | 'added' | 'removed' | 'changed'; before?: string; now?: string }
interface VersionDiff { oldLabel: string; newLabel: string; rows: VersionDiffRow[]; counts: Record<string, number> }
type Panel = 'none' | 'material' | 'artifact' | 'settings' | 'people' | 'interview' | 'search' | 'sources';
const err = (e: unknown) => e instanceof Error ? e.message : String(e);

export default function UnifiedWorkspace() {
  const { ask, confirm: confirmDialog } = useDialogs();
  const {writingTarget, sidebarOpen, toggleSidebar, quiet, documentWidth, setDocumentWidth, setQuiet, layout, setLayout, tabs, setTabs, openTab } = useWorkspaceUI();
  const [settingsOpen,setSettingsOpen]=useState(false);
  const [projectOpen,setProjectOpen]=useState(false);
  const [commandsOpen,setCommandsOpen]=useState(false);
  const [role,setRole]=useState('owner');
  const [auth,setAuth]=useState<{mode:string;authenticated:boolean;user_id?:string;name?:string}>();
  const userRef=useRef('local');
  const scoped=(key:string)=>`${key}:user:${userRef.current}`;
  const personalRevision=useRef(0);
  const readOnly=!['owner','editor'].includes(role);
  const [messageLimit,setMessageLimit]=useState(80);
  const [hasOlder,setHasOlder]=useState(false);
  const mergeMessages=(old:Message[],recent:Message[])=>{const map=new Map(old.map(m=>[m.id,m]));recent.forEach(m=>map.set(m.id,m));return [...map.values()];};
  const [timelineBlocks,setTimelineBlocks]=useState<TimelineBlock[]>([]);
  const [liveDrafts,setLiveDrafts]=useState<Record<string,string>>({});
  const [newMessages,setNewMessages]=useState(false);
  const documentRequest=useRef(0);
  const documentTrail=useRef<{panel:Panel;assetId:string;versionId:string;artifact?:ResearchRecord;editText:string;editTitle:string;editorJson?:Record<string,unknown>;segments:Segment[];reading?:ReadingView;sourcePage:number;selection?:Omit<Anchor,'id'>;scroll:number}[]>([]);
  const [trailLength,setTrailLength]=useState(0);
  const [graphKind,setGraphKind]=useState<'research'|'concept'>();
  const [editorJson, setEditorJson] = useState<Record<string, unknown>>();
  const sendKey = useRef<{text:string;key:string}|undefined>(undefined);
  const [projects, setProjects] = useState<Project[]>([]);
  const [pid, setPid] = useState(localStorage.getItem('scriptorium_research_project') || '');
  const {conversations,setConversations,materials,setMaterials,artifacts,setArtifacts,jobs,setJobs,decisions,setDecisions,people,personas,oldAnalyses,interviews,citationDrafts,setCitationDrafts,usage,setUsage}=useProjectResources(pid,!!auth?.authenticated);
  const [cid, setCid] = useState('');
  const [messages, setMessages] = useState<Message[]>([]);
  const contextAbort=useRef(new AbortController());const contextEpoch=useRef(0);const [restoreError,setRestoreError]=useState('');const [eventConnected,setEventConnected]=useState(false);
  const [workspaceReady,setWorkspaceReady] = useState(false);
  const [scrollPosition, setScrollPosition] = useState(0);
  const [documentScroll, setDocumentScroll] = useState(0);
  const documentPane = useRef<HTMLDivElement>(null);
  const [panel, setPanel] = useState<Panel>('none');
  const [theme, setThemeState] = useState<Theme>(() => getTheme());
  const [halo, setHalo] = useState(() => localStorage.getItem('scriptorium_halo') === '1');
  const [reviewMode, setReviewMode] = useState<'auto' | 'review'>(() => localStorage.getItem('scriptorium_review_mode') === 'review' ? 'review' : 'auto');
  const chooseReviewMode = (value: 'auto' | 'review') => { setReviewMode(value); localStorage.setItem('scriptorium_review_mode', value); };
  const toggleHalo = () => { const next = !halo; setHalo(next); localStorage.setItem('scriptorium_halo', next ? '1' : '0'); if (next && theme !== 'dark') { setTheme('dark'); setThemeState('dark'); } };
  const toggleTheme = () => { const next = theme === 'light' ? 'dark' : 'light'; setTheme(next); setThemeState(next); };
  const [assetId, setAssetId] = useState('');
  const [versionId, setVersionId] = useState('');
  const [segments, setSegments] = useState<Segment[]>([]);
  const [reading,setReading]=useState<ReadingView>();const [readerLoading,setReaderLoading]=useState(false);
  const [sourcePage,setSourcePage]=useState(0);
  const [selected, setSelected] = useState<string[]>([]);
  const [selection, setSelection] = useState<Omit<Anchor, 'id'>>();
  const [artifact, setArtifact] = useState<ResearchRecord>();
  const activeArtifact=useRef<string|undefined>(undefined);
 useEffect(()=>{activeArtifact.current=artifact?.id;},[artifact?.id]);
  const [editText, setEditText] = useState('');
  const [editTitle, setEditTitle] = useState('');
  const [searchAuthor, setSearchAuthor] = useState('');
  const [searchYear, setSearchYear] = useState('');
  const [note, setNote] = useState('');
  const [draft, setDraft] = useState('');
  const [tool, setTool] = useState<Tool>('auto');
  const [method, setMethod] = useState('');
  const [mode, setMode] = useState<'live' | 'demo'>('live');
  const [participantId, setParticipantId] = useState('');
  const [personaId, setPersonaId] = useState('');
  const [activeInterview, setActiveInterview] = useState<Interview>();
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [busy, setBusy] = useState(false);
  const [searchText, setSearchText] = useState('');
  const [hits, setHits] = useState<Segment[]>([]);
  const [serviceAddress, setServiceAddress] = useState(serviceUrl());
  const [apiKey, setApiKey] = useState(localStorage.getItem('scriptorium_research_key') || '');
  const [startup, setStartup] = useState(loadConfig());
  const [compare, setCompare] = useState<ResearchRecord[]>();
  const [versionDiff, setVersionDiff] = useState<VersionDiff>();
  const [originalUrl, setOriginalUrl] = useState('');
  const feed = useRef<HTMLDivElement>(null);
  const following=useRef(true);
  const active = useRef({ pid, cid });
  const workspaceTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const root = projectPath(pid);
  const current = conversations.find(c => c.id === cid);
  const currentMaterial = materials.find(a => a.id === assetId);

  const resetTransient=useCallback(()=>{
    following.current=true;useWorkspaceUI.getState().setWritingTarget(undefined);contextEpoch.current++;contextAbort.current.abort();contextAbort.current=new AbortController();
    void queryClient.cancelQueries();if(workspaceTimer.current)clearTimeout(workspaceTimer.current);
    documentRequest.current++;documentTrail.current=[];setTrailLength(0);setSelection(undefined);setSelected([]);setLiveDrafts({});setTimelineBlocks([]);setNewMessages(false);setGraphKind(undefined);setActiveInterview(undefined);setParticipantId('');setPersonaId('');setTool('auto');setMethod('');setMode('live');setArtifact(undefined);setEditorJson(undefined);setEditText('');setEditTitle('');setSegments([]);setReading(undefined);setReaderLoading(false);setSourcePage(0);setAssetId('');setVersionId('');setNote('');setHits([]);setCompare(undefined);setVersionDiff(undefined);setNotice('');setError('');setRestoreError('');setBusy(false);setEventConnected(false);sendKey.current=undefined;
    setOriginalUrl(value=>{if(value)URL.revokeObjectURL(value);return '';});
  },[]);
  const action = useCallback(async (fn: () => Promise<void>) => {
    const epoch=contextEpoch.current;setBusy(true);setError('');
    try{await fn();}catch(e){if(epoch===contextEpoch.current)setError(err(e));}finally{if(epoch===contextEpoch.current)setBusy(false);}
  }, []);

  const loadProject=useCallback(async(projectId:string)=>{if(projectId)await refreshProject(projectId);},[]);

  const chooseConversation = useCallback(async (projectId: string, conversationId: string, cs: Conversation[]) => {
    resetTransient();setWorkspaceReady(false);
    const epoch=contextEpoch.current;try{
    active.current = { pid: projectId, cid: conversationId };
    if(window.innerWidth<1180&&useWorkspaceUI.getState().sidebarOpen)useWorkspaceUI.getState().toggleSidebar();
    setCid(conversationId); setMessages([]); setActiveInterview(undefined); setPanel('none'); setCompare(undefined);
    localStorage.setItem(`scriptorium_last_conversation:${projectId}`, conversationId);
    const personal=await request<{revision:number;payload:Conversation['workspace']}>(`${projectPath(projectId)}/conversations/${conversationId}/workspace`,{signal:contextAbort.current.signal});
    if(active.current.pid!==projectId||active.current.cid!==conversationId)return;
    const pending=safeJson(localStorage.getItem(scoped(`scriptorium_workspace:${projectId}:${conversationId}`))) as{base_revision:number;workspace:Conversation['workspace']}|null;if(pending?.base_revision===personal.revision)personal.payload=pending.workspace;
    personalRevision.current=personal.revision;useWorkspaceUI.getState().setWritingTarget(personal.payload.writing_target);
    const original=cs.find(c=>c.id===conversationId);
    const c=original?{...original,workspace:personal.payload}:undefined;
    queryClient.setQueryData<Conversation[]>(['api',serviceUrl(),projectPath(projectId)+'/conversations'],items=>(items||cs).map(item=>item.id===conversationId?{...item,workspace:personal.payload}:item));
    useWorkspaceUI.getState().setTabs(personal.payload.tabs||[]);
    useWorkspaceUI.getState().setLayout(personal.payload.layout||'chat');
    const local = localStorage.getItem(scoped(`scriptorium_draft:${projectId}:${conversationId}`));
    // Unsaved document edits survive a session switch even when the workspace PUT lost a race.
    const localDoc = safeJson(localStorage.getItem(scoped(`scriptorium_doc:${projectId}:${conversationId}`))) as
      { record_id?: string; title?: string; text?: string; editor_json?:Record<string,unknown> } | null;
    setDraft(local ?? c?.workspace.draft ?? '');setSelected(c?.workspace.asset_ids||[]);setTool(c?.workspace.tool==='ask'&&!c?.workspace.method?'auto':c?.workspace.tool||'auto');setMethod(c?.workspace.method||'');setMode(c?.workspace.provider_mode||'live');setSelection(c?.workspace.selection);
    if (conversationId) {
      const result = await request<Message[]>(`${projectPath(projectId)}/conversations/${conversationId}/messages?limit=80`,{signal:contextAbort.current.signal});
      setHasOlder(result.length===80);setMessageLimit(80);
      if (active.current.pid !== projectId || active.current.cid !== conversationId) return;
      setMessages(result);
      // Timeline blocks can race the event snapshot on a cold load; re-read once after history.
      try { const snap = await request<{blocks:TimelineBlock[]}>(`${projectPath(projectId)}/conversations/${conversationId}/snapshot`,{signal:contextAbort.current.signal});
        if (active.current.pid===projectId && active.current.cid===conversationId && snap.blocks?.length) setTimelineBlocks(snap.blocks); } catch {}
      setScrollPosition(c?.workspace.scroll || 0); setDocumentScroll(c?.workspace.document_scroll || 0);
      setTimeout(() => { if (feed.current) feed.current.scrollTop = c?.workspace.scroll || 0; }, 80);
      const w = c?.workspace;
      if (w?.panel === 'material' && w.open_material) {
        const data=await readWindow(projectPath(projectId),w.open_material,w.version_id||'',w.source_page||0,contextAbort.current.signal);
        if(active.current.pid!==projectId||active.current.cid!==conversationId)return;
        setReading(data);setSegments(windowSegments(data));setAssetId(w.open_material);setVersionId(data.version.id);setSourcePage(data.page);setSelection(w.selection);setPanel('material');
        useWorkspaceUI.getState().setTabs((personal.payload.tabs||[]).map(tab=>tab.kind==='material'&&tab.id===w.open_material&&!tab.version?{...tab,version:data.version.id}:tab));
      } else if(w?.panel==='sources'){setPanel('sources');setLayout(w.layout||'split');
      } else if (w?.panel === 'artifact' && w.open_artifact) {
        const a = await request<ResearchRecord>(`${projectPath(projectId)}/artifacts/${w.open_artifact}`,{signal:contextAbort.current.signal});
        if (active.current.pid !== projectId || active.current.cid !== conversationId) return;
        const unsaved = localDoc && localDoc.record_id === a.id ? localDoc : null;
        const recoveryKey=`scriptorium_document:${projectId}:${a.id}:user:${userRef.current}`;if(unsaved&&!localStorage.getItem(recoveryKey)&&(unsaved.text!==a.payload.text||unsaved.title!==a.payload.title))localStorage.setItem(recoveryKey,JSON.stringify({base_revision:0,title:unsaved.title||'',text:unsaved.text||'',json:unsaved.editor_json}));
        setArtifact(a);setEditorJson(unsaved?.editor_json ?? a.payload.editor_json);
        setEditTitle(unsaved?.title ?? w.edit_title ?? a.payload.title ?? '');
        setEditText(unsaved?.text ?? w.edit_text ?? a.payload.text ?? '');
        setPanel('artifact');
      }
      setWorkspaceReady(true);
      setTimeout(() => {if(documentPane.current) documentPane.current.scrollTop=w?.document_scroll || 0;},80);
    }
    }catch(e){if(epoch===contextEpoch.current){setRestoreError(err(e));setError('工作区恢复未完成，临时草稿仍保留。');}}
  }, [resetTransient,setLayout]);

  const chooseProject = useCallback(async (projectId: string) => {
    resetTransient();setWorkspaceReady(false);try{
    void queryClient.cancelQueries({predicate:q => typeof q.queryKey[2] === 'string' && !q.queryKey[2].includes(projectPath(projectId))});
    active.current = { pid: projectId, cid: '' };
    setPid(projectId); setCid(''); setMessages([]);
    useWorkspaceUI.getState().setTabs([]);useWorkspaceUI.getState().setLayout('chat');documentTrail.current=[];setTrailLength(0);setLiveDrafts({});setTimelineBlocks([]);setNewMessages(false);setGraphKind(undefined);
    setPanel('none'); setDraft(''); setSelected([]); setParticipantId(''); setPersonaId(''); setSegments([]); setSelection(undefined);
    localStorage.setItem('scriptorium_research_project', projectId);
    if (!projectId) return;
    const membership=await request<{role:string}>(projectPath(projectId)+'/membership');if(active.current.pid!==projectId)return;setRole(membership.role);
    await loadProject(projectId);
    const cs = await request<Conversation[]>(projectPath(projectId) + '/conversations');
    if (active.current.pid !== projectId) return;
    const saved = localStorage.getItem(`scriptorium_last_conversation:${projectId}`);
    const latest = cs.find(c => c.id === saved && !c.archived) || cs.find(c => !c.archived);
    if(latest)await chooseConversation(projectId,latest.id,cs);else setWorkspaceReady(true);
    }catch(e){if(active.current.pid===projectId)setError(err(e));}
  }, [chooseConversation, loadProject,resetTransient]);

  useEffect(()=>{document.documentElement.dataset.quiet=String(quiet);return()=>{delete document.documentElement.dataset.quiet;};},[quiet]);
  useEffect(() => {
    void request<{mode:string;authenticated:boolean;user_id?:string;name?:string}>('/api/v2/auth/session').then(async session=>{setAuth(session);userRef.current=session.user_id||'local';if(!session.authenticated)return;const ps=await request<Project[]>('/api/v2/projects');
      setProjects(ps);
      const preferred = localStorage.getItem('scriptorium_research_project');
      await chooseProject(ps.some(p => p.id === preferred) ? preferred! : ps[0]?.id || '');
    }).catch(e => setError(err(e)));
  }, [chooseProject]);

  useEffect(() => {
    if(!pid||eventConnected)return;
    let stopped=false;
    const timer = setInterval(() => {
      void loadProject(pid).catch(e => { if (!stopped) setError(err(e)); });
      if (cid) void request<Message[]>(`${projectPath(pid)}/conversations/${cid}/messages?limit=80`).then(ms => {
        if (!stopped && active.current.cid === cid) setMessages(old=>mergeMessages(old,ms));
      }).catch(e => { if (!stopped) setError(err(e)); });
    }, 10000);
    return () => { stopped = true; clearInterval(timer); };
  }, [pid, cid, loadProject,eventConnected]);

  useEffect(() => {
    if (!pid || !cid || !current || !workspaceReady) return;
    localStorage.setItem(scoped(`scriptorium_draft:${pid}:${cid}`), draft);
    const workspace = {...current.workspace,writing_target:writingTarget,tool,method,provider_mode:mode,tabs,layout,draft,asset_ids:selected,scroll:scrollPosition,document_scroll:documentScroll,
      panel,selection,source_page:sourcePage,open_material:assetId,version_id:versionId,open_artifact:artifact?.id,edit_text:editText,edit_title:editTitle};
    localStorage.setItem(scoped(`scriptorium_workspace:${pid}:${cid}`),JSON.stringify({base_revision:personalRevision.current,workspace}));
    if (JSON.stringify(current.workspace) === JSON.stringify(workspace)) return;
    if (workspaceTimer.current) clearTimeout(workspaceTimer.current);
    workspaceTimer.current = setTimeout(() => {
      const save = (_revision: number, retried: boolean) => {
        void request<{revision:number;payload:Conversation['workspace']}>(`${projectPath(pid)}/conversations/${cid}/workspace`, { method: 'PUT', body: JSON.stringify({revision:personalRevision.current,payload:workspace}) })
          .then(updated=>{if(active.current.pid!==pid||active.current.cid!==cid)return;personalRevision.current=updated.revision;const recovery=scoped(`scriptorium_workspace:${pid}:${cid}`);const pending=safeJson(localStorage.getItem(recovery)) as{workspace:unknown}|null;if(JSON.stringify(pending?.workspace)===JSON.stringify(workspace))localStorage.removeItem(recovery);setConversations(cs=>cs.map(c=>c.id===cid?{...c,workspace:updated.payload}:c));})
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
  }, [draft, selected, pid, cid, current, workspaceReady, scrollPosition, documentScroll, panel, assetId, versionId, artifact, editText, editTitle, editorJson, selection, sourcePage, tabs, layout,tool,method,mode,writingTarget,setConversations]);


  async function newResearch() {
    if (!pid) throw new Error('请先创建或选择项目。');
    const c = await request<Conversation>(root + '/conversations', { method: 'POST', body: JSON.stringify({ title: '新研究' }) });
    const cs = [c, ...conversations]; setConversations(cs); await chooseConversation(pid, c.id, cs);
  }

  function rememberDocument(){
    if(panel==='material'||panel==='artifact'||panel==='sources'){documentTrail.current.push({panel,assetId,versionId,artifact,editText,editTitle,editorJson,segments,reading,sourcePage,selection,scroll:documentPane.current?.scrollTop||0});if(documentTrail.current.length>12)documentTrail.current.shift();setTrailLength(documentTrail.current.length);}
  }
  function previousDocument(){documentRequest.current++;const old=documentTrail.current.pop();if(!old)return;setTrailLength(documentTrail.current.length);setPanel(old.panel);setAssetId(old.assetId);setVersionId(old.versionId);setArtifact(old.artifact);setEditText(old.editText);setEditTitle(old.editTitle);setEditorJson(old.editorJson);setSegments(old.segments);setReading(old.reading);setSourcePage(old.sourcePage);setSelection(old.selection);setTimeout(()=>{if(documentPane.current)documentPane.current.scrollTop=old.scroll;},50);}
  async function openMaterial(id: string, version = '', anchor?: Anchor) {
    const remembered=useWorkspaceUI.getState().tabs.find(t=>sameDocument(t,{kind:'material',id,version}));rememberDocument();
    const project=pid;const conversation=cid;const requestId=++documentRequest.current;
    if(window.innerWidth<1180&&useWorkspaceUI.getState().sidebarOpen)useWorkspaceUI.getState().toggleSidebar();
    openTab({kind:'material',id,version,title:String(materials.find(m=>m.id===id)?.metadata.title||materials.find(m=>m.id===id)?.name||'原文')+(version?' · 版本 '+([...(materials.find(m=>m.id===id)?.versions||[])].sort((a,b)=>a.created_at-b.created_at).findIndex(v=>v.id===version)+1):'')});
    setSourcePage(useWorkspaceUI.getState().tabs.find(t=>sameDocument(t,{kind:'material',id,version}))?.readerPage||0);
    setReading(undefined);setSegments([]);setSelection(undefined);setAssetId(id); setVersionId(version); setPanel('material');setOriginalUrl(value=>{if(value)URL.revokeObjectURL(value);return '';}); setVersionDiff(undefined);
    setReaderLoading(true);
    try{const data=await readWindow(root,id,version,useWorkspaceUI.getState().tabs.find(t=>sameDocument(t,{kind:'material',id,version}))?.readerPage||0,contextAbort.current.signal,anchor);
    if(active.current.pid!==project||active.current.cid!==conversation||documentRequest.current!==requestId)return;
    setReading(data);setSegments(windowSegments(data));setVersionId(data.version.id);setSourcePage(data.page);setSelection(anchor);
    const canonicalTab={kind:'material' as const,id,version:data.version.id,title:String(materials.find(m=>m.id===id)?.metadata.title||materials.find(m=>m.id===id)?.name||'原文')+' · 版本 '+([...(materials.find(m=>m.id===id)?.versions||[])].sort((a,b)=>a.created_at-b.created_at).findIndex(v=>v.id===data.version.id)+1),readerPage:data.page,scroll:remembered?.scroll||0};
    setTabs(useWorkspaceUI.getState().tabs.filter(t=>!(t.kind==='material'&&t.id===id&&!t.version)));openTab(canonicalTab);
    if(anchor)setTimeout(()=>{if(documentRequest.current!==requestId)return;const section=document.getElementById(`uw-segment-${anchor.segment_id}`);(section?.querySelector('mark')||section)?.scrollIntoView({block:'center',behavior:quiet||window.matchMedia('(prefers-reduced-motion: reduce)').matches?'auto':'smooth'});},100);else setTimeout(()=>{if(documentRequest.current===requestId&&documentPane.current)documentPane.current.scrollTop=remembered?.scroll||0;},150);
    }finally{if(documentRequest.current===requestId)setReaderLoading(false);}

  }

  async function changeReadingPage(page:number){
    const identity=active.current;const requestId=++documentRequest.current;setReaderLoading(true);
    try{const data=await readWindow(root,assetId,versionId,page,contextAbort.current.signal);
      if(identity!==active.current||requestId!==documentRequest.current)return;
      setReading(data);setSegments(windowSegments(data));setSourcePage(data.page);setTabs(useWorkspaceUI.getState().tabs.map(tab=>sameDocument(tab,{kind:'material',id:assetId,version:versionId})?{...tab,readerPage:data.page}:tab));
    }finally{if(requestId===documentRequest.current)setReaderLoading(false);}
  }
  async function openArtifact(id: string) {
    if(window.innerWidth<1180&&useWorkspaceUI.getState().sidebarOpen)useWorkspaceUI.getState().toggleSidebar();
    const remembered=useWorkspaceUI.getState().tabs.find(t=>sameDocument(t,{kind:'artifact',id}));rememberDocument();
    const project=pid;const conversation=cid;const requestId=++documentRequest.current;
    const a = await request<ResearchRecord>(root + '/artifacts/' + id,{signal:contextAbort.current.signal});
    if(active.current.pid!==project||active.current.cid!==conversation||documentRequest.current!==requestId)return;
    openTab({kind:'artifact',id,title:a.payload.title||'研究文档'});
    setArtifact(a);setEditorJson(a.payload.editor_json); setEditTitle(a.payload.title || '研究文档'); setEditText(a.payload.text || '');
    setPanel('artifact');setCompare(undefined);setTimeout(()=>{if(documentRequest.current===requestId&&documentPane.current)documentPane.current.scrollTop=remembered?.scroll||0;},200);
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
    const start = Number(a.dataset.sourceOffset||0)+codepointOffset(a.textContent || '', before.toString().length);
    setSelection({ segment_id: a.dataset.source!, start_codepoint: start,
      end_codepoint: start + Array.from(range.toString()).length, exact_quote: range.toString() });
  }

  useEffect(() => {
    if (panel !== 'material') return;
    document.addEventListener('keyup', capture);
    return () => document.removeEventListener('keyup', capture);
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
      personalRevision.current=0;conversationId = c.id; setWorkspaceReady(true); setCid(c.id); active.current.cid = c.id; setConversations(cs => [c, ...cs]);
    }
    if (activeInterview?.current_question) {
      await request(`${root}/interviews/${activeInterview.id}/turns`, { method: 'POST', body: JSON.stringify({
        question_id: activeInterview.current_question.id, answer_text: draft }) });
      setActiveInterview(await request(`${root}/interviews/${activeInterview.id}`));
    } else {
      const fingerprint=JSON.stringify([draft,tool,selected,selection,mode,participantId,personaId,method]);
      if(sendKey.current?.text!==fingerprint)sendKey.current={text:fingerprint,key:crypto.randomUUID()};
      await sendMessage(pid,conversationId,{text:draft,tool,
          ...(selection ? {scope:[{asset_id:assetId,version_id:segments.find(s=>s.id===selection.segment_id)?.version_id,...selection}]} : {asset_ids:selected}), provider_mode:mode, review_mode:reviewMode,
          participant_id:participantId||null,persona_id:personaId||null,
          methods:method ? [method as 'situating.v1'|'immanent_critique.v1'|'parallax.v1'] : []},sendKey.current.key);
    }
    if(active.current.pid!==project||active.current.cid!==conversationId)return;
    sendKey.current=undefined;
    setDraft(value=>value===submittedDraft?'':value); localStorage.removeItem(scoped(`scriptorium_draft:${pid}:${conversationId}`));
    const nextMessages=await request<Message[]>(`${root}/conversations/${conversationId}/messages`);
    if(active.current.pid!==project||active.current.cid!==conversationId)return;
    setMessages(nextMessages);
    await loadProject(pid); if(feed.current && feed.current.scrollHeight-feed.current.scrollTop-feed.current.clientHeight<200)setTimeout(()=>feed.current?.scrollTo({top:feed.current.scrollHeight,behavior:'smooth'}),100);
  }

  async function deepen(record: ResearchRecord) {
    if (!pid || !cid) throw new Error('请先选择会话。');
    const question = String(record.payload.question || record.payload.title || draft);
    await sendMessage(pid, cid, { text: question, tool: 'research', scope: record.payload.scope,
      provider_mode: mode, token_budget: 40000 }, crypto.randomUUID());
    setNotice('已按这次阅读范围提交完整研究；进度显示在对话下方。');
    await loadProject(pid);
    setMessages(await request(`${root}/conversations/${cid}/messages`));
    setPanel('none');
  }

  async function upload(file: File) {
    const epoch=contextEpoch.current;const form = new FormData(); form.append('file', file);
    const job = await request<Job & { payload: { asset_id: string } }>(root + '/imports'+(cid?'?conversation_id='+encodeURIComponent(cid):''), {
      method: 'POST', headers: { 'Idempotency-Key': crypto.randomUUID() }, body: form });
    if(epoch!==contextEpoch.current)return;
    setSelected(xs => [...new Set([...xs, job.payload.asset_id])]);
    setNotice('材料已加入项目，正在处理。完成后可阅读和研究。');
  }

  const {sources:researchSources,intakes,sourceTotal}=useSources(pid,cid,eventConnected);
  const openSources=()=>{rememberDocument();setPanel('sources');setLayout('split');};
  const openSource=async(source:ResearchSource)=>{if(source.asset_id)await openMaterial(source.asset_id,source.version_id||'');};
  const conversationJobs=jobs.filter(j=>j.payload?.conversation_id===cid);
  const busyJobs = jobs.filter(j => ['running', 'queued'].includes(j.state));
  const runId = (conversationJobs[0]?.id || cid || '').slice(0, 4).toUpperCase();
  // A live answer can be both a timeline answer block and a persisted assistant message;
  // show it once (the flight log), even when the assistant metadata lacks job_id.
  const answeredInTimeline=(m:Message)=>{if(m.role!=='assistant')return false;if(m.metadata.job_id&&timelineBlocks.some(b=>b.job_id===m.metadata.job_id))return true;const text=(m.content||'').trim().slice(0,80);return !!text&&timelineBlocks.some(b=>b.kind==='answer'&&(b.payload.text||'').trim().startsWith(text));};
  // UI-04: unsaved edits and the saved version must stay distinguishable after a reload.
  const card = (a: ResearchRecord) => <article className="uw-artifact-content" key={a.id}>
    <h2>{a.payload.title}</h2>{a.payload.provider_mode === 'demo' && <span className="uw-badge">演示 · 非学术结论</span>}
    <MarkdownRenderer content={a.payload.text || ''} />
    {a.payload.dimensions && <dl>{Object.entries(a.payload.dimensions).map(([name, text]) => <div key={name}><dt>{name}</dt><dd>{text}</dd></div>)}</dl>}
    {a.payload.findings?.map((f, i) => <section key={i}><h3>{f.title}</h3><MarkdownRenderer content={f.text} />{f.evidence_ids?.map(id => <button key={id} onClick={() => void action(() => locate(id))}>查看依据</button>)}</section>)}
    {!!a.payload.open_questions?.length && <details><summary>未决问题</summary><ul>{a.payload.open_questions.map((q, i) => <li key={i}>{q}</li>)}</ul></details>}
    {a.payload.plan && <details><summary>检索与覆盖</summary><p>检索方式：{String(a.payload.plan.retrieval)}；命中 {String(a.payload.plan.hits ?? '—')}；阅读 {a.payload.coverage?.filter(c => c.status === 'read').length ?? 0} 段，未覆盖 {a.payload.coverage?.filter(c => c.status === 'unread').length ?? 0} 段。</p>{!!a.payload.followups?.length && <ul>{a.payload.followups.map((q, i) => <li key={i}>{q}</li>)}</ul>}</details>}
    {!!a.payload.evidence_ids?.length && <div className="uw-inline-actions">{a.payload.evidence_ids.map((id, i) => <button key={id} onClick={() => void action(() => locate(id))}>原文 {i + 1}</button>)}</div>}
  </article>;

  useConversationEvents(pid,cid,event=>{
    const resources=event?.type.startsWith('source.')?['materials']:event?.type==='research.phase'?['jobs']:event?.type==='message.created'?['conversations','records']:event?.type==='job.progress'?['conversations','jobs','records','materials','decisions','citation-drafts','model-calls']:['messages','jobs','records','materials','decisions','citation-drafts','model-calls'];
    const path=projectPath(pid);
    for(const name of ['sources','intakes'])void queryClient.invalidateQueries({predicate:q=>q.queryKey[0]==='api'&&q.queryKey[1]===serviceUrl()&&String(q.queryKey[2]).startsWith(path+'/'+name)});
    for(const resource of resources){const route=resource==='messages'?`/conversations/${cid}/messages?limit=80`:'/'+resource+(['jobs','records','model-calls'].includes(resource)?'?summary=true':'');void queryClient.invalidateQueries({queryKey:['api',serviceUrl(),path+route]}).then(()=>request(path+route)).then(data=>{if(active.current.pid!==pid||active.current.cid!==cid)return;switch(resource){case'messages':setMessages(old=>mergeMessages(old,data as Message[]));break;case'jobs':setJobs(data as Job[]);break;case'records':setArtifacts(data as ResearchRecord[]);break;case'materials':setMaterials(data as Material[]);break;case'conversations':setConversations(old=>(data as Conversation[]).map(c=>({...c,workspace:old.find(x=>x.id===c.id)?.workspace||c.workspace})));break;case'decisions':setDecisions(data as Decision[]);break;case'citation-drafts':setCitationDrafts(data as CitationDraft[]);break;case'model-calls':setUsage((data as{totals:typeof usage}).totals);}}).catch(()=>{});}
    void queryClient.invalidateQueries({queryKey:['api',serviceUrl(),path+'/tasks']});
  },event=>{
    if(event.type==='source.discovered'&&panel==='none'){setPanel('sources');setLayout('split');}
    if(event.type==='access.denied'){resetTransient();queryClient.removeQueries({predicate:q=>String(q.queryKey[2]||'').startsWith(projectPath(pid)+'/')});setMessages([]);setPid('');setCid('');setPanel('none');setNotice('当前会话不可访问，请重新选择项目或登录。');return;}
    if(event.type==='message.delta'||event.type==='message.created'||event.type==='timeline.block'){const view=feed.current;const follow=!!view&&following.current&&!window.getSelection()?.toString();if(follow){const identity=active.current;requestAnimationFrame(()=>{if(identity===active.current&&feed.current)feed.current.scrollTop=feed.current.scrollHeight;});}else setNewMessages(true);}
    if(event.type==='material.withdrawn'){setSelection(undefined);setSelected([]);setLiveDrafts({});setTimelineBlocks([]);setMessages([]);setPanel('none');setArtifact(undefined);setSegments([]);setTabs([]);void loadProject(pid);}
    if(event.type==='timeline.snapshot')setTimelineBlocks(event.payload.blocks||[]);
    if(event.type==='timeline.block'&&event.payload.block)setTimelineBlocks(old=>{try{return mergeBlock(old,{block:event.payload.block!,delta:event.payload.delta});}catch{void request<{blocks:TimelineBlock[]}>(`${root}/conversations/${cid}/snapshot`).then(value=>{if(active.current.pid===pid&&active.current.cid===cid)setTimelineBlocks(value.blocks);});return old;}});
    if(event.type==='message.delta')setLiveDrafts(old=>({...old,[event.payload.job_id]:(event.payload.replace?'':old[event.payload.job_id]||'')+event.payload.text}));
    if(event.type==='message.created'&&event.payload.message){setMessages(old=>mergeMessages(old,[event.payload.message as Message]));}
    if(event.type==='message.created'||event.type==='job.progress'){const id=event.payload.message?.metadata?.job_id||(['failed','cancelled','running','succeeded'].includes(event.payload.state||'')?event.payload.job_id:undefined);if(id)setLiveDrafts(old=>{const next={...old};delete next[id];return next;});}
  },setEventConnected);


  useEffect(()=>{const handler=(e:KeyboardEvent)=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='k'){e.preventDefault();setCommandsOpen(v=>!v);}if(e.key==='Escape'&&!settingsOpen&&!projectOpen&&!commandsOpen&&layout==='focus')setLayout('split');};window.addEventListener('keydown',handler);return()=>window.removeEventListener('keydown',handler);},[layout,settingsOpen,projectOpen,commandsOpen,setLayout]);
  useEffect(()=>{const resize=()=>{if(window.innerWidth<1180&&useWorkspaceUI.getState().sidebarOpen)useWorkspaceUI.getState().toggleSidebar();};window.addEventListener('resize',resize);return()=>window.removeEventListener('resize',resize);},[]);
  const commands:Command[]=[{id:'new',title:'开始新研究',group:'操作',icon:'plus',run:()=>{void action(newResearch);}},{id:'settings',title:'设置与模型',group:'操作',icon:'settings',run:()=>setSettingsOpen(true)},{id:'library',title:'检索项目材料',group:'操作',icon:'search',run:()=>{setPanel('search');setLayout('split');}},...conversations.filter(c=>!c.archived).map(c=>({id:'c-'+c.id,title:c.title,group:'研究会话',icon:'chat',run:()=>{void action(()=>chooseConversation(pid,c.id,conversations));}})),...materials.map(m=>({id:'m-'+m.id,title:String(m.metadata.title||m.name),group:'项目材料',icon:'book',run:()=>{void action(()=>openMaterial(m.id));}})),...artifacts.map(a=>({id:'a-'+a.id,title:a.payload.title||'研究文档',group:'文稿与报告',icon:'file',run:()=>{void action(()=>openArtifact(a.id));}}))];
  const selectTab=(tab:DocumentTab)=>void action(()=>tab.kind==='material'?openMaterial(tab.id,tab.version):openArtifact(tab.id));
  const closeTab=(index:number)=>{const remaining=tabs.filter((_,i)=>i!==index);setTabs(remaining);const tab=tabs[index];if((panel==='material'&&sameDocument(tab,{kind:'material',id:assetId,version:versionId}))||(tab.kind==='artifact'&&artifact?.id===tab.id&&panel==='artifact')){if(remaining.length)selectTab(remaining[Math.max(0,index-1)]);else{setPanel('none');setLayout('chat');}}};
  return <div className={'layout-'+layout+' unified-workspace ' + (panel !== 'none' ? 'uw-document-open ' : '') + (!sidebarOpen ? 'uw-sidebar-collapsed ' : '') + (quiet ? 'uw-quiet' : '') + (halo ? 'fd-halo' : '')}>
    <HaloLayer visible={halo}/>
    <ProjectSidebar onSources={openSources} sourceCount={sourceTotal} projects={projects} pid={pid} conversations={conversations} cid={cid} materials={materials} artifacts={artifacts} selected={selected} open={sidebarOpen} busy={busyJobs.length} readOnly={readOnly}
      onToggle={toggleSidebar} onProject={id=>void action(()=>chooseProject(id))} onCreateProject={()=>void action(async()=>{const name=await ask('项目名称');if(!name)return;const p=await request<Project>('/api/v2/projects',{method:'POST',body:JSON.stringify({name})});setProjects(xs=>[...xs,p]);await chooseProject(p.id);})}
      onResearch={()=>void action(newResearch)} onConversation={id=>void action(()=>chooseConversation(pid,id,conversations))} onMaterial={id=>void action(()=>openMaterial(id))} onArtifact={id=>void action(()=>openArtifact(id))} onSelect={id=>setSelected(xs=>xs.includes(id)?xs.filter(x=>x!==id):[...xs,id])} onUpload={upload} onRecordPatch={(id,value)=>action(async()=>{const record=await request<ResearchRecord>(`${root}/artifacts/${id}`);await request(`${root}/records/${id}`,{method:'PUT',body:JSON.stringify({kind:record.kind,revision:record.revision,payload:{...record.payload,...value}})});await loadProject(pid);})} onSearch={()=>setCommandsOpen(true)} onSettings={()=>setSettingsOpen(true)} onTeam={()=>setProjectOpen(true)} onNewManuscript={()=>void action(async()=>{const a=await request<ResearchRecord>(root+'/records',{method:'POST',body:JSON.stringify({kind:'manuscript',payload:{title:'未命名文稿',text:''}})});await loadProject(pid);await openArtifact(a.id);})}/>


    <main className="uw-conversation">
      <MissionBar project={projects.find(p=>p.id===pid)?.name||''} title={current?.title||''}
        runId={runId} usage={usage} sources={sourceTotal} jobs={busyJobs.length} connected={eventConnected}
        theme={theme} onTheme={toggleTheme} onMenu={toggleSidebar} onSearch={()=>setCommandsOpen(true)} halo={halo} onHalo={toggleHalo}
        menu={current?<ConversationMenu onRename={()=>void action(async()=>{const title=await ask('会话名称',current.title);if(title){await request(`${root}/conversations/${cid}`,{method:'PUT',body:JSON.stringify({revision:current.revision,title})});await loadProject(pid);}})} onArchive={()=>void action(async()=>{await request(`${root}/conversations/${cid}`,{method:'PUT',body:JSON.stringify({revision:current.revision,archived:true})});await chooseProject(pid);})}/>:undefined}/>
      {!eventConnected&&cid&&<div className="wb-connection-state" role="status">正在恢复实时连接 · 已保存内容可继续查看</div>}{restoreError&&<div className="uw-error"><span>工作区恢复未完成，已保留草稿。</span><button onClick={()=>void chooseConversation(pid,cid,conversations)}>重新恢复当前会话</button></div>}{error&&<div className="uw-error" role="alert"><span>{/401|LOGIN_REQUIRED/.test(error)?'请登录课题组，或检查服务连接。':/signal|timeout|fetch/i.test(error)?'连接暂时中断，已保存内容和当前输入仍然保留。':'操作未完成，当前内容已保留。'}</span><button className="wb-icon" onClick={()=>setError('')} aria-label="关闭提示"><Icon name="close" size={14}/></button><details><summary>查看详情</summary>{error}</details></div>}
      {notice && <div className="uw-notice" role="status">{notice}<button onClick={() => setNotice('')}>关闭</button></div>}
      {!!researchSources.length&&<button className="wb-source-entry" onClick={openSources}><Icon name="book" size={16}/>查看研究来源 <span>{researchSources.length}</span></button>}
      <SectionBoundary key={cid} name="对话"><div className="uw-feed" ref={feed} onScroll={e=>{following.current=e.currentTarget.scrollHeight-e.currentTarget.scrollTop-e.currentTarget.clientHeight<96;setScrollPosition(e.currentTarget.scrollTop);}}>
        {!messages.length&&<section className="uw-welcome"><span className="wb-welcome-mark"><Icon name="spark" size={28}/></span><span className="wb-eyebrow">RESEARCH INSTRUMENT · STANDBY</span><h2>把问题交给任务台。</h2><p>提出问题，自动寻找材料、阅读分析，并保留每一处来源。</p>{auth?.authenticated===false?<a className="wb-login" href={serviceUrl()+'/api/v2/auth/login'}>登录课题组</a>:<div className="wb-starters">{['研究黑格尔与马克思对自由的不同理解','梳理一个概念的来源与历史变化','检验这项解释，寻找反例'].map((text,i)=><button key={text} disabled={!pid} onClick={()=>{setDraft(text);setTool(i===0?'ask':'research');}}><Icon name={i===0?'chat':i===1?'book':'spark'} size={17}/><span>{text}</span><Icon name="chevron" size={14}/></button>)}</div>}<div className="wb-welcome-secondary"><label><Icon name="attach" size={15}/>导入材料<input type="file" hidden accept=".txt,.md,.pdf,.xml,.tei" disabled={!pid||readOnly} onChange={e=>{const f=e.target.files?.[0];if(f)void action(()=>upload(f));}}/></label><button disabled={!pid||readOnly} onClick={()=>{setPanel('people');setLayout('split');}}><Icon name="users" size={15}/>开始访谈</button></div></section>}
        {hasOlder&&<button className="wb-load-older" onClick={()=>void action(async()=>{const first=messages[0];if(!first)return;const height=feed.current?.scrollHeight||0;const top=feed.current?.scrollTop||0;const older=await request<Message[]>(`${root}/conversations/${cid}/messages?limit=80&before=${encodeURIComponent(first.id)}`);setHasOlder(older.length===80);setMessages(old=>[...older.filter(m=>!old.some(x=>x.id===m.id)),...old]);setMessageLimit(v=>v+80);requestAnimationFrame(()=>{if(feed.current)feed.current.scrollTop=top+feed.current.scrollHeight-height;});})}>加载较早消息</button>}
        {messages.slice(-messageLimit).filter(m=>m.role==='user'||!answeredInTimeline(m)).map(m => <div key={m.id}><article key={m.id} className={'uw-message ' + m.role}><small>{m.role === 'user' ? '你' : 'Scriptorium'}{m.metadata.provider_mode === 'demo' ? ' / 演示' : ''}</small><MarkdownRenderer content={m.content} />
          {!!m.artifact_ids.length && <div className="uw-result-actions">{m.artifact_ids.map(id => <button key={id} onClick={() => void action(() => openArtifact(id))}><Icon name="file" size={16}/> {artifacts.find(a => a.id === id)?.payload.title || '打开研究文档'}</button>)}</div>}
          {m.metadata.interview_id && <button onClick={() => void action(async () => { setActiveInterview(await request(`${root}/interviews/${m.metadata.interview_id}`)); setPanel('interview'); })}>继续此访谈</button>}
        </article>{m.role==='user'&&timelineBlocks.some(b=>b.job_id===m.metadata.job_id)&&<ResearchTimeline blocks={timelineBlocks.filter(b=>b.job_id===m.metadata.job_id)} job={conversationJobs.find(j=>j.id===m.metadata.job_id)} onCancel={()=>void action(async()=>{await request(`${root}/jobs/${m.metadata.job_id}/cancel`,{method:'POST'});})} onArtifact={id=>void action(()=>openArtifact(id))} onLocate={id=>void action(()=>locate(id))}>{intakes.filter(i=>i.job_id===m.metadata.job_id).map(i=><IntakeProgress key={i.job_id} items={[i]} root={root} readOnly={readOnly} onSources={openSources} onSettings={()=>setSettingsOpen(true)} onError={setError} compact/>)}{conversationJobs.filter(j=>j.id===m.metadata.job_id&&j.state==='failed').map(j=><TaskFailure key={j.id} error={j.error||''} onRetry={()=>void action(async()=>{await request(`${root}/jobs/${j.id}/retry`,{method:'POST'});await loadProject(pid);})} onMaterials={()=>setProjectOpen(true)} onAuto={()=>setTool('auto')} onSettings={()=>setSettingsOpen(true)}/>)}{decisions.filter(d=>d.conversation_id===cid&&timelineBlocks.some(b=>b.job_id===m.metadata.job_id&&b.kind==='turn'&&b.payload.result?.run_id===d.run_id)).map(d=><ResearchDecision key={d.id} decision={d} readOnly={readOnly} onAnswer={(accept,tokens)=>action(async()=>{await request(`${root}/decisions/${d.id}`,{method:'POST',body:JSON.stringify({accept,additional_tokens:tokens})});await loadProject(pid);})}/>)}</ResearchTimeline> }</div>)}
        {Object.entries(liveDrafts).filter(([id])=>!timelineBlocks.some(b=>b.job_id===id)).map(([id,text])=><article className="uw-message assistant" key={id}><small>SCRIPTORIUM / 正在生成的草稿</small><MarkdownRenderer content={text}/></article>)}
        {newMessages&&<button className="uw-new-messages" onClick={()=>{feed.current?.scrollTo({top:feed.current.scrollHeight,behavior:quiet?'auto':'smooth'});setNewMessages(false);}}>查看新进展 ↓</button>}
        {decisions.filter(d=>d.conversation_id===cid&&!timelineBlocks.some(b=>b.kind==='turn'&&b.payload.result?.run_id===d.run_id)).map(d=><ResearchDecision key={d.id} decision={d} readOnly={readOnly} onAnswer={(accept,tokens)=>action(async()=>{await request(`${root}/decisions/${d.id}`,{method:'POST',body:JSON.stringify({accept,additional_tokens:tokens})});await loadProject(pid);})}/>)}
        {citationDrafts.filter(d=>d.conversation_id===cid||(!d.conversation_id&&jobs.some(j=>j.id===d.job_id&&j.payload?.conversation_id===cid))).map(d=><CitationReview key={d.id} draft={d} onBind={index=>void action(async()=>{if(!selection)throw new Error('请先打开对应原文并选择正确摘录。');const result=await request<{state:string}>(`${root}/citation-drafts/${d.id}/resolve`,{method:'POST',body:JSON.stringify({revision:d.revision,bindings:[{index,...selection,version_id:segments.find(s=>s.id===selection.segment_id)?.version_id}]})});setNotice(result.state==='pending'?'已保存这一处绑定，其余摘录仍需核验。':'引文已通过核验，研究继续。');await loadProject(pid);})} onDiscard={()=>void action(async()=>{await request(`${root}/citation-drafts/${d.id}/resolve`,{method:'POST',body:JSON.stringify({revision:d.revision,discard:true})});await loadProject(pid);})}/>)}
        <IntakeProgress items={intakes.filter(i=>!timelineBlocks.some(b=>b.job_id===i.job_id))} root={root} readOnly={readOnly} onSources={openSources} onSettings={()=>setSettingsOpen(true)} onError={setError}/>
        <ResearchProgress jobs={conversationJobs.filter(j=>['running','queued'].includes(j.state)&&!intakes.some(i=>i.job_id===j.id)&&!timelineBlocks.some(b=>b.job_id===j.id)&&!['method','source_fetch'].includes(j.kind))} usage={usage} onCancel={id=>void action(async()=>{await request(`${root}/jobs/${id}/cancel`,{method:'POST'});await loadProject(pid);})}/>
        {conversationJobs.filter(j=>j.state==='failed'&&!timelineBlocks.some(b=>b.job_id===j.id)&&!intakes.some(i=>i.job_id===j.id&&['completed','awaiting_input'].includes(i.state))).slice(0,3).map(j=><TaskFailure key={j.id} error={j.error||''} onRetry={()=>void action(async()=>{await request(`${root}/jobs/${j.id}/retry`,{method:'POST'});await loadProject(pid);})} onMaterials={()=>setProjectOpen(true)} onAuto={()=>{setTool('auto');setNotice('已切换为自动。请重新提出研究问题，或补充你希望寻找的材料。');}} onSettings={()=>setSettingsOpen(true)}/>)}
      </div>
      </SectionBoundary><ResearchComposer draft={draft} onDraft={setDraft} onSend={()=>void action(send)} onUpload={f=>void action(()=>upload(f))}
        disabled={!pid||readOnly||!workspaceReady} busy={busy} tool={tool} method={method} mode={mode} onMode={setMode} reviewMode={reviewMode} onReviewMode={chooseReviewMode}
        onTool={(t,m)=>{setTool(t);setMethod(m);if(t==='persona'||t==='subject'){setPanel('people');setLayout('split');}}} onPeople={()=>{setPanel('people');setLayout('split');}}
        selection={selection} onClearSelection={()=>setSelection(undefined)} materials={selected.map(id=>({id,name:String(materials.find(m=>m.id===id)?.metadata.title||materials.find(m=>m.id===id)?.name||'所选材料')}))}
        onRemoveMaterial={id=>setSelected(xs=>xs.filter(x=>x!==id))} answering={!!activeInterview?.current_question}
        interview={activeInterview&&<div className="uw-interview-banner">访谈：{people.find(p=>p.id===activeInterview.participant_id)?.pseudonym} · {activeInterview.state}<button onClick={()=>setPanel('interview')}>访谈控制</button><button onClick={()=>setActiveInterview(undefined)}>返回研究对话</button></div>}/>

    </main>

    {panel !== 'none' && panel!=='settings' && <DocumentPane width={documentWidth} onResize={setDocumentWidth}><header><button className="wb-icon" aria-label="打开项目导航" onClick={toggleSidebar}><Icon name="panel" size={16}/></button>{trailLength>0&&<button className="wb-icon" onClick={previousDocument} aria-label="返回上一个文档"><Icon name="back" size={16}/></button>}<span className="wb-doc-context">{panel==='sources'?'研究来源':panel==='material'?'原文阅读':panel==='artifact'?'研究文档':panel==='people'?'研究对象':panel==='search'?'项目检索':'研究访谈'}</span><button className="wb-icon" aria-label={layout==='focus'?'恢复并置布局':'专注阅读'} onClick={()=>setLayout(layout==='focus'?'split':'focus')}><Icon name={layout==='focus'?'panel':'expand'} size={16}/></button><button className="wb-icon" aria-label="关闭文档" onClick={()=>{setPanel('none');setLayout('chat');}}><Icon name="close" size={17}/></button></header>
    {tabs.length>0&&<div className="wb-document-tabs" role="tablist" aria-label="打开的文档">{tabs.map((tab,i)=><div className={'wb-document-tab '+((panel==='material'&&sameDocument(tab,{kind:'material',id:assetId,version:versionId}))||(panel==='artifact'&&sameDocument(tab,{kind:'artifact',id:artifact?.id||''}))?'active':'')} key={documentKey(tab)}><button role="tab" aria-selected={(panel==='material'&&sameDocument(tab,{kind:'material',id:assetId,version:versionId}))||(panel==='artifact'&&sameDocument(tab,{kind:'artifact',id:artifact?.id||''}))} onClick={()=>selectTab(tab)}><Icon name={tab.kind==='material'?'book':'file'} size={14}/><span>{tab.title}</span></button><button aria-label={'关闭 '+tab.title} onClick={()=>closeTab(i)}><Icon name="close" size={12}/></button></div>)}</div>}
    <div className="uw-document-body" ref={documentPane} onScroll={e=>{const top=e.currentTarget.scrollTop;setDocumentScroll(top);const target=panel==='material'?{kind:'material' as const,id:assetId,version:versionId}:panel==='artifact'?{kind:'artifact' as const,id:artifact?.id||''}:undefined;if(target)setTabs(useWorkspaceUI.getState().tabs.map(tab=>sameDocument(tab,target)?{...tab,scroll:top}:tab));}}>
      <div hidden={panel!=='sources'}><SourceLibrary key={pid+cid} root={root} conversationId={cid} online={eventConnected} onOpen={s=>void action(()=>openSource(s))} onError={setError} readOnly={readOnly}/></div>
      {panel === 'material' && <>{currentMaterial?.metadata.source_quality==='search_excerpt'&&<p className="wb-source-warning">搜索摘要快照 · 非原文全文；引用只代表这份摘要。</p>}<h2>{String(currentMaterial?.metadata.title || currentMaterial?.name || '研究材料')}</h2><div className="uw-inline-actions"><select aria-label="文本版本" value={versionId} onChange={e => { setVersionDiff(undefined); void action(() => openMaterial(assetId, e.target.value)); }}><option value="">最新文本</option>{[...(currentMaterial?.versions || [])].sort((a, b) => a.created_at - b.created_at).map((v, i) => <option key={v.id} value={v.id}>版本 {i + 1}</option>)}</select><button disabled={(currentMaterial?.versions.length || 0) < 2} onClick={() => void action(compareVersion)}>比较上一版</button><button onClick={() => void action(async () => { if(!currentMaterial?.name.toLowerCase().endsWith('.pdf')){await download(`${root}/materials/${assetId}/original`,currentMaterial?.metadata.source_mime==='text/html'?'source-snapshot.html':currentMaterial?.name||'source');return;}const r = await response(`${root}/materials/${assetId}/original`); if (originalUrl) URL.revokeObjectURL(originalUrl); setOriginalUrl(URL.createObjectURL(await r.blob())); })}>原件</button><button onClick={() => void action(() => download(`${root}/materials/${assetId}/tei${versionId?'?version_id='+encodeURIComponent(versionId):''}`, 'source.xml'))}>导出 TEI</button></div>
        {versionDiff && <section className="uw-version-diff"><h3>版本对照 · {versionDiff.oldLabel} → {versionDiff.newLabel}</h3><p className="uw-muted">按 xml:id 对齐逐段比较：未变 {versionDiff.counts.same || 0} · 修改 {versionDiff.counts.changed || 0} · 新增 {versionDiff.counts.added || 0} · 删除 {versionDiff.counts.removed || 0}。旧版引用保持原段落位置，不随修订移动。</p><ol>{versionDiff.rows.filter(row => row.state !== 'same').map(row => <li key={row.xml_id} className={'uw-diff-' + row.state}><small>{({ added: '新增段落', removed: '删除段落', changed: '文本修改' } as Record<string, string>)[row.state]} · {row.xml_id}</small>{row.before && <p className="uw-diff-old">{row.before}</p>}{row.now && <p className="uw-diff-new">{row.now}</p>}</li>)}{!versionDiff.rows.some(row => row.state !== 'same') && <li className="uw-diff-same">两个版本正文没有段落差异。</li>}</ol><button onClick={() => setVersionDiff(undefined)}>关闭对照</button></section>}
        {originalUrl && <><object className="uw-original" data={originalUrl} type="application/pdf"><p>原件无法内嵌预览，请下载查看。</p></object><button onClick={() => setOriginalUrl('')}>返回文本</button></>}
        {!originalUrl&&<SourceReader locationLabel={currentMaterial?.metadata.source_quality==='search_excerpt'?'摘要快照':currentMaterial?.name.toLowerCase().endsWith('.pdf')?'文件页':'文本页'} key={pid+':'+assetId+':'+versionId} segments={segments} selection={selection} page={sourcePage} reading={reading} loading={readerLoading} onPage={page=>void action(()=>changeReadingPage(page))} onCapture={capture} onDismiss={()=>setSelection(undefined)} selectionTools={selection && <section className="uw-selection"><blockquote>{selection.exact_quote}</blockquote><div className="uw-inline-actions"><button onClick={() => { setDraft('请解释这段材料：\n' + selection.exact_quote); setTool('chat'); setSelected(xs => [...new Set([...xs, assetId])]); }}>解释</button><button onClick={() => { setDraft('请比较这段材料与所选材料：\n' + selection.exact_quote); setTool('research'); }}>比较</button><button onClick={() => { setSelected(xs => [...new Set([...xs, assetId])]); setNotice('当前材料已加入研究范围。'); }}>用于研究</button></div><textarea aria-label="原文笔记" value={note} onChange={e => setNote(e.target.value)} placeholder="记录理解；保存时自动关联原文证据" /><button onClick={() => void action(saveSelection)}>保存笔记与证据</button></section>}/> }

        <details><summary>书目信息与处理状态</summary>{currentMaterial&&<BibliographyForm key={currentMaterial.id} root={root} material={currentMaterial} readOnly={readOnly} onSaved={()=>void loadProject(pid)}/>}{currentMaterial?.versions.map(v => <p key={v.id}>{String(v.quality.extractor).startsWith('ocr') || v.quality.extractor === 'local-tesseract' ? 'OCR 转录（' + String(v.quality.engine || v.quality.extractor) + '），未经人工校核' : '文本转录'}{Array.isArray(v.quality.empty_pages) && v.quality.empty_pages.length > 0 ? '，存在未识别页面：' + (v.quality.empty_pages as number[]).join('、') : ''}{Array.isArray(v.quality.ocr_unavailable_pages) && v.quality.ocr_unavailable_pages.length > 0 ? '，未识别（缺引擎或语言数据）：' + (v.quality.ocr_unavailable_pages as number[]).join('、') : ''}</p>)}{currentMaterial?.name.toLowerCase().endsWith('.pdf') && <button onClick={() => void action(async () => {await request(`${root}/materials/${assetId}/ocr`,{method:'POST'});await loadProject(pid);setNotice('已提交本地 OCR；结果保存为新版本并标为待校核。');})}>识别扫描页</button>}</details><details><summary>版本修订与材料管理</summary><label>上传修订 TEI<input type="file" accept=".xml,.tei" onChange={e => { const f = e.target.files?.[0]; if (f && currentMaterial) void action(async () => { await request(`${root}/materials/${assetId}/revisions`, { method: 'POST', body: JSON.stringify({ revision: currentMaterial.revision, tei: await f.text() }) }); await loadProject(pid); await openMaterial(assetId); }); }} /></label><button onClick={() => void action(async () => { if (!await confirmDialog('撤回此材料并清理相关派生内容？')) return; await request(`${root}/materials/${assetId}`, { method: 'DELETE' }); setPanel('none'); await loadProject(pid); })}>撤回材料</button></details>
      </>}

      {panel==='artifact'&&artifact&&<SectionBoundary key={artifact.id} name="文档" resetKey={artifact.id}><Suspense fallback={<div className="wb-skeleton">正在打开研究文档…</div>}><ArtifactWorkspace key={artifact.id} record={artifact} root={root} conversationId={cid} online={eventConnected} draftKey={`scriptorium_document:${pid}:${artifact.id}:user:${auth?.user_id||'local'}`} mode={mode} readOnly={readOnly} onSaved={r=>{if(r.id!==artifact.id)openTab({kind:'artifact',id:r.id,title:r.payload.title||'文稿副本'});useWorkspaceUI.getState().setTabs(useWorkspaceUI.getState().tabs.map(t=>t.id===r.id?{...t,title:r.payload.title||t.title}:t));setArtifact(r);setEditorJson(r.payload.editor_json);setEditText(r.payload.text||'');setEditTitle(r.payload.title||'');}} onDraft={(title,text,json)=>{setEditTitle(title);setEditText(text);setEditorJson(json);}} onLocate={id=>void action(()=>locate(id))} onContinue={()=>{setDraft('请回到原文，继续检验这项解释：'+(artifact.payload.title||''));setTool('research');setLayout('split');if(artifact.kind==='research_answer')void action(()=>deepen(artifact));}} onInsert={()=>void action(async()=>{if(writingTarget?.project===pid&&writingTarget.record!==artifact.id){const id=await insertResearch(root,writingTarget,artifact);await openArtifact(id);setNotice('已插入当前写作位置。');await loadProject(pid);return;}const a=await request<ResearchRecord>(root+'/records',{method:'POST',body:JSON.stringify({kind:'manuscript',payload:{title:'文稿 · '+artifact.payload.title,text:artifact.payload.text||'',editor_json:artifact.payload.editor_json,evidence_ids:artifact.payload.evidence_ids||[],source_record_ids:[artifact.id]}})});await loadProject(pid);await openArtifact(a.id);})}/></Suspense>
      {artifact.payload.legacy_run_id&&<details className="wb-unresolved"><summary>历史分析与评议</summary>{['approve','revise','reject'].map(decision=><button key={decision} onClick={()=>void action(async()=>{const reason=await ask('评议说明')||'';await request(`${root}/analysis-runs/${artifact.payload.legacy_run_id}/reviews`,{method:'POST',body:JSON.stringify({decision,reason})});setNotice('评议已保存。');})}>{({approve:'通过',revise:'要求修订',reject:'驳回'} as Record<string,string>)[decision]}</button>)}<button onClick={()=>void action(()=>download(`${root}/analysis-runs/${artifact.payload.legacy_run_id}/export`,'historical-analysis.json'))}>导出原分析</button></details>}
      <details className="wb-unresolved"><summary>比较与关系视图</summary><div className="uw-inline-actions"><button onClick={()=>{setGraphKind('research');setLayout('focus');}}>研究关系</button><button onClick={()=>{setGraphKind('concept');setLayout('focus');}}>概念演化</button>{artifacts.filter(a=>a.id!==artifact.id).map(a=><button key={a.id} onClick={()=>{setCompare([artifact,a]);setLayout('focus');}}>{a.payload.title}</button>)}</div>{compare&&<div className="uw-comparison">{compare.map(card)}</div>}{graphKind&&<Suspense fallback={<p>正在打开关系视图…</p>}><ReportGraph root={root} kind={graphKind} records={artifacts} onOpen={id=>void action(()=>openArtifact(id))}/></Suspense>}</details></SectionBoundary>}

      {panel === 'people' && <><h2>访谈与风格模拟</h2><p>参与者与材料属于当前项目，授权用途分别记录。</p><form onSubmit={e => { e.preventDefault(); const f = new FormData(e.currentTarget); void action(async () => { const p = await request<Participant>(root + '/participants', { method: 'POST', body: JSON.stringify({ pseudonym: f.get('name'), material_collection: f.get('collection') === 'on', profile_analysis: f.get('profile') === 'on', agent_simulation: f.get('simulation') === 'on' }) }); setParticipantId(p.id); await loadProject(pid); }); }}><label>参与者代称<input name="name" required /></label><label className="uw-check"><input type="checkbox" name="collection" required />已获得材料采集授权</label><label className="uw-check"><input type="checkbox" name="profile" />已获得主体分析授权</label><label className="uw-check"><input type="checkbox" name="simulation" />已获得风格模拟授权</label><button>登记参与者与授权</button></form>
        <label>当前参与者<select value={participantId} onChange={e => setParticipantId(e.target.value)}><option value="">选择参与者</option>{people.filter(p => !p.withdrawn_at).map(p => <option key={p.id} value={p.id}>{p.pseudonym}</option>)}</select></label>
        <div className="uw-inline-actions"><button disabled={!participantId || !cid} onClick={() => void action(async () => { const iv = await request<Interview>(root + '/interviews', { method: 'POST', body: JSON.stringify({ participant_id: participantId, conversation_id: cid, provider_mode: mode }) }); setActiveInterview(iv); setPanel('interview'); await loadProject(pid); setMessages(await request(`${root}/conversations/${cid}/messages`)); })}>开始访谈</button><button disabled={!participantId} onClick={() => void action(async () => { await request(`${root}/participants/${participantId}/materials`, { method: 'POST', body: JSON.stringify({ asset_ids: selected }) }); setNotice('所选材料已关联参与者。'); })}>关联所选材料</button><button disabled={!participantId} onClick={() => { setTool('subject'); setDraft('请基于所选授权材料进行主体分析。'); }}>主体分析</button></div>
        {participantId && <details><summary>更新用途授权</summary>{['material_collection','profile_analysis','agent_simulation'].map(k => <label className="uw-check" key={k}><input type="checkbox" checked={people.find(p => p.id === participantId)?.permissions[k] || false} onChange={e => void action(async () => { const person=people.find(p=>p.id===participantId)!; await request(`${root}/participants/${participantId}`, {method:'PUT',body:JSON.stringify({pseudonym:person.pseudonym,...person.permissions,[k]:e.target.checked})}); await loadProject(pid);})}/>{({material_collection:'材料采集',profile_analysis:'主体分析',agent_simulation:'风格模拟'} as Record<string,string>)[k]}</label>)}<button onClick={() => void action(async () => {if(!await confirmDialog('撤回参与者及其材料和派生数据？'))return;await request(`${root}/participants/${participantId}/withdraw`,{method:'POST'});setParticipantId('');await loadProject(pid);})}>撤回授权与相关数据</button></details>}<h3>风格模拟</h3><button disabled={!participantId} onClick={() => void action(async () => { const name = await ask('风格模拟名称'); if (!name) return; const p = await request<Persona>(root + '/personas', { method: 'POST', body: JSON.stringify({ name, participant_id: participantId }) }); setPersonaId(p.id); await loadProject(pid); })}>新建模拟对象</button>
        {personas.map(p => <section className="uw-object-card" key={p.id}><strong>{p.name}</strong><small>AI 模拟 / {p.status}</small><div className="uw-inline-actions"><button onClick={() => void action(async () => { await request(`${root}/personas/${p.id}/train`, { method: 'POST' }); setNotice('已提交本地训练任务。'); await loadProject(pid); })}>训练</button><button onClick={() => { setPersonaId(p.id); setTool('persona'); setNotice('已选择风格模拟，回复将标注 AI 身份。'); }}>开始对话</button><button onClick={() => void action(async () => { await request(`${root}/personas/${p.id}`, { method: 'DELETE' }); await loadProject(pid); })}>删除模拟</button></div></section>)}
        <h3>已有访谈</h3>{interviews.map(iv => <button className="uw-document-item" key={iv.id} onClick={() => void action(async () => { setActiveInterview(await request(`${root}/interviews/${iv.id}`)); setPanel('interview'); })}>{people.find(p => p.id === iv.participant_id)?.pseudonym || '访谈'} · {iv.state}</button>)}
      </>}

      {panel === 'interview' && activeInterview && <><h2>研究访谈</h2><p>{activeInterview.current_question?.text || '主问题已完成，可以生成研究材料。'}</p><p className="uw-muted">在中间输入框回答。访谈状态和问答将持久保存。</p><div className="uw-inline-actions">{['pause', 'resume', 'complete', 'reset'].map(a => <button key={a} onClick={() => void action(async () => { const r = await request<Interview & { job_id?: string }>(`${root}/interviews/${activeInterview.id}/${a}`, { method: 'POST' }); if (a === 'complete') { setActiveInterview(undefined); setNotice('访谈已完成，正在生成项目材料。'); } else setActiveInterview(r); await loadProject(pid); })}>{({ pause: '暂停', resume: '恢复', complete: '生成材料', reset: '重新开始' } as Record<string, string>)[a]}</button>)}</div></>}

      {panel === 'search' && <><h2>检索材料</h2><form onSubmit={e => { e.preventDefault(); void action(async () => { const result = await request<{ items: Segment[] }>(root + '/search?q=' + encodeURIComponent(searchText) + (searchAuthor ? '&author=' + encodeURIComponent(searchAuthor) : '') + (searchYear ? '&year_from=' + encodeURIComponent(searchYear) : '')); setHits(result.items); }); }}><label>原词或短语<input value={searchText} onChange={e => setSearchText(e.target.value)} /></label><details><summary>书目筛选</summary><label>作者<input value={searchAuthor} onChange={e => setSearchAuthor(e.target.value)} /></label><label>起始年份<input type="number" value={searchYear} onChange={e => setSearchYear(e.target.value)} /></label></details><button>搜索当前项目</button></form>{hits.map(hit => <button className="uw-search-hit" key={hit.id} onClick={() => void action(() => openMaterial(hit.asset_id, hit.version_id))}>{hit.text.slice(0, 200)}</button>)}</>}


    </div></DocumentPane>}
    <SurfaceDialog open={settingsOpen} onClose={()=>setSettingsOpen(false)} title="设置" description="模型、连接与工作台偏好" wide><SectionBoundary name="设置"><form onSubmit={e => { e.preventDefault(); void action(async () => { const url = new URL(serviceAddress); if (!['http:', 'https:'].includes(url.protocol) || url.username || url.password || url.pathname !== '/') throw new Error('请填写不含路径和凭证的服务地址。'); await configureConnection(url.origin,apiKey); const ps = await request<Project[]>('/api/v2/projects'); setProjects(ps); await chooseProject(ps[0]?.id || ''); setNotice('连接已保存，所有研究能力使用此服务。'); }); }}><label>统一服务地址<input value={serviceAddress} onChange={e => setServiceAddress(e.target.value)} /></label><label>访问密钥（仅本次会话）<input type="password" value={apiKey} onChange={e => setApiKey(e.target.value)} /></label><button>保存连接</button></form>
        {auth?.mode==='oidc'&&<div className="uw-inline-actions"><span>{auth.name||auth.user_id}</span><button onClick={()=>void action(async()=>{await request('/api/v2/auth/logout',{method:'POST'});window.location.reload();})}>退出当前登录</button></div>}<ModelProviderForm/>
        <h3>界面与动效</h3><label className="uw-check"><input type="checkbox" checked={quiet} onChange={e=>setQuiet(e.target.checked)}/>安静模式（减少转场与动态效果）</label><h3>品牌与启动</h3>{([['enabled', '启动动画'], ['requireInteraction', '交互式播放'], ['sound', '声音'], ['voice', '语音']] as const).map(([name, label]) => <label className="uw-check" key={name}><input type="checkbox" checked={startup[name]} onChange={e => { const patch = { [name]: e.target.checked }; saveConfig(patch); setStartup({ ...startup, ...patch }); }} />{label}</label>)}
        </SectionBoundary></SurfaceDialog>
    <SurfaceDialog open={projectOpen} onClose={()=>setProjectOpen(false)} title="项目设置" description={projects.find(p=>p.id===pid)?.name} wide>{pid&&<SectionBoundary name="项目设置"><Suspense fallback={<p>正在读取项目…</p>}><details><summary>高级授权、成员与操作记录</summary><ProjectGovernance root={root}/></details></Suspense><h3>项目文稿与导出</h3><div className="uw-inline-actions"><button disabled={!pid} onClick={() => void action(async () => { const r = await request<ResearchRecord>(root + '/records', { method: 'POST', body: JSON.stringify({ kind: 'manuscript', payload: { title: '研究文稿', text: '' } }) }); await loadProject(pid); await openArtifact(r.id); })}>新建文稿</button>{['md', 'json', 'tei'].map(format => <button key={format} disabled={!pid} onClick={() => void action(() => download(`${root}/export?format=${format}`, `research.${format === 'tei' ? 'xml' : format}`))}>导出 {format.toUpperCase()}</button>)}</div>
        <h3>历史分析</h3>{oldAnalyses.map(r=><button className="uw-document-item" key={r.id} onClick={()=>void action(async()=>{const a=await request<ResearchRecord>(`${root}/analysis-runs/${r.id}/artifact`,{method:'POST'});await openArtifact(a.id);setProjectOpen(false);})}>历史分析 · {r.state}</button>)}<h3>历史迁移</h3><button onClick={exportBrowserHistory}>导出浏览器旧聊天</button><label>导入聊天备份<input type="file" accept=".json" disabled={!pid} onChange={e => { const f = e.target.files?.[0]; if (f) void action(async () => { await request(root + '/history-import', { method: 'POST', body: await f.text() }); await loadProject(pid); setNotice('历史会话已导入当前项目。'); }); }} /></label>
        <h3>归档会话</h3>{conversations.filter(c => c.archived).map(c => <button className="uw-document-item" key={c.id} onClick={() => void action(async () => { await request(`${root}/conversations/${c.id}`, { method: 'PUT', body: JSON.stringify({ revision: c.revision, archived: false }) }); await loadProject(pid); })}>恢复 {c.title}</button>)}
        <h3>任务详情</h3>{jobs.map(j => <div className="uw-task-detail" key={j.id}>{j.kind} / {j.state}{j.error ? ' · ' + j.error : ''}</div>)}</SectionBoundary>}</SurfaceDialog>
    <CommandPalette key={commandsOpen?'open':'closed'} open={commandsOpen} onClose={()=>setCommandsOpen(false)} commands={commands}/>
  </div>;
}
