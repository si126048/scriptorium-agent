import type {CSSProperties} from 'react';
const paths:Record<string,string>={
 search:'m21 21-4.5-4.5M19 11a8 8 0 1 1-16 0 8 8 0 0 1 16 0',plus:'M12 5v14M5 12h14',
 chat:'M21 11.5a8.5 8.5 0 0 1-8.5 8.5H4l-2 2V11.5A8.5 8.5 0 0 1 10.5 3h2a8.5 8.5 0 0 1 8.5 8.5Z',
 file:'M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8ZM14 2v6h6M8 13h8M8 17h6',
 book:'M12 6c-3-3-7-3-10-2v15c3-1 7-1 10 2 3-3 7-3 10-2V4c-3-1-7-1-10 2Zm0 0v15',
 close:'m6 6 12 12M6 18 18 6',arrow:'M12 19V5m-6 6 6-6 6 6',back:'M19 12H5m6-6-6 6 6 6',
 chevron:'m9 5 7 7-7 7',down:'m6 9 6 6 6-6',panel:'M8 3v18M3 3h18v18H3Z',expand:'M8 3H3v5m13-5h5v5M3 16v5h5m8 0h5v-5',
 settings:'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM9 3h6l1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1Z',
 attach:'m21 11-8.5 8.5a6 6 0 0 1-8.5-8.5L13 2a4 4 0 0 1 6 6L10 17a2 2 0 0 1-3-3l8-8',
 check:'m5 12 4 4L20 5',stop:'M6 6h12v12H6Z',more:'M5 12h.01M12 12h.01M19 12h.01',
 spark:'m12 3 2.5 6.5L21 12l-6.5 2.5L12 21l-2.5-6.5L3 12l6.5-2.5Z',
 users:'M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2M9 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8M22 21v-2a4 4 0 0 0-3-3.9M16 3a4 4 0 0 1 0 8',
 clock:'M12 8v5l3 2M22 12A10 10 0 1 1 2 12a10 10 0 0 1 20 0',download:'M12 3v12m-5-5 5 5 5-5M5 16v5h14v-5',
 edit:'m16 3 5 5-13 13H3v-5ZM13 6l5 5',copy:'M9 9h12v12H9ZM5 15H3V3h12v2',quote:'M4 5h6v7H7c0 4-1 5-3 7M14 5h6v7h-3c0 4-1 5-3 7',refresh:'M20 7v5h-5M4 17v-5h5M6 7a7 7 0 0 1 12-2l2 7M4 12l2 7a7 7 0 0 0 12-2'};
export function Icon({name,size=18,style}:{name:string;size?:number;style?:CSSProperties}){return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={style}><path d={paths[name]||paths.file}/></svg>}
