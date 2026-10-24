import { create } from 'zustand';

export type Register = 'S' | 'I' | 'R';
export type CardVariant = 'observation' | 'hypothesis' | 'counterexample' | 'synthesis' | 'report';
export type MessageRole = 'user' | 'assistant' | 'system' | 'tool';

export interface AnalysisCard {
  variant: CardVariant;
  tag: string;
  content: string;
  register?: Register;
  meta?: Record<string, string>;
}

export interface ChatMessage {
  id: string;
  role: MessageRole;
  content: string;
  cards?: AnalysisCard[];
  phase?: number;
  streaming?: boolean;
  attachments?: string[];
  timestamp: number;
}

export interface Task {
  id: string;
  name: string;
  messages: ChatMessage[];
  mode: 'analysis' | 'dialectical' | 'interview' | 'chat';
  createdAt: number;
}

interface ChatState {
  tasks: Task[];
  currentTaskId: string | null;
  messages: ChatMessage[];
  isStreaming: boolean;
  currentPhase: number;
  sidebarTab: 'tasks' | 'perspectives' | 'documents' | 'search' | 'interview' | 'settings';
  sidebarOpen: boolean;
  topBarOpen: boolean;
  interviewSessionId: string | null;
  interviewQuestionId: string | null;
  mode: 'analysis' | 'dialectical' | 'interview' | 'chat';
  startupCompleted: boolean;
  addMessage: (msg: Omit<ChatMessage, 'id' | 'timestamp'>) => string;
  updateMessage: (id: string, patch: Partial<ChatMessage>) => void;
  appendToMessage: (id: string, text: string) => void;
  addCardToMessage: (id: string, card: AnalysisCard) => void;
  setStreaming: (v: boolean) => void;
  setPhase: (n: number) => void;
  setSidebarTab: (tab: ChatState['sidebarTab']) => void;
  setSidebarOpen: (v: boolean) => void;
  setTopBarOpen: (v: boolean) => void;
  setInterviewSessionId: (id: string | null) => void;
  setInterviewQuestionId: (id: string | null) => void;
  setMode: (m: ChatState['mode']) => void;
  setStartupCompleted: (v: boolean) => void;
  createTask: () => string;
  switchTask: (id: string) => void;
  deleteTask: (id: string) => void;
  renameTask: (id: string, name: string) => void;
  loadMessages: () => void;
  saveMessages: () => void;
  clearMessages: () => void;
}

const STORAGE_KEY = 'scriptorium_tasks';
const TASK_KEY = 'scriptorium_current_task';
const MAX_STORED = 100;

function taskNameFromMessages(messages: ChatMessage[]): string {
  const first = messages.find((m) => m.role === 'user');
  if (first) {
    const text = first.content.trim().replace(/\n/g, ' ');
    return text.length > 20 ? text.slice(0, 20) + '...' : text || '未命名任务';
  }
  return '未命名任务';
}

function newTask(): Task {
  return {
    id: crypto.randomUUID(),
    name: '未命名任务',
    messages: [],
    mode: 'chat',
    createdAt: Date.now(),
  };
}

