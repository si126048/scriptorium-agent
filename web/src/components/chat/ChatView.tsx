import { useEffect, useRef } from 'react';
import { useChatStore } from '../../lib/store';
import { MessageBubble } from './MessageBubble';
import { LogoSVG } from '../startup/LogoSVG';

export function ChatView() {
  const { messages } = useChatStore();
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  return (
    <div
      className="flex-1 overflow-y-auto px-4 py-6 space-y-4"
      style={{
        background: 'linear-gradient(168deg, var(--color-surface-2, #eceae6) 0%, var(--color-surface, #e5e3df) 42%)',
      }}
    >
      {messages.length === 0 && (
        <div className="flex items-center justify-center h-full">
          <div className="text-center max-w-md flex flex-col items-center">
            <div className="opacity-[0.08] mb-4">
              <LogoSVG size={96} />
            </div>
            <h2
              className="text-2xl font-bold text-ink/70 dark:text-ink-dark/60 tracking-widest mb-2"
              style={{ fontFamily: 'var(--font-din)' }}
            >
              SCRIPTORIUM
            </h2>
            <p
              className="text-[11px] text-muted tracking-[0.3em] mb-5"
              style={{ fontFamily: 'var(--font-mono)' }}
            >
              ADVERSARIAL DISCOURSE ANALYSIS
            </p>
            <p className="text-sm text-ink-soft dark:text-ink-soft-dark leading-relaxed" style={{ fontFamily: 'var(--font-zh)' }}>
              输入文本或上传文件，开始话语分析。
              <br />
              支持单视角分析、辩证分析和结构化访谈。
            </p>
            <div className="mt-6 w-24 h-px bg-border dark:bg-border-dark" />
            <p
              className="mt-3 text-[10px] text-muted/60 tracking-widest"
              style={{ fontFamily: 'var(--font-mono)' }}
            >
              AWAITING INPUT
            </p>
          </div>
        </div>
      )}
      {messages.map((msg) => (
        <MessageBubble key={msg.id} message={msg} />
      ))}
      <div ref={bottomRef} />
    </div>
  );
}
