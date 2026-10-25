export function cslMetadata(value:Record<string,unknown>):Record<string,string>{
 const result:Record<string,string>={};
 const fields:Record<string,string>={title:'title',publisher:'publisher','container-title':'journal',volume:'volume',issue:'issue',page:'pages',DOI:'doi',ISBN:'isbn',language:'language'};
 for(const [from,to]of Object.entries(fields))if(typeof value[from]==='string')result[to]=String(value[from]);
 for(const field of ['author','translator'])if(Array.isArray(value[field]))result[field]=(value[field] as Record<string,unknown>[]).map(p=>typeof p.literal==='string'?p.literal:[p.given,p.family].filter(x=>typeof x==='string').join(' ')).join('; ');
 const issued=value.issued as{'date-parts'?:number[][]}|undefined;const date=issued?.['date-parts']?.[0];if(date?.length)result.publication_date=date.map((v,i)=>i?String(v).padStart(2,'0'):String(v)).join('-');
 result.csl_type=value.type==='article-journal'?'article-journal':'book';return result;
}
