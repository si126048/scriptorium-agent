import {test} from 'node:test';
import assert from 'node:assert/strict';
import {readingPages,pageForAnchor,expandForAnchor} from '../src/features/workspace/reader.ts';
import {sameDocument,mergeDocumentTab,documentKey} from '../src/features/workspace/document-tabs.ts';
const segment=(id:string,text:string)=>({id,text,asset_id:'material',version_id:'v1',xml_id:id,page_label:'12'});
test('long sources bound page size and retain every original code point',()=>{
 const source=[segment('a','甲😀e\u0301'.repeat(4100)),...Array.from({length:100},(_,i)=>segment('b'+i,'短段落'+i))];
 const pages=readingPages(source);assert.ok(pages.length>3);
 for(const page of pages){assert.ok(page.length<=40);assert.ok(page.reduce((n,p)=>n+Array.from(p.text).length,0)<=6000);}
 for(const s of source)assert.equal(pages.flat().filter(p=>p.segment.id===s.id).map(p=>p.text).join(''),s.text);
});
test('citation on a later page and across a boundary retains canonical offsets',()=>{
 const s=segment('a','甲😀e\u0301'.repeat(4000));const pages=readingPages([s]);
 const anchor={segment_id:'a',start_codepoint:11998,end_codepoint:12012};const index=pageForAnchor(pages,anchor);assert.equal(index,1);
 const part=expandForAnchor(pages[index][0],anchor);assert.equal(part.end,12012);
 assert.equal(Array.from(part.text).slice(anchor.start_codepoint-part.start,anchor.end_codepoint-part.start).join(''),Array.from(s.text).slice(anchor.start_codepoint,anchor.end_codepoint).join(''));
 assert.equal(pageForAnchor(pages,{segment_id:'a',start_codepoint:12000}),2);
});
test('empty sources and missing evidence do not invent a location',()=>{assert.deepEqual(readingPages([]),[]);assert.equal(pageForAnchor(readingPages([segment('a','text')]),{segment_id:'missing',start_codepoint:0}),-1);});
test('latest and fixed versions are distinct, undefined and empty latest are the same',()=>{
 const latest={kind:'material' as const,id:'a',title:'Original',readerPage:3};const fixed={...latest,version:'v1'};
 assert.ok(!sameDocument(latest,fixed));assert.ok(sameDocument(latest,{...latest,version:''}));assert.notEqual(documentKey(latest),documentKey(fixed));
 const merged=mergeDocumentTab([latest],{kind:'material' as const,id:'a',title:'Renamed',version:''});assert.equal(merged.length,1);assert.equal(merged[0].title,'Renamed');assert.equal(merged[0].readerPage,3);
 assert.equal(mergeDocumentTab(merged,fixed).length,2);
});
