import { useState, useEffect } from 'react';
import { loadConfig, saveConfig } from '../startup/startupConfig';
import type { StartupConfig } from '../startup/startupConfig';

interface TauriWindow {
  __TAURI__: {
    invoke: (cmd: string, args?: Record<string, unknown>) => Promise<unknown>;
  };
}

function tauriInvoke(cmd: string, args?: Record<string, unknown>): Promise<unknown> | null {
  if (!('__TAURI__' in window)) return null;
  return (window as unknown as TauriWindow).__TAURI__.invoke(cmd, args);
}

export function SettingsPanel() {
  const [apiKey, setApiKey] = useState(() => localStorage.getItem('scriptorium_dashscope_key') || '');
  const [dataDir, setDataDir] = useState(() => ('__TAURI__' in window ? '' : 'Browser mode (data stored in backend)'));
  const [showKey, setShowKey] = useState(false);
  const [saved, setSaved] = useState(false);
  const [startupCfg, setStartupCfg] = useState<StartupConfig>(loadConfig());

  const isTauri = '__TAURI__' in window;
  const mono = { fontFamily: 'var(--font-mono)' };
  const inputCls = 'w-full bg-transparent border-0 border-b border-border dark:border-border-dark px-0 py-1.5 text-sm text-ink dark:text-ink-dark placeholder-muted outline-none focus:border-accent transition-colors';

  useEffect(() => {
    if (isTauri) {
      tauriInvoke('get_data_dir')?.then((d) => setDataDir(String(d))).catch(console.error);
    }
  }, [isTauri]);

  const handleSave = async () => {
    localStorage.setItem('scriptorium_dashscope_key', apiKey);
    if (isTauri) {
      await tauriInvoke('set_api_key', { key: apiKey });
    }
    try {
      const base = import.meta.env.VITE_API_BASE || '';
      await fetch(`${base}/api/v1/config/api-key`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ key: apiKey }),
      });
    } catch { /* backend may not be reachable yet */ }
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  const updateStartup = (patch: Partial<StartupConfig>) => {
    const next = { ...startupCfg, ...patch };
    setStartupCfg(next);
    saveConfig(patch);
  };

  return (
    <div className="p-4 space-y-5">
      <h2 className="text-sm font-semibold text-ink dark:text-ink-dark tracking-tight" style={{ fontFamily: 'var(--font-din)' }}>
        SETTINGS
      </h2>

      <div className="space-y-3">
        <div className="text-[10px] text-muted tracking-wider" style={mono}>API</div>
        <div className="space-y-2">
          <label className="text-[10px] text-muted tracking-wider block" style={mono}>DASHSCOPE KEY</label>
          <div className="flex gap-2">
            <input
              type={showKey ? 'text' : 'password'}
              value={apiKey}
              onChange={(e) => setApiKey(e.target.value)}
              placeholder="sk-..."
              className={inputCls + ' flex-1'}
            />
            <button
              onClick={() => setShowKey(!showKey)}
              className="text-[10px] text-muted hover:text-accent transition-colors shrink-0"
              style={mono}
            >
              {showKey ? 'HIDE' : 'SHOW'}
            </button>
          </div>
        </div>
      </div>

      <div className="space-y-2">
        <label className="text-[10px] text-muted tracking-wider block" style={mono}>DATA DIR</label>
        <div className="text-xs text-ink-soft dark:text-ink-soft-dark border-b border-border dark:border-border-dark pb-1.5" style={mono}>
          {dataDir || 'Loading...'}
        </div>
      </div>

      <button
        onClick={handleSave}
        disabled={!apiKey.trim()}
        className="w-full px-4 py-1.5 text-xs border border-ink dark:border-ink-dark bg-transparent text-ink dark:text-ink-dark hover:bg-ink hover:text-ink-dark disabled:opacity-30 transition-colors"
        style={mono}
      >
        {saved ? 'SAVED' : 'SAVE'}
      </button>

      <div className="border-t border-border dark:border-border-dark pt-4 space-y-3">
        <div className="text-[10px] text-muted tracking-wider" style={mono}>STARTUP</div>

        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={startupCfg.enabled}
            onChange={(e) => updateStartup({ enabled: e.target.checked })}
            className="accent-accent"
          />
          <span className="text-xs text-ink dark:text-ink-dark" style={{ fontFamily: 'var(--font-zh)' }}>启用启动动画</span>
        </label>

        <div className="space-y-1">
          <label className="text-[10px] text-muted tracking-wider block" style={mono}>MODE</label>
          <select
            value={startupCfg.mode}
            onChange={(e) => updateStartup({ mode: e.target.value as StartupConfig['mode'] })}
            className="w-full bg-transparent border-0 border-b border-border dark:border-border-dark px-0 py-1.5 text-xs text-ink dark:text-ink-dark outline-none"
            style={mono}
          >
            <option value="session">每个会话一次</option>
            <option value="daily">每天一次</option>
            <option value="always">每次都播放</option>
          </select>
        </div>

        <div className="space-y-1">
          <label className="text-[10px] text-muted tracking-wider block" style={mono}>IDENTITY</label>
          <input
            className={inputCls}
            value={startupCfg.identity}
            onChange={(e) => updateStartup({ identity: e.target.value })}
            placeholder="OPERATOR"
            style={mono}
          />
        </div>

        <div className="space-y-1">
          <label className="text-[10px] text-muted tracking-wider block" style={mono}>SPEED ({startupCfg.speed.toFixed(2)}x)</label>
          <input
            type="range"
            min="0.35"
            max="3"
            step="0.05"
            value={startupCfg.speed}
            onChange={(e) => updateStartup({ speed: parseFloat(e.target.value) })}
            className="w-full accent-accent"
          />
        </div>

        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={startupCfg.voice}
            onChange={(e) => updateStartup({ voice: e.target.checked })}
            className="accent-accent"
          />
          <span className="text-xs text-ink dark:text-ink-dark" style={{ fontFamily: 'var(--font-zh)' }}>语音播报</span>
        </label>

        <label className="flex items-center gap-2 cursor-pointer">
          <input
            type="checkbox"
            checked={startupCfg.sound}
            onChange={(e) => updateStartup({ sound: e.target.checked })}
            className="accent-accent"
          />
          <span className="text-xs text-ink dark:text-ink-dark" style={{ fontFamily: 'var(--font-zh)' }}>界面音效</span>
        </label>
      </div>

      <div className="border-t border-border dark:border-border-dark pt-3">
        <p className="text-[10px] text-muted/60" style={mono}>
          {isTauri
            ? 'DESKTOP MODE · LOCAL STORAGE'
            : 'BROWSER MODE · BACKEND STORAGE'}
        </p>
      </div>
    </div>
  );
}
