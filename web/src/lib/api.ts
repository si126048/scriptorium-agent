const API_BASE = import.meta.env.VITE_API_BASE || '';

function getApiKey(): string | null {
  return localStorage.getItem('scriptorium_api_key');
}

function headers(extra: Record<string, string> = {}): Record<string, string> {
  const h: Record<string, string> = { 'Content-Type': 'application/json', ...extra };
  const key = getApiKey();
  if (key) h['Authorization'] = `Bearer ${key}`;
  return h;
}

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: headers(init?.headers as Record<string, string>),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`API ${res.status}: ${detail}`);
  }
  return res.json();
}

export async function apiUpload(path: string, file: File, extra: Record<string, string> = {}): Promise<unknown> {
  const form = new FormData();
  form.append('file', file);
  for (const [k, v] of Object.entries(extra)) form.append(k, v);
  const h: Record<string, string> = {};
  const key = getApiKey();
  if (key) h['Authorization'] = `Bearer ${key}`;
  const res = await fetch(`${API_BASE}${path}`, { method: 'POST', headers: h, body: form });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`Upload ${res.status}: ${detail}`);
  }
  return res.json();
}

export async function apiStream(path: string, body: unknown, onEvent: (event: string, data: unknown) => void): Promise<void> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`Stream ${res.status}: ${detail}`);
  }
  const reader = res.body?.getReader();
  if (!reader) throw new Error('No response body');
  const decoder = new TextDecoder();
  let buffer = '';
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split('\n');
    buffer = lines.pop() || '';
    let currentEvent = 'message';
    for (const line of lines) {
      if (line.startsWith('event:')) {
        currentEvent = line.slice(6).trim();
      } else if (line.startsWith('data:')) {
        try {
          onEvent(currentEvent, JSON.parse(line.slice(5).trim()));
        } catch {
          onEvent(currentEvent, line.slice(5).trim());
        }
        currentEvent = 'message';
      }
    }
  }
}

export const health = () => apiFetch<{ status: string }>('/health');
export const perspectives = async () => {
  const res = await apiFetch<{ perspectives: unknown[] }>('/api/v1/perspectives');
  return res.perspectives;
};
export const theorySearch = async (q: string, projectId = 'default', limit = 10) => {
  const res = await apiFetch<{ items: unknown[] }>(
    `/api/v1/theory/search?project_id=${encodeURIComponent(projectId)}&q=${encodeURIComponent(q)}&limit=${limit}`
  );
  return res.items;
};

export interface ProjectData {
  id: string;
  name: string;
  description: string;
  policy_version: string;
  owner_id: string;
  created_at: string;
}

export interface ParticipantData {
  id: string;
  project_id: string;
  pseudonym: string;
  consent_scope: { withdrawn_at?: string; expires_at?: string };
  withdrawn_at: string | null;
  created_at: string;
}

export const ensureProject = (id: string, name?: string) =>
  apiFetch('/api/v1/projects', { method: 'POST', body: JSON.stringify({ id, name: name || id }) }).catch(() => {});
export const ensureParticipant = (id: string, projectId: string) =>
  apiFetch('/api/v1/participants', { method: 'POST', body: JSON.stringify({ id, project_id: projectId }) }).catch(() => {});

export const listProjects = () =>
  apiFetch<{ projects: ProjectData[] }>('/api/v1/projects');
export const createProject = (body: { id: string; name?: string; description?: string }) =>
  apiFetch<ProjectData>('/api/v1/projects', { method: 'POST', body: JSON.stringify(body) });
export const deleteProject = (id: string) =>
  apiFetch<void>(`/api/v1/projects/${encodeURIComponent(id)}`, { method: 'DELETE' });
export const listParticipants = (projectId: string) =>
  apiFetch<{ participants: ParticipantData[] }>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/participants`
  );
export const deleteParticipant = (projectId: string, participantId: string) =>
  apiFetch<void>(
    `/api/v1/projects/${encodeURIComponent(projectId)}/participants/${encodeURIComponent(participantId)}`,
    { method: 'DELETE' }
  );

export type Persona = { id: string; project_id: string; participant_id: string; name: string; status: string; model: string; mode: string; alpha: number };
export const listPersonas = (projectId: string, participantId?: string) => apiFetch<{ personas: Persona[] }>(`/api/v1/personas?project_id=${encodeURIComponent(projectId)}${participantId ? `&participant_id=${encodeURIComponent(participantId)}` : ''}`);
export const createPersona = (body: { project_id: string; participant_id: string; name: string; model?: string; mode?: string; alpha?: number }) => apiFetch<Persona>('/api/v1/personas', { method: 'POST', body: JSON.stringify(body) });
export const trainPersona = (id: string) => apiFetch<unknown>(`/api/v1/personas/${id}/train`, { method: 'POST' });
export const chatPersona = (id: string, body: { prompt: string; conversation_id?: string }, onEvent: (event: string, data: unknown) => void) => apiStream(`/api/v1/personas/${id}/chat`, body, onEvent);
