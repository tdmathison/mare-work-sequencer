import { BUFFERS, modifierValues, parse } from './snort-model';

export function componentRange(c) {
  return {from:Math.min(...c.spans.map(s=>s.from)),to:Math.max(...c.spans.map(s=>s.to))};
}
export function captureTarget(model,c,side) {
  const range=componentRange(c);
  return {...range,text:model.source.slice(range.from,range.to),kind:c.kind,side};
}
export function resolveTarget(model,target) {
  if(!target) throw Error('Choose an insertion location below.');
  if(model.diagnostics.length) throw Error('Complete the source syntax before insertion: '+model.diagnostics.join(' '));
  const c=model.components.find(c=>{const r=componentRange(c);return r.from===target.from&&r.to===target.to&&c.kind===target.kind;});
  if(!c||!c.safe||model.source.slice(target.from,target.to)!==target.text)
    throw Error('Insertion target changed or was removed. Choose a new location below.');
  return c;
}
export function planInsertion(model,target,syntax,buffer=null) {
  const c=resolveTarget(model,target),rule=model.rules[c.rule];
  if(rule.components.some(c=>!c.safe))throw Error('Resolve unsafe match values or source-only associations in this rule before inserting.');
  if(!rule.complete||rule.dialect==='ambiguous') throw Error('Choose Legacy or Snort 3 interpretation before insertion.');
  if(!['before','after','end'].includes(target.side))throw Error('Choose before, after, or end of rule.');
  if(c.kind!=='content'&&target.side!=='end')throw Error('Choose a match group or the end of the option block.');
  const point=target.side==='end'?rule.close:target.side==='before'?target.from:target.to;
  const later=rule.components.filter(x=>x.kind==='content'&&x.content.from>=point);
  // New content changes the detection cursor even when the sticky buffer is restored.
  const dependent=later.some(x=>['distance','within'].some(k=>modifierValues(x)[k]!==undefined));
  const knownIndependent=['msg','sid','gid','rev','classtype','priority','metadata','reference','flow','content',...BUFFERS,'nocase','fast_pattern','offset','depth','distance','within'];
  const advanced=rule.options.some(o=>o.from>=point&&!knownIndependent.includes(o.key));
  if(dependent||advanced)throw Error('Later relative matches or advanced cursor options may depend on this position. Choose End of option block, or resolve those dependencies in source.');
  let insert=syntax,effect='Existing match buffers are unchanged.';
  if(buffer!==null){
    if(buffer!=='payload'&&!BUFFERS.includes(buffer))throw Error('Choose a supported inspection buffer.');
    if(rule.dialect==='legacy'){
      if(buffer!=='payload'&&!buffer.startsWith('http_'))throw Error('This legacy workflow supports payload or trailing HTTP modifiers. Choose another buffer or explicitly convert the rule first.');
      if(buffer!=='payload')insert+=' '+buffer+';';
      effect='Legacy buffer modifier applies only to the new content match.';
    }else{
      const previous=rule.options.filter(o=>o.from<point&&BUFFERS.includes(o.key)).at(-1)?.key||'pkt_data';
      const desired=buffer==='payload'?'pkt_data':buffer;
      if(desired!==previous){
        const rest=rule.options.some(o=>o.from>=point);
        insert=desired+'; '+insert+(rest?' '+previous+';':'');
        effect=rest?`New match uses ${desired}; ${previous} is restored immediately afterward. ${later.length} later content match(es) retain their buffers.`:`New match uses ${desired}. No later matches are affected.`;
      }else effect=`New match uses the current ${previous} buffer. Existing buffers are unchanged.`;
    }
  }
  const change={from:point,to:point,insert:' '+insert+' '};
  const proposed=model.source.slice(0,point)+change.insert+model.source.slice(point);
  const parsed=parse(proposed,rule.dialect);
  if(parsed.diagnostics.length||parsed.rules.length!==model.rules.length)
    throw Error('Proposed insertion has incomplete or unsupported syntax: '+parsed.diagnostics.join(' '));
  return {change,effect,from:point,to:point+change.insert.length};
}