export const useChatStore = create<ChatState>((set, get) => ({
  tasks: [],
  currentTaskId: null,
  messages: [],
  isStreaming: false,
  currentPhase: 0,
  sidebarTab: 'tasks',
  sidebarOpen: true,
  topBarOpen: false,
  interviewSessionId: null,
  interviewQuestionId: null,
  mode: 'chat',
  startupCompleted: false,

  addMessage: (msg) => {
    const id = crypto.randomUUID();
    const newMsg = { ...msg, id, timestamp: Date.now() };
    set((s) => {
      if (!s.currentTaskId) return { messages: s.messages };
      const tasks = s.tasks.map((t) =>
        t.id === s.currentTaskId
          ? { ...t, messages: [...t.messages, newMsg], name: t.messages.length === 0 ? taskNameFromMessages([newMsg]) : t.name }
          : t
      );
      return { tasks, messages: [...s.messages, newMsg] };
    });
    get().saveMessages();
    return id;
  },

  updateMessage: (id, patch) => {
    set((s) => ({
      messages: s.messages.map((m) => (m.id === id ? { ...m, ...patch } : m)),
    }));
    const s = get();
    if (s.currentTaskId) {
      const tasks = s.tasks.map((t) =>
        t.id === s.currentTaskId
          ? { ...t, messages: t.messages.map((m) => (m.id === id ? { ...m, ...patch } : m)) }
          : t
      );
      set({ tasks });
    }
    get().saveMessages();
  },

  appendToMessage: (id, text) => {
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === id ? { ...m, content: m.content + text } : m
      ),
    }));
    const s = get();
    if (s.currentTaskId) {
      const tasks = s.tasks.map((t) =>
        t.id === s.currentTaskId
          ? { ...t, messages: t.messages.map((m) => (m.id === id ? { ...m, content: m.content + text } : m)) }
          : t
      );
      set({ tasks });
    }
    get().saveMessages();
  },

  addCardToMessage: (id, card) => {
    set((s) => ({
      messages: s.messages.map((m) =>
        m.id === id ? { ...m, cards: [...(m.cards || []), card] } : m
      ),
    }));
    const s = get();
    if (s.currentTaskId) {
      const tasks = s.tasks.map((t) =>
        t.id === s.currentTaskId
          ? { ...t, messages: t.messages.map((m) => (m.id === id ? { ...m, cards: [...(m.cards || []), card] } : m)) }
          : t
      );
      set({ tasks });
    }
    get().saveMessages();
  },

  setStreaming: (v) => set({ isStreaming: v }),
  setPhase: (n) => set({ currentPhase: n }),
  setSidebarTab: (tab) => set({ sidebarTab: tab }),
  setSidebarOpen: (v) => set({ sidebarOpen: v }),
  setTopBarOpen: (v) => set({ topBarOpen: v }),
  setInterviewSessionId: (id) => set({ interviewSessionId: id }),
  setInterviewQuestionId: (id) => set({ interviewQuestionId: id }),
  setMode: (m) => {
    set({ mode: m });
    const s = get();
    if (s.currentTaskId) {
      const tasks = s.tasks.map((t) =>
        t.id === s.currentTaskId ? { ...t, mode: m } : t
      );
      set({ tasks });
      get().saveMessages();
    }
  },
  setStartupCompleted: (v) => set({ startupCompleted: v }),

  createTask: () => {
    const task = newTask();
    set((s) => ({
      tasks: [task, ...s.tasks],
      currentTaskId: task.id,
      messages: [],
      mode: 'chat',
      interviewSessionId: null,
      interviewQuestionId: null,
    }));
    get().saveMessages();
    return task.id;
  },

  switchTask: (id) => {
    const s = get();
    const task = s.tasks.find((t) => t.id === id);
    if (!task) return;
    set({
      currentTaskId: id,
      messages: task.messages,
      mode: task.mode,
      interviewSessionId: null,
      interviewQuestionId: null,
    });
    localStorage.setItem(TASK_KEY, id);
  },

  deleteTask: (id) => {
    set((s) => {
      const tasks = s.tasks.filter((t) => t.id !== id);
      let next = s.currentTaskId;
      if (s.currentTaskId === id) {
        next = tasks.length > 0 ? tasks[0].id : null;
      }
      const nextTask = next ? tasks.find((t) => t.id === next) : null;
      return {
        tasks,
        currentTaskId: next,
        messages: nextTask?.messages || [],
        mode: nextTask?.mode || 'chat',
        interviewSessionId: null,
        interviewQuestionId: null,
      };
    });
    const s = get();
    if (s.currentTaskId) {
      localStorage.setItem(TASK_KEY, s.currentTaskId);
    } else {
      localStorage.removeItem(TASK_KEY);
    }
    get().saveMessages();
  },

  renameTask: (id, name) => {
    set((s) => ({
      tasks: s.tasks.map((t) => (t.id === id ? { ...t, name } : t)),
    }));
    get().saveMessages();
  },

  clearMessages: () => {
    const s = get();
    if (s.currentTaskId) {
      const tasks = s.tasks.map((t) =>
        t.id === s.currentTaskId ? { ...t, messages: [], name: '未命名任务' } : t
      );
      set({ tasks, messages: [] });
      get().saveMessages();
    }
  },

  loadMessages: () => {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      let tasks: Task[] = [];
      if (raw) {
        tasks = JSON.parse(raw);
      }
      if (tasks.length === 0) {
        const t = newTask();
        tasks = [t];
      }
      const savedTaskId = localStorage.getItem(TASK_KEY);
      let currentId = savedTaskId && tasks.find((t) => t.id === savedTaskId) ? savedTaskId : tasks[0].id;
      const currentTask = tasks.find((t) => t.id === currentId) || tasks[0];
      set({
        tasks,
        currentTaskId: currentTask.id,
        messages: currentTask.messages,
        mode: currentTask.mode,
      });
    } catch (e) { console.warn('Failed to load tasks:', e); }
  },

  saveMessages: () => {
    const s = get();
    const stripped = s.tasks.map((t) => ({
      ...t,
      messages: t.messages.slice(-MAX_STORED).map(({ streaming, ...rest }) => rest),
    }));
    localStorage.setItem(STORAGE_KEY, JSON.stringify(stripped));
  },
}));
