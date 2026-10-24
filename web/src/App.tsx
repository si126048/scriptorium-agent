import { lazy, Suspense, useState, useEffect } from 'react';
import { ErrorBoundary } from './components/ui/ErrorBoundary';
import { StartupAnimation } from './components/startup/StartupAnimation';
import {QueryClientProvider} from '@tanstack/react-query';
import {MotionConfig} from 'motion/react';
import {DialogProvider} from './features/workspace/components/Dialogs';
import {queryClient} from './features/workspace/api/query';
import {useWorkspaceUI} from './features/workspace/state';
import {loadConfig} from './components/startup/startupConfig';
const Workspace = lazy(() => import('./features/workspace/UnifiedWorkspace'));

export default function App() {
  const [ready, setReady] = useState(() => sessionStorage.getItem('scriptorium_brand_seen') === '1');
  const quiet=useWorkspaceUI(s=>s.quiet);
  useEffect(()=>{if(ready || loadConfig().requireInteraction)return;const timer=setTimeout(()=>{sessionStorage.setItem('scriptorium_brand_seen','1');setReady(true);},1800);return()=>clearTimeout(timer);},[ready]);
  return <ErrorBoundary><QueryClientProvider client={queryClient}><MotionConfig reducedMotion={quiet?'always':'user'}><DialogProvider>
    <Suspense fallback={<div className="unified-loading">SCRIPTORIUM / 正在准备研究工作台</div>}><Workspace /></Suspense>
    {!ready && <StartupAnimation brandingOnly onComplete={() => { sessionStorage.setItem('scriptorium_brand_seen', '1'); setReady(true); }} />}
  </DialogProvider></MotionConfig></QueryClientProvider></ErrorBoundary>;
}
