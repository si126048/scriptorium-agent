import type {Components} from 'react-markdown';
export const markdownComponents:Components={
        p: ({ children }) => <p className="mb-2 last:mb-0">{children}</p>,
        code: ({ className, children }) => {
          const isInline = !className;
          return isInline ? (
            <code className="px-1 py-0.5 rounded bg-black/5 dark:bg-white/10 text-xs font-mono">
              {children}
            </code>
          ) : (
            <code className={`${className} block p-3 rounded-lg bg-black/5 dark:bg-white/10 text-xs font-mono overflow-x-auto`}>
              {children}
            </code>
          );
        },
        strong: ({ children }) => (
          <strong className="font-semibold text-gray-900 dark:text-gray-100">
            {children}
          </strong>
        ),
        ul: ({ children }) => (
          <ul className="list-disc list-inside mb-2 space-y-0.5">{children}</ul>
        ),
        ol: ({ children }) => (
          <ol className="list-decimal list-inside mb-2 space-y-0.5">{children}</ol>
        ),
        h1: ({ children }) => <h1 className="text-lg font-bold mb-2">{children}</h1>,
        h2: ({ children }) => <h2 className="text-base font-bold mb-1.5">{children}</h2>,
        h3: ({ children }) => <h3 className="text-sm font-semibold mb-1">{children}</h3>,
      };
