import {test} from 'node:test';
import assert from 'node:assert/strict';
import {mergeBlock,markdownBlocks,type TimelineBlock} from '../src/features/workspace/timeline.ts';
const block=(value:Partial<TimelineBlock>={}):TimelineBlock=>({id:'answer',job_id:'job',project_id:'project',conversation_id:'chat',block_key:'answer',kind:'answer',state:'streaming',generation:1,revision:1,payload:{text:''},created_at:0,updated_at:0,...value});
test('unicode deltas use code points and duplicate events never append twice',()=>{
 let state=mergeBlock([],{block:block()});const first={block:block({revision:2,payload:{offset:4}}),delta:{offset:0,text:'甲😀e\u0301'}};state=mergeBlock(state,first);state=mergeBlock(state,first);assert.equal(state[0].payload.text,'甲😀e\u0301');state=mergeBlock(state,{block:block({revision:3}),delta:{offset:4,text:'乙'}});assert.equal(state[0].payload.text,'甲😀e\u0301乙');
});
test('snapshot resumes the same block and offset gaps require a fresh snapshot',()=>{
 const state=[block({payload:{text:'已保存'}})];assert.throws(()=>mergeBlock(state,{block:block({revision:2}),delta:{offset:99,text:'重复'}}),/GAP/);const final=mergeBlock(state,{block:block({revision:3,state:'completed',payload:{text:'已保存的回答'}})});assert.equal(final.length,1);assert.equal(final[0].state,'completed');
});
test('older execution cannot add a late block after recovery',()=>{
 const state=[block({id:'turn',kind:'turn',generation:2})];assert.equal(mergeBlock(state,{block:block({id:'late',generation:1})}),state);
});

test('completed markdown paragraphs stay stable while fenced content keeps blank lines',()=>{
 const before=markdownBlocks('段落一\n\n段落二');const after=markdownBlocks('段落一\n\n段落二继续');assert.equal(before[0],after[0]);assert.equal(markdownBlocks('```text\n代码\n\n更多代码\n```\n\n结尾').length,2);
});
