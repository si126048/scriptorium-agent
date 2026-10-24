export interface Project { id: string; name: string; description: string }
export interface Version { id: string; quality: Record<string, unknown>; created_at: number }
export interface Material { id: string; name: string; status: string; revision: number; versions: Version[]; metadata: Record<string, unknown> }
export interface Segment { id: string; asset_id: string; version_id: string; xml_id: string; text: string; page_label: string | null }
export interface Anchor { id: string; segment_id: string; start_codepoint: number; end_codepoint: number; exact_quote: string; segment?: Segment }
export interface ResearchRecord { id: string; kind: string; revision: number; payload: Payload; created_at: number }
export interface Payload {
  legacy_run_id?: string; title?: string; text?: string; status?: string; provider_mode?: string; evidence_ids?: string[];
  dimensions?: Record<string, string>; findings?: { title: string; text: string; evidence_ids: string[] }[];
  open_questions?: string[]; alternatives?: string[]; outcome?: string; method_id?: string;
  coverage?: { segment_id: string; status: string }[];
  from_id?: string; to_id?: string; parent_id?: string; difficulty_id?: string;
  difficulty_type?: string; criterion_id?: string; position_id?: string;
  retained?: string; negated?: string; reason?: string; shift?: string; excluded_causes?: string;
  rebuttal_conditions?: string; source_record_ids?: string[]; author_id?: string;
  relation?: string; target_id?: string;
}
export interface Job { id: string; kind: string; state: string; error: string | null; result?: { record_id?: string } }
export interface LegacyRecord { id: string; table_name: string; legacy_key: string; status: string; payload: unknown }

export function serviceUrl() {
  return (localStorage.getItem('scriptorium_research_url') ||
    ('__TAURI_INTERNALS__' in window ? 'http://127.0.0.1:8010' :
      location.protocol.startsWith('http') ? location.origin : 'http://127.0.0.1:8010')).replace(/\/$/, '');
}

export async function response(path: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  const key = localStorage.getItem('scriptorium_research_key');
  if (key) headers.set('Authorization', `Bearer ${key}`);
  if (typeof init.body === 'string') headers.set('Content-Type', 'application/json');
  const r = await fetch(`${serviceUrl()}${path}`, { ...init, headers });
  if (!r.ok) throw new Error(`${r.status}：${await r.text()}`);
  return r;
}

export async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  return (await response(path, init)).json();
}

export function projectPath(projectId: string) { return `/api/v2/projects/${encodeURIComponent(projectId)}`; }

export async function download(path: string, filename: string) {
  const r = await response(path);
  saveBlob(await r.blob(), filename);
}

export function saveBlob(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a'); a.href = url; a.download = filename; a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function exportBrowserHistory() {
  const raw = localStorage.getItem('scriptorium_tasks');
  const content = { format: 'scriptorium-browser-history.v1', tasks: raw ? JSON.parse(raw) : [],
    exported_at: new Date().toISOString(), current_task: localStorage.getItem('scriptorium_current_task'),
    note: '仅包含当前浏览器仍保存的历史；不包含密钥，未删除原记录。' };
  saveBlob(new Blob([JSON.stringify(content, null, 2)], { type: 'application/json' }), 'scriptorium-history.json');
}

export function codepointOffset(text: string, utf16: number) { return Array.from(text.slice(0, utf16)).length; }

export async function persistDesktopConnection(url: string) {
  const internal = (window as unknown as { __TAURI_INTERNALS__?: { invoke: (cmd: string, args: Record<string, unknown>) => Promise<unknown> } }).__TAURI_INTERNALS__;
  if (internal) await internal.invoke('set_research_service', { url });
}
