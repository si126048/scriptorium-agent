import {test} from 'node:test';
import assert from 'node:assert/strict';
import {SaveQueue} from '../src/features/workspace/save-queue.ts';
import {changedText} from '../src/features/workspace/text-diff.ts';
test('concurrent flush callers await one write and see its failure',async()=>{
 const queue=new SaveQueue();let calls=0;let release!:()=>void;const barrier=new Promise<void>(r=>{release=r;});
 const first=queue.run(async()=>{calls++;await barrier;throw new Error('offline');});const second=queue.run(async()=>{calls++;});
 assert.equal(first,second);release();const results=await Promise.allSettled([first,second]);assert.equal(calls,1);assert.ok(results.every(r=>r.status==='rejected'));
 await queue.run(async()=>{calls++;});assert.equal(calls,2);
});
test('a flush drains changes typed during an in-flight request',async()=>{
 const queue=new SaveQueue();let current='a',saved='';const writes:string[]=[];
 await queue.run(async()=>{while(current!==saved){const snapshot=current;await Promise.resolve();writes.push(snapshot);if(snapshot==='a')current='b';saved=snapshot;}});
 assert.deepEqual(writes,['a','b']);assert.equal(saved,'b');
});
test('revision display preserves both original texts including unicode',()=>{
 const before='论点😀e\u0301：原文',after='论点😀e\u0301：新解释';const d=changedText(before,after);
 assert.equal(d.prefix+d.removed+d.suffix,before);assert.equal(d.prefix+d.added+d.suffix,after);
});

import {cslMetadata} from '../src/features/workspace/bibliography.ts';
test('CSL import keeps article, translated author and issued date as local metadata',()=>{
 const value=cslMetadata({type:'article-journal',title:'A study',author:[{family:'Smith',given:'A'}],translator:[{literal:'译者'}],issued:{'date-parts':[[2024,3]]},'container-title':'Journal',DOI:'10.1/example',page:'1-20'});
 assert.equal(value.author,'A Smith');assert.equal(value.translator,'译者');assert.equal(value.publication_date,'2024-03');assert.equal(value.csl_type,'article-journal');assert.equal(value.journal,'Journal');
});
