import {useMemo} from 'react';
import {changedText} from '../text-diff';
export function RevisionDiff({before,after}:{before:string;after:string}){
 const diff=useMemo(()=>changedText(before,after),[before,after]);
 return <div className="wb-text-diff" aria-label="修订增删差异"><p className="uw-muted">删除显示为删除线，新增显示为下划线；正文原有引用仍关联原文。</p><div>{diff.prefix}{diff.removed&&<del>{diff.removed}</del>}{diff.added&&<ins>{diff.added}</ins>}{diff.suffix}{!diff.removed&&!diff.added&&<small>正文没有差异。</small>}</div></div>;
}
