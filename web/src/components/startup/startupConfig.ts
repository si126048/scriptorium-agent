export interface StartupStep {
  zh: string;
  en: string;
  say: string;
  log: string;
  logEn: string;
  badge: string;
  action: 'grant' | 'confirm' | 'auto';
  btnZh?: string;
  btnEn?: string;
  hold: number;
  progress: number;
  assembleLogo?: boolean;
  hex?: boolean;
  reticle?: boolean;
}

export interface StartupConfig {
  enabled: boolean;
  mode: 'always' | 'session' | 'daily';
  theme: 'light' | 'dark';
  speed: number;
  requireInteraction: boolean;
  allowSkip: boolean;
  sound: boolean;
  soundVolume: number;
  voice: boolean;
  voiceLang: 'en' | 'zh' | 'both';
  voiceRate: number;
  voicePitch: number;
  voiceVolume: number;
  voiceCue: boolean;
  voiceLead: number;
  identity: string;
  identityId: string;
  accessLevel: string;
  brand1: string;
  brand2: string;
  brand3a: string;
  brand3b: string;
  orgZh: string;
  orgEn: string;
  orgSub: string;
  welcomeBox: string;
  footer: string;
  accent: string;
  glitchA: string;
  glitchB: string;
}

export const DEFAULT_CONFIG: StartupConfig = {
  enabled: true,
  mode: 'session',
  theme: 'light',
  speed: 1,
  requireInteraction: false,
  allowSkip: true,
  sound: true,
  soundVolume: 0.5,
  voice: false,
  voiceLang: 'en',
  voiceRate: 0.88,
  voicePitch: 0.85,
  voiceVolume: 0.9,
  voiceCue: true,
  voiceLead: 240,
  identity: 'OPERATOR',
  identityId: '0001',
  accessLevel: '3',
  brand1: 'HERMENEUT',
  brand2: 'ADVERSARIAL DISCOURSE ANALYSIS',
  brand3a: 'AGENT',
  brand3b: 'v3',
  orgZh: '诠释者',
  orgEn: 'HERMENEUT',
  orgSub: 'HERMENEUT-AGENT',
  welcomeBox: 'HERMENEUT-AGENT',
  footer: 'POWERED BY HERMENEUT',
  accent: '#ff7500',
  glitchA: '#ff3b30',
  glitchB: '#2971b8',
};

export const STEPS: StartupStep[] = [
  {
    zh: '需要阐释许可',
    en: 'INTERPRETATION ACCESS REQUIRED',
    say: 'Interpretation access required.',
    log: '等待用户授权…',
    logEn: 'AWAITING OPERATOR CONSENT',
    badge: 'AUTHORIZATION',
    action: 'grant',
    btnZh: '授予阐释权限',
    btnEn: 'GRANT ACCESS',
    hold: 900,
    progress: 0.34,
  },
  {
    zh: '身份资料确认',
    en: 'IDENTITY VERIFICATION',
    say: 'Identity verification.',
    log: '核对身份资料…',
    logEn: 'MATCHING OPERATOR RECORD',
    badge: 'IDENTITY',
    action: 'confirm',
    btnZh: '确认身份',
    btnEn: 'CONFIRM IDENTITY',
    hold: 700,
    progress: 0.5,
  },
  {
    zh: '接收分析请求',
    en: 'ANALYSIS REQUEST RECEIVED',
    say: 'Analysis request received.',
    log: '接收分析请求，建立会话通道…',
    logEn: 'HANDSHAKE ESTABLISHED',
    badge: 'REQUEST',
    action: 'auto',
    hold: 1200,
    progress: 0.66,
    assembleLogo: true,
  },
  {
    zh: '开始读取权限',
    en: 'PERMISSION READ STARTED',
    say: 'Beginning permission read.',
    log: '开始读取权限，索引工作区与会话…',
    logEn: 'READING PERMISSION SET',
    badge: 'READ',
    action: 'auto',
    hold: 1200,
    progress: 0.8,
    hex: true,
  },
  {
    zh: '读取完毕 · 核验通过',
    en: 'READ COMPLETE · VERIFIED',
    say: 'Read complete. Verification passed.',
    log: '读取完毕，核验通过，权限已授予',
    logEn: 'PERMISSION AUTHORIZED',
    badge: 'VERIFY',
    action: 'auto',
    hold: 1600,
    progress: 0.93,
    reticle: true,
  },
];

export function loadConfig(): StartupConfig {
  try {
    const raw = localStorage.getItem('hermeneut_startup_config');
    if (raw) {
      const parsed = JSON.parse(raw) as Partial<StartupConfig>;
      return { ...DEFAULT_CONFIG, ...parsed };
    }
  } catch { /* noop */ }
  return { ...DEFAULT_CONFIG };
}

export function saveConfig(cfg: Partial<StartupConfig>): void {
  const current = loadConfig();
  localStorage.setItem('hermeneut_startup_config', JSON.stringify({ ...current, ...cfg }));
}

export function shouldPlay(mode: StartupConfig['mode']): boolean {
  if (mode === 'always') return true;
  if (mode === 'session') {
    if (sessionStorage.getItem('ha-startup:shown')) return false;
    sessionStorage.setItem('ha-startup:shown', '1');
    return true;
  }
  if (mode === 'daily') {
    const today = new Date().toISOString().slice(0, 10);
    if (localStorage.getItem('ha-startup:day') === today) return false;
    localStorage.setItem('ha-startup:day', today);
    return true;
  }
  return true;
}
