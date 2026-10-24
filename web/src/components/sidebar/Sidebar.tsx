import { useEffect, useRef, useCallback } from 'react';
import { useChatStore } from '../../lib/store';
import { TaskPanel } from './TaskPanel';
import { PerspectivePanel } from './PerspectivePanel';
import { DocumentPanel } from './DocumentPanel';
import { SearchPanel } from './SearchPanel';
import { InterviewPanel } from './InterviewPanel';
import { SettingsPanel } from '../settings/SettingsPanel';

const navItems = [
  { key: 'tasks' as const, label: '任务', icon: 'T' },
  { key: 'perspectives' as const, label: '视角', icon: 'P' },
  { key: 'documents' as const, label: '文档', icon: 'D' },
  { key: 'search' as const, label: '检索', icon: 'S' },
  { key: 'interview' as const, label: '访谈', icon: 'I' },
  { key: 'settings' as const, label: '设置', icon: 'C' },
];

export function Sidebar() {
  const { sidebarOpen, sidebarTab, setSidebarTab, setSidebarOpen } = useChatStore();
  const dragRef = useRef(false);
  const startX = useRef(0);

  const close = useCallback(() => setSidebarOpen(false), [setSidebarOpen]);

  useEffect(() => {
    if (!sidebarOpen) return;
    function onEsc(e: KeyboardEvent) { if (e.key === 'Escape') close(); }
    document.addEventListener('keydown', onEsc);
    return () => document.removeEventListener('keydown', onEsc);
  }, [sidebarOpen, close]);

  const onPointerDown = (e: React.PointerEvent) => {
    dragRef.current = true;
    startX.current = e.clientX;
    (e.target as HTMLElement).setPointerCapture(e.pointerId);
  };
  const onPointerMove = (e: React.PointerEvent) => {
    if (!dragRef.current) return;
    const dx = e.clientX - startX.current;
    if (dx > 60) close();
  };
  const onPointerUp = () => { dragRef.current = false; };

  return (
    <>
      {/* 遮罩层 */}
      <div
        className={`fixed inset-0 z-[100] transition-opacity duration-300 ${
          sidebarOpen ? 'opacity-100 pointer-events-auto' : 'opacity-0 pointer-events-none'
        }`}
        style={{ background: 'rgba(0,0,0,0.25)' }}
        onClick={close}
      />

      {/* 抽屉 */}
      <aside
        className={`fixed left-0 top-0 bottom-0 z-[110] flex transition-transform duration-300 ease-[cubic-bezier(0.4,0,0.2,1)] ${
          sidebarOpen ? 'translate-x-0' : '-translate-x-full'
        }`}
        style={{
          background: 'var(--color-surface, #e5e3df)',
          borderRight: '1px solid var(--color-border, rgba(10,10,10,0.16))',
        }}
      >
        {/* 图标导航列 */}
        <div className="w-10 flex flex-col items-center py-3 border-r border-border dark:border-border-dark shrink-0">
          {navItems.map((item) => (
            <button
              key={item.key}
              onClick={() => setSidebarTab(item.key)}
              className={`w-8 h-8 flex items-center justify-center text-xs mb-1 transition-all relative ${
                sidebarTab === item.key
                  ? 'text-ink dark:text-ink-dark font-bold'
                  : 'text-muted/50 hover:text-muted'
              }`}
              style={{ fontFamily: 'var(--font-mono)', fontSize: '11px' }}
              title={item.label}
            >
              {sidebarTab === item.key && (
                <span className="absolute left-0 top-1 bottom-1 w-[2px] bg-accent" />
              )}
              {item.icon}
            </button>
          ))}
        </div>

        {/* 拖拽关闭手柄 */}
        <div
          className="absolute right-0 top-0 bottom-0 w-3 cursor-ew-resize z-10"
          onPointerDown={onPointerDown}
          onPointerMove={onPointerMove}
          onPointerUp={onPointerUp}
        />

        {/* 面板内容区 */}
        <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
          {/* 头部 */}
          <div className="flex items-center justify-between px-3 py-2 border-b border-border dark:border-border-dark shrink-0">
            <div className="flex flex-col">
              <h1 className="text-base font-bold text-ink dark:text-ink-dark tracking-tight" style={{ fontFamily: 'var(--font-din)' }}>
                SCRIPTORIUM
              </h1>
              <span className="text-[9px] text-muted tracking-widest" style={{ fontFamily: 'var(--font-mono)' }}>
                ADVERSARIAL DISCOURSE
              </span>
            </div>
            <button
              onClick={close}
              className="text-muted hover:text-ink dark:hover:text-ink-dark transition-colors text-lg w-6 h-6 flex items-center justify-center"
              aria-label="Close sidebar"
            >
              &times;
            </button>
          </div>

          {/* 面板内容 */}
          <div className="flex-1 overflow-y-auto">
            {sidebarTab === 'tasks' && <TaskPanel />}
            {sidebarTab === 'perspectives' && <PerspectivePanel />}
            {sidebarTab === 'documents' && <DocumentPanel />}
            {sidebarTab === 'search' && <SearchPanel />}
            {sidebarTab === 'interview' && <InterviewPanel />}
            {sidebarTab === 'settings' && <SettingsPanel />}
          </div>
        </div>
      </aside>
    </>
  );
}
