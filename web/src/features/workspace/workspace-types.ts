import type {Tool} from './components/ResearchComposer';
import type {DocumentTab} from './state';
import type {Anchor} from './api/client';
import type {WritingTarget} from './api/writing-target';
export interface Conversation { id: string; title: string; archived: boolean; revision: number; workspace: { writing_target?:WritingTarget; tool?:Tool; method?:string; provider_mode?:'live'|'demo'; source_page?:number; tabs?:DocumentTab[]; layout?:'chat'|'split'|'focus'; selection?:Omit<Anchor,'id'>; draft?: string; asset_ids?: string[]; open_artifact?: string; open_material?: string; scroll?: number; document_scroll?: number; panel?: string; version_id?: string; edit_text?: string; edit_title?: string } }
export interface Message { id: string; role: string; content: string; artifact_ids: string[]; metadata: { provider_mode?: string; interview_id?: string; job_id?: string; decision_id?: string } }
export interface Participant { id: string; pseudonym: string; permissions: Record<string, boolean>; withdrawn_at: string | null }
export interface Persona { id: string; name: string; participant_id: string; status: string }
export interface Interview { id: string; participant_id: string; state: string; current_question?: { id: string; text: string } | null; conversation_id?: string }
