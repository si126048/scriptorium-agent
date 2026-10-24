import {lazy,Suspense} from 'react';
import ReactMarkdown from 'react-markdown';
import {markdownComponents} from './markdown-components';
import remarkGfm from 'remark-gfm';
const MathMarkdown=lazy(()=>import('./MathMarkdown'));

export function MarkdownRenderer({content}:{content:string}){const plain=<ReactMarkdown remarkPlugins={[remarkGfm]} components={markdownComponents}>{content}</ReactMarkdown>;return <div className="markdown-body">{content.includes('$')||content.includes('\\[')||content.includes('\\(')?<Suspense fallback={plain}><MathMarkdown content={content}/></Suspense>:plain}</div>;}
